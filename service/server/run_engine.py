"""Trading Runs scheduler engine (Plan 10, Phase 2).

Driven by tasks.trading_run_loop. Responsibilities per tick:

  1. CONTROL PASS (cheap, zero-LLM): arm -> running when start conditions
     fire; finish `stopping` runs that hold no run-owned position; nothing
     here calls an LLM.
  2. DISPATCH: due running runs execute one cycle each on a DEDICATED
     ThreadPoolExecutor (never asyncio.to_thread's shared default pool — four
     30-90s LLM calls there would starve the SL/TP watcher), bounded by
     RUN_CYCLE_CONCURRENCY.

Exactly-once model (the Phase 2 blocker fix):
  * The lease claim is its own SHORT COMMITTED transaction on a fresh
    connection, executed at slot acquisition (not scan time), and it
    atomically increments cycle_seq + stamps last_cycle_at. MySQL's
    REPEATABLE READ + autocommit=False makes a long-held claim both a lock
    hazard and a stale-read hazard (commit 73f4573 bug class) — so the claim
    commits before any analysis begins.
  * client_order_id = "run:{id}:cyc:{seq}" is UNIQUE on signals: the same
    seq can never trade twice.
  * The trade transaction re-reads the lease (fence) and the run status —
    a zombie claimant whose lease was reclaimed, or a run stopped mid-cycle,
    aborts before money moves.
  * A worker that crashes mid-cycle leaves last_cycle_at stamped, so the run
    simply waits for its next due window; the reclaimer then runs a FRESH
    cycle under a new seq. At-most-once per due window, exactly-once per seq.
  * Lease TTL (RUN_LEASE_TTL, default 300s) exceeds the worst-case cycle
    (semaphore wait is excluded — the claim happens after the slot).

Kill switch: AUTO_TRADING_ENABLED (default false — the feature ships dark
and is enabled per environment).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import order_intent
import trading_runs
import desk_memory_ingest
from database import begin_write_transaction, get_db_connection
from order_params import (
    exit_prices as order_exit_prices,
    mode as order_params_mode,
    outcome as order_params_outcome,
    parse_order_block,
    rr_floor_violation,
)
from trading_runs import (
    STATUS_ARMED,
    STATUS_PAUSED,
    STATUS_RUNNING,
    STATUS_STOPPED,
    STATUS_STOPPING,
    TS_FMT,
    _emit_event,
    emit_telemetry_event,
)

logger = logging.getLogger(__name__)

WORKER_IDENTITY = f"{socket.gethostname()}:{os.getpid()}"

_executor: Optional[ThreadPoolExecutor] = None
_semaphore: Optional[asyncio.Semaphore] = None
_in_flight: set[int] = set()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_dt().strftime(TS_FMT)


def _iso_in(seconds: int) -> str:
    return (_now_dt() + timedelta(seconds=seconds)).strftime(TS_FMT)


def auto_trading_enabled() -> bool:
    return os.getenv("AUTO_TRADING_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on")


def _lease_ttl() -> int:
    try:
        return max(120, int(os.getenv("RUN_LEASE_TTL", "300")))
    except ValueError:
        return 300


def _concurrency() -> int:
    try:
        return max(1, int(os.getenv("RUN_CYCLE_CONCURRENCY", "4")))
    except ValueError:
        return 4


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=_concurrency(),
                                       thread_name_prefix="run-cycle")
    return _executor


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_concurrency())
    return _semaphore


def _mark_staleness_max() -> int:
    """Mark age beyond which stop evaluation FAILS CLOSED. Default 3× the
    position-refresh interval (prod ships 300s) with a 900s floor — a frozen
    price is indistinguishable from a fresh one without this."""
    try:
        base = int(os.getenv("POSITION_REFRESH_INTERVAL", "300"))
    except ValueError:
        base = 300
    try:
        return int(os.getenv("RUN_MARK_STALENESS_MAX", str(max(900, base * 3))))
    except ValueError:
        return max(900, base * 3)


def _flatten_timeout() -> int:
    try:
        return max(300, int(os.getenv("RUN_FLATTEN_TIMEOUT", "3600")))
    except ValueError:
        return 3600


def _armed_timeout() -> int:
    try:
        return max(3600, int(os.getenv("RUN_ARMED_TIMEOUT", str(7 * 86400))))
    except ValueError:
        return 7 * 86400


# ── fee/edge entry gate (2026-07-26) ───────────────────────────────────────
# An entry only pays if the move it is predicting is bigger than the round
# trip it costs. Prod evidence: the ZEC winners captured 0.24–0.44% gross
# against a 0.2% round trip, so fees took 44–82% of every win. Require the
# thesis' expected move to clear a multiple of the round-trip cost before
# committing. Reduce/close orders are never gated — exiting only cuts risk.
def _fee_edge_multiple() -> float:
    """How many round trips of REALIZED edge an entry must promise. 0 disables."""
    try:
        return max(0.0, float(os.getenv("RUN_FEE_EDGE_MULTIPLE", "3.0") or 3.0))
    except ValueError:
        return 3.0


def _thesis_realization() -> float:
    """Fraction of a thesis' claimed move the desk actually captures.

    Measured on prod 2026-07-26 across the 40 runs of the prior week that
    traded: median 0.154, mean 0.246 — theses claim 1.2–6.6% and realize a
    small fraction of it. Comparing the raw claim against the fee hurdle
    therefore passed every single run (40/40, zero effect); the claim must be
    discounted to a realistic capture before it is graded."""
    try:
        val = float(os.getenv("RUN_FEE_EDGE_REALIZATION", "0.25") or 0.25)
    except ValueError:
        val = 0.25
    return min(1.0, max(0.01, val))


def _min_edge_pct() -> float:
    """Minimum REALIZED (discounted) move an entry must promise, independent
    of what the fill costs. 0 disables.

    The fee multiple alone stopped filtering the moment fees became per-market
    (2026-07-28). It ties the edge requirement to the fee, so once fees differ
    20x across venues one multiple cannot serve them: at 20x the crypto
    hurdle is 1.80% while futures is 0.20%. Measured on the live universe the
    old flat-fee gate admitted 67% of theses; per-market fees took that to
    100%, which is not a gate.

    This is a NOISE floor, not a proven edge threshold — I do not have data
    separating winners from losers by claimed size. 0.15% admits 96% of the
    universe and 78% of forex, refusing only the weakest FX theses (AUDJPY at
    0.111% discounted). Raising it to 0.25% would cut forex to 28%, which
    would quietly undo a market we had just deliberately opened. The real
    per-symbol answer is the expectancy gate, which already works.
    """
    try:
        return max(0.0, float(os.getenv("RUN_MIN_EDGE_PCT", "0.15") or 0.15))
    except ValueError:
        return 0.15


def _fee_edge_skip(expected_move_pct: "float | None",
                   leverage: float = 1.0,
                   market: "str | None" = None) -> Optional[str]:
    """Skip reason when the expected move cannot pay for its own round trip.

    expected_move_pct is the thesis' predicted move in PERCENT of price, which
    is the same scale the fee is charged on — leverage multiplies both the
    gain and the fee, so it cancels and is accepted only to keep the signature
    honest for callers. None/0 (no stated expectation) leaves the entry alone;
    this gate refuses only moves it can prove are too small.

    The claim is discounted by _thesis_realization() first: the desk's stated
    move is systematically optimistic, and grading the raw number made this
    gate a no-op on every run in the week that motivated it."""
    from fees import fee_rate
    mult = _fee_edge_multiple()
    if mult <= 0 or expected_move_pct is None:
        return None
    try:
        claimed = abs(float(expected_move_pct))
    except (TypeError, ValueError):
        return None
    if claimed <= 0:
        return None
    realization = _thesis_realization()
    expected = claimed * realization
    round_trip_pct = fee_rate(market) * 2 * 100.0
    fee_required = round_trip_pct * mult
    # Two independent hurdles: the move must out-earn its own fees AND clear an
    # absolute noise floor. Whichever binds, binds — a cheap venue does not get
    # to admit a move that is indistinguishable from zero.
    floor = _min_edge_pct()
    required = max(fee_required, floor)
    if expected < required:
        if floor > fee_required:
            return (f"min_edge: claimed {claimed:.2f}% × {realization:.2f} "
                    f"realization = {expected:.2f}% < {floor:.2f}% floor "
                    f"(fees would have allowed {fee_required:.2f}%)")
        return (f"fee_edge: claimed {claimed:.2f}% × {realization:.2f} realization "
                f"= {expected:.2f}% < {fee_required:.2f}% "
                f"({mult:g}× the {round_trip_pct:.2f}% round trip)")
    return None


def _reentry_cooldown_enabled() -> bool:
    return os.getenv("RUN_REENTRY_COOLDOWN", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _reentry_cooldown_minutes(cfg: dict) -> float:
    lev = max(1.0, float(cfg.get("leverage") or 1.0))
    interval = max(1, int(cfg.get("interval_minutes") or 60))
    try:
        mult = float(os.getenv("RUN_REENTRY_LEV_MULT", "1.0") or 1.0)
    except ValueError:
        mult = 1.0
    return interval * (lev - 1.0) * max(0.0, mult)   # 1× → 0; 3×/30m → 60m


def _reentry_cooldown_reason(last_close_iso: Optional[str], cfg: dict,
                             now: datetime) -> Optional[str]:
    """Skip reason when a just-flat run is still inside its post-close cooldown.
    Pure (last-close time in, reason out) so it unit-tests without a DB."""
    if not _reentry_cooldown_enabled():
        return None
    cd = _reentry_cooldown_minutes(cfg)
    if cd <= 0 or not last_close_iso:
        return None
    try:  # tolerate microseconds / trailing Z by parsing the first 19 chars
        last_dt = datetime.strptime(str(last_close_iso)[:19],
                                    "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    if now - last_dt < timedelta(minutes=cd):
        lev = max(1.0, float(cfg.get("leverage") or 1.0))
        return f"re-entry cooldown ({cd:.0f}m at {lev:.0f}x leverage)"
    return None


# ── #3 leverage-aware conviction sizing ────────────────────────────────────
def _lev_sizing_enabled() -> bool:
    return os.getenv("RUN_LEV_SIZING", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _lev_size_damp() -> float:
    try:
        return max(0.0, float(os.getenv("RUN_LEV_SIZE_DAMP", "0.5") or 0.5))
    except ValueError:
        return 0.5


# ── #4 stop-inside-liquidation cushion ─────────────────────────────────────
def _liq_cushion_enabled() -> bool:
    return os.getenv("RUN_LIQ_CUSHION", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _liq_cushion_frac() -> float:
    """Fraction of the way to the liquidation price at which the protective
    cushion stop fires (0.85 ⇒ close at 85% of the liq distance)."""
    try:
        f = float(os.getenv("RUN_LIQ_CUSHION_FRAC", "0.85") or 0.85)
    except ValueError:
        f = 0.85
    return min(0.98, max(0.50, f))


# ── confidence recalibration (2026-07-26) ──────────────────────────────────
# The LLM's confidence scalar is severely quantized: over 7 prod days 261
# decisions landed on exactly 0.58 and 137 on exactly 0.62, and only 13 all
# week reached the 0.65 gate. Those anchors are prompt artefacts, not a
# calibrated probability, so a fixed absolute threshold sits just above the
# model's ceiling and rejects on noise. Grade each decision against the
# agent's own recent distribution instead: gate on percentile RANK, keeping a
# much lower absolute floor as a sanity rail so a uniformly terrible tape
# cannot promote its least-bad idea.
def _conf_percentile_enabled() -> bool:
    return os.getenv("RUN_CONF_PERCENTILE", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _conf_percentile_min() -> float:
    """Required rank within the recent window (0.70 ⇒ top 30%)."""
    try:
        return min(0.99, max(0.0, float(
            os.getenv("RUN_CONF_PERCENTILE_MIN", "0.70") or 0.70)))
    except ValueError:
        return 0.70


def _conf_percentile_window() -> int:
    try:
        return max(10, int(os.getenv("RUN_CONF_PERCENTILE_WINDOW", "100")))
    except ValueError:
        return 100


def _conf_percentile_min_samples() -> int:
    """Below this many observations the distribution is not meaningful and the
    absolute min_confidence gate is used unchanged."""
    try:
        return max(5, int(os.getenv("RUN_CONF_PERCENTILE_MIN_SAMPLES", "20")))
    except ValueError:
        return 20


def _conf_abs_floor() -> float:
    """Absolute sanity floor kept underneath the percentile gate."""
    try:
        return min(1.0, max(0.0, float(
            os.getenv("RUN_CONF_ABS_FLOOR", "0.55") or 0.55)))
    except ValueError:
        return 0.55


def percentile_rank(value: float, sample: "list[float]") -> float:
    """Fraction of `sample` strictly below `value`, plus half the ties — the
    midrank convention, so a heavily tied distribution (0.58 × 261) does not
    hand the whole cluster either a 0.0 or a 1.0 rank. Empty sample ⇒ 1.0
    (nothing to be worse than)."""
    if not sample:
        return 1.0
    below = sum(1 for s in sample if s < value)
    ties = sum(1 for s in sample if s == value)
    return (below + 0.5 * ties) / len(sample)


def _recent_confidences(agent_id: int, window: int) -> "list[float]":
    """Confidence scalars from the agent's most recent decision events."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT e.payload FROM run_events e
               JOIN trading_runs t ON t.id = e.run_id
               WHERE e.event_type = 'decision' AND t.agent_id = ?
               ORDER BY e.id DESC LIMIT ?""",
            (agent_id, window))
        rows = cursor.fetchall()
    except Exception:  # noqa: BLE001 — telemetry read, never blocks a cycle
        return []
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    out: list[float] = []
    for row in rows:
        try:
            val = json.loads(row["payload"] or "{}").get("confidence")
        except (ValueError, TypeError):
            continue
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out.append(float(val))
    return out


# ── conviction-collapse exit (2026-07-31, desk-adopted item I5) ─────────────
# The desk computes a `conviction` scalar every decision but today it only
# rides in telemetry — nothing acts on it. When a HELD position's own desk has
# read conviction below the floor for N consecutive cycles, the thesis is gone
# but the position is still on. Close it before it round-trips. Prod KAITO:
# peaked +$11, gave it all back, and only exited once conviction had already
# fallen to 0.275 — this rail would have closed it earlier. Ships dark.
def _conviction_exit_enabled() -> bool:
    return (os.getenv("RUN_CONVICTION_EXIT", "false") or "false").strip().lower() in (
        "1", "true", "yes", "on")


def _conviction_exit_floor() -> float:
    try:
        return max(0.0, float(os.getenv("RUN_CONVICTION_EXIT_FLOOR", "0.35") or 0.35))
    except ValueError:
        return 0.35


def _conviction_exit_strikes() -> int:
    try:
        return max(1, int(os.getenv("RUN_CONVICTION_EXIT_STRIKES", "2") or 2))
    except ValueError:
        return 2


def _recent_run_convictions(run_id: int, window: int) -> "list[float]":
    """The most recent `window` conviction scalars for THIS run, newest first.
    Missing/None conviction is skipped, so a run must have ACTUALLY read low
    conviction `window` times — an absent score never triggers the exit."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT payload FROM run_events
               WHERE run_id = ? AND event_type = 'decision'
               ORDER BY id DESC LIMIT ?""",
            (run_id, window))
        rows = cursor.fetchall()
    except Exception:  # noqa: BLE001 — telemetry read, never blocks a cycle
        return []
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    out: list[float] = []
    for row in rows:
        try:
            val = json.loads(row["payload"] or "{}").get("conviction")
        except (ValueError, TypeError):
            continue
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out.append(float(val))
    return out


def _conf_percentile_skip(agent_id: int, gate_confidence: "float | None",
                          min_confidence: "float | None") -> "tuple[Optional[str], Optional[float]]":
    """(skip_reason, effective_min_confidence).

    effective_min_confidence is what the risk gate should enforce: the low
    absolute floor when percentile grading applied, or the caller's original
    threshold when it did not (too few samples, disabled, no confidence)."""
    if not _conf_percentile_enabled() or gate_confidence is None:
        return None, min_confidence
    sample = _recent_confidences(agent_id, _conf_percentile_window())
    if len(sample) < _conf_percentile_min_samples():
        return None, min_confidence          # not enough history to grade
    floor = _conf_abs_floor()
    conf = float(gate_confidence)
    if conf < floor:
        return (f"confidence {conf:.2f} below absolute floor {floor:.2f}",
                min_confidence)
    rank = percentile_rank(conf, sample)
    need = _conf_percentile_min()
    if rank < need:
        # A purely RELATIVE gate always rejects ~(1-need) of decisions, however
        # good they are. Observed live: RUN 115's futures short sat at 0.60 —
        # comfortably over its own 0.57 threshold — and was refused twice for
        # ranking 52%, because the reference window is dominated by the same
        # handful of runs. A desk that is consistently decent can never clear
        # a moving bar set by its own output.
        #
        # So the percentile is a TIE-BREAKER inside the band where confidence
        # is ambiguous, not an independent hurdle. Clear the caller's own
        # threshold by a real margin and the absolute reading wins.
        margin = _conf_absolute_override_margin()
        if min_confidence is not None and margin > 0 \
                and conf >= float(min_confidence) + margin:
            return None, floor
        return (f"confidence {conf:.2f} ranks {rank:.0%} of the last "
                f"{len(sample)} decisions (needs {need:.0%})", min_confidence)
    return None, floor


def _conf_absolute_override_margin() -> float:
    """How far above its own min_confidence a decision must sit to bypass the
    percentile tie-breaker. 0 restores the pure-relative gate."""
    try:
        return max(0.0, float(os.getenv("RUN_CONF_ABSOLUTE_MARGIN", "0.03") or 0.03))
    except ValueError:
        return 0.03


def _idle_retire_cycles() -> int:
    """Cycles a never-traded, flat run may burn before it is retired.
    0 disables the rail entirely."""
    try:
        return max(0, int(os.getenv("RUN_IDLE_RETIRE_CYCLES", "12")))
    except ValueError:
        return 12


def _infeasible_retire_enabled() -> bool:
    """Default-on kill switch for the fee-infeasible retire rail."""
    return os.getenv("RUN_INFEASIBLE_RETIRE", "true").strip().lower() in (
        "1", "true", "yes", "on")


def run_thesis_expected_move(run: dict) -> "float | None":
    """The run's frozen thesis expected_move_pct, or None when it carries no
    thesis (manual runs) or the snapshot is unreadable."""
    try:
        cfg = json.loads(run.get("config_snapshot_json") or "{}")
    except (ValueError, TypeError):
        return None
    thesis = cfg.get("thesis")
    if not isinstance(thesis, dict):
        return None
    val = thesis.get("expected_move_pct")
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    return None


def _run_thesis_fee_infeasible(run: dict) -> Optional[str]:
    """Reason the run's own thesis can never pay for a round trip, or None.

    Reuses the per-cycle gate verbatim so the retire rail and the entry gate
    can never disagree — if _fee_edge_skip would refuse every entry this run
    will ever attempt, the run is dead and the slot should go back."""
    return _fee_edge_skip(run_thesis_expected_move(run),
                          market=run.get("market"))


UNACTIONABLE_SKIP = "spot sell with no inventory"


def _thesis_invalidation_strikes() -> int:
    """Consecutive unactionable-direction cycles before the thesis is declared
    dead. 0 disables, leaving only the blunter idle-retire timer."""
    try:
        return max(0, int(os.getenv("RUN_THESIS_INVALIDATION_STRIKES", "3")))
    except ValueError:
        return 3


def _closed_market_cycles(run_id: int) -> int:
    """Cycles this run burned with its market shut.

    cycle_seq increments when the cycle is CLAIMED (run_engine ~1409), before
    _pre_gate_skip runs, so a run parked on a closed market still counts a
    cycle every tick. The idle-retire rail then collects it for "never
    traded" — which it never had the chance to do.

    Live 2026-07-28: runs 127 (ORCL) and 128 (CAT) were built at 19:56:40,
    3m20s before the US close, spent twelve cycles on `pre: market closed`,
    and were idle-retired at 04:27 — 9 hours before the market reopened. Two
    slots and their allocation, spent on a rail whose own premise ("burning a
    multi-agent analysis per tick for nothing") is false here: a pre-gate skip
    returns before any analysis is requested and costs nothing at all.

    Fail-soft: an unreadable journal reports 0, so the rail behaves exactly as
    it did before rather than becoming un-retirable.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) AS n FROM run_events
               WHERE run_id = ? AND event_type = 'gate_skip'
                 AND payload LIKE '%"stage": "pre"%'
                 AND payload LIKE '%market closed%'""", (run_id,))
        row = cursor.fetchone()
    except Exception:  # noqa: BLE001 — including the connect itself
        return 0
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
    try:
        return int((row["n"] if row else 0) or 0)
    except (KeyError, TypeError, ValueError):
        return 0


def _thesis_decay_enabled() -> bool:
    """Ship gate, default OFF.

    Retiring a run that HOLDS a position is a money path: _control_stopping
    either flattens it at market or releases it with run_id = NULL, which is
    the orphan path. Every other money-path change in this codebase ships
    dark and is enabled deliberately after the journal shows the rail firing
    where it should. This one is no different — the decay signal is only as
    good as the desk's own self-scoring, and it has never been measured
    against an outcome.

    Enable with RUN_THESIS_DECAY_ENABLED=true once the shadow read looks
    right; the floor is a separate tuning knob."""
    return (os.getenv("RUN_THESIS_DECAY_ENABLED", "false") or "false"
            ).strip().lower() in ("1", "true", "yes", "on")


def _thesis_decay_floor() -> float:
    """thesis_alignment at or below which the desk no longer believes its own
    thesis. Boundary is inclusive: run 345's decay read exactly 0.35, and a
    strict comparison would have scored that cycle healthy and let the rail
    miss the case it exists for. 0 disables the rail."""
    try:
        return max(0.0, min(1.0, float(
            os.getenv("RUN_THESIS_DECAY_FLOOR", "0.35") or 0.35)))
    except ValueError:
        return 0.35


def _thesis_decay_strikes() -> int:
    """Consecutive cycles under the floor before the run is handed back.

    Three, matching _thesis_invalidation_strikes: one weak read is a market
    wobble, three in a row is the desk having changed its mind."""
    try:
        return max(2, int(os.getenv("RUN_THESIS_DECAY_STRIKES", "3")))
    except ValueError:
        return 3


def _thesis_decay_streak(run_id: int) -> int:
    """How many of the run's most recent decisions rated thesis_alignment
    below the floor, counted back from the latest and stopping at the first
    one that recovered.

    The gap this closes: _unactionable_streak catches the desk CONTRADICTING
    its thesis — a long book being told to sell. It cannot catch the desk
    quietly abandoning one. Live 2026-07-28, run 345 (ZC, "corn shows robust
    positive momentum, 18% over 20 days"):

        cycle 1  alignment 0.70  momentum 0.62  -> traded
        cycle 3  alignment 0.35  momentum 0.20  -> hold
        cycle 4  alignment 0.30  momentum 0.15  -> hold
        cycle 5  alignment 0.30  momentum 0.20  -> hold

    Every decision was `hold`, so no rail fired and the position sat on a
    thesis its own author had marked down by more than half. A run that has
    stopped believing its reason for existing should hand the slot back.

    Fail-soft: an unreadable journal reports 0 and the rail stays quiet.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT payload FROM run_events
               WHERE run_id = ? AND event_type = 'decision'
               ORDER BY id DESC LIMIT 20""", (run_id,))
        rows = cursor.fetchall()
    except Exception:  # noqa: BLE001
        return 0
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
    floor = _thesis_decay_floor()
    streak = 0
    for row in rows:
        try:
            scores = (json.loads(row["payload"] or "{}") or {}).get("scores")
        except (ValueError, TypeError):
            return streak
        if not isinstance(scores, dict):
            # A decision with no scores says nothing either way — it must not
            # extend a streak, and it must not silently reset one either.
            return streak
        val = scores.get("thesis_alignment")
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            return streak
        if float(val) <= floor:
            streak += 1
        else:
            break
    return streak


def _unactionable_streak(run_id: int) -> int:
    """How many of the run's most recent gate skips were the direction its
    book cannot express — counted back from the latest, stopping at the first
    skip of any other kind so an intervening ordinary skip resets the streak.
    Fail-soft: an unreadable journal reports 0 and the rail stays quiet."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT payload FROM run_events
               WHERE run_id = ? AND event_type = 'gate_skip'
               ORDER BY id DESC LIMIT 20""", (run_id,))
        rows = cursor.fetchall()
    except Exception:  # noqa: BLE001
        return 0
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    streak = 0
    for row in rows:
        try:
            reason = str(json.loads(row["payload"]).get("reason") or "")
        except Exception:  # noqa: BLE001
            break
        if UNACTIONABLE_SKIP in reason:
            streak += 1
        else:
            break
    return streak


def _stop_eval_failure_limit() -> int:
    try:
        return max(1, int(os.getenv("RUN_STOP_EVAL_FAILURES", "5")))
    except ValueError:
        return 5


# ── run P&L (fee-inclusive average-cost replay; ledger is the truth) ──────

def compute_run_pnl(run: dict) -> dict:
    """Replay the run's attributed signals with the EXACT leg math of
    execute_paper_trade (fees included — the fee-exclusive trade_stats
    precedent fires max_loss late by ~0.2%/round-trip on churny runs).
    Run exclusivity (D4) guarantees no other writer commingles the tuple's
    position, so average-cost replay is exact."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT side, entry_price, quantity, fee_usd FROM signals
               WHERE run_id = ? AND message_type = 'operation' ORDER BY id""",
            (run["id"],))
        legs = [dict(r) for r in cursor.fetchall()]
        cursor.execute(
            """SELECT quantity, entry_price, current_price, price_updated_at, leverage
               FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ? AND run_id = ?""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        pos = cursor.fetchone()
        pos = dict(pos) if pos else None
    finally:
        conn.close()

    qty = 0.0
    avg = 0.0
    realized = 0.0
    for leg in legs:
        side = leg["side"]
        p = float(leg["entry_price"] or 0)
        q = float(leg["quantity"] or 0)
        fee = float(leg["fee_usd"] or 0)
        if side == "buy":
            avg = (avg * qty + p * q) / (qty + q) if qty + q > 0 else p
            qty += q
            realized -= fee
        elif side == "sell":
            realized += (p - avg) * min(q, qty) - fee
            qty -= min(q, qty)
        elif side == "short":
            held = -qty  # current short size
            avg = (avg * held + p * q) / (held + q) if held + q > 0 else p
            qty -= q
            realized -= fee
        elif side == "cover":
            held = -qty
            realized += (avg - p) * min(q, held) - fee
            qty += min(q, held)
    unrealized = 0.0
    mark_age_ok = True
    if pos and float(pos["quantity"] or 0) != 0:
        mark = pos["current_price"]
        if mark is not None:
            pq = float(pos["quantity"])
            entry = float(pos["entry_price"] or 0)
            unrealized = (float(mark) - entry) * pq if pq > 0 \
                else (entry - float(mark)) * (-pq)
        updated = pos.get("price_updated_at")
        if mark is None or not updated or _age_seconds(updated) > _mark_staleness_max():
            mark_age_ok = False
    return {"realized": realized, "unrealized": unrealized,
            "total": realized + unrealized, "trades": len(legs),
            "position": pos, "mark_age_ok": mark_age_ok}


def _age_seconds(ts: str) -> float:
    try:
        then = datetime.strptime(ts, TS_FMT).replace(tzinfo=timezone.utc)
        return (_now_dt() - then).total_seconds()
    except Exception:  # noqa: BLE001
        return float("inf")


# ── stop-condition evaluation (every scan, running AND paused) ─────────────

def _trailing_lock_hit(peak_pnl: "float | None", current_pnl: float,
                       trail: "dict | None") -> bool:
    """Peak-tracked profit lock. Once the run's best total P&L clears the
    activation floor, exit if it retraces more than giveback_frac from that
    peak — banks a winner that would otherwise round-trip and catches a
    reversal off the top (the fleet's small, mean-reverting moves never reach
    the far profit_target). Inert without a trail config (manual runs) or
    before the peak arms.

    Ratchet (2026-07-26): a fixed 40% giveback surrendered most of every
    winner — the five prod ZEC runs peaked at $6.95–$27.83 and banked
    $1.98–$7.50, because the 40% retrace fires and THEN the round-trip fee
    (0.1%/side) takes 44–82% of what is left. Once the peak clears
    tighten_usd (the fee-aware "this is a real winner" line) the giveback
    compresses to tighten_giveback_frac, so a large peak is protected far
    harder than the one that just armed. Absent tighten_usd the behaviour is
    the flat giveback exactly as before."""
    if not trail or peak_pnl is None:
        return False
    activate = float(trail.get("activate_usd") or 0)
    giveback = float(trail.get("giveback_frac") or 0)
    peak = float(peak_pnl)
    if peak < activate or peak <= 0 or not (0 < giveback < 1):
        return False
    tighten_at = float(trail.get("tighten_usd") or 0)
    tight = float(trail.get("tighten_giveback_frac") or 0)
    if tighten_at > 0 and peak >= tighten_at and 0 < tight < giveback:
        giveback = tight
    return current_pnl <= peak * (1.0 - giveback)


def _breakeven_ratchet_enabled() -> bool:
    """Kill switch for the ratchet. A new rail that fires on EVERY run needs
    one — default on, `BREAKEVEN_RATCHET=0` disables without a deploy."""
    return (os.getenv("BREAKEVEN_RATCHET", "1") or "1").strip().lower() \
        not in ("0", "false", "off", "no")


def _breakeven_arm_usd(pnl: dict, floor_qty: "float | None" = None) -> float:
    """The peak a position must clear before the floor applies: ITS OWN
    round-trip cost.

    Fee-anchored on purpose rather than a flat dollar figure — a peak that
    has not yet paid for the trade is not a winner worth protecting, and a
    constant would be a noise-trigger on small books and inert on large
    ones. BREAKEVEN_ARM_FEES tunes the multiple of that round trip.

    `floor_qty` anchors the threshold to the LARGEST book the run has ever
    held (see _run_max_abs_qty for why — run 976's reduce halved the arm
    under a full-book peak and turned the desk's partial exit into a full
    flatten). A flat book still never arms, whatever the history says.
    """
    try:
        pos = pnl.get("position") or {}
        qty = abs(float(pos.get("quantity") or 0))
        mark = float(pos.get("current_price") or 0)
        if qty <= 0 or mark <= 0:
            return 0.0
        try:
            qty = max(qty, float(floor_qty or 0))
        except (TypeError, ValueError):
            pass
        rate = float(os.getenv("BREAKEVEN_FEE_RATE", "0.001"))
        mult = float(os.getenv("BREAKEVEN_ARM_FEES", "1.0"))
        return qty * mark * rate * 2.0 * max(0.0, mult)
    except (TypeError, ValueError):
        return 0.0


def _run_max_abs_qty(run: dict) -> float:
    """The largest absolute position this run has EVER held, replayed from
    its own `trade` events (same signed-qty convention as pnl_audit:
    buy/cover build a long, sell/short build a short).

    WHY (2026-08-06, run 976): the breakeven floor's arm threshold was
    sized off the CURRENT book while `peak_pnl_usd` is a lifetime
    high-water mark. 976 was never armed on its full book (arm 11.36 >
    peak 7.22); the desk's own `reduce 0.5` halved the book, the arm fell
    to 5.68, the floor retro-armed against a peak the FULL book had earned
    and flattened the remainder the same second — escalating the desk's
    deliberate partial exit into the full close it had just declined, on a
    position that then recovered. A peak must cover the round trip of the
    largest book held while it was being earned; shrinking the book
    afterwards must not lower that bar.

    Fail-soft to 0.0: the caller then falls back to the current book,
    i.e. the pre-fix behaviour — this is a protection rail, not a blocker.
    """
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT payload FROM run_events "
                "WHERE run_id = ? AND event_type = 'trade' ORDER BY seq",
                (run["id"],))
            rows = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        qty = 0.0
        biggest = 0.0
        for row in rows:
            try:
                t = json.loads(row.get("payload") or "{}")
                q = abs(float(t.get("quantity") or 0))
                side = str(t.get("side") or "").strip().lower()
            except (TypeError, ValueError):
                continue
            if q <= 0 or not side:
                continue
            qty += q if side in ("buy", "cover") else -q
            biggest = max(biggest, abs(qty))
        return biggest
    except Exception:  # noqa: BLE001 — fail-soft, see docstring
        return 0.0


def _breakeven_floor_hit(peak_pnl: "float | None", current_pnl: float,
                         arm_usd: float) -> bool:
    """Once a position has genuinely been in profit, do not let it go
    negative. Deterministic, needs NOTHING from the desk.

    Why this exists (measured 2026-08-05/06): the configured trailing lock
    NO LONGER ARMS AT CURRENT BUDGETS. `trail.activate_usd` is set equal to
    `max_loss_usd`, so it has RISEN with position size over time — 0.8, then
    6.0, 26.17, 43.48, and now $78-81 on the live fleet — while the best
    peak any run reached in two days was $22.07 and most were $2-6.

    It is NOT dead code: it genuinely fired on runs 921, 919, 125, 119, 854
    and 897 back when activation sat at 0.8-43.48. But across runs 940-972,
    the entire current budget regime, it fired ZERO times. The protection
    that is supposed to work without the desk has been outrun by its own
    threshold. (An earlier draft of this comment claimed it had "never fired
    on any run" — that was wrong, and the six runs above are the disproof.)

    Note the opposite failure at the low end: run 921 armed at 0.8 and was
    stopped 28 SECONDS after opening. That is why this rail anchors its arm
    to the position's own round-trip cost rather than to a small constant.

    Meanwhile the desk cannot cover the gap: it armed on only 37 of 133
    held cycles (28%), and every arm it did place sat 11-13% from price. An
    LLM will never be 100% compliant, so the guarantee cannot depend on one.

    Replayed against the 08-05 book this fires on 971 at -5.10 instead of
    -54.50, on 955 at -2.64 instead of -21.66 and on 967 at -0.54 instead
    of -13.24 (~+81 total), while 969 — the day's best run at +19.11 — arms
    and NEVER breaches, so the winner is protected rather than cut. Runs
    whose peak never covered its own round trip never arm at all.

    This is the breakeven ratchet PR #118 recommended after measuring and
    REJECTING a lower trail_activate_rr; it was never built until now.
    """
    if not _breakeven_ratchet_enabled() or peak_pnl is None or arm_usd <= 0:
        return False
    try:
        peak = float(peak_pnl)
        if peak < arm_usd:
            return False        # never was a winner — nothing to protect
        return float(current_pnl) <= 0.0
    except (TypeError, ValueError):
        return False


def _cycle_in_flight(run: dict) -> bool:
    """True while a decision cycle holds the run's claim — the idle-retire
    verdict yields to it (plan 24 fix 3). Live 2026-08-12: run 1085 was
    idle-retired at 16:35:55 and its FIRST actionable decision (`sell`)
    landed at 16:35:56, dying on the stopped-run fence — twelve cycles of
    paid research forbidden to act by a one-second race. A run whose desk
    is deciding RIGHT NOW is not idle by definition; deferring costs one
    scan interval and the verdict re-fires next scan if the desk held again.
    Reads the scan's own row snapshot (seconds old — the LLM call the claim
    covers runs far longer than that), so the check stays DB-free."""
    return bool(run.get("claimed_by")
                and (run.get("claim_expires_at") or "") > _now_iso())


def _evaluate_stop(run: dict) -> Optional[str]:
    """Return a stop reason string when a stop event fired, None otherwise.
    Raises on evaluation FAILURE (stale marks, unreadable state) — the
    caller treats failure as fail-closed (pause entries + alert), the
    inverse of the codebase's fail-open telemetry convention."""
    conditions = json.loads(run.get("stop_conditions_json") or "{}")
    pnl = compute_run_pnl(run)
    pos = pnl["position"]
    has_position = bool(pos and float(pos["quantity"] or 0) != 0)

    # Idle retire (2026-07-26): a run that has cycled N times without ever
    # opening a position is not "waiting for its setup", it is burning a
    # multi-agent analysis per tick for nothing. Prod: run 111 held for 13
    # cycles / 8.5h at confidence 0.58–0.62 against a 0.65 gate, and the
    # us-stock board (runs 70/71/82) cycled 8–35 times with zero trades all
    # week. Flat and never-traded only — an open position is never abandoned
    # on a cycle count.
    if not has_position and int(pnl.get("trades") or 0) == 0:
        # Fee-infeasible retire (2026-07-27), the sharpest rail of the three:
        # it needs no samples at all. expected_move_pct is frozen in the config
        # snapshot and never changes, so a thesis that cannot clear the fee
        # hurdle on cycle 1 cannot clear it on cycle 12 either — the idle timer
        # just makes the desk pay nine hours of a held slot to learn a fact
        # arithmetic already knew. Prod: runs 129/130/131 (ZC, USDKRW, USDZAR)
        # were each blocked by fee_edge on their FIRST cycle and held $3,399 of
        # allocation between them; 100% of all forex theses ever generated are
        # in this class. Flat and never-traded only, same as the timer.
        if _infeasible_retire_enabled():
            infeasible = _run_thesis_fee_infeasible(run)
            if infeasible:
                return "fee_infeasible_retired"
        limit = _idle_retire_cycles()
        if limit:
            # Only cycles the run could actually have traded in count. A
            # closed-market tick costs nothing and proves nothing — see
            # _closed_market_cycles for the two runs this rail wrongly
            # collected.
            worked = int(run.get("cycle_seq") or 0) - _closed_market_cycles(run["id"])
            if worked >= limit and not _cycle_in_flight(run):
                return "idle_retired"
        # Thesis invalidation (2026-07-27), a sharper rail than the idle timer.
        # A spot run built on a LONG thesis whose desk keeps reading bearish
        # cannot act at all: nothing to sell, and it will not buy. Observed
        # live — runs 116/117 carried long theses and the desk returned `sell`
        # while flat, so both would have burned every cycle to idle-retire for
        # a thesis already dead. The desk repeatedly contradicting its own
        # thesis IS the invalidation signal; hand the slot back early so the
        # fleet can build a fresh candidate.
        strikes = _thesis_invalidation_strikes()
        if strikes and _unactionable_streak(run["id"]) >= strikes:
            return "thesis_invalidated"

    # Thesis decay (2026-07-28). Unlike the two rails above this one applies to
    # a run HOLDING a position — that is the whole point. A flat run with a
    # dead thesis merely wastes a slot; a run still holding on a thesis its own
    # desk has marked down is carrying risk for a reason nobody believes any
    # more. Exits stay with the safety system, so this hands the slot back the
    # same way every other retire does and the stop conditions do the closing.
    decay_strikes = _thesis_decay_strikes()
    run_id = run.get("id")
    if run_id and _thesis_decay_enabled() and _thesis_decay_floor() > 0 \
            and decay_strikes \
            and _thesis_decay_streak(run_id) >= decay_strikes:
        return "thesis_decayed"

    # Synthetic liquidation: a position's loss can wipe 100% of its escrowed
    # margin. Isolated-margin liq price from leverage L: long at
    # entry×(1−1/L), short at entry×(1+1/L). At L=1 this is exactly the prior
    # rule (short at 2×entry; a fully-funded long never liquidates).
    if has_position and pnl["mark_age_ok"]:
        entry = float(pos["entry_price"] or 0)
        mark = float(pos["current_price"] or 0)
        try:
            lev = max(1.0, float(pos["leverage"])) if pos["leverage"] else 1.0
        except (KeyError, TypeError, ValueError):
            lev = 1.0
        qty = float(pos["quantity"] or 0)
        if entry > 0 and mark > 0:
            # #4: protective cushion INSIDE the liquidation line. A small
            # position's USD max_loss stop can sit BEYOND the liq price, so
            # without this the run would liquidate (100% margin wipe) before
            # the P&L stop fires. Firing at c/L (c<1) guarantees a controlled
            # close first. Only leveraged runs can liquidate, so L=1 is inert.
            if lev > 1 and _liq_cushion_enabled():
                c = _liq_cushion_frac()
                if qty < 0 and mark >= entry * (1 + c / lev):
                    return "stop_event:liq_cushion"
                if qty > 0 and mark <= entry * (1 - c / lev):
                    return "stop_event:liq_cushion"
            if qty < 0 and mark >= entry * (1 + 1 / lev):
                return "synthetic_liquidation"
            if qty > 0 and lev > 1 and mark <= entry * (1 - 1 / lev):
                return "synthetic_liquidation"

    at = conditions.get("at_time")
    if at and at <= _now_iso():
        return "stop_event:at_time"
    mt = conditions.get("max_trades")
    if mt and pnl["trades"] >= int(mt):
        return "stop_event:max_trades"

    needs_pnl = ("max_loss_usd" in conditions or "profit_target_usd" in conditions)
    if needs_pnl and has_position and not pnl["mark_age_ok"]:
        # Plan 23 Phase B: a CLOSED market's frozen marks are expected, not a
        # fault — P&L stops go dormant and re-evaluate on the first fresh
        # mark after the open, where a gap through max_loss flattens at the
        # gapped price. Raising here would spam every overnight hold's ~60s
        # scan all night. The raise remains for the genuinely broken case:
        # an OPEN market serving stale prices.
        try:
            import markets as _mkts
            if not _mkts.is_market_open(run.get("market")):
                logger.debug("stops dormant (run %s): market closed",
                             run["id"])
                return None
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            f"marks stale beyond {_mark_staleness_max()}s — refusing to evaluate "
            "P&L stops on frozen prices")
    # max_loss wins ties (safety first — Plan 10 D3).
    ml = conditions.get("max_loss_usd")
    if ml is not None and pnl["total"] <= -float(ml):
        return "stop_event:max_loss"
    pt = conditions.get("profit_target_usd")
    if pt is not None and pnl["total"] >= float(pt):
        return "stop_event:profit_target"

    # Trailing profit lock (fleet path): bank the peak before it round-trips.
    # Only on a live position with fresh marks. Reported as its own reason
    # rather than profit_target — the far target is typically ~$410 while the
    # lock banks single dollars, and reusing the label told users "profit
    # target reached" for a $2.82 exit against a $413 target. Classified
    # alongside profit_target in the fleet disposition sets so replacement and
    # auto-restart behaviour is unchanged.
    if has_position and pnl["mark_age_ok"] and \
            _trailing_lock_hit(run.get("peak_pnl_usd"), pnl["total"],
                               conditions.get("trail")):
        return "stop_event:trailing_lock"

    # Breakeven ratchet (2026-08-06). Deliberately reuses the trailing_lock
    # REASON rather than minting a new one: this IS a trailing lock whose
    # floor sits at breakeven, the string is already classified in both
    # fleet disposition sets and all six notification languages, and a new
    # reason would silently fall through every one of them. It needs no
    # `trail` config at all, which is the point — runs like 961 carry
    # `stop_conditions_json = {}` and had NO peak protection whatsoever.
    # The arm is anchored to the largest book the run ever held — a reduce
    # must not lower the bar under an already-earned peak (run 976).
    if has_position and pnl["mark_age_ok"]:
        _be_arm = _breakeven_arm_usd(pnl, _run_max_abs_qty(run))
        if _breakeven_floor_hit(run.get("peak_pnl_usd"), pnl["total"], _be_arm):
            logger.info("breakeven ratchet fired (run %s): peak=%s now=%s arm=%s",
                        run["id"], run.get("peak_pnl_usd"), pnl["total"],
                        round(_be_arm, 4))
            return "stop_event:trailing_lock"

    # Conviction-collapse exit (2026-07-31, desk item I5). Ships dark. A held
    # position whose desk has read conviction below the floor for N straight
    # cycles is being carried on a thesis the desk no longer believes — close
    # it. Only reads the DB when armed (hot path); needs `strikes` real reads
    # below the floor, so a single wobble or an absent score cannot trigger it.
    if has_position and pnl["mark_age_ok"] and _conviction_exit_enabled():
        _floor = _conviction_exit_floor()
        _strikes = _conviction_exit_strikes()
        if _floor > 0:
            _convs = _recent_run_convictions(run["id"], _strikes)
            if len(_convs) >= _strikes and all(c < _floor for c in _convs):
                return "stop_event:conviction_collapse"

    pc = conditions.get("price_cross")
    if pc:
        price = None
        if has_position and pnl["mark_age_ok"] and pos.get("current_price") is not None:
            price = float(pos["current_price"])
        elif not has_position:
            try:
                from price_fetcher import get_price_from_market
                fetched = get_price_from_market(run["symbol"], None, run["market"])
                price = float(fetched) if fetched is not None else None
            except Exception:  # noqa: BLE001
                price = None
        if price is not None:
            if pc.get("direction") == "above" and price >= float(pc["price"]):
                return "stop_event:price_cross"
            if pc.get("direction") == "below" and price <= float(pc["price"]):
                return "stop_event:price_cross"
    return None


# equity telemetry: on-change with a heartbeat — NOT a blind 10s cadence
# (marks only move every poll interval; identical rows are pure prune load)
_last_equity: dict[int, tuple[float, float]] = {}  # run_id -> (total, monotime)


def _equity_heartbeat_seconds() -> int:
    try:
        return max(30, int(os.getenv("RUN_EQUITY_HEARTBEAT", "60")))
    except ValueError:
        return 60


def _maybe_emit_equity(run: dict, pnl: dict) -> None:
    import time as _time
    try:
        total = round(float(pnl.get("total") or 0), 6)
        prev = _last_equity.get(run["id"])
        now_mono = _time.monotonic()
        if prev is not None and prev[0] == total \
                and now_mono - prev[1] < _equity_heartbeat_seconds():
            return
        _last_equity[run["id"]] = (total, now_mono)
        emit_telemetry_event(run["id"], "equity",
                             {"realized": round(float(pnl.get("realized") or 0), 6),
                              "unrealized": round(float(pnl.get("unrealized") or 0), 6),
                              "total": total, "trades": pnl.get("trades")})
    except Exception:  # noqa: BLE001
        pass


def _cache_realized_pnl(run_id: int, realized: float) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("UPDATE trading_runs SET realized_pnl_usd = ? WHERE id = ?",
                       (realized, run_id))
        conn.commit()
    except Exception:  # noqa: BLE001
        logger.debug("realized_pnl cache write failed for run %s", run_id, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _ratchet_peak_pnl(run: dict, pnl: dict) -> None:
    """Ratchet peak_pnl_usd up so the trailing lock has a high-water mark.
    Tracked for ANY run holding a live position — a monotone climb, written
    only when it advances.

    Previously gated on a trail config, which meant every non-fleet run kept
    peak_pnl_usd NULL (confirmed on prod: NULL on all 63 manual runs). The
    high-water mark is also plain telemetry the reports read, and a run that
    later gains a trail would otherwise arm from a cold NULL."""
    pos = pnl.get("position")
    holding = bool(pos and float(pos.get("quantity") or 0) != 0)
    cur = float(pnl.get("total") or 0)
    prev = run.get("peak_pnl_usd")
    if holding:
        if prev is not None and cur <= float(prev):
            return
    else:
        # Flat: RE-ANCHOR to the banked total. A high-water mark belongs
        # to the exposure that set it — once that position is closed and
        # banked, it is not a drawdown signal for the next one. Prod
        # 2026-08-02 run 921: a fresh probe was stopped by trailing_lock 28
        # SECONDS after opening, at its own entry price, against a peak from
        # hours earlier (realized -3.25). Prod 2026-08-03 run 932 cycle 19:
        # the desk closed a one-cycle-old position because _position_state_line
        # told it it was "holding 0% of that high-water mark" — same stale
        # value, second consumer. Anchoring is unconditional in either
        # direction: the baseline for the NEXT exposure is simply the banked
        # total, whatever it is.
        if prev is not None and abs(cur - float(prev)) < 1e-9:
            return
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("UPDATE trading_runs SET peak_pnl_usd = ? WHERE id = ?",
                       (cur, run["id"]))
        conn.commit()
    except Exception:  # noqa: BLE001
        logger.debug("peak_pnl ratchet failed for run %s", run["id"], exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _manual_halt_blocks(agent_id: int, market: str) -> bool:
    """Exits bypass every gate EXCEPT a manual breaker HALT (the watcher's
    convention, risk_engine 'exits only reduce risk')."""
    try:
        from risk_engine import _is_halted
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            return bool(_is_halted(cursor, agent_id, market, include_auto=False))
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return False


def _flatten_run(run: dict) -> tuple[bool, Optional[str]]:
    """Close the run-owned position via the watcher-convention exit path.
    Fill price is the last mark (same as watcher closes — the staleness
    caveat is surfaced in the UI, not hidden here). Idempotent via the
    'run:{id}:flatten' client_order_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT quantity, current_price FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ? AND run_id = ?
                 AND quantity != 0""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        pos = cursor.fetchone()
    finally:
        conn.close()
    if not pos:
        return True, None
    qty = float(pos["quantity"])
    mark = pos["current_price"]
    if mark is None:
        return False, "no mark price to flatten at"
    if _manual_halt_blocks(run["agent_id"], run["market"]):
        return False, "manual breaker halt blocks exits"
    from automation import execute_paper_trade
    side = "cover" if qty < 0 else "sell"
    # Realized BEFORE the exit leg, so the flatten's own P&L can be
    # journalled below. See the emit for why this matters.
    try:
        realized_before = float((compute_run_pnl(run) or {}).get("realized") or 0)
    except Exception:  # noqa: BLE001 — reporting must never block the exit
        realized_before = None
    signal_id, skip = execute_paper_trade(
        run["agent_id"], run["symbol"], run["market"], side, abs(qty), float(mark),
        content=f"Trading run #{run['id']} flatten on stop",
        run_id=run["id"], client_order_id=f"run:{run['id']}:flatten")
    if signal_id:
        # FINDING 1 (2026-08-05), fixed here. A forced flatten emitted a
        # `trade` event and NOTHING else, while every ordinary close emits an
        # `adapt` carrying `realized` — so the standard realized-P&L query
        # silently OMITTED every flatten. It understates losses exactly on
        # the worst days, because a flatten happens when a brake, a retire or
        # a stop fires on a losing position: 08-04 read −20.61 against a true
        # −62.57, and 08-05 read +73.21 against a true +8.62, the gap being
        # almost entirely run 971's −54.47 flatten. 70+ flattens exist
        # historically.
        #
        # Emitting an `adapt` with `realized` (rather than inventing a new
        # event type) fixes every downstream consumer at once without a query
        # change. It cannot double-count: run_feedback derives its own adapt
        # events from closed SIGNALS on a later cycle, and a flattened run is
        # stopping/stopped, so no later cycle ever processes this leg — which
        # is precisely why the number went missing in the first place.
        try:
            if realized_before is not None:
                realized_after = float(
                    (compute_run_pnl(run) or {}).get("realized") or 0)
                emit_telemetry_event(run["id"], "adapt", {
                    "trigger": "flatten_close",
                    "realized": round(realized_after - realized_before, 4),
                    "side": side, "quantity": abs(qty), "price": float(mark),
                    "client_order_id": f"run:{run['id']}:flatten"})
        except Exception:  # noqa: BLE001 — never let reporting undo an exit
            logger.debug("flatten realized journal failed (run %s)",
                         run["id"], exc_info=True)
        return True, None
    if skip and "duplicate client_order_id" in skip:
        return True, None  # a prior attempt already flattened
    return False, skip


# ── arm executor (2026-08-05) ──────────────────────────────────────────────

def _store_armed_order(run_id: int, arm: Optional[dict], seq: int) -> None:
    """Persist (or clear) the desk's pre-committed exit level.

    Each cycle's arm REPLACES the previous one — the desk is restating its
    standing order with fresh information, and a stale level from hours ago
    is exactly the class of bug that stopped run 921 twenty-eight seconds
    after it opened (see _ratchet_peak_pnl). Passing arm=None clears.
    """
    payload = None
    if isinstance(arm, dict):
        payload = json.dumps({"arm": arm, "seq": int(seq),
                              "armed_at": _now_iso()})
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            "UPDATE trading_runs SET armed_order_json = ? WHERE id = ?",
            (payload, run_id))
        conn.commit()
    except Exception:  # noqa: BLE001 — arming must never break a cycle
        logger.debug("arm store failed for run %s", run_id, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _fire_armed_order(run: dict, pnl: dict, out: dict) -> None:
    """Execute the desk's armed exit if its level has been reached.

    THE WHOLE POINT is that this runs on the CONTROL PASS, not the decision
    cycle — it is the only path that can act between two decisions. Cycle 65
    measured why that is the largest loss class: on 2026-08-05 every losing
    run was in profit first, and for four of seven the profit existed ONLY
    between cycles (5-20 min dwell against a ~45 min cycle), so the desk
    never saw it. 54 arm intents had been emitted lifetime and every one was
    discarded for want of this function.

    Safety: fires ONLY reduce/close (ARM_THEN enforces it), so it can only
    shed risk; fail-closed on a missing arm, missing position or missing
    mark; honours the manual breaker exactly like _flatten_run; one-shot —
    the arm is cleared before the trade so a retry cannot double-fire, and
    the client_order_id makes the execution idempotent regardless.
    """
    raw = run.get("armed_order_json")
    if not raw:
        return
    try:
        blob = json.loads(raw)
        arm = blob.get("arm")
        armed_seq = int(blob.get("seq") or 0)
    except (ValueError, TypeError):
        _store_armed_order(run["id"], None, 0)      # unparseable: clear it
        return

    pos = pnl.get("position") or {}
    try:
        qty = float(pos.get("quantity") or 0)
        mark = pos.get("current_price")
        mark = float(mark) if mark is not None else None
    except (TypeError, ValueError):
        return
    if not qty:
        # Flat: the exposure that justified this arm is gone. A standing
        # order against a position that no longer exists is the stale-peak
        # bug wearing a different hat.
        _store_armed_order(run["id"], None, 0)
        return
    if not pnl.get("mark_age_ok", True) or mark is None:
        return                                       # never act on a stale mark
    if not order_intent.arm_fires(arm, mark=mark):
        return

    frac = order_intent.arm_exit_fraction(arm)
    if frac <= 0:
        _store_armed_order(run["id"], None, 0)
        return
    if _manual_halt_blocks(run["agent_id"], run["market"]):
        return                                       # retry next tick

    exit_qty = abs(qty) * frac
    if exit_qty <= 0:
        return
    side = "cover" if qty < 0 else "sell"
    # Clear FIRST: a crash between here and the trade must not leave a live
    # arm that fires again on the next tick. The client_order_id is the
    # second, independent guard.
    _store_armed_order(run["id"], None, 0)
    from automation import execute_paper_trade
    signal_id, skip = execute_paper_trade(
        run["agent_id"], run["symbol"], run["market"], side, exit_qty,
        float(mark),
        content=f"Trading run #{run['id']} armed exit",
        run_id=run["id"],
        client_order_id=f"run:{run['id']}:arm:{armed_seq}")
    level = None
    try:
        level = float(arm.get("level"))
    except (TypeError, ValueError):
        pass
    emit_telemetry_event(run["id"], "armed_exit", {
        "armed_seq": armed_seq, "if": arm.get("if"), "level": level,
        "then": arm.get("then"), "size_frac": frac,
        "mark": mark, "qty": exit_qty, "side": side,
        # Slippage is REPORTED, never a veto — an arm may only shed risk and
        # this module never refuses that. A large value means price gapped.
        "slippage_pct": (round((mark - level) / level * 100.0, 4)
                         if level else None),
        "executed": bool(signal_id), "skip": skip})
    if signal_id:
        out["armed_exits_fired"] = out.get("armed_exits_fired", 0) + 1


# ── control pass (sync, zero-LLM) ──────────────────────────────────────────

def _start_condition_fires(run: dict) -> bool:
    """Evaluate an armed run's start condition. Strictly-validated JSON was
    stored at create time; any read/parse problem here means STAY ARMED
    (fail closed — never 'start now')."""
    try:
        cond = json.loads(run.get("start_condition_json") or "{}")
    except Exception:  # noqa: BLE001
        return False
    ctype = cond.get("type")
    if ctype == "at_time":
        return str(cond.get("at") or "9999") <= _now_iso()
    if ctype == "window":
        try:
            from schedule import in_window
            return in_window(cond.get("schedule"), datetime.now(timezone.utc))
        except Exception:  # noqa: BLE001
            return False
    if ctype == "price_cross":
        try:
            from price_fetcher import get_price_from_market
            price = get_price_from_market(run["symbol"], None, run["market"])
        except Exception:  # noqa: BLE001
            return False
        if price is None:
            return False
        if cond.get("direction") == "above":
            return float(price) >= float(cond.get("price") or 0)
        return float(price) <= float(cond.get("price") or float("inf"))
    return False


def _transition_row(cursor, run: dict, target: str, reason: str,
                    clear_active_key: bool = False) -> bool:
    """Guarded status flip inside the caller's transaction + journal event."""
    sets = "status = ?, status_reason = ?"
    args: list = [target, reason]
    if clear_active_key:
        sets += ", active_key = NULL, stopped_at = ?"
        args.append(_now_iso())
    cursor.execute(f"UPDATE trading_runs SET {sets} WHERE id = ? AND status = ?",
                   (*args, run["id"], run["status"]))
    if cursor.rowcount != 1:
        return False
    _emit_event(cursor, run["id"], "run_status",
                {"from": run["status"], "to": target, "reason": reason})
    return True


def _simple_transition(run: dict, target: str, reason: str,
                       clear_active_key: bool = False,
                       extra_sets: str = "", extra_args: tuple = ()) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        sets = "status = ?, status_reason = ?"
        args: list = [target, reason]
        if clear_active_key:
            sets += ", active_key = NULL, stopped_at = ?"
            args.append(_now_iso())
            # Mirror of trading_runs._transition: release any position the run
            # still holds back to the unowned book, so the owner can still
            # close it by hand. `run_id` marks an ACTIVE run's book now that
            # sibling runs share a symbol, and every non-run reader filters on
            # `run_id IS NULL`.
            cursor.execute(
                "UPDATE positions SET run_id = NULL WHERE run_id = ? AND agent_id = ?",
                (run["id"], run["agent_id"]))
        if extra_sets:
            sets += ", " + extra_sets
            args.extend(extra_args)
        cursor.execute(f"UPDATE trading_runs SET {sets} WHERE id = ? AND status = ?",
                       (*args, run["id"], run["status"]))
        ok = cursor.rowcount == 1
        if ok:
            _emit_event(cursor, run["id"], "run_status",
                        {"from": run["status"], "to": target, "reason": reason})
        conn.commit()
        return ok
    finally:
        conn.close()


def _alert_run(run: dict, kind: str, msg_id: str, params: dict, dedupe: str) -> None:
    try:
        from alerts import send_alert
        send_alert(run["agent_id"], kind, msg_id, params, dedupe_key=dedupe)
    except Exception:  # noqa: BLE001
        logger.debug("run alert failed (run %s)", run["id"], exc_info=True)


def control_pass() -> dict:
    """Zero-LLM control work, every scan:
      * armed: fire start conditions; time out ancient armed runs
      * running/paused: evaluate stop conditions (pause blocks entries, not
        stops or the clock); FAIL CLOSED on evaluation errors/stale marks
      * stopping: flatten (watcher-convention) or hold; bounded retry then
        the explicit stopped(positions_held) terminal
    Every active run is first checked for its `active_key` (see
    _guard_active_key) — a run that lost its exclusivity lock must not trade.
    Returns counters for logs."""
    out = {"armed_started": 0, "stopping_finished": 0, "stops_fired": 0,
           "armed_exits_fired": 0,
           "eval_failures": 0, "keys_healed": 0, "keys_conflicted": 0}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trading_runs WHERE status IN (?, ?, ?, ?)",
            (STATUS_ARMED, STATUS_RUNNING, STATUS_PAUSED, STATUS_STOPPING))
        runs = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    for run in runs:
        try:
            if not _guard_active_key(run, out):
                continue
            if run["status"] == STATUS_ARMED:
                _control_armed(run, out)
            elif run["status"] in (STATUS_RUNNING, STATUS_PAUSED):
                _control_active(run, out)
            elif run["status"] == STATUS_STOPPING:
                _control_stopping(run, out)
        except Exception:  # noqa: BLE001
            logger.warning("control pass failed for run %s", run["id"], exc_info=True)
    return out


def _guard_active_key(run: dict, out: dict) -> bool:
    """An active run MUST hold `active_key` — that UNIQUE row is the only
    thing keeping one agent+market+symbol+filter_key to a single run. Runs
    that differ in strategy shape may share a symbol (they hold separate
    `positions` rows); two runs with the SAME shape would race one signal
    with two books, so exactly one of them may hold the key.

    `start_run` is the only writer and `-> stopped` the only clearer, so a
    NULL key here means the row was written outside the state machine (a raw
    DB edit, a half-applied migration, a restore). Reclaim the key when the
    tuple is free; when another run already owns it this run is the genuine
    duplicate and must stop trading. Returns False when the caller should
    skip the run this scan.

    `stopping` is exempt: it takes no entries and only flattens its own
    run-owned position, so letting it finish is safer than stranding it.

    A run that was already active when the filter key shipped holds the legacy
    `agent:market:symbol` form. It is upgraded here rather than left alone:
    a legacy key can never collide with a new-format one, so a genuinely
    duplicate run would otherwise start alongside it. Migration 0027 does the
    same rewrite in bulk — this covers databases that do not run alembic."""
    if run["status"] == STATUS_STOPPING:
        return True
    key = trading_runs._active_key(run["agent_id"], run["market"], run["symbol"],
                                   trading_runs.run_filter_key(run))
    existing = run.get("active_key")
    if existing == key:
        return True
    if existing:
        # Legacy (or otherwise stale) key: claim the correctly-formatted one.
        # Losing the race means a live run already holds this exact strategy
        # slot, so fall through to the duplicate handling below.
        if _reclaim_active_key(run, key, from_key=existing):
            run["active_key"] = key
            return True
        out["keys_conflicted"] += 1
        return _halt_duplicate(run)
    if not _reclaim_active_key(run, key, from_key=None):
        out["keys_conflicted"] += 1
        return _halt_duplicate(run)
    out["keys_healed"] += 1
    logger.warning("run %s was active without an exclusivity key — "
                   "reclaimed %s", run["id"], key)
    run["active_key"] = key
    return True


def _reclaim_active_key(run: dict, key: str, from_key: Optional[str]) -> bool:
    """Claim `key` for this run, conditional on its key still being `from_key`
    (None meaning NULL). False when the UNIQUE index says another live run
    already holds this exact agent+market+symbol+filter slot."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        if from_key is None:
            cursor.execute(
                "UPDATE trading_runs SET active_key = ? WHERE id = ? AND active_key IS NULL",
                (key, run["id"]))
        else:
            cursor.execute(
                "UPDATE trading_runs SET active_key = ? WHERE id = ? AND active_key = ?",
                (key, run["id"], from_key))
        conn.commit()
        return cursor.rowcount == 1
    except Exception:  # noqa: BLE001 — UNIQUE(active_key): another run owns it
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def _halt_duplicate(run: dict) -> bool:
    """Stop (armed) or pause (running) a run whose strategy slot is taken.
    Always returns False — the caller must skip this run."""
    # armed -> paused is not a legal transition; armed -> stopped is. The
    # stopped branch reuses clear_active_key purely to stamp stopped_at.
    if run["status"] == STATUS_ARMED:
        halted = _simple_transition(run, STATUS_STOPPED, "duplicate_active_key",
                                    clear_active_key=True)
    else:
        halted = _simple_transition(run, STATUS_PAUSED, "duplicate_active_key",
                                    extra_sets="paused_reason = ?",
                                    extra_args=("duplicate_active_key",))
    if halted:
        _alert_run(run, "run_stopped", "run_dup_key",
                   {"run_id": run["id"], "symbol": run["symbol"], "market": run["market"]},
                   dedupe=f"run:{run['id']}:dup_key")
    return False


def _control_armed(run: dict, out: dict) -> None:
    # Plan 14 §6.7 depth (3): armed runs stay ARMED under an account master
    # hold (armed→paused is an illegal transition and would bypass the start
    # condition on resume). The hold blocks the start here — and suspends the
    # armed-timeout clock, so a long hold cannot silently expire the run
    # ("reversible" must stay true).
    try:
        if _master_held(run["agent_id"]):
            return
    except Exception:  # noqa: BLE001 — fail closed: no start under uncertainty
        return
    started = run.get("started_at")
    if started and _age_seconds(started) > _armed_timeout():
        if _simple_transition(run, STATUS_STOPPED, "armed_timeout",
                              clear_active_key=True):
            _alert_run(run, "run_stopped", "run_armed_timeout",
                       {"run_id": run["id"], "symbol": run["symbol"],
                        "hours": _armed_timeout() // 3600},
                       dedupe=f"run:{run['id']}:armed_timeout")
        return
    if _start_condition_fires(run):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            if _transition_row(cursor, run, STATUS_RUNNING, "start_condition_fired"):
                out["armed_started"] += 1
            conn.commit()
        finally:
            conn.close()


def _control_active(run: dict, out: dict) -> None:
    """Stop-condition evaluation for running AND paused runs."""
    try:
        reason = _evaluate_stop(run)
        pnl = compute_run_pnl(run)
        _cache_realized_pnl(run["id"], pnl["realized"])
        _ratchet_peak_pnl(run, pnl)
        # The desk's pre-committed exit. This is the ONLY path that can act
        # between two decision cycles, which is where the profit lived on
        # 2026-08-05 (see _fire_armed_order). Never allowed to break the
        # control pass — stop evaluation above it has already run.
        try:
            _fire_armed_order(run, pnl, out)
        except Exception:  # noqa: BLE001
            logger.warning("armed exit failed for run %s", run["id"],
                           exc_info=True)
        try:
            from run_reports import evaluate_thresholds
            evaluate_thresholds(run, pnl)
        except Exception:  # noqa: BLE001 — reporting must never block safety
            logger.debug("threshold hook failed (run %s)", run["id"], exc_info=True)
        _maybe_emit_equity(run, pnl)
        # healthy evaluation resets the failure counter
        if int(run.get("consecutive_errors") or 0) > 0:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                begin_write_transaction(cursor)
                cursor.execute(
                    "UPDATE trading_runs SET consecutive_errors = 0 WHERE id = ?",
                    (run["id"],))
                conn.commit()
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001 — FAIL CLOSED
        out["eval_failures"] += 1
        failures = int(run.get("consecutive_errors") or 0) + 1
        if failures >= _stop_eval_failure_limit():
            # persistent failure escalates to stop — never an infinite
            # pause<->resume livelock.
            #
            # …but do NOT flatten on the way out (2026-07-26). The trigger for
            # this path is that marks are stale or unreadable, so a forced
            # market exit prices the position on exactly the data we just
            # declared untrustworthy. Six prod runs died here and the forced
            # flatten realised −$14.41 (runs 79/80: −$6.83 / −$7.36 with no
            # other trade). Stop and HOLD the position; the user (or the
            # watcher, once the feed recovers) decides the exit.
            if _simple_transition(
                    run, STATUS_STOPPING, "stop_eval_failed",
                    extra_sets="consecutive_errors = ?, stopped_at = ?, stop_flatten = 0",
                    extra_args=(failures, _now_iso())):
                _alert_run(run, "run_stopped", "run_stop_eval_failed",
                           {"run_id": run["id"], "failures": failures, "exc": exc},
                           dedupe=f"run:{run['id']}:eval_stop")
            return
        if run["status"] == STATUS_RUNNING:
            if _simple_transition(run, STATUS_PAUSED, "stop_eval_failed",
                                  extra_sets="consecutive_errors = ?, paused_reason = ?",
                                  extra_args=(failures, "stop_eval_failed")):
                _alert_run(run, "run_stopped", "run_stop_eval_paused",
                           {"run_id": run["id"], "exc": exc},
                           dedupe=f"run:{run['id']}:eval_pause")
        else:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                begin_write_transaction(cursor)
                cursor.execute(
                    "UPDATE trading_runs SET consecutive_errors = ? WHERE id = ?",
                    (failures, run["id"]))
                conn.commit()
            finally:
                conn.close()
        return

    if reason is None:
        # auto-recovery: a run we paused for eval failures resumes once
        # evaluation is healthy again (user pauses stay paused)
        if run["status"] == STATUS_PAUSED and run.get("paused_reason") == "stop_eval_failed":
            _simple_transition(run, STATUS_RUNNING, "stop_eval_recovered",
                               extra_sets="paused_reason = NULL", extra_args=())
        return

    out["stops_fired"] += 1
    emit_telemetry_event(run["id"], "alert", {"stop_reason": reason})
    _alert_run(run, "run_stopped", "run_stop_event",
               {"run_id": run["id"], "reason": reason, "symbol": run["symbol"],
                "market": run["market"],
                "outcome": "flatten" if run.get("stop_flatten") else "hold"},
               dedupe=f"run:{run['id']}:{reason}")
    if _simple_transition(run, STATUS_STOPPING, reason,
                          extra_sets="stopped_at = ?", extra_args=(_now_iso(),)):
        # finish in the SAME scan when possible (flatten or position-less stop)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trading_runs WHERE id = ?", (run["id"],))
            fresh = cursor.fetchone()
        finally:
            conn.close()
        if fresh is not None:
            _control_stopping(dict(fresh), out)


# ── auto-restart after a goal-reached stop ────────────────────────────────
# A run that finished its job is cloned and restarted with identical settings,
# so the board never goes idle after a win.
#
# ONLY goal-reached reasons qualify, deliberately:
#   * max_loss / synthetic_liquidation / stop_eval_failed are PROTECTIVE — a
#     restart re-enters the setup that just lost money and turns a one-time
#     loss cap into a repeating loss.
#   * user_stop must stay stopped, or the Stop button resurrects its own run.
#   * at_time / price_cross would re-fire on the very next scan (the deadline
#     is still past, the price still beyond the line) — an instant stop loop.
# That leaves the two reasons whose condition genuinely resets on a fresh run:
# profit_target (P&L back to 0) and max_trades (trade count back to 0).
_RESTARTABLE_STOP_REASONS = frozenset({
    "stop_event:profit_target",
    "stop_event:trailing_lock",   # same disposition: a banked win, P&L back to 0
    "stop_event:max_trades",
})


def _auto_restart_enabled() -> bool:
    return os.getenv("RUN_AUTO_RESTART", "true").strip().lower() in ("1", "true", "yes")


def _maybe_auto_restart(run: dict) -> None:
    """Clone a goal-reached run and start the clone, carrying over settings,
    start condition, stop conditions and the flatten flag verbatim.

    Best-effort: any failure (entitlement denial, a conflicting rule, a
    position that reappeared) leaves the original stopped — the safe
    direction — and is logged rather than raised, because this runs inside
    the control pass and must never wedge the scan."""
    reason = run.get("status_reason") or ""
    if reason not in _RESTARTABLE_STOP_REASONS or not _auto_restart_enabled():
        return
    # Plan 14: fleet members NEVER auto-restart — the fleet's slot replacement
    # is the ONLY replacement mechanism. A clone would trade the same symbol
    # with fleet-sized budget outside N, outside the rails, and re-clone on
    # every profit_target hit (the round-2 QA double-deploy critical).
    if run.get("fleet_id") or (run.get("created_via") or "user") == "fleet":
        return
    # Plan 14 §6.7: a held account must not spawn new active runs.
    try:
        if _master_held(run["agent_id"]):
            return
    except Exception:  # noqa: BLE001
        return
    try:
        from trading_runs import create_run, start_run
        settings = json.loads(run.get("config_snapshot_json") or "{}")
        if not settings.get("symbol"):
            return
        new_id = create_run(
            run["agent_id"], settings,
            json.loads(run.get("start_condition_json") or '{"type": "manual"}'),
            json.loads(run.get("stop_conditions_json") or "{}"),
            bool(run.get("stop_flatten")),
        )
        start_run(new_id, run["agent_id"])
    except Exception as exc:  # noqa: BLE001 — never break the control pass
        logger.warning("auto-restart of run %s failed: %s", run["id"], exc)
        return
    emit_telemetry_event(run["id"], "alert",
                         {"auto_restart_run_id": new_id, "stop_reason": reason})
    _alert_run(run, "custom", "run_goal_restart",
               {"run_id": run["id"], "new_run_id": new_id, "symbol": run["symbol"],
                "market": run["market"], "reason": reason},
               dedupe=f"run:{run['id']}:auto_restart")


def _flush_pending_close_adapts(run: dict) -> int:
    """Journal any close whose `adapt` never fired because the run stopped
    first. Returns how many were emitted.

    WHY (2026-08-06, cycle 79). #249 fixed the forced flatten's missing
    `adapt` and its own comment states the mechanism exactly:

        "run_feedback derives its own adapt events from closed SIGNALS on a
         later cycle, and a flattened run is stopping/stopped, so no later
         cycle ever processes this leg"

    That is true of the flatten leg — and EQUALLY true of every other close
    still pending when the run stops. #249 fixed one leg and left the desk's
    own final-cycle exits behind. Measured on 08-06: run 960's `reduce` at
    08:18:07 (−4.3752) and run 976's `reduce` at 05:40:01 (−2.3142) were both
    followed by a stop before the next cycle, so neither ever reached the
    adapt stream. Together **−6.69 of that day's −9.56 ledger-vs-adapt drift,
    70% of it** — a bigger hole than the flatten defect #249 was raised for.

    It is the SAME failure shape twice: a number that is only journalled
    "next cycle" is lost precisely when there is no next cycle, which is
    precisely when the run died — the worst moments, again.

    Emits, never adapts. A terminal run's `size_mult` ladder is moot, so this
    deliberately does NOT take the claim fence `run_feedback.save_state`
    needs (a stopping run is unclaimed, and the write would be discarded).
    It is a record of what already happened, exactly as #249's is.

    Idempotent by construction — the watermark is read back out of the
    run's OWN adapt events rather than from `adapt_state_json`, so the
    bounded flatten retry in `_control_stopping` cannot double-journal, and
    a run carrying older unjournalled closes is self-healed.
    """
    try:
        import run_feedback
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT payload FROM run_events WHERE run_id = ? "
                "AND event_type = 'adapt'", (run["id"],))
            done: set[int] = set()
            for row in cursor.fetchall():
                try:
                    sid = json.loads(dict(row)["payload"]).get("signal_id")
                except (ValueError, TypeError):
                    continue
                if sid is not None:
                    done.add(int(sid))
            # #249 already journals the flatten leg under `flatten_close`,
            # and that event carries no signal_id — so it would NOT appear in
            # `done` and would be re-journalled here on a retry after a
            # successful flatten whose transition failed. Exclude by id.
            cursor.execute(
                "SELECT id FROM signals WHERE run_id = ? "
                "AND client_order_id LIKE '%flatten%'", (run["id"],))
            done.update(int(dict(r)["id"]) for r in cursor.fetchall())
        finally:
            conn.close()
        emitted = 0
        for o in run_feedback.leg_outcomes(run, 0):
            if int(o["signal_id"]) in done:
                continue
            emit_telemetry_event(run["id"], "adapt", {
                "trigger": "pending_close",
                "signal_id": int(o["signal_id"]),
                "realized": round(float(o["realized"]), 4),
                "direction": o.get("direction"),
                "reason": "run stopped before the next cycle could ingest it"})
            emitted += 1
        return emitted
    except Exception:  # noqa: BLE001 — reporting must never wedge a stop
        logger.debug("pending-close flush failed (run %s)", run["id"],
                     exc_info=True)
        return 0


# queued-flatten telemetry: first queue entry writes, then a heartbeat — NOT
# a row per control scan (run 1161 wrote 1,144 identical "flatten queued"
# rows over one 10.5h closed session; R12). The retry itself is untouched —
# only the journal write is throttled. Leaving the queue (market open, or a
# broken calendar failing open to the flatten) clears the entry, so the next
# queueing writes immediately again.
_last_flatten_queued: dict[int, float] = {}  # run_id -> monotime of last write


def _flatten_queued_heartbeat_seconds() -> int:
    try:
        return max(60, int(os.getenv("RUN_FLATTEN_QUEUED_HEARTBEAT", "1800")))
    except ValueError:
        return 1800


def _control_stopping(run: dict, out: dict) -> None:
    # BEFORE any branch, and before the flatten leg exists as a signal: all
    # three exits below are terminal, and each one is a place a pending close
    # would otherwise be lost.
    _flush_pending_close_adapts(run)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ?
                 AND run_id = ? AND quantity != 0""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        has_position = cursor.fetchone() is not None
    finally:
        conn.close()

    if not has_position:
        if _simple_transition(run, STATUS_STOPPED,
                              run.get("status_reason") or "stop_complete",
                              clear_active_key=True):
            out["stopping_finished"] += 1
            _cache_realized_pnl(run["id"], compute_run_pnl(run)["realized"])
            _maybe_auto_restart(run)
        return

    if not run.get("stop_flatten"):
        # hold: the position stays under the SL/TP watcher, and the stop
        # releases its run_id back to the unowned book — a finished run must
        # not keep the owner from closing by hand. Realized P&L up to the stop
        # is already cached on the run.
        if _simple_transition(run, STATUS_STOPPED, "positions_held",
                              clear_active_key=True):
            out["stopping_finished"] += 1
        return

    # Plan 23 Phase C2: a flatten on a CLOSED market would fill at the last
    # (stale) mark — the paper book would book a phantom price no live order
    # could get. Queue instead: stay `stopping`, touch neither the flatten
    # nor the timeout clock (a Friday-evening stop must not strand its
    # position as positions_held before Monday's open), and execute on the
    # first scan after the open, at a fresh mark.
    try:
        import markets as _mkts
        if not _mkts.is_market_open(run.get("market")):
            import time as _time
            now_mono = _time.monotonic()
            prev = _last_flatten_queued.get(run["id"])
            if prev is None \
                    or now_mono - prev >= _flatten_queued_heartbeat_seconds():
                _last_flatten_queued[run["id"]] = now_mono
                emit_telemetry_event(run["id"], "gate_skip",
                                     {"stage": "flatten",
                                      "reason": "market closed — flatten queued "
                                                "to the next open"})
            return
    except Exception:  # noqa: BLE001 — a missing calendar must not block a stop
        pass
    _last_flatten_queued.pop(run["id"], None)  # left the queue: a state change

    ok, why = _flatten_run(run)
    if ok:
        if _simple_transition(run, STATUS_STOPPED,
                              run.get("status_reason") or "stop_complete",
                              clear_active_key=True):
            out["stopping_finished"] += 1
            # reconcile the display cache AFTER the flatten leg landed
            _cache_realized_pnl(run["id"], compute_run_pnl(run)["realized"])
            _maybe_auto_restart(run)
        return
    # bounded retry, then the explicit terminal — a stop can never wedge
    stopping_since = run.get("stopped_at")
    if not stopping_since:
        # self-heal older rows that entered stopping without a stamp
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            stopping_since = _now_iso()
            cursor.execute("UPDATE trading_runs SET stopped_at = ? WHERE id = ?",
                           (stopping_since, run["id"]))
            conn.commit()
        finally:
            conn.close()
    emit_telemetry_event(run["id"], "gate_skip",
                         {"stage": "flatten", "reason": why})
    if stopping_since and _age_seconds(stopping_since) > _flatten_timeout():
        if _simple_transition(run, STATUS_STOPPED, "positions_held",
                              clear_active_key=True):
            out["stopping_finished"] += 1
            _alert_run(run, "run_stopped", "run_positions_held",
                       {"run_id": run["id"], "why": why,
                        "minutes": _flatten_timeout() // 60},
                       dedupe=f"run:{run['id']}:positions_held")


# ── cycle cadence (#269) ───────────────────────────────────────────────────
# Owner, 2026-08-06: "Sooppiy AI analysis each run 30 min (make time gap
# each)". Two separate problems, two separate mechanisms.
INTERVAL_CAP_MIN = 30


def _interval_cap_min() -> int:
    """Platform ceiling on how long a live run may go unanalysed. Applied at
    SCHEDULING time, deliberately: the per-run `interval_minutes` in the
    config snapshot belongs to the desk that built the run, and this caps it
    without rewriting a single run row."""
    try:
        return max(5, int(os.environ.get("RUN_INTERVAL_CAP_MIN", INTERVAL_CAP_MIN)))
    except ValueError:
        return INTERVAL_CAP_MIN


def _phase_offset_min(run_id: int, interval_min: int) -> int:
    """Each run's own repeating slot on the absolute clock grid.

    A fleet built in one pass inherits one identical `last_cycle_at` (six runs
    here shared 22:57:00) and then cycles in lockstep forever — every run
    competing for the same worker slot and, worse, every decision taken on the
    same tick of the same data. 7 is coprime with the intervals in use, so
    consecutive run ids land 7 minutes apart."""
    return (run_id * 7) % max(1, interval_min)


def _slot(dt: datetime, interval_min: int, offset_min: int) -> int:
    """Index of the run's slot containing `dt`."""
    return (int(dt.timestamp()) // 60 - offset_min) // max(1, interval_min)


def _opened_since(market: "str | None", last_dt: datetime,
                  now: datetime) -> bool:
    """True when the market is open NOW but was closed at the run's last
    cycle — the bell rang in between. Owner (2026-08-12): "most people try
    to buy and sell when the US market opens — we must catch that time."
    A staggered slot could put a run's first in-session decision up to a
    full interval after the open, missing the day's highest-volume window.
    24×7 markets are always open at both stamps, so this never fires for
    them. Fail-closed: a calendar problem falls back to normal slotting."""
    try:
        import markets as _mkts
        return (_mkts.is_market_open(market, now)
                and not _mkts.is_market_open(market, last_dt))
    except Exception:  # noqa: BLE001
        return False


def due_run_ids() -> list[int]:
    """Running runs whose per-run interval has elapsed (interval lives in the
    config snapshot; the comparison is done in Python — dual-dialect date
    math is deliberately avoided)."""
    now = _now_dt()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, market, config_snapshot_json, last_cycle_at "
            "FROM trading_runs WHERE status = ?", (STATUS_RUNNING,))
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    due: list[int] = []
    try:
        import stop_router
        _stop_routing = stop_router.enabled()
    except Exception:  # noqa: BLE001
        stop_router, _stop_routing = None, False
    for row in rows:
        try:
            # Stop-hit routing: a noted hit dispatches NOW — before slots,
            # intervals, even the analysis window (the desk must rule inside
            # the fail-safe clock; its ORDER still obeys session rules).
            if (_stop_routing and stop_router is not None
                    and stop_router.pending(row["id"])):
                due.append(row["id"])
                continue
            cfg = json.loads(row.get("config_snapshot_json") or "{}")
            # Swing dormancy (owner spec 2026-08-12): a run stamped with an
            # analysis_window cycles only from pre_open before the open to
            # post_close after the close. Outside that it is not merely
            # skipped — it is never dispatched, so overnight/weekend produce
            # zero cycles and zero journal noise. Fail-open on calendar
            # trouble: a broken clock must not silence a live run.
            win = cfg.get("analysis_window") or {}
            if win:
                try:
                    import markets as _mkts
                    if _mkts.extended_session_state(
                            row.get("market"),
                            pre_minutes=int(win.get("pre_open_minutes") or 0),
                            post_minutes=int(win.get("post_close_minutes") or 0),
                    ) == "closed":
                        continue
                except Exception:  # noqa: BLE001
                    pass
            # Owner decision 2026-08-13 (AMENDS Plan 23 Phase B): the
            # us-stock block DAY-trades — every archetype thinks on the
            # platform's 30-min clock. The 240-min swing special-case never
            # actually slowed a run (compose stamps interval_minutes=30 and
            # this cap is a ceiling, so min(240, 30) was 30 all along);
            # removing it makes the design match the tape. Stops stay on
            # the ~60s control scan — thinking cadence never delays an exit.
            cap = _interval_cap_min()
            interval_min = max(5, min(cap,
                                       int(cfg.get("interval_minutes") or 60)))
            last = row.get("last_cycle_at")
            if not last:
                due.append(row["id"])
                continue
            last_dt = datetime.strptime(last, TS_FMT).replace(tzinfo=timezone.utc)
            # Catch the open (owner 2026-08-12): the bell rang since this
            # run's last cycle ⇒ due NOW, bypassing slot phase and the
            # half-interval guard. Every session-market run gets its first
            # decision within one scheduler pass of the open instead of up
            # to a full interval late.
            if _opened_since(row.get("market"), last_dt, now):
                due.append(row["id"])
                continue
            offset = _phase_offset_min(row["id"], interval_min)
            # A plain "elapsed >= interval" test can never break lockstep:
            # once a full interval has passed the slot has ALWAYS advanced, so
            # the two conditions collapse into one and every run keeps its
            # inherited phase forever. Allowing one early fire — never sooner
            # than half an interval — lets a run snap onto its own slot once,
            # after which it fires exactly once per slot at a true period.
            if (_slot(now, interval_min, offset) > _slot(last_dt, interval_min, offset)
                    and now - last_dt >= timedelta(minutes=interval_min / 2)):
                due.append(row["id"])
        except Exception:  # noqa: BLE001
            logger.warning("due-check failed for run %s", row.get("id"), exc_info=True)
    return due


# ── the cycle (sync; runs on the dedicated executor) ───────────────────────

def _claim(run_id: int) -> Optional[dict]:
    """Lease claim: own short committed transaction; atomically increments
    cycle_seq and stamps last_cycle_at. Predicate allows expiry-reclaim and
    owner renewal. Returns the fresh run row on success, None when another
    worker owns the lease or the run left `running`."""
    now = _now_iso()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """UPDATE trading_runs
               SET claimed_by = ?, claim_expires_at = ?, cycle_seq = cycle_seq + 1,
                   last_cycle_at = ?
               WHERE id = ? AND status = ?
                 AND (claim_expires_at IS NULL OR claim_expires_at < ? OR claimed_by = ?)""",
            (WORKER_IDENTITY, _iso_in(_lease_ttl()), now, run_id, STATUS_RUNNING,
             now, WORKER_IDENTITY),
        )
        claimed = cursor.rowcount == 1
        conn.commit()
        if not claimed:
            return None
        cursor.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _release(run_id: int) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute(
            """UPDATE trading_runs SET claimed_by = NULL, claim_expires_at = NULL
               WHERE id = ? AND claimed_by = ?""",
            (run_id, WORKER_IDENTITY))
        conn.commit()
    except Exception:  # noqa: BLE001
        logger.debug("lease release failed for run %s", run_id, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _fence(run_id: int):
    """Fencing predicate evaluated INSIDE the trade transaction: the lease
    must still be ours and unexpired, and the run must still be running
    (a stop pressed during the in-flight cycle prevents the trade)."""
    def _check(cursor) -> Optional[str]:
        from database import using_mysql
        query = ("SELECT status, claimed_by, claim_expires_at FROM trading_runs "
                 "WHERE id = ?")
        if using_mysql():
            query += " FOR UPDATE"  # row-lock the lease for the txn's duration
        try:
            cursor.execute(query, (run_id,))
        except Exception:  # noqa: BLE001
            return "fence: run row unreadable"
        row = cursor.fetchone()
        if not row:
            return "fence: run vanished"
        if row["status"] != STATUS_RUNNING:
            return f"fence: run is {row['status']}"
        if row["claimed_by"] != WORKER_IDENTITY:
            return "fence: lease reclaimed by another worker"
        if (row["claim_expires_at"] or "") < _now_iso():
            return "fence: lease expired"
        return None
    return _check


def _master_held(agent_id: int) -> bool:
    """Plan 14 §6.7: account-level master hold — the zero-cost pre-gate. A
    held account cannot trade even if an individual object was missed by the
    hold fan-out. Fail CLOSED on lookup errors (money gate)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.ai_automation_state AS s FROM users u "
            "JOIN agents a ON a.user_id = u.id WHERE a.id = ?", (agent_id,))
        row = cursor.fetchone()
        if row is None:
            return False  # unlinked agent — no user-level hold exists
        return (row["s"] or "active") == "held"
    finally:
        conn.close()


def _open_cost_basis(agent_id: int, market: str, symbol: str, run_id: int) -> float:
    """Deployed MARGIN of the run's own position row: |qty| × avg entry / L.
    The Plan 14 run-budget cap input — run_budget caps committed margin, so a
    leveraged run controls L× the notional for the same budget. L=1 ⇒ the
    prior |qty|×entry notional basis."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # SUM over every lot: a fetchone here read ONE arbitrary row and
        # under-counted a multi-lot book to near zero (run 1099 stacked
        # $9,189 of margin basis past a $1,580 run budget that never bit).
        cursor.execute(
            """SELECT quantity, entry_price, leverage FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ? AND run_id = ?""",
            (agent_id, market, symbol, run_id))
        basis = 0.0
        for row in cursor.fetchall():
            try:
                lev = max(1.0, float(row["leverage"])) if row["leverage"] else 1.0
            except (KeyError, TypeError, ValueError):
                lev = 1.0
            basis += abs(float(row["quantity"] or 0)) * \
                float(row["entry_price"] or 0) / lev
        return basis
    finally:
        conn.close()


def _fleet_cycle_mode(cfg: dict) -> str:
    """Plan 14 §9.2: fleet members default to the LIGHT cycle profile (one
    decision-tier call) — the lever the fleet cost model rests on. Full
    pipeline is per-run opt-in via config, or globally via env."""
    per_run = (cfg.get("cycle_mode") or "").strip().lower()
    if per_run in ("light", "full"):
        return per_run
    return os.getenv("FLEET_CYCLE_MODE", "light").strip().lower()


def _adds_require_profit() -> bool:
    """Kill switch for the underwater-add block (default on)."""
    return os.getenv("RUN_ADDS_REQUIRE_PROFIT", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _unrealized_pnl(run: dict) -> Optional[float]:
    """This run's unrealized P&L, or None when it cannot be trusted (no live
    mark, stale mark, unreadable book) — callers must treat None as 'unknown'
    and not as 'flat'."""
    try:
        pnl = compute_run_pnl(run)
    except Exception:  # noqa: BLE001
        return None
    if not pnl.get("mark_age_ok"):
        return None
    pos = pnl.get("position")
    if not (pos and float(pos.get("quantity") or 0) != 0):
        return None
    return float(pnl.get("unrealized") or 0)


# ── the desk's own order plan, honoured (2026-07-30) ───────────────────────
# The full trader prompt asks for eight fields and the desk fills them in.
# Three were wired through (size_frac, leverage, stop_pct/target_pct) and four
# were parsed, railed, journalled and then DISCARDED. Prod run 825 authored
# {"size_frac":0.6, "leverage":1.5, "stop_pct":8, "target_pct":27,
#  "trail_arm_pct":12, "trail_give":0.3, "horizon_hours":72, "max_adds":1}
# — a complete, internally consistent risk plan — and the engine kept less
# than half of it. This section honours the rest.
_AMBIENT_TRIGGERS = frozenset({"psych_shock", "hot_issue"})


def _order_plan_enabled() -> bool:
    """Kill switch for the PRICE-INDEPENDENT honoured fields: the reduce
    basis, the trail conversion, and max_adds. Default ON.

    Those three are defects whichever way the tape goes — a 60% trim executing
    as a 100% flatten is wrong in either direction, and a discarded trail is
    discarded regardless of price. Independent of RUN_AI_ORDER_PARAMS so the
    already-shipped three (size_frac, leverage, bracket) can stay on if this
    regresses."""
    return (os.getenv("RUN_ORDER_PLAN", "true") or "true").strip().lower() in (
        "1", "true", "yes", "on")


def _horizon_gate_enabled() -> bool:
    """Whether the desk's horizon may actually SUPPRESS a cycle. Default OFF.

    Split out from _order_plan_enabled on 2026-07-30 after the only evidence
    for it reversed. Run 825 authored horizon_hours 72 and was re-decided at
    30 minutes; measured against holding the plan it wrote, that exit was
    worth −$4.79 at 05:30, −$5.54 at 06:01, and then **+$1.78** at 07:31 as
    KAITO fell through the sell price. A $7.32 swing in 90 minutes on n=1 is
    not a basis for a rail — that is the same standard that rejected
    trail_activate_rr, the breakeven ratchet, the peak-relative brake cap and
    RUN_CONF_V2, and it has to apply to this recommendation too.

    Off, the horizon is still COMPUTED and journalled (`horizon_shadow`), so
    the suppression dataset accumulates without anything being suppressed.
    Revisit with n >> 1, comparing each shadow-suppressed cycle's decision
    against what the position actually did over the authored horizon."""
    return (os.getenv("RUN_HORIZON_GATE", "false") or "false").strip().lower() in (
        "1", "true", "yes", "on")


def _warm_report_i18n(agent_id: int, report: Any) -> None:
    """Schedule the owner's-language translation of a just-journaled report.

    The journal stays English (the desk_memory corpus contract); the
    AI-analysis panel localizes at read time through market_i18n's cached
    translator. Warming HERE — in the worker, the moment the report exists —
    is what makes the panel's first read come back localized, because the
    cache's DB tier carries the translation across the worker->backend
    process boundary. Cache-only and non-blocking: localize_texts returns
    immediately and runs the model in a background thread. Fail-soft: a
    localization problem must never touch a trading cycle.
    """
    try:
        text = report.strip() if isinstance(report, str) else ""
        if not text:
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT u.lang FROM users u JOIN agents a ON a.user_id = u.id "
                "WHERE a.id = ?", (agent_id,))
            row = cursor.fetchone()
        finally:
            conn.close()
        from analysis_agents import normalize_lang
        lang = normalize_lang(row["lang"] if row else None)
        if lang == "en":
            return
        import market_i18n
        market_i18n.localize_texts([text], lang)
    except Exception:  # noqa: BLE001 — i18n warm must never break a cycle
        logger.debug("desk report i18n warm skipped for agent %s", agent_id,
                     exc_info=True)


def _conviction_divergence(confidence: Any, conviction: Any) -> dict:
    """Telemetry only: how far apart the two numbers are, and whether the
    computed one exists at all.

    Pure measurement, no behaviour. RUN_CONF_V2 exists to flip the gate onto
    conviction and stays OFF because it was measured earlier and conviction was
    better-RESOLVED but not better-CORRELATED (r~0 for both) — so the right
    next step is a count, not a flag flip. `conviction_missing` is its own
    field because compute_conviction returns None whenever any one of the four
    component scores is absent, which silently falls sizing back to the
    quantized scalar with nothing recording that it happened (prod run 825
    cycle 11 was the first observed).
    """
    out: dict[str, Any] = {"conviction_missing": conviction is None}
    try:
        if conviction is not None and confidence is not None:
            out["conf_conviction_gap"] = round(
                float(confidence) - float(conviction), 4)
    except (TypeError, ValueError):
        pass
    return out


def _order_size_usd(action: str, size_frac: float, *, max_bet_usd: float,
                    held_qty: float, entry: float, leverage: float) -> float:
    """Committed MARGIN for an order the desk sized itself.

    THE BASIS SWITCHES WITH THE INTENT. An open asks "how much risk should I
    take?" and is a fraction of max_bet_usd. A reduce asks "how much of what I
    HOLD should I give up?" — a different question in different units, and
    answering it with entry-sizing maths is why prod run 825's authored
    size_frac 0.6 sold 308.4643 of 308.4643 units: 1000 x 0.6 = $600 of budget
    bought 499 units against a 308-unit book, and min() turned a 60% trim into
    a 100% flatten.

    Returns margin, because the caller hands the gate margin x leverage as the
    notional; dividing by leverage here is what makes the round trip exact.

    A real function rather than an inline branch so the test and the shipped
    path share ONE implementation — the first version of this was tested
    against a hand-written mirror of the arithmetic, and a mutation that
    reverted production to the old basis passed the whole suite.
    """
    lev = max(1.0, float(leverage or 1.0))
    if action in ("sell", "cover") and _order_plan_enabled():
        return abs(float(held_qty or 0)) * float(entry or 0) * size_frac / lev
    return float(max_bet_usd or 0) * size_frac


def _horizon_bypass(triggers: Any) -> bool:
    """Does this cycle's situation override the desk's stated horizon?

    Only POSITION- or SYMBOL-specific triggers do. `psych_shock` and
    `hot_issue` are market-wide and stay on for long stretches — run_engine's
    own routing comment says so, and on 2026-07-30 all four live runs carried
    both simultaneously. Letting an ambient flag bypass the horizon would make
    the horizon inert on arrival, which is the failure mode this whole change
    exists to fix. Stops are unaffected either way: _evaluate_stop runs on the
    ~60s control scan, not in run_cycle, so a horizon skip never delays an exit.
    """
    try:
        return bool(set(triggers or []) - _AMBIENT_TRIGGERS)
    except TypeError:
        return True          # unreadable triggers -> do not suppress the cycle


def _horizon_state(run: dict, route: Any, has_position: bool) -> Optional[str]:
    """The reason this cycle WOULD be held by the desk's own horizon, or None.

    Computed regardless of whether the gate is armed — that is what makes the
    shadow dataset possible: with RUN_HORIZON_GATE off we still learn, on every
    cycle, which ones the horizon would have suppressed and can score them
    afterwards against what the position actually did."""
    if not has_position:
        return None
    try:
        until = json.loads(run.get("stop_conditions_json") or "{}").get(
            "horizon_until")
    except (ValueError, TypeError):
        return None
    if not until or until <= _now_iso():
        return None
    triggers = (route or {}).get("triggers") if isinstance(route, dict) else None
    if _horizon_bypass(triggers):
        return None
    return f"desk horizon holds until {until}"


def _run_archetype(run: dict) -> str:
    """'swing' | 'short' from the run's config snapshot (Plan 23 Phase A
    stamps it at compose). Fail-soft to 'short' — the pre-archetype default."""
    try:
        cfg = json.loads(run.get("config_snapshot_json") or "{}")
        return "swing" if cfg.get("archetype") == "swing" else "short"
    except (ValueError, TypeError):
        return "short"


def _horizon_skip(run: dict, route: Any, has_position: bool) -> Optional[str]:
    """Skip reason ONLY when the gate is armed. Off by default — see
    _horizon_gate_enabled for why the evidence does not yet support arming it.
    Plan 23 Phase B: armed for the SWING archetype specifically — a 1-2 day
    thesis re-litigated every cycle is the churn the swing design exists to
    remove, and the swing paper trial doubles as the shadow-vs-outcome
    measurement the global arming rule demands."""
    if not (_horizon_gate_enabled() or _run_archetype(run) == "swing"):
        return None
    return _horizon_state(run, route, has_position)


def _plan_stop_conditions(run: dict, params: Any, entry: float,
                          quantity: float, leverage: float) -> Optional[dict]:
    """Merge the desk's horizon and trail into this run's stop conditions.

    trail_arm_pct/trail_give are converted into the {activate_usd,
    giveback_frac} shape the trailing lock and validate_stop_conditions
    already speak, so nothing downstream changes: _trailing_lock_hit keeps
    reading exactly the keys it reads today. arm_pct is a percent of the
    POSITION NOTIONAL, which is what the desk is quoting a move against.
    """
    if params is None or not _order_plan_enabled():
        return None
    try:
        conditions = json.loads(run.get("stop_conditions_json") or "{}")
    except (ValueError, TypeError):
        conditions = {}
    changed = False
    hz = getattr(params, "horizon_hours", None)
    if hz:
        conditions["horizon_until"] = _iso_in(int(float(hz) * 3600))
        changed = True
    arm = getattr(params, "trail_arm_pct", None)
    give = getattr(params, "trail_give", None)
    if arm and give:
        notional = abs(float(quantity or 0)) * float(entry or 0)
        activate = notional * float(arm) / 100.0
        if activate > 0 and 0 < float(give) < 1:
            # Replace rather than merge: a half-desk/half-house trail would
            # arm on one author's number and give back on the other's.
            conditions["trail"] = {"activate_usd": round(activate, 2),
                                   "giveback_frac": float(give)}
            changed = True
    return conditions if changed else None


def _persist_order_plan(run_id: int, conditions: dict) -> None:
    """Write merged stop conditions back, through the validator.

    Through validate_stop_conditions on purpose: a key it does not whitelist
    is a silent no-op, and writing raw JSON here would let a future field look
    stored while being invisible to _evaluate_stop."""
    try:
        cleaned = trading_runs.validate_stop_conditions(conditions)
    except ValueError:
        logger.debug("order plan rejected by validator (run %s)", run_id)
        return
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        begin_write_transaction(cursor)
        cursor.execute("UPDATE trading_runs SET stop_conditions_json = ? "
                       "WHERE id = ?", (json.dumps(cleaned), run_id))
        conn.commit()
    except Exception:  # noqa: BLE001
        logger.debug("order plan persist failed (run %s)", run_id, exc_info=True)
    finally:
        conn.close()


def _add_limit_skip(run: dict, cfg: dict, action: str,
                    max_adds_override: Optional[int] = None) -> Optional[str]:
    """Add-churn guard (2026-07-25, Fleet 17 finding): a run averaging into an
    open position every cycle stacks fees for no new information (SOL: 5
    same-direction adds at conf 0.58 into a flat tape). Config-driven via
    cfg.add_limits {max_adds, cooldown_minutes} — emitted by the fleet
    composer; absent config (manual runs) disables the guard. Reduce/close
    orders are never limited. Returns a skip reason or None."""
    limits = cfg.get("add_limits") if isinstance(cfg.get("add_limits"), dict) else None
    if not limits:
        return None
    try:
        qty = _position_quantity(run["agent_id"], run["market"],
                                 run["symbol"], run["id"])
    except Exception:  # noqa: BLE001
        return None
    if not qty:
        return None
    is_futures = trading_runs.is_futures_book(run.get("market"),
                                              run.get("market_type") or "spot")
    if qty > 0 and action == "buy":
        open_side = "buy"
    elif qty < 0 and is_futures and action in ("sell", "short"):
        # "short" is the verb the caller actually sends: run_cycle remaps a
        # futures sell with no long to "short" BEFORE this gate. Matching only
        # "sell" here fell through to the reduce branch below, so no short was
        # ever add-limited (prod run 816 added to a $12.60 underwater NQ short
        # and emitted no skip at all). "sell" stays for a futures run that is
        # short and sells again without the remap.
        open_side = "short"
    else:
        return None  # reducing/closing — never limited
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT executed_at FROM signals WHERE run_id = ? AND side = ? "
            "AND executed_at IS NOT NULL ORDER BY id",
            (run["id"], open_side))
        opens = [r["executed_at"] for r in cursor.fetchall()]
    finally:
        conn.close()
    if not opens:
        return None
    # Never average into a loser (2026-07-26). Run 112 doubled a losing ETH
    # short at −$27 unrealized, and run 104 stacked five shorts on the way to
    # −$38.62: an add is a fresh bet that the thesis is working, so it must be
    # earned by the position already working. Only the sign of unrealized P&L
    # gates here — the fee hurdle on the new leg is a separate gate.
    if _adds_require_profit():
        upnl = _unrealized_pnl(run)
        if upnl is not None and upnl < 0:
            return f"add_limit: position underwater (unrealized ${upnl:.2f})"
    max_adds = int(limits.get("max_adds") or 0)
    # The desk's own max_adds, when it authored one. Shrink-only against the
    # house limit for the same reason every other order-block field is: the
    # desk may always be MORE cautious than the config, never less. 0 from the
    # desk means "no further adds", which is stricter than the house default
    # and must not be read as the config's "no limit" sentinel.
    if max_adds_override is not None and _order_plan_enabled():
        desk_cap = max(0, int(max_adds_override))
        max_adds = min(max_adds, desk_cap) if max_adds else desk_cap
        if desk_cap == 0:
            return "add_limit: the desk set max_adds=0 on this position"
    adds_so_far = len(opens) - 1  # first open is the entry, not an add
    if max_adds and adds_so_far >= max_adds:
        return f"add_limit: max {max_adds} adds reached on the open position"
    cooldown = float(limits.get("cooldown_minutes") or 0)
    if cooldown and _age_seconds(opens[-1]) < cooldown * 60:
        return f"add_limit: cooldown {cooldown:.0f}m since the last add"
    return None


def _decision_routing_enabled() -> bool:
    """E1-A kill switch (default off): route each fleet cycle by situation —
    full analyst pipeline on the tails, light path in the middle."""
    return os.getenv("DECISION_ROUTING_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on")


def _classify_situation(run: dict, cfg: dict) -> dict:
    """E1-A: deterministic, ZERO-LLM situation classifier. Any trigger routes
    this cycle to the FULL analyst pipeline (news/sentiment/psych/macro — the
    judgment layer an algorithm can't encode); quiet cycles take the light
    path. Every signal is one that already ships in prod, and every read is
    fail-soft: a broken feed silently drops that trigger — routing must never
    break a cycle. Returns {"route": "full"|"light", "triggers": [...]}."""
    # Stop-hit routing (owner 2026-08-13, "AI is main"): a noted stop/target
    # hit IS the emergency — the discussion is mandatory, no other signal
    # needs consulting.
    try:
        import stop_router
        if stop_router.enabled() and stop_router.pending(run["id"]):
            return {"route": "full", "triggers": ["stop_hit"],
                    "route_by": "rule"}
    except Exception:  # noqa: BLE001
        pass
    triggers: list[str] = []
    try:
        from market_events import active_event_window
        if active_event_window():
            triggers.append("event_window")
    except Exception:  # noqa: BLE001
        pass
    if (run.get("market") or "") == "crypto":
        # liquidation-shock proxy is OKX crypto data — meaningless elsewhere
        try:
            from psych_feed import get_psych_payload
            psych = get_psych_payload()
            if psych.get("available") and psych.get("shock"):
                triggers.append("psych_shock")
        except Exception:  # noqa: BLE001
            pass
    try:
        from regime import current_regime_state
        state = current_regime_state()
        if state and state.get("regime") in ("event", "panic", "euphoria"):
            triggers.append(f"regime:{state['regime']}")
    except Exception:  # noqa: BLE001
        pass
    try:
        conditions = json.loads(run.get("stop_conditions_json") or "{}")
        max_loss = conditions.get("max_loss_usd")
        if max_loss:
            pnl = compute_run_pnl(run)
            pos = pnl.get("position")
            if pos and float(pos.get("quantity") or 0) != 0 and \
                    float(pnl.get("total") or 0) <= -0.5 * float(max_loss):
                triggers.append("near_stop")
    except Exception:  # noqa: BLE001
        pass
    try:
        # E2 escalation: the hot-issue daemon flagged this symbol recently —
        # the per-user final verification IS this cycle running full.
        from hot_issue_daemon import recent_hot_issue
        if recent_hot_issue(run.get("market") or "", run.get("symbol") or ""):
            triggers.append("hot_issue")
    except Exception:  # noqa: BLE001
        pass
    deterministic = "full" if triggers else "light"
    if not triggers or not _ai_routing_enabled():
        return {"route": deterministic, "triggers": triggers}
    # PRIMARY RULE applied to routing (2026-07-27). `full if triggers else
    # light` treats every trigger as decisive, and two of them — psych_shock
    # and hot_issue — are MARKET-WIDE flags that stay on for long stretches.
    # Result in prod: 85% of cycles took the expensive path against a 15-20%
    # design target, so the routing saving was not merely reduced, it was
    # inverted. Which combination of signals genuinely warrants the desk is
    # exactly the judgement no threshold table can hold, so the desk decides.
    verdict = _ai_route_verdict(run, cfg, triggers)
    if verdict is None:
        return {"route": deterministic, "triggers": triggers, "route_by": "rule"}
    route, why = verdict
    return {"route": route, "triggers": triggers, "route_by": "ai",
            "route_why": why, "rule_route": deterministic}


def _ai_routing_enabled() -> bool:
    """Let the desk decide whether a triggered cycle is really critical.
    false restores `any trigger => full`."""
    return os.getenv("RUN_AI_ROUTING", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _ai_route_verdict(run: dict, cfg: dict,
                      triggers: list) -> "tuple[str, str] | None":
    """One cheap call: are these signals critical FOR THIS RUN, or ambient?

    Returns (route, why) or None to fall back to the deterministic answer —
    routing must never break a cycle, and an unreachable model must not strand
    a run. Deliberately tiny: this exists to avoid six expensive calls, so it
    must not become a seventh."""
    try:
        from llm_client import generate_text, llm_configured
        if not llm_configured():
            return None
        pos_note = "flat"
        try:
            pnl = compute_run_pnl(run)
            pos = pnl.get("position")
            if pos and float(pos.get("quantity") or 0) != 0:
                pos_note = f"open, P&L ${float(pnl.get('total') or 0):+.2f}"
        except Exception:  # noqa: BLE001
            pass
        prompt = (
            "Route ONE trading cycle. The full desk costs six model calls; the "
            "light path costs one. Spend the desk only where judgement can "
            "change the outcome.\n"
            f"Symbol: {run.get('symbol')} ({run.get('market')})\n"
            f"Position: {pos_note}\n"
            f"Signals firing: {', '.join(str(t) for t in triggers)}\n"
            "Note: psych_shock and hot_issue are MARKET-WIDE flags that can "
            "stay on for hours — on their own, with a flat book and nothing "
            "specific to this symbol, they are ambient noise, not an event. "
            "near_stop and event_window are specific and usually do warrant "
            "the desk.\n"
            'Respond ONLY with JSON: {"route":"full"|"light","why":"<8 words>"}'
        )
        text = generate_text(prompt, max_tokens=60, temperature=0.0,
                             tier="decision")
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        obj = json.loads(match.group(0))
        route = str(obj.get("route") or "").strip().lower()
        if route not in ("full", "light"):
            return None
        return route, str(obj.get("why") or "")[:120]
    except Exception:  # noqa: BLE001 — routing is never allowed to break a cycle
        return None


def _llm_stamp() -> dict:
    """Which model authored this decision. Without it, a provider-vs-provider
    profit comparison (owner A/B, 2026-08-08: Claude vs local) can only be
    attributed by wall-clock windows — which breaks the moment a setting is
    flipped mid-window. Resolved under the run's active LLM context, the same
    resolution the decision's own generate_text used moments earlier."""
    try:
        from llm_client import resolve_provider
        ap = resolve_provider("decision")
        if ap:
            return {"provider": ap.spec.name, "model": ap.model,
                    "source": ap.source}
    except Exception:  # noqa: BLE001 — telemetry must never break a cycle
        pass
    return {}


# Plan 15 P2: the scalar confidence proved quantized (0.62 pin), so the
# desk also scores four components and CODE computes the conviction the
# gate can eventually trust. Weights are deterministic and documented in
# docs/plan/15-run-ai-reading-algorithm-fix.html §5-A.
CONVICTION_WEIGHTS = {
    "thesis_alignment": 0.35,
    "momentum_quality": 0.25,
    "entry_quality": 0.25,
    "risk_context": 0.15,
}


def compute_conviction(scores: Optional[dict]) -> Optional[float]:
    """Weighted blend of the component scores, or None when the model did
    not produce a complete, valid score set (shadow logging must stay honest
    about absence — never fabricate a midpoint)."""
    if not isinstance(scores, dict):
        return None
    total = 0.0
    for key, weight in CONVICTION_WEIGHTS.items():
        try:
            v = float(scores[key])
        except (KeyError, TypeError, ValueError):
            return None
        if not (0.0 <= v <= 1.0):
            return None
        total += weight * v
    return round(total, 4)


def _conviction_size_scale(value: Optional[float], leverage: float = 1.0) -> Optional[float]:
    """Plan 15 rec-2: bet-size scale from conviction (or the scalar when no
    scores exist). Linear 0.45→0.75 mapped to 0.40→1.00, clamped — strictly
    shrink-only so it can never lever up. None disables scaling (no signal,
    or the kill-switch is off)."""
    if os.getenv("RUN_SIZE_BY_CONVICTION", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    base = max(0.40, min(1.0, (v - 0.45) / 0.30))
    # #3: temper MARGINAL conviction at leverage L>1 — a wrong L× thesis burns
    # margin L× faster toward the 1/L liquidation line, so commit less unless
    # conviction is high. base→1.0 (certain) is untouched (1.0**x == 1.0); L=1
    # is byte-identical to before.
    lev = max(1.0, float(leverage or 1.0))
    if lev > 1.0 and _lev_sizing_enabled():
        base = min(1.0, max(0.30, base ** (1.0 + _lev_size_damp() * (lev - 1.0))))
    return round(base, 4)


def _conf_v2_enabled() -> bool:
    """Plan 15 P3: flip the gate from the LLM's scalar confidence to the
    computed conviction. Default OFF — enable only after the shadow period
    shows conviction correlates with outcomes better than the scalar."""
    return os.getenv("RUN_CONF_V2", "false").strip().lower() in {"1", "true", "yes", "on"}


def _closing_soon_minutes() -> int:
    """How close to the session close counts as "act now or carry the gap".
    One cycle interval plus slack — the desk must be warned while it still has
    a cycle left to act in, not on the cycle that finds the market already
    shut."""
    try:
        return max(0, int(os.getenv("RUN_CLOSING_SOON_MINUTES", "45")))
    except ValueError:
        return 45


def _desk_exit_awareness() -> bool:
    """Whether the desk is shown its open position's trajectory and told that
    banking is an action. Default ON — the entry-only prompt is what let three
    prod runs round-trip their peaks. Kill switch matches the other behavioural
    rails here (_adds_require_profit, _liq_cushion_enabled)."""
    return (os.getenv("RUN_DESK_EXIT_AWARENESS", "true") or "true"
            ).strip().lower() in ("1", "true", "yes", "on")


# A brief whose invalidation the tape has already passed is worse than no brief:
# the desk re-reads it every cycle and is asked to resist it. Prod 2026-08-03 —
# run 938 carried "a break above 152.00" for a SHORT at 156.7 and went 7 cycles
# without a position, treating the level as stale on cycle 5, half-doing so on
# cycle 6, and fully regressing on cycle 7. Runs 933 and 934 died the same way.
# `level-integrity` tells the desk to judge on structure instead; this makes
# that the only option by not showing it the number.
_STALE_INVALIDATION = ("(stale — the level in this brief sits where the tape has "
                       "already passed; derive your own from the structure you "
                       "can see)")


def _thesis_freshness_line(thesis: dict) -> str:
    """One prompt line telling the desk how old its frozen brief is.

    Plan 21 P2 (brief integrity, from the hermes work-package's data-freshness
    contract): the run's thesis is frozen at build, and the desk had no way to
    see whether the level it was handed was written an hour or a week ago —
    the :496026 incident class. Renders nothing when the snapshot carries no
    `as_of` (manual runs, pre-P2 fleets); a malformed timestamp also renders
    nothing rather than a wrong number.
    """
    as_of = str(thesis.get("as_of") or "") if isinstance(thesis, dict) else ""
    if not as_of:
        return ""
    try:
        written = datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - written).total_seconds() / 3600.0
    except Exception:  # noqa: BLE001 — a bad stamp must never break a cycle
        return ""
    if age_h < 0:
        return ""
    if age_h < 6:
        label = "fresh"
    elif age_h <= 24:
        label = "aging — verify its levels against the current price"
    else:
        label = ("STALE — written well before current conditions; prefer the "
                 "structure you can see over its levels")
    return f"Thesis brief age: {age_h:.1f}h ({label}).\n"


def _usable_thesis(thesis: dict, entry: Optional[float]) -> dict:
    """The stored thesis with an already-passed invalidation level removed.

    Returns the thesis unchanged when there is nothing to judge (no price, no
    direction, no level, or a relative level carrying no number). Never mutates
    the caller's dict — the stored brief stays as written.
    """
    if not isinstance(thesis, dict) or not thesis or not entry:
        return thesis
    level = str(thesis.get("invalidation") or "")
    direction = str(thesis.get("direction") or "").strip().lower()
    if not level or direction not in ("long", "short"):
        return thesis
    try:
        import symbol_research
        if symbol_research.invalidation_is_coherent(level, direction, float(entry)):
            return thesis
    except Exception:  # noqa: BLE001 - a scrub must never break a cycle
        return thesis
    return {**thesis, "invalidation": _STALE_INVALIDATION}


# A print inside this many calendar days is close enough to shape THIS
# cycle's decision; further out it is noise on a 4h-168h horizon.
EARNINGS_BRIEF_DAYS = 5


def _earnings_state_line(run: dict) -> str:
    """A scheduled earnings print is a session gap with a date on it.

    The session-close brief below warns a desk it is about to lose the
    ability to act for hours; a print does the same for the minutes that
    matter most, and us-stock desks (939 TSLA / 940 NVDA) held positions
    with no knowledge of it. Shown flat AND holding — entering fresh
    exposure into a print is the same unpriced gap as carrying one through
    it. Fail-soft: no feed key, no date, or a far date all render as "".
    """
    if (run.get("market") or "") != "us-stock":
        return ""
    try:
        import fmp_feed
        days = fmp_feed.days_to_earnings(run.get("symbol") or "")
    except Exception:  # noqa: BLE001 — a feed problem must never block a cycle
        return ""
    if days is None or days > EARNINGS_BRIEF_DAYS:
        return ""
    when = "TODAY" if days == 0 else f"in {days} calendar day(s)"
    return (f"{run.get('symbol')} reports earnings {when}. A print is a gap "
            "you cannot act through: decide EXPLICITLY whether any position "
            "should carry through it, and treat fresh exposure opened this "
            "close to the print as a bet on the print itself.\n")


HOLD_STREAK_BRIEF_MIN = 4

# A held book emits an equity heartbeat every few minutes, so 6 identical
# reads is minutes of a motionless tape — well past ordinary quiet, and far
# short of the 36 straight reads GC and SI produced on 2026-08-06.
MARK_FROZEN_BRIEF_MIN = 6
MARK_FROZEN_BRIEF_SCAN = 60


def _hold_streak_line(run: dict, pos_qty: float) -> str:
    """The desk's own flat streak, as a fact it cannot otherwise perceive.

    reentry-discipline's flat-retirement clause asks the desk to weigh
    retiring after "several consecutive cycles below actionable conviction"
    — but each cycle's prompt shows only that cycle, so the desk cannot
    count its own streak (949: NINE consecutive flat holds at conviction
    0.24–0.30, clause in context, retire verb untouched — the lesson had
    no data to fire on). Fact only; the judgment lives in the skill.
    Flat books only, and fail-soft: any lookup problem renders "".
    """
    if pos_qty:
        return ""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT payload FROM run_events WHERE run_id = ? AND "
                "event_type = 'decision' ORDER BY seq DESC LIMIT 12",
                (run["id"],))
            rows = cursor.fetchall()
        finally:
            conn.close()
        streak = 0
        for row in rows:
            try:
                action = json.loads(row["payload"]).get("action")
            except (ValueError, TypeError):
                break
            if action != "hold":
                break
            streak += 1
        if streak < HOLD_STREAK_BRIEF_MIN:
            return ""
        return (f"Streak: you have been flat with no action for {streak} "
                "consecutive cycles.\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _mark_freshness_line(run: dict, pos_qty: float) -> str:
    """How many straight reads returned the SAME price — the one thing a
    fresh timestamp cannot tell the desk.

    WHY (2026-08-06, cycle 82). `mark_age_ok` checks `price_updated_at`, not
    whether the value moved. A feed that keeps answering with a stale quote
    refreshes that timestamp every ~90s and is invisible to every staleness
    check in the engine. Measured live: GC printed 4320.700195 for 2h26m and
    SI 62.099998 for 2h05m — three SI fills at the identical price — while
    BTCUSDT moved normally and Alpha Vantage sat fully rate-limited at 25
    requests/day. The desk was reading a frozen tape and could not tell.

    Fact only; the judgment lives in the skill. Deliberately NOT a gate: a
    value-staleness rail HALTS TRADING when it fires and quiet markets are
    real, so this hands the desk the observable and lets it be the actor.

    Counts trailing `equity` events whose `unrealized` is unchanged. That is
    conservative in the right direction: `unrealized = (mark - avg) * qty`,
    so an add or a reduce moves it even under a frozen mark and RESETS the
    count — this can under-report a freeze, never invent one. Held books
    only (a flat book's unrealized is a constant 0 and would read as frozen
    forever), and fail-soft.
    """
    if not pos_qty:
        return ""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ts, payload FROM run_events WHERE run_id = ? AND "
                "event_type = 'equity' ORDER BY seq DESC LIMIT ?",
                (run["id"], MARK_FROZEN_BRIEF_SCAN))
            rows = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        seen: Optional[float] = None
        reads = 0
        oldest = None
        for row in rows:
            try:
                u = float(json.loads(row["payload"]).get("unrealized"))
            except (ValueError, TypeError):
                break
            if seen is None:
                seen = u
            elif u != seen:
                break
            reads += 1
            oldest = row.get("ts")
        if reads < MARK_FROZEN_BRIEF_MIN:
            return ""
        span = ""
        try:
            mins = _age_seconds(str(oldest)) / 60.0
            if mins >= 1:
                span = f" (~{mins:.0f} minutes)"
        except Exception:  # noqa: BLE001
            span = ""
        return (f"Mark check: this symbol has returned the SAME price for "
                f"{reads} straight reads{span}.\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _stop_hit_line(run: dict) -> str:
    """The emergency brief for a routed stop hit (owner 2026-08-13: the
    sooppiy AI is the MAIN author of stop exits; the watcher is only the
    fail-safe). Renders only while a hit is pending for this run."""
    try:
        import stop_router
        hit = stop_router.pending(run["id"]) if stop_router.enabled() else None
        if not hit:
            return ""
        return (f"STOP HIT: your {hit['trigger']} level traded at "
                f"{hit['price']}. This cycle IS the decision the watcher "
                "would otherwise make for you — choose: close (bank the "
                "protection), reduce (cut, keep a re-entry), or hold ONLY "
                "with a re-authored stop_pct that reflects why this level "
                "no longer binds. If you do not decide, the fail-safe "
                "closes the whole book.\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _ordinary_day_line(run: dict) -> str:
    """The symbol's ordinary daily move, stated WHEN the bracket is asked
    for — not only after the position is already drifting.

    WHY (2026-08-13, session 1 of the day block — main handoff §8(a)'s
    prescribed fix, trigger met at n=2): SLV's authored stop sat at 0.84%
    against a 1.52% ordinary day (0.55 days) and UBER's at 0.94% against
    1.90% (0.50 days); both were collected by routine range within the
    hour (−1.82, −3.53), executed by the SL/TP watcher as full closes.
    The desk authors stop_pct on every cycle but only ever saw the
    ordinary-day scale via _exit_size_line — which renders AFTER adverse
    drift, long past authoring. Fact plus one unit lesson, fail-soft."""
    try:
        t = _typical_daily_move_pct(run)
        if not t:
            return ""
        return (f"Scale: an ordinary day on this symbol moves ±{t:.2f}% "
                "(median daily). A stop inside a small fraction of one "
                "ordinary day sits in routine noise and gets collected — "
                "size stops in ordinary-day units.\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


BIG_TRADER_MAX_AGE_H = 48.0


def _big_trader_line(run: dict) -> str:
    """Latest recorded big-trader tape for a us-stock symbol — FINRA daily
    short-volume ratio, front-expiry put/call OI, StockTwits tilt.

    WHY (owner 2026-08-13: "must follow big trader — it's key"). Plan 23
    Phase D records these 6-hourly into us_stock_factor_snapshots and
    NOTHING showed them to the desk — the one signal the owner names as the
    key was record-only (0 references in the decision layer, verified by
    grep on 2026-08-13). Facts only, null-honest: a field the feed could
    not see is omitted, never guessed. The judgment lives in the
    follow-the-flow skill, which teaches level reads for exactly the fields
    rendered here — teach nothing this line does not show. us-stock only;
    48h age cap (FINRA publishes T+1 and weekends gap); fail-soft.
    """
    if (run.get("market") or "") != "us-stock":
        return ""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT putcall_oi_ratio, short_volume_ratio, "
                "stocktwits_tilt, tilt_n, created_at "
                "FROM us_stock_factor_snapshots WHERE symbol = ? "
                "ORDER BY id DESC LIMIT 1",
                (str(run.get("symbol") or "").upper(),))
            row = cursor.fetchone()
        finally:
            conn.close()
        if not row:
            return ""
        age_h = _age_seconds(str(row["created_at"])) / 3600.0
        if age_h > BIG_TRADER_MAX_AGE_H:
            return ""
        bits: list[str] = []
        if row["short_volume_ratio"] is not None:
            bits.append(f"FINRA short-volume ratio "
                        f"{float(row['short_volume_ratio']):.2f} "
                        f"(share of the day's volume sold short)")
        if row["putcall_oi_ratio"] is not None:
            bits.append(f"put/call OI {float(row['putcall_oi_ratio']):.2f}")
        if row["stocktwits_tilt"] is not None:
            n = int(row["tilt_n"] or 0)
            bits.append(f"StockTwits tilt {float(row['stocktwits_tilt']):+.2f}"
                        + (f" (n={n})" if n else ""))
        if not bits:
            return ""
        return (f"Big-trader tape ({age_h:.0f}h old): "
                + "; ".join(bits) + ".\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _standing_arm_line(run: dict, pos_qty: float) -> str:
    """The arm the desk already has standing — which it could not see.

    WHY (2026-08-06, cycle 82). `_store_armed_order` is called ONLY when
    `intent == "arm"` (see its call site), so a cycle that reduces or holds
    leaves the previous arm in force. The arm skill told the desk "each
    cycle's arm replaces the last", which is true only of ARMING cycles —
    the desk was being asked to restate something it was never shown and
    whose lifetime it was told wrongly. Run 968 armed `close 1.0` at 09:27,
    reduced at 10:12 without restating, and the full-book arm stood on.

    Fact only. Held books only, fail-soft.
    """
    if not pos_qty:
        return ""
    try:
        blob = json.loads(run.get("armed_order_json") or "null") or {}
        arm = blob.get("arm") or {}
        cond, level = arm.get("if"), arm.get("level")
        verb, frac = arm.get("then"), arm.get("size_frac")
        if not cond or level is None or not verb:
            return ""
        try:
            age = f", set {_age_seconds(str(blob.get('armed_at'))) / 60.0:.0f} minutes ago"
        except Exception:  # noqa: BLE001
            age = ""
        try:
            size = f" {float(frac):.0%} of the book"
        except (TypeError, ValueError):
            size = ""
        return (f"Standing arm: {cond} {level} then {verb}{size}{age}. It "
                "stays in force until you arm a different one.\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _typical_daily_move_pct(run: dict) -> Optional[float]:
    """This symbol's ORDINARY day, as a percentage. Median absolute
    close-to-close change over the recent daily bars.

    Median, not mean: one event day must not redefine "ordinary". Returns
    None when the history is too short to say, because a fabricated noise
    floor is worse than none — the caller renders nothing.
    """
    try:
        import price_fetcher
        candles = price_fetcher.get_daily_candles(
            run["symbol"], run["market"], days=30) or []
        closes = [float(c["close"]) for c in candles[-21:] if c.get("close")]
        if len(closes) < 6:
            # Loud on purpose (2026-08-06, run 976): the GC daily fetch
            # failed at build time and this returned None SILENTLY, so the
            # brief's ordinary-day context vanished with no trace to find.
            logger.info("typical-daily-move unavailable for %s/%s (%d bars) "
                        "— ordinary-day context absent from this brief",
                        run.get("symbol"), run.get("market"), len(closes))
            return None
        moves = [abs(b - a) / a * 100.0
                 for a, b in zip(closes, closes[1:]) if a]
        if len(moves) < 5:
            return None
        moves.sort()
        mid = len(moves) // 2
        return (moves[mid] if len(moves) % 2
                else (moves[mid - 1] + moves[mid]) / 2.0)
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return None


def _exit_size_line(run: dict, pos_qty: float) -> str:
    """Scale the adverse move the desk is reacting to, and name the verb.

    Measured over 2026-08-04/05 (84 closes): losing TRIMS cost -1.53 on
    average and are harmless; losing FULL closes cost -6.68 and carry 91%
    of all loss. Every one of the six catastrophic losses dumped 100% of
    the book on a 0.49-1.74% move, and 37 of 38 losing closes were taken on
    a move under 1% — at a MEDIAN of 28% of the desk's own authored stop.
    Only 1 of 38 ever reached that stop.

    The desk was never told how big the move it is reacting to actually is
    relative to an ordinary day, nor that "reduce" is available instead of
    "close" — every existing exit lesson says what NOT to do without
    supplying either number or an alternative verb. This supplies both.
    Fact and verb only; the judgment lives in exit-discipline. Held books
    only, fail-soft to "".
    """
    if not pos_qty:
        return ""
    try:
        pnl = compute_run_pnl(run) or {}
        if not pnl.get("mark_age_ok"):
            return ""
        pos = pnl.get("position") or {}
        ent = float(pos.get("entry_price") or 0)
        mark = float(pos.get("current_price") or 0)
        if ent <= 0 or mark <= 0:
            return ""
        move = (mark - ent) / ent * 100.0
        if pos_qty < 0:                       # a short profits as price falls
            move = -move
        if move >= 0:
            return ""                         # this line is about adverse drift
        adverse = abs(move)
        bits = [f"Exit scale: the move against you is {adverse:.2f}%."]
        day = _typical_daily_move_pct(run)
        if day and day > 0:
            bits.append(f"An ordinary day on this symbol moves {day:.2f}%, "
                        f"so this is {adverse / day * 100:.0f}% of one "
                        f"ordinary day.")
        bits.append(
            "If you act, choose the VERB deliberately: 'reduce' with a "
            "size_frac sheds part of the book and keeps the thesis alive; "
            "'close' ends it entirely. Closing the WHOLE position is the "
            "expensive verb and it is only warranted when the thesis is "
            "actually dead — say why in the intent's 'why' field when you "
            "use it.")
        return " ".join(bits) + "\n"
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _brake_distance_line(run: dict, pos_qty: float) -> str:
    """How far the equity brake is, expressed as a price move.

    The desk authors its stop in PRICE PERCENT on the position. The platform
    retires the run on EQUITY drawdown from the high-water mark in USD
    (run_feedback's drawdown_brake, at retire_drawdown_frac x max_loss_usd).
    Nothing reconciled the two, so the rail that actually ends the run was
    invisible to the desk that gets ended by it.

    Prod 971 (2026-08-05): authored a 3.5% stop while its brake sat 0.72%
    away — 4.9x tighter — and was retired on a -0.62% move it had explicitly
    budgeted for. An audit of 21 runs found the brake inside the desk's own
    stop in SEVEN of them; 960 was carrying a 2.9x gap live at the time.
    The gap widens with every add, because the rail is a fixed dollar amount
    while an add only grows the notional it is divided by.

    Fact only; the judgment lives in risk-reward-structure. Held books only,
    and fail-soft: any missing or untrustworthy input renders "".
    """
    if not pos_qty:
        return ""
    try:
        stops = json.loads(run.get("stop_conditions_json") or "{}")
        max_loss = float(stops.get("max_loss_usd") or 0)
        if max_loss <= 0:
            return ""            # no P&L stop at all — nothing to report
        pnl = compute_run_pnl(run) or {}
        # An unknown mark must never be rendered as a confident distance:
        # the same reasoning as _position_state_line's P&L suppression.
        if not pnl.get("mark_age_ok"):
            return ""
        mark = float((pnl.get("position") or {}).get("current_price") or 0)
        notional = abs(float(pos_qty)) * mark
        if mark <= 0 or notional <= 0:
            return ""
        total = float(pnl.get("total") or 0)
        import run_feedback           # local: matches the cycle path's import
        state = run_feedback.load_state(run)
        peak = max(float(state.get("peak_total_pnl") or 0), total)
        # Read the fraction from the rail itself so this line can never drift
        # out of sync with the brake it describes.
        frac = float(run_feedback.ADAPT_BOUNDS["retire_drawdown_frac"])
        room = frac * max_loss - (peak - total)
        if room <= 0:
            return ("Risk rail: this run is already at or past the equity "
                    "drawdown that retires it — the next cycle may close the "
                    "book regardless of your stop.\n")
        pct = room / notional * 100.0
        return (f"Risk rail: this run is RETIRED when equity falls a further "
                f"${room:,.2f} from its high-water mark. At your current "
                f"position size that is a {pct:.2f}% adverse price move. "
                f"This rail is separate from the stop you author and can be "
                f"much tighter than it; adding to the position divides this "
                f"distance.\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _stop_coherence_enabled() -> bool:
    """R10 kill switch (default on) for the entry rail line and the size
    clamp together — the lesson and its enforcement ship as one unit."""
    return (os.getenv("RUN_STOP_COHERENCE", "true") or "true"
            ).strip().lower() in ("1", "true", "yes", "on")


def _brake_room_usd(run: dict) -> Optional[float]:
    """USD of further equity loss this run can take before the platform's
    loss rail acts: the binding rail's cap minus the drawdown already
    spent from the high-water mark.

    WHICH rail binds depends on the run (R10 adversarial pass): the
    drawdown brake at retire_drawdown_frac × max_loss exists only for
    feedback-enabled runs (run_feedback.apply_policy is gated on
    cfg.feedback — fleet runs); a manual run carrying max_loss_usd is
    ended by stop_event:max_loss at the FULL cap. Using the brake frac
    for a manual run over-shrank its size ~30% against a rail that never
    fires for it.

    Same formula as _brake_distance_line renders for feedback-enabled
    held books (a test pins the two together); factored here because the
    R10 entry line and the size clamp both need the number for a book
    that does not exist yet. None when the run has no max_loss stop, the
    mark on a HELD book is stale (an unknown room must never clamp or
    render), or anything is unreadable."""
    try:
        stops = json.loads(run.get("stop_conditions_json") or "{}")
        max_loss = float(stops.get("max_loss_usd") or 0)
        if max_loss <= 0:
            return None
        pnl = compute_run_pnl(run) or {}
        pos = pnl.get("position") or {}
        if float(pos.get("quantity") or 0) and not pnl.get("mark_age_ok"):
            return None
        total = float(pnl.get("total") or 0)
        import run_feedback           # local: matches the cycle path's import
        state = run_feedback.load_state(run)
        peak = max(float(state.get("peak_total_pnl") or 0), total)
        try:
            cfg = json.loads(run.get("config_snapshot_json") or "{}")
        except (ValueError, TypeError):
            cfg = {}
        frac = (float(run_feedback.ADAPT_BOUNDS["retire_drawdown_frac"])
                if run_feedback.feedback_enabled(cfg) else 1.0)
        return frac * max_loss - (peak - total)
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return None


def _entry_rail_line(run: dict, pos_qty: float) -> str:
    """The rail arithmetic for a position that does NOT exist yet.

    _brake_distance_line (#244) reconciles the desk's price-percent stop
    with the platform's USD equity rail — but only for a held book, and
    every large entry loss of 2026-08-13 happened while this brief was
    silent: SPCX sized $3,317 whose 6.4% stop meant $212 against a $44
    budget (the brake fired on a −1.07% wiggle 26 minutes in), GC went
    full size under a 1.31% stop worth $27.5 against a ~$13 floor. n=3,
    −$118 in one day, and in every case the platform acted before the
    authored stop COULD — a stop needing more room than the rail has is
    not a stop, it is fiction.

    Fact + the one line of arithmetic that makes size answerable at entry
    time; the apply-path clamp enforces the same identity shrink-only for
    the desks that ignore it. Flat books only; fail-soft."""
    if pos_qty or not _stop_coherence_enabled():
        return ""
    room = _brake_room_usd(run)
    if room is None:
        return ""
    if room <= 0:
        return ("Sizing rail: this run has NO remaining loss budget — the "
                "equity brake is at or past its trigger, so any new "
                "position may be retired regardless of your stop.\n")
    return (f"Sizing rail for a NEW entry: the platform's loss rail ends "
            f"this book ${room:,.2f} below its high-water mark. Your stop "
            f"is only real if notional × stop% fits inside ${room:,.2f} — "
            f"e.g. a 1% stop supports at most ${room / 0.01:,.0f} of "
            f"notional. Size to your stop, or the platform exits before "
            f"your stop can (2026-08-13: three entries sized past this "
            f"rail lost $118 and no authored stop ever acted).\n")


def _last_cycle_word_line(run: dict) -> str:
    """The desk's OWN last-cycle verdict, quoted back to it.

    2026-08-13, run 1157 (QNT): cycle 2 wrote "Long thesis is already
    invalidated because price is below today's open — no entry", and
    cycle 3 bought 29 minutes later on the same tape; run 1169 (INTC)
    entered after twice writing down why the bracket did not work. −$47
    across three runs whose losing entries contradicted the desk's own
    words from the cycle before. Nothing in the prompt showed the desk
    what it had just said, so each cycle re-derived the world from
    scratch and the sharpest fact it owned — its own standing
    invalidation — was the one thing it could not see.

    Quote, verbatim and labelled as the desk's own; the rule stated is
    the R11 lesson. Renders flat or held. Fail-soft.

    Two shapes the adversarial pass reproduced, both guarded here: an
    ERRORED cycle still emits a decision event with empty action/report,
    and a LIMIT-1 read of that row would erase the standing invalidation
    exactly one failed cycle after it was written — so scan back past
    empty rows. And words can be days old across a weekend or a pause;
    quoting them undated as "last cycle" lends them false freshness — so
    the line carries the age of the words and lets the desk weigh it."""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT ts, payload FROM run_events
                   WHERE run_id = ? AND event_type = 'decision'
                   ORDER BY id DESC LIMIT 5""", (run["id"],))
            rows = cursor.fetchall()
        finally:
            conn.close()
        action = report = ts = ""
        for row in rows or []:
            payload = json.loads(row["payload"] or "{}")
            action = str(payload.get("action") or "").strip()
            report = " ".join(str(payload.get("report") or "").split())
            if action and report:
                ts = str(row["ts"] or "")
                break
        if not action or not report:
            return ""
        age = ""
        try:
            mins = _age_seconds(ts) / 60.0
            if mins >= 1:
                age = (f", {mins:.0f} min ago" if mins < 120 else
                       f", {mins / 60:.0f} h ago" if mins < 2880 else
                       f", {mins / 1440:.0f} days ago")
        except Exception:  # noqa: BLE001 — an unreadable ts drops the age only
            age = ""
        if len(report) > 400:
            report = report[:400].rsplit(" ", 1)[0] + "…"
        return (f"Your own last cycle (action: {action}{age}): \"{report}\"\n"
                "An invalidation you stated stands until you explicitly "
                "overturn it with NEW evidence in this cycle's report — "
                "entering against your own standing invalidation is the "
                "measured failure (2026-08-13: QNT bought 29 minutes after "
                "writing 'thesis already invalidated'; −$47 across three "
                "such entries).\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


_PREDECESSOR_LOOKBACK_HOURS = 72


def _predecessor_run_line(run: dict) -> str:
    """R16: what happened the LAST time this agent ran this symbol.

    2026-08-14: fleet 32 retired its NQ long at 09:47Z citing "no safe
    bracket", rebuilt NQ four hours later, and the successor desk
    re-longed at a HIGHER price with zero reference to the predecessor —
    −$2.42 then −$2.15 the same day. _last_cycle_word_line (R11) carries
    a run's OWN memory; nothing carried memory ACROSS runs, so every
    rebuild re-derived the symbol from scratch and repeated the entry
    its predecessor had just proven wrong. desk_retired symbols carry no
    cooldown (only adapt-retires do) — by design, since tape genuinely
    changes; the fix is memory, not a ban.

    Fact only — predecessor's ending, P&L, and age; re-underwriting is
    the desk's call. Recent window only (a week-old run is stale tape).
    Fail-soft."""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, status_reason, realized_pnl_usd, stopped_at
                   FROM trading_runs
                   WHERE agent_id = ? AND market = ? AND symbol = ?
                     AND id <> ? AND stopped_at IS NOT NULL
                   ORDER BY id DESC LIMIT 1""",
                (run["agent_id"], run["market"], run["symbol"], run["id"]))
            row = cursor.fetchone()
        finally:
            conn.close()
        if not row:
            return ""
        age_s = _age_seconds(str(row["stopped_at"] or ""))
        if age_s > _PREDECESSOR_LOOKBACK_HOURS * 3600:
            return ""
        pnl = float(row["realized_pnl_usd"] or 0)
        reason = str(row["status_reason"] or "").strip() or "stopped"
        hours = age_s / 3600.0
        age = (f"{age_s / 60:.0f} min ago" if hours < 2
               else f"{hours:.0f} h ago")
        return (f"This agent's PREVIOUS run on {run['symbol']} ended {age}: "
                f"{reason}, realized ${pnl:,.2f}. A fresh run is not fresh "
                f"tape — re-underwrite against what just happened here, and "
                f"say in your report what has CHANGED since that ending "
                f"(2026-08-14: NQ was retired for 'no safe bracket', rebuilt "
                f"4h later, re-longed higher with no reference to it, and "
                f"lost again — −$4.57 across the pair).\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _breadth_state_line(run: dict) -> str:
    """US market breadth as market-environment evidence (advisory).

    The catalogue already teaches distribution counting and follow-through
    confirmation (market-topping-evidence / bottom-confirmation), but the
    desk's prompt carried no market-wide data to apply them to — every
    us-stock desk read only its own symbol's candles. This supplies the
    missing evidence from the public tradermonty breadth CSV. Advisory
    only: it informs exposure posture, never a per-symbol signal, and a
    feed problem renders "".
    """
    if (run.get("market") or "") != "us-stock":
        return ""
    try:
        import breadth_feed
        b = breadth_feed.latest_breadth()
    except Exception:  # noqa: BLE001 — a feed problem must never block a cycle
        return ""
    if not b:
        return ""
    trend = {1: "rising", -1: "falling"}.get(b.get("trend200"))
    line = (f"US market breadth (advisory, S&P 500, data to {b['date']}): "
            f"{b['above_ma200']:.0%} of stocks above their 200-day MA "
            f"(8-day avg {b['above_ma200_8ema']:.0%}"
            + (f", long-term breadth trend {trend}" if trend else "")
            + f"); {b['above_ma50']:.0%} above their 50-day MA.")
    if b.get("pink_zone"):
        line += (" Structural bearish zone: the long-term breadth trend is "
                 "falling AND short-term breadth sits below it.")
    if b.get("bearish"):
        line += " The dataset's backtested bearish breadth signal is ACTIVE."
    line += (" Weigh this as market-environment evidence for exposure "
             "posture, not as a signal about this symbol.")
    return line + "\n"



def _us_psych_line(run: dict) -> str:
    """US market-level crowd psychology as regime evidence (advisory).

    Plan 25 Phase B (owner directive 2026-08-14): the Phase-A skill
    us-crowd-psychology-lens teaches the judgment, but until this line
    existed no us-stock desk read a market-level crowd gauge — CNN's
    fear&greed had been fetched-but-never-wired since Plan 14. Facts only;
    the skill owns the interpretation. A feed problem renders "".
    """
    if (run.get("market") or "") != "us-stock":
        return ""
    try:
        import psych_feed
        fg = psych_feed.us_fear_greed()
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""
    if not fg or fg.get("value") is None:
        return ""
    prev = fg.get("prev_1w")
    if fg.get("source") == "vix":
        line = (f"US crowd psychology (advisory, VIX volatility gauge): "
                f"VIX {fg['value']:.1f}")
        if prev is not None:
            line += f", {fg['value'] - prev:+.1f} vs a week ago"
        line += (". Above roughly 30 signals fear/panic, below roughly 15 "
                 "complacency-greed; extremes are contrarian regimes.")
    else:
        line = (f"US crowd psychology (advisory, CNN Fear & Greed): "
                f"{fg['value']:.0f}/100"
                + (f" ({fg['classification']})" if fg.get("classification")
                   else ""))
        if prev is not None:
            line += f", {fg['value'] - prev:+.0f} vs a week ago"
        line += (". Extremes (roughly 20 and below, or 80 and above) are "
                 "contrarian regimes; mid-range confirms momentum.")
    line += (" Regime evidence only — crowd psychology is never the sole "
             "reason for an order.")
    return line + "\n"


def _fx_risk_line(run: dict) -> str:
    """Global risk appetite for the forex desk (advisory).

    Plan 25 Phase B: forex desks read no psychology at all — pairs have no
    crowd of their own here, so the read is global risk appetite (equity
    fear&greed + the broad dollar's direction). Facts only; the Phase-A
    skill fx-risk-sentiment-lens owns the judgment. Renders "" when
    nothing is available — an unknown regime is stated by absence, never
    guessed.
    """
    if (run.get("market") or "") != "forex":
        return ""
    fg = dxy = None
    try:
        import psych_feed
        fg = psych_feed.us_fear_greed()
    except Exception:  # noqa: BLE001
        fg = None
    try:
        import cross_market
        dxy = cross_market.dollar_index_cached()
    except Exception:  # noqa: BLE001
        dxy = None
    if not (fg and fg.get("value") is not None) and not dxy:
        return ""
    parts = []
    if fg and fg.get("value") is not None:
        if fg.get("source") == "vix":
            parts.append(f"US equity volatility VIX {fg['value']:.1f}"
                         + (f" ({fg['value'] - fg['prev_1w']:+.1f} w/w)"
                            if fg.get("prev_1w") is not None else ""))
        else:
            parts.append(f"US equity Fear & Greed {fg['value']:.0f}/100"
                         + (f" ({fg['classification']})"
                            if fg.get("classification") else ""))
    if dxy and dxy.get("value") is not None:
        d = f"broad dollar index {dxy['value']:.1f}"
        if dxy.get("change_1d_pct") is not None:
            d += f" ({dxy['change_1d_pct']:+.2f}% 1d)"
        parts.append(d)
    line = ("FX risk sentiment (advisory): " + "; ".join(parts)
            + ". Risk-off bids JPY/CHF/USD and pressures high-beta FX; "
              "risk-on is the mirror. Regime evidence only — one signal "
              "alone is no trade.")
    return line + "\n"

LOSS_FLOOR_USD = 0.99
LOSS_FLOOR_FRAC = 0.006   # of run budget — what $0.99 WAS at the $1000 seed


def _loss_floor_usd(run: "dict | None" = None) -> float:
    """The owner's house floor for a losing run (2026-08-06): below this, the
    run is a candidate to be closed and its slot returned for a fresh thesis.

    Budget-proportional since 2026-08-13 (owner: "do", after the two-subagent
    pass): the dollar constant is the owner's verbatim rule at the $1000-seed
    scale, where 6 slots ≈ $166 made $0.99 ≈ 0.6% of a slot. On today's
    $1,580 slots the same dollar figure is 0.06% — fee noise — and desks
    spent 2026-08-13 dutifully closing fee-scale "wounds" on big books while
    their authored 3–5% stops never got to act. floor = max(USD floor,
    FRAC × run budget): same rule, scale-aware threshold. Runs without a
    budget (older rows, tests) keep the plain dollar floor."""
    try:
        base = abs(float(os.getenv("RUN_LOSS_FLOOR_USD", str(LOSS_FLOOR_USD))))
    except (TypeError, ValueError):
        base = LOSS_FLOOR_USD
    try:
        frac = float(os.getenv("RUN_LOSS_FLOOR_FRAC", str(LOSS_FLOOR_FRAC)))
        budget = float((run or {}).get("run_budget_usd") or 0)
        return max(base, frac * budget)
    except (TypeError, ValueError):
        return base


def _loss_verdict_line(run: dict, pnl: dict) -> str:
    """The owner's house rule on a losing run, handed to the desk with the
    arithmetic that decides whether it is a real loss or a tick.

    OWNER RULE (2026-08-06): *"if got more -0.99 then clean that RUN, and make
    RUN again by AI Analysis ... It's make decision by sooppiy AI."* The
    decision is the desk's — this line supplies the rule and the two numbers
    that make it answerable.

    ⚠️ WHY THE RAW DOLLAR FIGURE CANNOT STAND ALONE, measured before writing
    this. On the live book, −$0.99 is **3.7% of one ordinary day** for GC and
    **0.23x its own round-trip cost** — closing there spends $4.26 in fees to
    avoid a $0.99 loss, and three runs today (971, 967, 955) were already
    below the floor from their ENTRY FEE alone, before any price moved. A bare
    threshold would retire runs on noise and pay a round trip each time; the
    fleet would churn itself flat. So the line always states the loss in the
    two units that separate a tick from a wound:

      * as a share of ONE ORDINARY DAY for this symbol, and
      * as a multiple of THIS position's own round-trip cost.

    When the loss has not yet cleared the round trip, the line says so
    plainly — closing costs more than it saves, and that is a fact the desk
    should have before it acts, not a veto on acting.

    Fact + the owner's rule; the verb is the desk's. Fail-soft.
    """
    try:
        total = float(pnl.get("total") or 0)
        floor = _loss_floor_usd(run)
        if total >= -floor:
            return ""
        pos = pnl.get("position") or {}
        qty = abs(float(pos.get("quantity") or 0))
        mark = float(pos.get("current_price") or 0)
        bits = [f"House floor: this run is at ${total:,.2f}, past the "
                f"${-floor:,.2f} floor."]
        if qty > 0 and mark > 0:
            notional = qty * mark
            rt = notional * float(os.getenv("BREAKEVEN_FEE_RATE", "0.001")) * 2.0
            od_pct = _typical_daily_move_pct(run)
            if od_pct:
                od_usd = notional * od_pct / 100.0
                if od_usd > 0:
                    bits.append(f"That is {abs(total) / od_usd:.0%} of one "
                                f"ordinary day for this symbol")
            if rt > 0:
                mult = abs(total) / rt
                bits.append(f"and {mult:.2f}x your own round-trip cost of "
                            f"${rt:,.2f}")
                if mult < 1.0:
                    bits.append("— closing here spends more than the loss it "
                                "avoids, so it is a tick, not a wound.")
                else:
                    bits.append("— this loss has cleared the cost of leaving, "
                                "so it is real.")
        bits.append("The house rule is to CLOSE a run that is genuinely past "
                    "the floor and hand its slot back for a fresh thesis, "
                    "unless you can name the specific condition that reverses "
                    "it before your next look.")
        return " ".join(bits) + "\n"
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


# ── retrieval from the desk corpus (#280) ─────────────────────────────────
# Owner, 2026-08-07: "from tomorrow sooppiy and this session must be ref RAG".
# Until now the corpus only ACCUMULATED — the desk filled it and never read it.
_RECALL_MAX = 2
_RECALL_CHARS = 700


def _recall_enabled() -> bool:
    return os.environ.get("DESK_RECALL_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off")


def _recall_query(run: dict, pnl: dict, pos_qty: float) -> str:
    """What this cycle is actually about, in the corpus's own vocabulary.

    Built from the run's SITUATION rather than its symbol: the lesson that
    helps a position giving back its peak is the same lesson whether the
    symbol is ZC or ETHUSDT, and keying on the symbol would return a handful
    of notes about that ticker and miss every one of them."""
    parts: list[str] = [str(run.get("market") or "")]
    if not pos_qty:
        parts.append("flat considering entry fee hurdle expected move")
        return " ".join(p for p in parts if p)
    try:
        upnl = float(pnl.get("unrealized") or 0)
        peak = float(run.get("peak_pnl_usd") or 0)
    except (TypeError, ValueError):
        upnl = peak = 0.0
    parts.append("holding position")
    if peak > 0 and upnl < peak:
        parts.append("gave back peak give-back bank the gain arm the level")
    if upnl < 0:
        parts.append("losing position stop distance cut or hold reduce")
    else:
        parts.append("winning position trailing take partial profit")
    return " ".join(p for p in parts if p)


def _recall_line(run: dict, pnl: dict, pos_qty: float) -> str:
    """What the desk has already learned about a cycle like this one.

    Fact only, and clearly labelled as PAST material so it is never mistaken
    for live tape. Fail-soft and hard-capped: the corpus must be able to be
    empty, slow or wrong without costing a cycle."""
    if not _recall_enabled():
        return ""
    try:
        import desk_memory
        query = _recall_query(run, pnl, pos_qty)
        explore = (_recall_explore_enabled()
                   and _recall_explore_allowed(pnl, pos_qty))
        hits = desk_memory.search(query,
                                  kind="monitoring",
                                  market=str(run.get("market") or "") or None,
                                  limit=(_RECALL_EXPLORE_POOL if explore
                                         else _RECALL_MAX))
        # Same reasoning as the capture guard below: a selector that raises
        # must fall back to the incumbent ranking, never to no recall at all.
        try:
            hits, meta = _recall_select(hits, explore)
        except Exception:  # noqa: BLE001
            hits = list(hits or [])[:_RECALL_MAX]
            meta = {"scheme": _RECALL_SCHEME_FIXED, "explore": False,
                    "propensity": 1.0}
        # Guarded HERE as well as inside the capture: a journal that raises
        # would otherwise fall to the outer handler and silently strip the
        # desk's recall — a degradation, not the no-op fail-soft demands.
        try:
            _recall_capture(run.get("id"), query, hits, meta)
        except Exception:  # noqa: BLE001
            pass
        if not hits:
            return ""
        out = ["What this desk has already learned about cycles like this "
               "(past findings, NOT live tape):"]
        for h in hits:
            body = " ".join(str(h.get("body") or "").split())
            if len(body) > _RECALL_CHARS:
                body = body[:_RECALL_CHARS].rsplit(" ", 1)[0] + "…"
            out.append(f"- {body}")
        return "\n".join(out) + "\n"
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


# ── Phase 3(a): journal WHAT recall injected (plan 22 §5, §7) ─────────────
# Retrieval weights can only be learned from VARIANCE in what was retrieved,
# and until now nothing recorded which chunks a decision actually saw: the
# corpus knew what it held, the journal knew what was decided, and no row
# joined the two. This captures the chunk identities the brief carried so the
# attribution dataset (increment b) has a left side to join outcomes onto.
# Journal-only — no prompt, gate, size or order reads any of it.
_RECALL_JOURNAL: dict[int, dict] = {}


def _recall_reset(run_id) -> None:
    """Forget any earlier capture for this run, before the brief is built.

    Load-bearing: `_recall_line` runs only when a run is HOLDING, so without
    this a flat cycle would emit the previous cycle's chunks as its own — the
    exact mislabelling that would teach the weights the wrong lesson."""
    try:
        _RECALL_JOURNAL.pop(int(run_id), None)
    except (TypeError, ValueError):
        pass


def _recall_capture(run_id, query: str, hits: list,
                    meta: "dict | None" = None) -> None:
    """Record the retrieval this cycle performed.

    Empty hits are recorded as an EMPTY list, never as absence: a decision
    that recalled nothing is the control group the attribution needs, and it
    has to be distinguishable from a cycle where recall never ran."""
    try:
        rid = int(run_id or 0)
        if not rid:
            return
        _RECALL_JOURNAL[rid] = {
            "query": (query or "")[:300],
            "chunks": [{"sha": h.get("sha"), "kind": h.get("kind"),
                        "source": h.get("source"), "score": h.get("score")}
                       for h in (hits or [])],
            **(meta or {}),
        }
    except Exception:  # noqa: BLE001 — telemetry must never cost a cycle
        pass


# ── Phase 3(a2): ε-exploration with LOGGED PROPENSITIES (plan 22 §3, §10) ──
# Measured on prod 2026-08-10: 262 `recall` events over 14 (market ×
# situation) cells, and EVERY cell returned exactly ONE chunk-pair. With no
# within-class variance "chunk c is harmful" and "this situation loses" are
# the same number, so no per-chunk effect is identifiable — and waiting for
# volume cannot fix that, only a counterfactual can.
#
# Scheme `eps-head-fixed-v1`: the rank-1 chunk is never displaced; with
# probability EPS the SECOND slot is drawn uniformly from the above-floor
# candidates ranked below the incumbent pair. Three consequences, all
# deliberate:
#   - min propensity is EPS/|alternates| ≈ 0.08 on the measured pools. IPS
#     estimators blow up on small propensities, so the design is few arms and
#     a fat epsilon, never a long tail of rarely-drawn options.
#   - the head is common to every arm, so it is NOT scoreable under v1. That
#     is the price of bounding exploration to one slot, and it is exactly why
#     the scheme VERSION is journaled: a later v2 that also drops the head
#     would be a different dataset, not more of this one.
#   - the floor is a FRACTION OF THE HEAD, not an absolute score. Measured,
#     the 'winning' class heads at 15.0 while the 'gave-back' class's eighth
#     chunk still scores 17.2 — one absolute number would mean two different
#     things in two situations.
_RECALL_SCHEME_FIXED = "deterministic-top2"
_RECALL_SCHEME_EPS = "eps-head-fixed-v1"
_RECALL_EXPLORE_POOL = 5
_RECALL_EXPLORE_FLOOR = 0.60
_RECALL_EXPLORE_EPS = 0.25


def _recall_explore_enabled() -> bool:
    return os.environ.get("DESK_RECALL_EXPLORE", "0").strip().lower() in (
        "1", "true", "yes", "on")


def _recall_explore_allowed(pnl: dict, pos_qty: float) -> bool:
    """Losing positions keep the incumbent ranking until the first promotion
    gate passes. Exploration swaps the advice a run reads while it is losing,
    and the mandate's asymmetry — never loosen an unproven thing on the losing
    side — applies to advice as much as it does to rails."""
    if not pos_qty:
        return True
    try:
        return float(pnl.get("unrealized") or 0) >= 0
    except (TypeError, ValueError):
        return False


def _recall_select(hits: list, explore: bool) -> "tuple[list, dict]":
    """Choose what the brief carries, and record the probability of the choice.

    The propensity is journaled ALWAYS, including when exploration is off: a
    row logged under the deterministic policy carries propensity 1.0, and
    pooling it with epsilon-scheme rows unlabelled would silently corrupt
    every off-policy estimate increment (c) computes."""
    head = list(hits or [])[:_RECALL_MAX]
    if not explore:
        return head, {"scheme": _RECALL_SCHEME_FIXED, "explore": False,
                      "propensity": 1.0}
    meta = {"scheme": _RECALL_SCHEME_EPS, "explore": False,
            "eps": _RECALL_EXPLORE_EPS, "pool": 0, "propensity": 1.0}
    if not head:
        return head, meta
    floor = float(head[0].get("score") or 0) * _RECALL_EXPLORE_FLOOR
    alts = [h for h in list(hits)[_RECALL_MAX:]
            if float(h.get("score") or 0) >= floor]
    meta["pool"] = len(alts)
    if not alts:
        return head, meta
    if random.random() < _RECALL_EXPLORE_EPS:
        meta["explore"] = True
        meta["propensity"] = round(_RECALL_EXPLORE_EPS / len(alts), 6)
        return [head[0], random.choice(alts)], meta
    meta["propensity"] = round(1.0 - _RECALL_EXPLORE_EPS, 6)
    return head, meta


def _take_recall_journal(run_id):
    """Pop this run's capture. Popping rather than reading is deliberate: a
    cycle that recalled but never reached a decision must not have its chunks
    attributed to the NEXT decision."""
    try:
        return _RECALL_JOURNAL.pop(int(run_id or 0), None)
    except (TypeError, ValueError):
        return None


def _excursion_scale_line(run: dict, pnl: dict, peak: "float | None") -> str:
    """The desk's own excursion, expressed in the unit it must ARM in.

    WHY (2026-08-07). Peak is reported to the desk in DOLLARS — "$0.10" — but
    an arm is a PRICE LEVEL, so choosing one requires knowing how far the price
    has actually travelled in percent. That conversion was never given, and the
    desk cannot do it reliably without the notional in front of it.

    Measured on the live book this cycle, arm distance against the largest move
    each tape had made:

        983 ETHUSDT  arm 0.74%  vs peak excursion 0.055%   13.4x
        984 HG       arm 2.60%  vs peak excursion 0.208%   12.5x
        982 BTCUSDT  arm 0.46%  vs peak excursion 0.205%    2.2x
        981 SI       arm 0.50%  vs peak excursion 0.297%    1.7x

    Every standing arm sat beyond anything its own tape had done, two of them
    by more than twelvefold — which is the mechanism behind the long-running
    "60+ arms authored, only two ever fired". It is a missing unit conversion,
    not a failure of judgment: a desk told "peak $0.10" and asked for a price
    has no way to know 0.10 was two tenths of one percent.

    Fact only — whether to move the arm is the desk's call and lives in the
    skills. Fail-soft: anything unreadable renders "".
    """
    try:
        best = float(peak or 0)
        if best <= 0:
            return ""
        pos = pnl.get("position") or {}
        entry = float(pos.get("entry_price") or 0)
        mark = float(pos.get("current_price") or 0) or entry
        qty = abs(float(pos.get("quantity") or 0))
        notional = qty * entry
        if notional <= 0 or mark <= 0:
            return ""
        peak_pct = best / notional * 100.0
        if peak_pct <= 0:
            return ""
        head = (f"Scale check: the furthest this has travelled in your favour "
                f"is {peak_pct:.2f}% of price (peak ${best:,.2f} on a "
                f"${notional:,.2f} position).")
        try:
            armed = json.loads(run.get("armed_order_json") or "{}") or {}
            level = float(((armed.get("arm") or {}).get("level")))
        except (TypeError, ValueError):
            level = 0.0
        if level > 0:
            away = abs(level - mark) / mark * 100.0
            ratio = away / peak_pct
            return (f"{head} Your standing arm sits {away:.2f}% away — "
                    f"{ratio:.1f}x that.\n")
        return f"{head} No level is armed.\n"
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _floor_status_line(run: dict, pnl: dict, peak: "float | None") -> str:
    """Whether the platform's automatic profit floor is even SWITCHED ON.

    WHY (2026-08-06, the 24-hour sweep). The breakeven floor arms only once a
    run's peak clears its own round-trip cost. Across the 22 runs that closed
    in that window the split was **13 of 13**: every one of the ten losers had
    a peak BELOW its arm threshold — the floor could never have armed for any
    of them — and all three winners were above it.

    The threshold scales with book size, so **the protection arms last exactly
    where it would save most.** Run 971 is the case that makes it concrete: a
    15.81-unit ZEC book needed a peak of **$16.36**, reached **$16.15**, and
    went on to lose **−$58.18**. It missed its own protection by 1.3% and
    nothing automatic could stop what followed.

    The desk sees its peak already; it has never been told where protection
    begins, so it cannot know it is uncovered. Fact only — the judgment
    (bank it, or arm a level) lives in the skills, and both verbs already
    exist. Fail-soft: anything unreadable renders "".
    """
    try:
        arm = _breakeven_arm_usd(pnl, _run_max_abs_qty(run))
        if arm <= 0:
            return ""
        best = float(peak or 0)
        if best >= arm:
            return (f"Automatic floor: ARMED (peak ${best:,.2f} cleared its "
                    f"${arm:,.2f} round-trip cost) — a give-back to breakeven "
                    "exits you without a decision.\n")
        return (f"Automatic floor: NOT ARMED — it switches on at a peak of "
                f"${arm:,.2f} and your best is ${best:,.2f}. Until then "
                "nothing exits this position automatically on a give-back.\n")
    except Exception:  # noqa: BLE001 — a brief must never block a cycle
        return ""


def _fresh_armed_order(run_id: int) -> Optional[dict]:
    """The CURRENT armed order, read fresh — the cycle's run dict is a
    snapshot, so an arm stored earlier in this same cycle is invisible in
    it. The contradiction rail must treat a just-placed arm as a standing
    plan, not silence."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT armed_order_json FROM trading_runs "
                       "WHERE id = ?", (run_id,))
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        blob = json.loads(row["armed_order_json"] or "null")
    except (ValueError, TypeError):
        return None
    return blob or None


_OPENING_WINDOW_MIN = 30


def _opening_window_line(run: dict) -> str:
    """Tells the desk it is inside the first minutes after the session open
    — the day's highest-volume, highest-range window (owner 2026-08-12:
    "most people try to buy and sell when the US market opens — we must
    catch that time"). WHERE the session stands is platform context; what
    to do with the window stays the desk's judgement. Pure clock
    arithmetic on the same calendar the scheduler uses: open now, but not
    open _OPENING_WINDOW_MIN ago ⇒ inside the window. A 24×7 market is
    open at both stamps and never renders it."""
    try:
        import markets as _mkts
        market = run.get("market")
        if not _mkts.is_market_open(market):
            return ""
        if _mkts.is_market_open(
                market, _now_dt() - timedelta(minutes=_OPENING_WINDOW_MIN)):
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return ("The session OPENED within the last 30 minutes — the day's "
            "highest-volume, highest-range window. Opening drives, gap "
            "continuations and gap fades resolve here, at the day's best "
            "liquidity; a plan acted on now beats the same plan 30 minutes "
            "late.\n")


_YOUNG_EXIT_CYCLES = 3


def _young_exit_brief(run: dict, cfg: dict, pos_qty: float) -> str:
    """A young position moving against you INSIDE its ordinary daily range
    is noise, not thesis evidence — and a full-book dump there is this
    book's single largest measured loss mechanism.

    Live 2026-08-13 (run 1104, KAITO): short at 0.44731, fully covered 30
    minutes later on a −0.9% wiggle for −$10.14 — the dump decision carried
    confidence 0.80 against conviction 0.30 — and the tape then fell BELOW
    the original entry: the thesis was right, the panic paid. Same class as
    the #245 finding (full-book dumps on sub-2% moves carry most loss).

    No rail: exits are never refused or shrunk (the asymmetry). This is the
    owner's decisions-become-skills path — the desk gets the situation and
    the mandate, and the verb stays its own. Renders ONLY when the position
    is young (< _YOUNG_EXIT_CYCLES decision intervals), losing, and the
    adverse move is smaller than the symbol's ordinary day. Fail-soft."""
    if not pos_qty:
        return ""
    try:
        pnl = compute_run_pnl(run) or {}
        pos = pnl.get("position") or {}
        entry = float(pos.get("entry_price") or 0)
        mark = float(pos.get("current_price") or 0)
        if entry <= 0 or mark <= 0 or not pnl.get("mark_age_ok"):
            return ""
        got = (mark - entry) / entry * 100.0
        if pos_qty < 0:
            got = -got
        if got >= 0:
            return ""                    # in profit — banking is not dumping
        ordinary = _typical_daily_move_pct(run)
        if not ordinary or abs(got) >= float(ordinary):
            return ""                    # a real move — the desk judges freely
        interval_min = max(5, int(cfg.get("interval_minutes") or 60))
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(first_opened_at, opened_at) AS o "
                "FROM positions WHERE run_id = ? AND quantity != 0 LIMIT 1",
                (run["id"],))
            row = cursor.fetchone()
        finally:
            conn.close()
        if not row or not row["o"]:
            return ""
        opened = datetime.strptime(str(row["o"])[:19],
                                   "%Y-%m-%dT%H:%M:%S").replace(
                                       tzinfo=timezone.utc)
        age_min = (_now_dt() - opened).total_seconds() / 60.0
        if age_min >= _YOUNG_EXIT_CYCLES * interval_min:
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return (f"Young-position check: this position is ~{age_min:.0f} minutes "
            f"old and the move against you ({got:+.2f}%) is INSIDE this "
            f"symbol's ordinary daily range (~{float(ordinary):.2f}%) — "
            "noise-sized, not evidence against the thesis. A full exit here "
            "realizes fees on a wiggle; the book's largest measured losses "
            "are exactly such dumps, made minutes before the tape went the "
            "thesis's way. If you still exit, your report MUST state why a "
            "FULL close beats a HALF reduce; and if your component scores "
            "disagree with your stated confidence, trust the scores.\n")


def _contradiction_line(run: dict, pos_qty: float) -> str:
    """Plan 24 fix 1 prompt line: a held position may not silently ignore
    the desk's own reading. Rendered from the adapt-state streak the full
    path maintains (run_feedback.note_contradiction); "" while flat, absent
    or at streak 0."""
    if not pos_qty:
        return ""
    try:
        state = json.loads(run.get("adapt_state_json") or "{}")
        streak = int(state.get("contradiction_streak") or 0)
    except (ValueError, TypeError):
        streak = 0
    if streak < 1:
        return ""
    side = "long" if pos_qty > 0 else "short"
    line = (f"Your own reading (technical + news together) has OPPOSED this "
            f"{side} for {streak} consecutive cycle(s).")
    if streak >= 2:
        line += (" A silent hold is not an available action: either reduce, "
                 "or explicitly re-underwrite the thesis with fresh evidence "
                 "in your report. At 3 straight cycles the platform reduces "
                 "half of this position itself.")
    return line + "\n"


def _position_state_line(run: dict, cfg: dict, pos_qty: float,
                         thesis: dict) -> str:
    """The open position's own trajectory, for the desk's exit decision.

    The four component scores are entry-framed, so nothing in the prompt told
    the desk whether the trade it is already in has worked, peaked, or is
    unwinding. This supplies exactly that: open P&L, the run's high-water
    mark and how much of it survives, and how much of the move the thesis was
    written for has actually arrived.

    Returns "" only when flat or switched off. An untrustworthy mark drops the
    NUMBERS but keeps the verb: an unknown P&L must never be rendered as a
    confident $0.00 (that reads as "breakeven, nothing to bank", the opposite
    of the truth), yet a desk holding a position can still validly close it.
    """
    if not pos_qty:
        return ""
    bits: list[str] = []
    pnl: dict = {}
    try:
        pnl = compute_run_pnl(run) or {}
    except Exception:  # noqa: BLE001
        pnl = {}
    # The exit brief and the margin brief are separate concerns behind separate
    # flags: switching off exit awareness must not also blind the desk to its
    # own liquidation distance.
    if not _desk_exit_awareness():
        return _margin_state_line(run, pnl, pos_qty)
    if pnl.get("mark_age_ok"):
        pos = pnl.get("position") or {}
        try:
            upnl = float(pnl.get("unrealized") or 0)
        except (TypeError, ValueError):
            upnl = None
        if upnl is not None:
            bits.append(f"Open P&L on this position: ${upnl:,.2f}.")
            try:
                peak = float(run.get("peak_pnl_usd"))
            except (TypeError, ValueError):
                peak = None
            if peak and peak > 0:
                bits.append(f"Best this run has reached: ${peak:,.2f} — you "
                            f"are holding {max(0.0, upnl) / peak:.0%} of that "
                            f"high-water mark.")
            bits.append(_floor_status_line(run, pnl, peak))
            bits.append(_excursion_scale_line(run, pnl, peak))
            bits.append(_loss_verdict_line(run, pnl))
            bits.append(_recall_line(run, pnl, pos_qty))
            try:
                want = abs(float(thesis.get("expected_move_pct")))
                ent = float(pos.get("entry_price") or 0)
                mark = float(pos.get("current_price") or 0)
                if want > 0 and ent > 0 and mark > 0:
                    got = (mark - ent) / ent * 100.0
                    if pos_qty < 0:              # a short profits as price falls
                        got = -got
                    bits.append(f"Thesis expected a {want:.2f}% move; "
                                f"{got:+.2f}% has arrived ({got / want:.0%} "
                                f"of it).")
            except (TypeError, ValueError, ZeroDivisionError):
                pass
    # Session close (2026-07-29). A gain the desk cannot act on is a gain it
    # carries through the gap. Prod run 818 held +$30.99 across the CME close
    # with every rail out of reach (brake −$27.15, trail arming at $89.02
    # against a $35.16 peak), so the only actor that could have banked it was
    # the desk — and nothing told it the window was shutting. The pre-gate
    # already refuses to trade a closed market; this is the warning BEFORE
    # that, while acting is still possible.
    try:
        import markets
        left = markets.session_minutes_left(run.get("market"))
        if 0 < left <= _closing_soon_minutes():
            # Plan 23 Phase B: for the SWING archetype the overnight hold is
            # the DESIGN, not a hazard — the intraday warning would order the
            # desk to undo its own strategy at every close.
            if _run_archetype(run) == "swing":
                bits.append(
                    f"This market closes in about {left} minute(s). Holding "
                    f"through the close is this run's DESIGN — a swing thesis "
                    f"is paid over days, not sessions. Use this window only "
                    f"if the thesis is broken or the position exceeds your "
                    f"overnight gap-risk budget; otherwise carrying it is the "
                    f"plan, not a failure to act.")
            else:
                bits.append(
                    f"This market closes in about {left} minute(s) and you cannot "
                    f"act again until it reopens. If you would not want to carry "
                    f"this position through the gap unattended, close or reduce it "
                    f"NOW — after the close the choice is no longer yours.")
    except Exception:  # noqa: BLE001 — a missing calendar must not block the desk
        pass
    # The verb, stated once, for whichever path is asking. Those four component
    # scores are ALL entry-framed — entry_quality literally asks how good this
    # price is as an ENTRY — so without this the deliberation collapses to
    # add / don't-add. Prod: runs 776, 811 and 816 round-tripped peaks of
    # $78.58, $33.44 and $75.29 to roughly zero while emitting `hold` or `buy`,
    # with `sell`/`cover` available on every one of those cycles; 811's own
    # reports read "...rather than adding". The rails cannot cover it either —
    # every one is indexed to max_loss, so a run whose peak never clears
    # 0.70x max_loss has no profit exit at all.
    if _run_archetype(run) == "swing":
        # Plan 23 Phase B: the intraday banking pressure ("this cycle") is
        # exactly the churn a 1-2 day thesis must not inherit — but banking
        # itself stays first-class per the mandate: a completed move is
        # never allowed to round-trip.
        bits.append(
            "You are a SWING desk: this thesis is paid over days, and the "
            "first red or green hours are noise, not a verdict. Index "
            "banking to the thesis — if MOST of the expected move has "
            "arrived, or open P&L is giving back its high-water mark after "
            "the move largely completed, reduce or close: a completed move "
            "is never allowed to round-trip. Short of that, re-deciding the "
            "position every cycle is churn, not diligence.")
    else:
        bits.append(
            "Banking is a first-class action, not merely the absence of an add. "
            "If the move your thesis was paid for has largely happened, or open "
            "P&L is rolling over from its high-water mark, then reducing or "
            "closing is the correct answer THIS cycle even while the thesis still "
            "technically holds — a thesis that is still valid is not a reason to "
            "keep giving back a gain.")
    return " ".join(bits) + "\n" + _margin_state_line(run, pnl, pos_qty)


def _margin_state_line(run: dict, pnl: dict, pos_qty: float) -> str:
    """Plan 16 survival brief, appended to whatever the exit brief already says.

    Deliberately hung off _position_state_line rather than written into each
    prompt: BOTH decision paths already route through this one function
    (_light_analysis at the cheap tier, run_analysis(position_state=...) at the
    full tier), and PR #125 had to retrofit exactly that after #124 shipped the
    light path alone. One insertion point, both paths, no second retrofit.

    Every prompt the desk sees today contains no leverage, no liquidation price
    and no margin — so it cannot reason about survival because it does not know
    it is leveraged. Every open position in prod carries 2x-3x.
    """
    try:
        import liquidation
    except Exception:  # noqa: BLE001 — a brief must never break a decision
        return ""
    if not liquidation.oracle_enabled() or not liquidation.desk_brief_enabled():
        return ""
    pos = (pnl or {}).get("position") or {}
    try:
        lev = float(pos.get("leverage") or 1.0)
    except (TypeError, ValueError):
        lev = 1.0
    if lev <= 1.0:
        return ""          # a fully-funded long cannot be wiped; say nothing
    try:
        state = liquidation.margin_state(
            {**pos,
             "id": f"run:{run.get('id')}",
             "run_id": run.get("id"),
             "symbol": run.get("symbol"),
             "market": run.get("market"),
             "quantity": pos.get("quantity", pos_qty)},
            cushion_frac=_liq_cushion_frac())
        # A run with no max_loss_usd has no P&L stop at all: prod runs 821-825
        # shipped with stop_conditions_json == {} on 2x-3x leverage, so the
        # desk's own exit is the only bound that exists. It should be told.
        conditions = json.loads(run.get("stop_conditions_json") or "{}")
        return liquidation.survival_brief(
            state, has_run_stop=conditions.get("max_loss_usd") is not None)
    except Exception:  # noqa: BLE001
        return ""


def _light_analysis(run: dict, cfg: dict) -> dict:
    """One decision-tier LLM call (agent_planner-style) replacing ONLY the
    analysis stage of run_cycle. Pre-gates, evaluate_execution_gates, the
    run-budget cap and the trade fence are byte-identical to the full path.
    Returns the same {decision: {action, confidence, entry}} shape."""
    import price_fetcher

    entry = None
    try:
        entry = price_fetcher.get_price_from_market(
            run["symbol"], _now_iso(), run["market"])
    except Exception:  # noqa: BLE001
        entry = None
    if entry is None:
        return {"decision": {}, "analysts": {}, "error": "no price"}

    thesis = (cfg.get("thesis") or {}) if isinstance(cfg.get("thesis"), dict) else {}
    thesis = _usable_thesis(thesis, entry)
    candles_summary = None
    try:
        candles = price_fetcher.get_daily_candles(run["symbol"], run["market"], days=30)
        if candles:
            closes = [c["close"] for c in candles[-10:]]
            candles_summary = {"last10_closes": [round(float(c), 6) for c in closes]}
    except Exception:  # noqa: BLE001
        pass

    # Plan 15 P1 (F1/F4): the naked "confidence: 0.0-1.0" ask produced a
    # quantized output pinned at 0.62 (53% of observed decisions), and the
    # desk had no idea what it held — spot runs emitted unactionable sells.
    # Give it the book and a calibration rubric.
    pos_qty = 0.0
    try:
        pos_qty = _position_quantity(run["agent_id"], run["market"],
                                     run["symbol"], run["id"])
    except Exception:  # noqa: BLE001
        pos_qty = 0.0
    market_type = (run.get("market_type") or "spot").strip().lower()
    if trading_runs.is_futures_book(run.get("market"), market_type):
        # A futures book can be LONG, and this branch used to be one
        # state-blind sentence describing short mechanics only — so a
        # profitable futures long was never told that 'sell' would bank it,
        # while "'buy' covers a short" actively primed the wrong picture.
        # Prod run 776 (ZC, long 14.02, peak +$78.58) emitted `buy` for 43
        # straight cycles and reported "I cover the existing short and go
        # long" while holding that long; it gave back 94% of the peak with
        # the desk unable to reach "reduce this long" at all. Short and flat
        # keep the original wording — only the long case was unreachable.
        if pos_qty > 0:
            inventory_rule = ("Futures book, currently LONG: 'sell' "
                              "reduces/closes this long; 'buy' adds to it.")
        else:
            inventory_rule = ("Futures book: 'sell' opens or extends a short; "
                              "'buy' covers a short or goes long.")
    elif pos_qty > 0:
        inventory_rule = "'sell' reduces/closes this long; 'buy' adds to it."
    else:
        inventory_rule = ("Spot book with no inventory: 'sell' is NOT available "
                          "(nothing to reduce) — a bearish read means 'hold'.")
    can_sell = bool(trading_runs.is_futures_book(run.get("market"), market_type)
                    or pos_qty > 0)
    position_state = (_position_state_line(run, cfg, pos_qty, thesis)
                      + _stop_hit_line(run)
                      + _opening_window_line(run)
                      + _young_exit_brief(run, cfg, pos_qty)
                      + _contradiction_line(run, pos_qty)
                      + _last_cycle_word_line(run)
                      + _predecessor_run_line(run)
                      + _earnings_state_line(run)
                      + _breadth_state_line(run)
                      + _us_psych_line(run)
                      + _fx_risk_line(run)
                      + _hold_streak_line(run, pos_qty)
                      + _brake_distance_line(run, pos_qty)
                      + _entry_rail_line(run, pos_qty)
                      + _exit_size_line(run, pos_qty)
                      + _mark_freshness_line(run, pos_qty)
                      + _big_trader_line(run)
                      + _ordinary_day_line(run)
                      + _standing_arm_line(run, pos_qty))
    # Trading skills (Plan 20): house decision methods scoped to the light
    # site. Fail-soft — a skills-registry problem must never break a cycle.
    try:
        from trading_skills import skills_block
        skills_text = skills_block("light", market=run.get("market"))
    except Exception:  # noqa: BLE001
        skills_text = ""
    prompt = (
        "You are the trading desk for one symbol. Decide THIS cycle's action.\n"
        f"Symbol: {run['symbol']} ({run['market']}, {market_type}), price now {entry}.\n"
        f"Position in this run's book: {pos_qty} units (negative = short, 0 = flat). "
        f"{inventory_rule}\n"
        f"{position_state}"
        f"{skills_text}"
        f"{_thesis_freshness_line(thesis)}"
        f"Thesis: {json.dumps(thesis, default=str)[:800]}\n"
        f"Recent closes: {json.dumps(candles_summary, default=str)[:400]}\n"
        "Calibrate confidence honestly across the full range, two decimals: "
        "0.50 = coin-flip, 0.55 = slight edge, 0.65 = clear thesis+momentum+entry "
        "alignment, 0.75 = strong multi-factor confirmation, 0.85+ = exceptional "
        "setup. Do not default to a habitual value; if your report states a "
        "percentage it MUST equal this number.\n"
        "Also score four components, each 0.00-1.00: thesis_alignment (does "
        "price action still support the thesis?), momentum_quality (strength "
        "and cleanliness of the current move), entry_quality (how good is THIS "
        "price as an entry vs the reference?), risk_context (headroom to "
        "invalidation; 1.0 = very safe).\n"
        # Order parameters, minimal edition (2026-07-27). Only the two fields
        # the flat 5%/10% actually overrides — a stop and a target sized to
        # THIS instrument. The full trader prompt asks for the whole block
        # (size, leverage, trail, horizon, adds); asking for all of that here
        # would defeat the point of the cheap path. Two numbers cost ~20
        # output tokens against the 200-token budget.
        "Then place THIS instrument's bracket. A 5% stop is a hair-trigger on "
        "a currency pair and unreachable on a volatile crypto name, so size "
        "both to the symbol's own recent range shown above: stop_pct = %% from "
        "entry to your invalidation level, target_pct = %% to a level the move "
        "can realistically reach. target_pct MUST be at least 2x stop_pct. If "
        "you have no concrete basis, omit them and the house defaults apply.\n"
        # 'retire' (2026-07-30): a desk whose book cannot express its read has
        # no legal action and no way to say so. Prod run 824 read the tape
        # bearish on a SPOT book, emitted three refused sells across three
        # cycles (~18 full-path LLM calls and an hour of a held slot) and was
        # collected by thesis_invalidated for a conclusion it plainly had at
        # cycle 2. Offered only when FLAT, so it can never move P&L: with a
        # position open the desk already has sell/cover.
        + ('Say "retire" instead if this book cannot express your read at all '
           '(e.g. you are bearish and can only go long) — it hands the slot '
           'back now rather than after several refused orders.\n'
           if not pos_qty else '')
        # Plan 17 (2026-07-30): the intent. The verb space cannot say "bank
        # half" — exit size was max_bet-derived and never referenced the
        # position, so the fraction reduced was a residue, not a decision.
        # size_frac's BASIS SWITCHES WITH THE INTENT, and the prompt says so
        # in the desk's own terms because that asymmetry is the entire point.
        + ('Also state your order as an intent: open|add grow exposure '
           '(size_frac = fraction of your max bet); reduce|close bank it '
           '(size_frac = fraction of WHAT YOU HOLD — 0.5 means half your '
           'position; banking is a first-class action, not the absence of an '
           'add); flip = you were wrong, reverse; hold = nothing. Or arm: act '
           'later without waiting for your next cycle, e.g. {"if":'
           '"price_above","level":27800,"then":"reduce","size_frac":0.5} — '
           'prefer arm over hold whenever you can name the level that would '
           'change your mind, because your next cycle is far away and the '
           'market is not.\n'
           if pos_qty else '')
        # A flat spot book cannot sell, and inventory_rule says so a few lines
        # up — but the action set listed "sell" anyway, so the desk kept
        # choosing it: 33 refusals of "spot sell with no inventory — treated as
        # hold" across 16 runs between 2026-07-27 and 2026-08-03, including run
        # 939's confidence-0.62 read. Telling it the verb is unavailable while
        # offering the verb is the contradiction; stop offering it, exactly as
        # "retire" is offered only when flat.
        + 'Respond ONLY with JSON: {"action": "buy"'
        + ('|"sell"' if can_sell else '') + '|"hold"'
        + ('|"retire"' if not pos_qty else '') + ', '
        '"confidence": 0.0-1.0, "scores": {"thesis_alignment": 0.0-1.0, '
        '"momentum_quality": 0.0-1.0, "entry_quality": 0.0-1.0, '
        '"risk_context": 0.0-1.0}, '
        '"stop_pct": number|null, "target_pct": number|null, '
        + ('"order_intent": {"intent": "open"|"add"|"reduce"|"close"|"flip"|'
           '"hold"|"arm", "size_frac": 0.0-1.0, "arm": {"if": "price_below"|'
           '"price_above", "level": number, "then": "reduce"|"close", '
           '"size_frac": 0.0-1.0}|null}, '
           if pos_qty else '')
        + '"report": "<one sentence>"}'
    )
    text = None
    try:
        from llm_client import generate_text
        # 200 was the budget before the intent object joined the payload; a
        # cut-off JSON is not a smaller answer, it is a lost one.
        text = generate_text(prompt, max_tokens=280 if pos_qty else 200,
                             temperature=0.2, tier="decision")
    except Exception:  # noqa: BLE001
        text = None
    action, confidence, report = "hold", 0.0, "light cycle: no LLM verdict"
    scores: Optional[dict] = None
    order_block: Optional[dict] = None
    intent_block: Optional[dict] = None
    if text:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                a = str(obj.get("action") or "").strip().lower()
                if a in ("buy", "sell", "hold", "retire"):
                    action = a
                confidence = max(0.0, min(1.0, float(obj.get("confidence") or 0)))
                report = str(obj.get("report") or "")[:500]
                raw_scores = obj.get("scores")
                if isinstance(raw_scores, dict):
                    parsed = {}
                    for k in CONVICTION_WEIGHTS:
                        try:
                            parsed[k] = max(0.0, min(1.0, float(raw_scores[k])))
                        except (KeyError, TypeError, ValueError):
                            parsed = None
                            break
                    scores = parsed
                # Lift the flat stop/target pair into the same `order` shape
                # the full path emits, so one parser and one set of rails
                # serve both. Absent or null -> no block at all, which
                # degrades to the deterministic bracket exactly as before.
                flat = {k: obj.get(k) for k in ("stop_pct", "target_pct")
                        if obj.get(k) is not None}
                if flat:
                    order_block = flat
                # Plan 17: the intent rides beside the verb. Extracted here
                # because this parser builds the decision from named keys —
                # an unextracted key is silently dropped, which is exactly
                # how the full path's extra keys survive and this one's
                # would not.
                oi = obj.get("order_intent")
                if isinstance(oi, dict):
                    intent_block = oi
            except (ValueError, TypeError):
                pass
    # `order_eligible` is now True: the light prompt DOES ask for a bracket
    # (stop_pct/target_pct only — the full block would defeat the cheap path).
    # Without the ask, every light cycle journaled 'not_eligible' and the
    # shadow dataset stayed empty while 100% of live runs routed here.
    decision = {"action": action, "confidence": confidence,
                "entry": entry, "report": report, "scores": scores}
    if order_block:
        decision["order"] = order_block
    if intent_block:
        decision["order_intent"] = intent_block
    return {"decision": decision,
            "analysts": {},
            "position_state": position_state}


def _order_discussion_enabled() -> bool:
    return (os.environ.get("ORDER_DISCUSSION", "1").strip().lower()
            not in ("0", "false", "no"))


def _produces_order(action: "str | None", held: float) -> bool:
    """buy/sell always produce an order; retire only flattens a held book."""
    if action in ("buy", "sell"):
        return True
    return action == "retire" and abs(held) > 1e-12


def _order_discussion(run: dict, cfg: dict, analysis: dict) -> dict:
    """Owner rule 2026-08-13 (STRONG, all trading orders): "Must be final
    discussion for contract or order by sooppiy AI — NOT any programming
    logic."

    A cheap-tier cycle may PROPOSE an order; the full 4-analyst + trader
    discussion is the FINAL AUTHOR of it. The panel's decision REPLACES the
    proposal wholesale — code convenes the meeting and never arbitrates the
    outcome (no action-matching, no veto rule; whatever the discussion
    concludes flows into the same gates and rails as any decision).

    Deliberately NOT escalated: holds (no order to author), the full tier
    (it already IS the discussion), and armed exits / protective stops —
    those execute brackets and levels the desk itself authored in an
    earlier decision, and delaying protective exits for a fresh meeting
    was measured and rejected (main handoff §7).

    Fail-OPEN on panel infrastructure errors: an LLM hiccup must not
    freeze the book (the no-provider-default lesson); the proposal stands
    and the failure is journaled in the same event."""
    proposal = (analysis.get("decision") or {})
    action = proposal.get("action")
    try:
        held = _position_quantity(run["agent_id"], run["market"],
                                  run["symbol"], run["id"])
    except Exception:  # noqa: BLE001
        held = 0.0
    if not _produces_order(action, held):
        return analysis
    payload: dict = {"proposed": {"action": action,
                                  "confidence": proposal.get("confidence")}}
    try:
        from analysis_agents import run_analysis
        second = run_analysis(
            run["symbol"], run["market"], cfg.get("lang") or "en",
            provider=cfg.get("provider") or None,
            agent_id=run["agent_id"],
            llm_tiers=cfg.get("llm_tiers") or None,
            position_state=analysis.get("position_state") or "",
            can_sell=bool(trading_runs.is_futures_book(
                run.get("market"), (run.get("market_type") or "spot"))
                or held > 0))
        final = dict(second.get("decision") or {})
        if not final.get("action"):
            raise ValueError("discussion returned no action")
        # A rule-engine fallback is NOT the sooppiy AI speaking (owner
        # policy 2026-07-31: user-owned calls never borrow the platform
        # default, so a user without Settings-page AI gets decided_by=
        # 'rule' here). Replacing the cheap tier's GENUINE AI verdict with
        # a rule hold would let programming overrule the AI — the exact
        # inversion of the owner's rule — and, worse, silently convert the
        # desk's own risk-reducing exits into holds. Treat it as a failed
        # meeting: journal it, keep the AI's proposal.
        if final.get("decided_by") == "rule":
            raise RuntimeError("panel fallback (not the AI): "
                               + str(final.get("fallback_reason") or "rule"))
        final["escalated_from"] = payload["proposed"]
        payload["final"] = {"action": final.get("action"),
                            "confidence": final.get("confidence")}
        emit_telemetry_event(run["id"], "order_discussion", payload)
        return {"decision": final,
                "analysts": (second.get("analysts")
                             if isinstance(second.get("analysts"), dict)
                             else {}),
                "position_state": analysis.get("position_state") or ""}
    except Exception as exc:  # noqa: BLE001 — fail-open, journal the miss
        payload["error"] = str(exc)[:200]
        try:
            emit_telemetry_event(run["id"], "order_discussion", payload)
        except Exception:  # noqa: BLE001
            pass
        return analysis


def _pre_gate_skip(run: dict, cfg: dict) -> Optional[str]:
    """Zero-LLM gates evaluated BEFORE run_analysis — a us-stock run cycling
    all weekend must not burn a multi-agent analysis per tick against a
    guaranteed 'market closed' skip (and skipped cycles don't count against
    tick budgets)."""
    from routes_shared import is_market_open

    # Plan 14 §6.7 depth (1): the account-level master hold, checked before
    # anything costs money or LLM.
    try:
        if _master_held(run["agent_id"]):
            return "account AI automation held by master switch"
    except Exception:  # noqa: BLE001 — money gate: fail closed
        return "master-hold check unavailable"

    if not is_market_open(run["market"]):
        # Swing cadence (owner spec 2026-08-12): a run stamped with an
        # analysis_window may THINK through the session shoulders (open−2h,
        # close+2h) — context building only; _order_gate_skip refuses every
        # order while the market is shut, so these cycles can never fill at
        # a stale mark. Outside the shoulders the run is dormant as before.
        win = (cfg or {}).get("analysis_window") or {}
        if win:
            import markets as _mkts
            state = _mkts.extended_session_state(
                run["market"],
                pre_minutes=int(win.get("pre_open_minutes") or 0),
                post_minutes=int(win.get("post_close_minutes") or 0))
            if state != "analysis":
                return "market closed"
        else:
            return "market closed"
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT cash FROM agents WHERE id = ?", (run["agent_id"],))
        row = cursor.fetchone()
        if row is None:
            return "agent deleted"
        cash = float(row["cash"] or 0)
        cursor.execute(
            """SELECT id FROM positions
               WHERE agent_id = ? AND market = ? AND symbol = ?
                 AND run_id = ? AND quantity != 0""",
            (run["agent_id"], run["market"], run["symbol"], run["id"]))
        has_position = cursor.fetchone() is not None
    finally:
        conn.close()
    max_bet = float(cfg.get("max_bet_usd") or 0)
    if not has_position and cash < max_bet * 1.001:
        return f"insufficient cash for max bet (${cash:.2f} < ${max_bet:.2f})"

    # Fee/edge re-entry cooldown: only a FLAT run can open, so only a flat run
    # is subject to the post-close spacing that keeps leveraged/fast tiers from
    # churning fees. Reads the run's last realized (closing) leg.
    if not has_position and _reentry_cooldown_enabled() and _reentry_cooldown_minutes(cfg) > 0:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MAX(created_at) AS last_close FROM signals "
                "WHERE run_id = ? AND pnl IS NOT NULL", (run["id"],))
            row = cursor.fetchone()
            last_close = row["last_close"] if row else None
        finally:
            conn.close()
        cooldown = _reentry_cooldown_reason(last_close, cfg, _now_dt())
        if cooldown:
            return cooldown

    # daily trade cap (always-on per-run rail)
    cap = int(run.get("max_trades_per_day") or 0)
    if cap > 0:
        day_start = _now_dt().strftime("%Y-%m-%dT00:00:00Z")
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) AS n FROM signals
                   WHERE run_id = ? AND created_at >= ?""",
                (run["id"], day_start))
            if int(cursor.fetchone()["n"] or 0) >= cap:
                return f"daily trade cap reached ({cap}/day)"
        finally:
            conn.close()

    # per-tier daily LLM budget (env-gated enforcement; Plan 10 D9)
    try:
        from entitlements import llm_ticks_exhausted
        conn = get_db_connection()
        try:
            deny = llm_ticks_exhausted(conn.cursor(), run["agent_id"])
            conn.commit()
        finally:
            conn.close()
        if deny:
            return deny
    except Exception:  # noqa: BLE001 — fail closed on spend gates
        return "entitlement check unavailable"
    return None


def _position_quantity(agent_id: int, market: str, symbol: str,
                       run_id: Optional[int]) -> float:
    """Signed position quantity in THIS run's book (negative = short), 0.0
    when flat. Scoped by run_id: a sibling run on the same symbol keeps its
    own row, and reading the combined book would invert the futures
    buy/sell -> short/cover remap."""
    from routes_shared import get_position_snapshot
    conn = get_db_connection()
    try:
        pos = get_position_snapshot(conn.cursor(), agent_id, market, symbol, None, run_id)
        return float(pos["quantity"]) if pos else 0.0
    finally:
        conn.close()


def _last_entry_at(run_id: int) -> Optional[str]:
    """created_at of this run's most recent ENTRY leg (buy/short), None when
    the run has never opened. Exits (sell/cover) deliberately excluded — they
    must never push the next entry's spacing window."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT MAX(created_at) AS ts FROM signals
               WHERE run_id = ? AND side IN ('buy', 'short')""", (run_id,))
        row = cursor.fetchone()
        return row["ts"] if row and row["ts"] else None
    finally:
        conn.close()


def _order_gate_skip(run: dict, cfg: dict, action: str) -> Optional[str]:
    """Swing order policy (owner spec 2026-08-12), read from the per-run
    stamps compose wrote: (1) orders fill only while the market is OPEN — an
    analysis-shoulder cycle may decide, log and plan, but a fill would land
    on the stale last mark, the phantom-price class Plan 23 C2 exists to
    prevent; (2) entries land at least entry_spacing_minutes apart. Exits
    are exempt from spacing by design — a risk brake must never delay
    getting OUT. Runs without the stamps are untouched."""
    if cfg.get("analysis_window"):
        from routes_shared import is_market_open
        if not is_market_open(run["market"]):
            return "analysis shoulder — orders resume at the open"
    spacing = int(cfg.get("entry_spacing_minutes") or 0)
    if spacing > 0 and action in ("buy", "short"):
        last = _last_entry_at(run["id"])
        if last:
            age_min = _age_seconds(last) / 60.0
            if age_min < spacing:
                return (f"entry spacing: last entry {age_min:.0f}m ago "
                        f"< {spacing}m minimum (exits unaffected)")
    return None


def run_cycle(run_id: int) -> dict:
    """One full cycle: claim -> pre-gates -> analysis -> gates -> trade.
    Sync; called on the dedicated executor. Never raises."""
    result: dict[str, Any] = {"run_id": run_id, "executed": False, "skip_reason": None}
    run = None
    ctx_token = None
    try:
        run = _claim(run_id)
        if run is None:
            result["skip_reason"] = "not claimed (lease held elsewhere or not running)"
            return result

        # Name the member this cycle's LLM spend belongs to, for the whole
        # cycle. The route verdict, the light analysis and run_feedback's
        # thesis review all call generate_text without setting a context of
        # their own; without this they inherit nothing and their llm_usage rows
        # land with user_id NULL. Measured 2026-08-05: that was 64% of all
        # metered spend, which is why no per-tier cost cap could be built.
        # analysis_agents.run_analysis sets its own (identical) context — the
        # inner one simply wins for the analyst pipeline. Fail-soft: metering
        # identity must never be the thing that breaks a trading cycle.
        try:
            from llm_client import LlmContext, set_llm_context
            from services import user_id_for_agent
            agent_id = run["agent_id"]
            ctx_token = set_llm_context(LlmContext(
                source="rule", user_id=user_id_for_agent(agent_id),
                agent_id=agent_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("run cycle LLM attribution unavailable (run %s): %s",
                           run_id, exc)

        seq = int(run["cycle_seq"])
        cfg = json.loads(run.get("config_snapshot_json") or "{}")

        # ── Plan 14 §7: feedback pass — zero-LLM, BEFORE pre-gates ─────────
        adapt_state = None
        adapt_params = None
        import run_feedback
        if run_feedback.feedback_enabled(cfg):
            adapt_state = run_feedback.load_state(run)
            pnl = compute_run_pnl(run)
            outcomes = run_feedback.leg_outcomes(
                run, int(adapt_state.get("last_processed_signal_id") or 0))
            adapt_events = run_feedback.ingest_outcomes(adapt_state, outcomes)
            if adapt_state.pop("_reset", None):
                adapt_events.append({"trigger": "state_reset"})
            policy = run_feedback.apply_policy(adapt_state, run, cfg, pnl)
            adapt_events.extend(policy["events"])
            review = run_feedback.maybe_review_thesis(adapt_state, run, cfg, pnl)
            if review:
                emit_telemetry_event(run_id, "thesis_review",
                                     {"cycle": seq, "status": review["status"],
                                      "rationale": review["rationale"]})
                if review["retire"]:
                    policy = {"retire": True, "reason": "thesis_invalidated"}
            if not run_feedback.save_state(run, adapt_state, adapt_events,
                                           WORKER_IDENTITY):
                # lease lost mid-pass: discard adaptation, skip the trade
                result["skip_reason"] = "adapt state fence lost"
                return result
            if policy["retire"]:
                run_feedback.retire_run(run, policy.get("reason") or "adapt")
                result["skip_reason"] = "adapt_retired"
                return result
            if run_feedback.in_cooldown(adapt_state):
                result["skip_reason"] = "adapt loss cooldown"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "adapt",
                                      "reason": "loss cooldown"})
                return result
            adapt_params = run_feedback.effective_gate_params(adapt_state, cfg,
                                                              run_id=run["id"])

        skip = _pre_gate_skip(run, cfg)
        if skip:
            result["skip_reason"] = skip
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "pre", "reason": skip})
            _handle_infeasible_skip(run, skip)
            return result

        is_fleet_run = bool(run.get("fleet_id")) or \
            (run.get("created_via") or "user") == "fleet"
        cycle_mode = _fleet_cycle_mode(cfg) if is_fleet_run else "full"
        route = None
        if is_fleet_run and _decision_routing_enabled() and \
                (cfg.get("cycle_mode") or "").strip().lower() not in ("light", "full"):
            # E1-A: situation routing — an explicit per-run pin always wins;
            # otherwise the classifier overrides the blanket env mode (full
            # analysts on the tails, light path in the middle).
            route = _classify_situation(run, cfg)
            cycle_mode = route["route"]

        # The desk's own horizon (2026-07-30). Placed AFTER routing so the
        # trigger list is available and BEFORE the analysis so a held horizon
        # also saves the LLM spend. Prod run 825 authored horizon_hours 72,
        # was re-decided 30 minutes later, and sold the exact low of its own
        # price series — worth $5.54 and widening against simply keeping the
        # plan it wrote. Stops are untouched: _evaluate_stop runs on the ~60s
        # control scan, so a horizon skip can never delay an exit.
        try:
            hz_held = _position_quantity(run["agent_id"], run["market"],
                                         run["symbol"], run["id"])
        except Exception:  # noqa: BLE001
            hz_held = 0.0
        hz_state = _horizon_state(run, route, bool(hz_held))
        if hz_state and _horizon_gate_enabled():
            result["skip_reason"] = hz_state
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "horizon",
                                  "reason": hz_state})
            return result
        if hz_state:
            # Gate disarmed: record what it WOULD have suppressed so the
            # dataset accumulates without anything being suppressed. Scoring
            # comes later — pair each shadow row with what the position did
            # over the authored horizon. n=1 swung $7.32 in 90 minutes, so
            # this needs many more rows before it can justify arming.
            emit_telemetry_event(run_id, "horizon_shadow",
                                 {"cycle": seq, "would_hold": hz_state,
                                  "triggers": (route or {}).get("triggers")
                                  if isinstance(route, dict) else None})

        # Phase 3(a): whatever recall this cycle performs is captured while the
        # brief is built and emitted beside the decision below. Cleared first
        # so a cycle that never recalls cannot inherit the last one's chunks.
        _recall_reset(run_id)
        # Both branches (and the contradiction tracker below, which now also
        # runs on light cycles whose order-discussion panel returned real
        # analysts) need the held book — compute it ONCE, ahead of the split.
        try:
            held = _position_quantity(run["agent_id"], run["market"],
                                      run["symbol"], run["id"])
        except Exception:  # noqa: BLE001
            held = 0.0
        if is_fleet_run and cycle_mode == "light":
            # Plan 14 §9.2: one decision-tier call — swaps ONLY this stage;
            # everything below (gates, budget cap, fence) is byte-identical.
            analysis = _light_analysis(run, cfg)
            # Owner rule 2026-08-13 (STRONG): the FINAL author of any order
            # is the sooppiy AI's full discussion — a cheap-tier proposal
            # that would trade convenes the panel, and the panel's verdict
            # replaces it wholesale. Holds convene nothing.
            if _order_discussion_enabled():
                analysis = _order_discussion(run, cfg, analysis)
        else:
            from analysis_agents import run_analysis
            # The router escalates here FOR position reasons, so the expensive
            # desk must see the same book the cheap one does — same helper, so
            # the two paths cannot drift apart.
            analysis = run_analysis(run["symbol"], run["market"],
                                    cfg.get("lang") or "en",
                                    provider=cfg.get("provider") or None,
                                    agent_id=run["agent_id"],
                                    llm_tiers=cfg.get("llm_tiers") or None,
                                    position_state=(_position_state_line(
                                        run, cfg, held,
                                        (cfg.get("thesis") or {})
                                        if isinstance(cfg.get("thesis"), dict)
                                        else {})
                                        + _stop_hit_line(run)
                                        + _opening_window_line(run)
                                        + _young_exit_brief(run, cfg, held)
                                        + _contradiction_line(run, held)
                                        + _last_cycle_word_line(run)
                                        + _predecessor_run_line(run)
                                        + _earnings_state_line(run)
                                        + _breadth_state_line(run)
                                        + _us_psych_line(run)
                                        + _fx_risk_line(run)
                                        + _hold_streak_line(run, held)
                                        + _brake_distance_line(run, held)
                                        + _entry_rail_line(run, held)
                                        + _exit_size_line(run, held)
                                        + _mark_freshness_line(run, held)
                                        + _big_trader_line(run)
                                        + _ordinary_day_line(run)
                                        + _standing_arm_line(run, held)),
                                    # Same book, same vocabulary: a flat spot
                                    # run must not be offered "sell" on the
                                    # expensive path either.
                                    can_sell=bool(
                                        trading_runs.is_futures_book(
                                            run.get("market"),
                                            (run.get("market_type") or "spot"))
                                        or held > 0))
        analysts = analysis.get("analysts") if isinstance(analysis.get("analysts"), dict) else {}
        tech_block = analysts.get("technical")
        technical = tech_block.get("data") if isinstance(tech_block, dict) else None
        # Plan 24 fix 1: the full path carries the desk's structured reading
        # (technical signal + news balance) — track it against the held side.
        # Best-effort persist: a lost fence here only loses one streak tick,
        # never the trade (the advisory counter must not gate the cycle).
        if adapt_state is not None and isinstance(technical, dict):
            news_block = analysts.get("news")
            news_data = (news_block.get("data")
                         if isinstance(news_block, dict) else None) or {}
            bd = news_data.get("sentiment_breakdown")
            if isinstance(bd, dict):
                c_bull = (bd.get("bullish", 0) or 0) + \
                    (bd.get("somewhat-bullish", 0) or 0)
                c_bear = (bd.get("bearish", 0) or 0) + \
                    (bd.get("somewhat-bearish", 0) or 0)
            else:
                c_bull = c_bear = None
            run_feedback.note_contradiction(
                adapt_state, held, (technical or {}).get("signal"),
                c_bull, c_bear)
            run_feedback.save_state(run, adapt_state, [], WORKER_IDENTITY)
        decision = (analysis.get("decision") or {})
        action = decision.get("action")
        confidence = decision.get("confidence")
        entry = decision.get("entry")
        # Plan 15 P2: conviction is computed HERE from the component scores
        # (shadow next to the legacy scalar in every decision event). P3:
        # when RUN_CONF_V2 is on and a conviction exists, the gate reads it.
        scores = decision.get("scores")
        conviction = compute_conviction(scores)
        use_conviction = _conf_v2_enabled() and conviction is not None
        gate_confidence = conviction if use_conviction else confidence
        size_scale = _conviction_size_scale(
            conviction if conviction is not None else confidence,
            leverage=cfg.get("leverage") or 1.0)

        emit_telemetry_event(run_id, "decision",
                             {"cycle": seq, "llm": _llm_stamp(),
                              "action": action, "confidence": confidence,
                              "conviction": conviction, "scores": scores,
                              "gate_source": "conviction" if use_conviction else "confidence",
                              "size_scale": size_scale,
                              "entry": entry,
                              "route": route,
                              # The gate reads ONE of these two numbers and
                              # they disagree materially: prod run 822 showed
                              # 0.68/0.345, 0.62/0.35 and 0.70/0.3325 on three
                              # consecutive cycles — same run, same direction,
                              # up to 0.3675 apart, with the gate taking the
                              # less-informative scalar. Journal the gap (and
                              # a null conviction, which silently downgrades
                              # sizing to that scalar with no signal today) so
                              # there is a count before anyone argues from it.
                              **_conviction_divergence(confidence, conviction),
                              "report": (decision.get("report") or "")[:1000]})

        # Stop-hit routing: this decision IS the desk's ruling on the noted
        # hit — clear it (which also suppresses re-noting for one think
        # window, so a justified hold is not re-litigated every scan tick).
        try:
            import stop_router
            if stop_router.enabled():
                stop_router.clear(run_id)
        except Exception:  # noqa: BLE001
            pass

        # The report just journaled is English on purpose (it is the corpus
        # desk_memory retrieves from), and the AI-analysis panel localizes it
        # at read time through a cached translator. Warm the OWNER's language
        # now, at write time, so the panel's first read is already localized —
        # before this, the cache was only ever populated by a read, so every
        # new report's first view was English. Non-blocking: the helper only
        # schedules a background translation.
        _warm_report_i18n(run["agent_id"], (decision.get("report") or "")[:1000])

        # Phase 3(a): what the desk was shown from its own corpus when it made
        # that call. Absent when this cycle never recalled (a flat run has no
        # position brief); present with an empty `chunks` when it recalled and
        # the corpus had nothing — those are different rows, and the second is
        # the control group the attribution needs.
        recalled = _take_recall_journal(run_id)
        if recalled is not None:
            emit_telemetry_event(run_id, "recall",
                                 {"cycle": seq, "action": action,
                                  "query": recalled.get("query"),
                                  "chunks": recalled.get("chunks"),
                                  # (a2): the logging policy that produced the
                                  # row. Without the propensity and the scheme
                                  # VERSION beside the choice, none of the
                                  # off-policy estimators can be computed
                                  # offline, and it cannot be retrofitted.
                                  **{k: recalled[k] for k in
                                     ("scheme", "explore", "propensity",
                                      "eps", "pool") if k in recalled}})

        # AI-authored order parameters (2026-07-27). Parsed and railed here,
        # journaled either way; whether they change the order is
        # RUN_AI_ORDER_PARAMS. Default 'shadow' — the block is recorded beside
        # the decision that produced it and the deterministic path runs
        # unchanged, which is what makes the constants-vs-AI comparison
        # possible without risking anything on an unproven model output.
        order_params = None
        op_mode = order_params_mode()
        if op_mode != "off":
            # Price the fee floor at THIS run's market. The entry gate already
            # uses fees.fee_rate(market); the bracket rail was still on the flat
            # legacy rate, which is 20x a US equity round trip and 12x a major
            # pair's. Only visible on a target-only block — with a stop present
            # the R:R floor lands on the same number.
            from fees import fee_rate as _fee_rate_for_market
            order_params = parse_order_block(
                decision.get("order"),
                leverage_cap=max(1.0, float(cfg.get("leverage") or 1.0)),
                fee_rate=_fee_rate_for_market(run.get("market")))
            emit_telemetry_event(
                run_id, "order_params",
                {"cycle": seq, "mode": op_mode, "action": action,
                 "deferred": order_params is None,
                 # 'absent' vs 'defer' are opposite findings — one says the
                 # prompt never reached the model (the cheap analysis path
                 # does not ask for the block at all), the other says the desk
                 # looked and chose the house default. A single `deferred`
                 # flag made the shadow dataset unreadable.
                 # `not_eligible` retained for any future path that opts out;
                 # the light path no longer sets it — it asks for a bracket
                 # like everything else.
                 "outcome": ("not_eligible" if decision.get("order_eligible") is False
                             else order_params_outcome(decision.get("order"))),
                 "route": (route or {}).get("route"),
                 **({"params": order_params.as_event()} if order_params else {})})

        # 'retire' (2026-07-30): the desk hands its own slot back when the book
        # cannot express its read. FLAT ONLY — enforced here and not merely in
        # the prompt, because a model that emits it while holding must not be
        # able to flatten a position through a verb that was never meant to
        # trade. With a position open this degrades to `hold`, which is exactly
        # what a desk unable to act should do. Reuses the ordinary stop path
        # (STOPPING -> _control_stopping) so alerting, flatten handling and the
        # auto-restart exclusion all behave as they do for every other reason.
        if action == "retire":
            held_for_retire = _position_quantity(
                run["agent_id"], run["market"], run["symbol"], run["id"])
            if held_for_retire:
                action = "hold"
            else:
                _simple_transition(run, STATUS_STOPPING, "desk_retired",
                                   extra_sets="stopped_at = ?",
                                   extra_args=(_now_iso(),))
                result["skip_reason"] = "desk retired this run"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "desk_retire",
                                      "reason": result["skip_reason"]})
                return result

        # Futures v1 (Plan 10 D5): the desk decides direction (buy/sell); the
        # futures book translates it. A bearish call with no long to reduce
        # OPENS a short; a bullish call while short COVERS the book instead of
        # buying on top of a negative row. Without this mapping no decision
        # path ever emits 'short', so a futures run could never trade. Spot
        # runs are untouched — a spot 'sell' still only reduces a long.
        if trading_runs.is_futures_book(run.get("market"), run.get("market_type")) \
                and action in ("buy", "sell"):
            pos_qty = _position_quantity(run["agent_id"], run["market"], run["symbol"],
                                         run["id"])
            if action == "sell" and pos_qty <= 0:
                action = "short"
            elif action == "buy" and pos_qty < 0:
                action = "cover"
        elif action == "sell":
            # Plan 15 P1 (F4): a spot 'sell' with an empty book has nothing to
            # reduce. Skip here instead of at the execute stage ("no long
            # position to sell") so the wasted verdict is visible as a gate
            # skip, not an execution failure.
            pos_qty = _position_quantity(run["agent_id"], run["market"], run["symbol"],
                                         run["id"])
            if pos_qty <= 0:
                result["skip_reason"] = "spot sell with no inventory — treated as hold"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "risk",
                                      "reason": result["skip_reason"]})
                return result

        # Plan 17: Order Intent (2026-07-30). The desk states WHAT it wants
        # (open/add/reduce/close/flip/hold/arm) and a total function compiles
        # it to the ledger's four verbs. Journalled beside the decision on
        # every cycle in shadow AND apply — the paired reduce measurement in
        # the plan doc's §8 is built from these events. Placed AFTER the
        # futures remap on purpose: an intent exit only compiles sell against
        # a long / cover against a short, which the remap never touches, so
        # the two cannot fight over the verb.
        intent_exit = None
        oi_mode = order_intent.intent_mode()
        if oi_mode != "off":
            oi_parsed = order_intent.parse(decision.get("order_intent"))
            if oi_parsed is not None:
                oi_pos = _position_quantity(run["agent_id"], run["market"],
                                            run["symbol"], run["id"])
                oi_lev = max(1.0, float(cfg.get("leverage") or 1.0))
                oi_railed = order_intent.rail(
                    oi_parsed,
                    position_notional_usd=abs(oi_pos) * float(entry or 0))
                compiled = order_intent.compile_intent(
                    oi_railed["intent"], oi_railed.get("size_frac"),
                    is_futures=trading_runs.is_futures_book(
                        run.get("market"), run.get("market_type")),
                    position_qty=oi_pos,
                    bull=order_intent.bull_from_action(action))
                # intent_size_usd on a position-basis intent is what the desk
                # ASKED to shed; machine_size_usd is what the legacy path is
                # about to size from the budget. The gap between them, priced
                # at this mark, is the shadow dataset.
                intent_size = None
                if oi_railed.get("size_basis") == "position" and oi_pos:
                    intent_size = order_intent.exit_size_usd(
                        oi_railed.get("size_frac") or 0,
                        position_qty=oi_pos, entry=float(entry or 0),
                        leverage=oi_lev)
                emit_telemetry_event(
                    run_id, "order_intent",
                    {"cycle": seq, "mode": oi_mode,
                     "intent": oi_railed["intent"],
                     "size_frac": oi_railed.get("size_frac"),
                     "size_basis": oi_railed.get("size_basis"),
                     "railed": oi_railed.get("railed") or {},
                     "arm": oi_railed.get("arm"),
                     "why": oi_railed.get("why"),
                     "compiled": compiled,
                     "position_qty": oi_pos,
                     "legacy_action": action,
                     "intent_size_usd": (round(intent_size, 4)
                                         if intent_size is not None else None),
                     "machine_size_usd": cfg.get("max_bet_usd")})
                # Arm EXECUTES from 2026-08-05 (cycle 65). It is not an
                # ordinary exit — it is a standing order evaluated on the
                # control pass, so it is the only mechanism that can act
                # between two decisions. That is precisely where the profit
                # lived on 08-05: for four of seven losing runs the entire
                # favourable excursion (5-20 min) fell between cycles ~45 min
                # apart, and the desk never saw it. Persist it here; the
                # control pass fires it. Each cycle's arm replaces the last.
                if oi_mode == "apply" and oi_railed["intent"] == "arm":
                    _store_armed_order(run_id, oi_railed.get("arm"), seq)
                # Phase 1 apply: exits only. reduce/close compile to a single
                # position-basis step; everything else (open/add/flip)
                # stays journal-only until its own phase — gated on shadow
                # evidence, not on this code existing.
                if oi_mode == "apply" \
                        and oi_railed["intent"] in ("reduce", "close") \
                        and compiled["steps"]:
                    step = compiled["steps"][0]
                    action = step["verb"]
                    intent_exit = {"size_frac": step["size_frac"],
                                   "position_qty": oi_pos,
                                   "intent": oi_railed["intent"]}

        # Plan 24 fix 1 backstop: at 3 straight cycles of the desk's own
        # reading opposing the held side, a SILENT hold (no exit intent, no
        # arm) forces a half reduce. Shed-only — never a full close, and
        # never while the desk has any standing plan. The streak resets so
        # continued contradiction de-risks progressively (0.5 → 0.25 → the
        # dust-remainder rail closes the rest). Live 2026-08-12, run 1086:
        # three silent contradicted cycles rode ZEC to −$5.55.
        if intent_exit is None and action == "hold" \
                and adapt_state is not None \
                and int(adapt_state.get("contradiction_streak") or 0) >= 3 \
                and _fresh_armed_order(run_id) is None:
            c_pos = _position_quantity(run["agent_id"], run["market"],
                                       run["symbol"], run["id"])
            if c_pos:
                action = "sell" if c_pos > 0 else "cover"
                intent_exit = {"size_frac": 0.5, "position_qty": c_pos,
                               "intent": "reduce"}
                adapt_state["contradiction_streak"] = 0
                run_feedback.save_state(run, adapt_state, [], WORKER_IDENTITY)
                emit_telemetry_event(run_id, "contradiction_reduce",
                                     {"cycle": seq, "side": action,
                                      "position_qty": c_pos})

        # Young-dump measurement (run 1104: −$10.14 covering a 30-minute-old
        # short on a −0.9% wiggle, confidence 0.80 vs conviction 0.30, tape
        # then went the thesis's way). NO behavior change — an exit-shaped
        # decision on a young, noise-adverse position is journalled with
        # both sizing signals so the weekly read can score the brief.
        if action in ("sell", "cover"):
            try:
                yd_pos = _position_quantity(run["agent_id"], run["market"],
                                            run["symbol"], run["id"])
                if ((yd_pos > 0 and action == "sell")
                        or (yd_pos < 0 and action == "cover")) \
                        and _young_exit_brief(run, cfg, yd_pos):
                    emit_telemetry_event(
                        run_id, "young_dump_flag",
                        {"cycle": seq, "action": action,
                         "confidence": confidence,
                         "conviction": conviction,
                         "intent": (intent_exit or {}).get("intent")})
            except Exception:  # noqa: BLE001 — telemetry never blocks a trade
                pass

        # Plan 14 §7: same-direction re-entry block after a losing close
        # (whipsaw/fee-churn guard) — deterministic, before the gates.
        # An intent exit is exempt: it sheds risk, and the whipsaw guard
        # exists to stop re-ENTRIES (Plan 17 §5: a rail that refuses a
        # reduction IS the risk).
        if intent_exit is None and adapt_state is not None and \
                run_feedback.blocked_reentry(adapt_state, action):
            result["skip_reason"] = "adapt re-entry blocked after losing close"
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "adapt",
                                  "reason": result["skip_reason"]})
            return result

        # Fee/edge entry gate (2026-07-26): an OPEN must promise a move that
        # outruns its own round trip. Exits are never gated.
        if action in ("buy", "short"):
            thesis = cfg.get("thesis") if isinstance(cfg.get("thesis"), dict) else {}
            fee_skip = _fee_edge_skip(thesis.get("expected_move_pct"),
                                      float(cfg.get("leverage") or 1.0),
                                      market=run.get("market"))
            if fee_skip:
                result["skip_reason"] = fee_skip
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "fee_edge",
                                      "reason": fee_skip})
                return result

        from automation import evaluate_execution_gates, execute_paper_trade
        # Plan 14 §6.3.2: for fleet-created runs, run_budget_usd is a HARD
        # deployed (open) cost-basis cap enforced at execution — until this,
        # it was validated at creation and then read only by reporting.
        size_usd = cfg.get("max_bet_usd")
        min_confidence = cfg.get("min_confidence")
        if adapt_params is not None:
            size_usd = adapt_params["size_usd"]
            min_confidence = adapt_params["min_confidence"]
        # Confidence recalibration: grade this decision against the agent's own
        # recent distribution rather than a fixed threshold the quantized
        # scalar barely reaches. On success the risk gate enforces only the low
        # absolute floor, because rank has already done the discriminating.
        # Plan 17 exit-gate split: a confidence gate on an exit refuses the
        # shedding of risk, which the asymmetry forbids — `close` must pass
        # every gate configuration. Entry stack applies to opens only.
        conf_skip, min_confidence = (None, min_confidence) if intent_exit \
            else _conf_percentile_skip(
                run["agent_id"], gate_confidence, min_confidence)
        if conf_skip:
            result["skip_reason"] = conf_skip
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "confidence_rank",
                                  "reason": conf_skip})
            return result
        # Plan 15 rec-2 (2026-07-23, Henry-approved): bet size follows stated
        # conviction — "modest long, slight edge only" must not execute a
        # full max_bet. Shrink-only (scale ≤ 1.0), composes with the adapt
        # ladder; kill-switch RUN_SIZE_BY_CONVICTION=0.
        if size_scale is not None and size_usd:
            size_usd = float(size_usd) * size_scale
        if is_fleet_run and cfg.get("run_budget_usd"):
            open_basis = _open_cost_basis(run["agent_id"], run["market"],
                                          run["symbol"], run["id"])
            headroom = float(cfg["run_budget_usd"]) - open_basis
            # Plan 15 overnight (2026-07-23, Henry-approved): floor raised
            # from a flat $10 to max($10, 2% of max_bet) — a $17 headroom on
            # a $5.2k max_bet produced a $17 dust add that burned a cycle and
            # fees for no meaningful exposure.
            headroom_floor = max(10.0, 0.02 * float(cfg.get("max_bet_usd") or 0))
            if action in ("buy", "short") and headroom < headroom_floor:
                result["skip_reason"] = "budget_headroom_skip"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "budget",
                                      "reason": "budget_headroom_skip",
                                      "open_basis": round(open_basis, 2),
                                      "run_budget": cfg["run_budget_usd"]})
                return result
            size_usd = min(float(size_usd or 0), max(headroom, 0.0))
        # Add-churn guard (2026-07-25): bound same-direction adds on an open
        # position — max_adds + cooldown from cfg.add_limits (fleet composer).
        # "short" must be here: by this point a futures sell with no long has
        # already been remapped to it above, so gating on ("buy", "sell") alone
        # skipped the guard entirely for every short position.
        # Plan 17 §9 worried this guard would see intent reductions; it cannot.
        # An intent exit compiles to `sell` only against a LONG (the guard's
        # own qty/action matrix reads that as a reduce and never limits it)
        # and to `cover` against a short (not in this action list at all). The
        # ambiguity §9 names — a futures short's `sell` mis-read as an open —
        # is resolved by compilation, not by an exemption here.
        if action in ("buy", "sell", "short"):
            add_skip = _add_limit_skip(
                run, cfg, action,
                max_adds_override=(order_params.max_adds
                                   if (op_mode == "apply" and order_params
                                       is not None) else None))
            if add_skip:
                result["skip_reason"] = add_skip
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "add_limit",
                                      "reason": add_skip})
                return result
        # Leverage (2026-07-23): size_usd is the MARGIN the run commits; the
        # position notional is margin × L. Size the gate with the leveraged
        # notional so Kelly / vol / exposure caps bound total exposure, then
        # the executor debits only the margin. L=1 leaves this untouched.
        lev = max(1.0, float(cfg.get("leverage") or 1.0))
        # Apply mode only: the desk's own sizing, already railed. size_frac is
        # a fraction OF the configured max bet and leverage is capped at the
        # run's own tier, so both can only shrink the order the config allowed.
        # Every downstream gate (Kelly, exposure, dust, budget headroom) still
        # runs on the result — this replaces the size, never the checks.
        if op_mode == "apply" and order_params is not None:
            # Leverage first: the reduce basis below divides by it.
            if order_params.leverage is not None:
                lev = max(1.0, min(lev, float(order_params.leverage)))
            if order_params.size_frac is not None and intent_exit is None:
                # Basis switches with the intent — see _order_size_usd. The
                # rail clamp (RAILS 0.05..1.00) is the same on either basis.
                held_now = 0.0
                if action in ("sell", "cover"):
                    held_now = _position_quantity(
                        run["agent_id"], run["market"], run["symbol"], run["id"])
                size_usd = _order_size_usd(
                    action, order_params.size_frac,
                    max_bet_usd=float(cfg.get("max_bet_usd") or 0),
                    held_qty=held_now, entry=float(entry or 0), leverage=lev)
        # Plan 17 apply: an intent exit is sized from the POSITION, full stop.
        # exit_size_usd never sees max_bet_usd — that derivation is the §2
        # defect and carries a permanent test tripwire. Takes precedence over
        # order_params sizing (guarded above) and over conviction scaling:
        # the desk said how much of its book to shed, and a scaler that
        # shrinks a reduction is a rail pointing the forbidden direction.
        if intent_exit is not None:
            size_usd = order_intent.exit_size_usd(
                intent_exit["size_frac"],
                position_qty=intent_exit["position_qty"],
                entry=float(entry or 0), leverage=lev)
        # R10 stop-coherence clamp (2026-08-14, shrink-only): the desk
        # authors a stop in price percent; the platform retires the run on
        # USD equity drawdown. When notional × stop% exceeds the brake's
        # remaining room, the rail is guaranteed to fire BEFORE the stop —
        # measured 2026-08-13 on SPCX/SOL/GC: n=3, −$118, no authored stop
        # ever acted. _entry_rail_line teaches the desk the identity; this
        # enforces it for the desks that ignore it, by shrinking size until
        # the authored stop fits the room. Opens/extends only — a rail that
        # shrinks a reduction points the forbidden direction — and only
        # when the desk actually authored a stop; unknown room never
        # clamps. Downstream dust guard remains the refusal path when the
        # room supports no meaningful size.
        if (op_mode == "apply" and order_params is not None
                and intent_exit is None and _stop_coherence_enabled()
                and order_params.stop_pct and float(size_usd or 0) > 0
                and action in ("buy", "short")):
            # By this point a futures sell with no long was already remapped
            # to "short" upstream, so "sell" here is always a reduce against
            # a long — reduces are never clamped (verified: the old
            # sell-extends-short branch was dead code).
            room = _brake_room_usd(run)
            if room is not None and room > 0:
                stop_frac = float(order_params.stop_pct) / 100.0
                # ADD-AWARE (R10 adversarial pass, HIGH): the rail prices the
                # WHOLE book, so an add must budget the held notional's stop
                # risk too — pricing only the increment let a second $100 add
                # rebuild exactly the SPCX/SOL shape the clamp exists to
                # close (reproduced: book 2× notional, whole-book stop-USD
                # 2× the room, brake first). Same-direction holdings only;
                # an opposite book reduces exposure and never reaches here.
                try:
                    held_qty = _position_quantity(run["agent_id"],
                                                  run["market"],
                                                  run["symbol"], run["id"])
                except Exception:  # noqa: BLE001
                    held_qty = 0.0
                same_dir = (max(held_qty, 0.0) if action == "buy"
                            else max(-held_qty, 0.0))
                held_notional = same_dir * float(entry or 0)
                room_eff = room - held_notional * stop_frac
                stop_usd = float(size_usd) * lev * stop_frac
                if stop_usd > room_eff:
                    clamped = max(room_eff, 0.0) / stop_frac / lev
                    emit_telemetry_event(run_id, "size_clamp",
                                         {"cycle": seq,
                                          "stage": "stop_coherence",
                                          "stop_pct": order_params.stop_pct,
                                          "room_usd": round(room, 2),
                                          "held_notional": round(held_notional, 2),
                                          "size_before": round(float(size_usd), 2),
                                          "size_after": round(clamped, 2)})
                    size_usd = clamped
        # Intent exits carry no confidence floor into the gate: a desk sure
        # enough to bank is not required to be sure enough to enter, and a
        # refused flatten is the failure mode the asymmetry exists to forbid.
        # Market-open and the risk engine's own exit handling still apply.
        gate_cfg = {"auto_execute": 1, "account_type": "simulator",
                    "min_confidence": 0.0 if intent_exit else min_confidence,
                    "size_usd": float(size_usd or 0) * lev, "mode": "manual"}
        gates = evaluate_execution_gates(gate_cfg, run["agent_id"], run["symbol"],
                                         run["market"], action, gate_confidence, entry,
                                         None, technical, run_id=run_id)
        gate = gates.get("gate")
        if gates["skip_reason"] is not None or gate is None:
            result["skip_reason"] = gates["skip_reason"] or "no gate verdict"
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "risk",
                                  "reason": result["skip_reason"]})
            return result

        # Swing order policy: session-only fills + entry spacing (exits
        # exempt). Checked AFTER the risk gate so the journaled decision
        # still records what the desk wanted; the skip reason says why the
        # order itself did not land.
        order_gate = _order_gate_skip(run, cfg, action)
        if order_gate:
            result["skip_reason"] = order_gate
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "order_policy",
                                  "reason": order_gate})
            return result

        # Plan 15 overnight (2026-07-23): dust guard on the FINAL sized order.
        # The budget-headroom floor upstream only bounds run_budget headroom;
        # the Kelly cap inside the risk engine can still shrink the sized
        # quantity to dust (observed: a $5.18 ZC add, fee half a cent).
        if action in ("buy", "short"):
            # Compare the committed MARGIN (notional / L) to the floor, since
            # the floor is denominated in max_bet (also margin).
            sized_margin = float(gate.quantity or 0) * float(entry or 0) / lev
            dust_floor = max(10.0, 0.02 * float(cfg.get("max_bet_usd") or 0))
            if sized_margin < dust_floor:
                result["skip_reason"] = (
                    f"dust order skip (margin ${sized_margin:.2f} "
                    f"< floor ${dust_floor:.2f})")
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "risk",
                                      "reason": result["skip_reason"]})
                return result

        # Exit bracket. In apply mode the desk's railed stop/target replace the
        # flat risk_limits percentages (5%/10% for every instrument in every
        # regime); otherwise the gate's own bracket stands.
        stop_loss, take_profit = gate.stop_loss, gate.take_profit
        is_short = action in ("short", "sell")
        if op_mode == "apply" and order_params is not None \
                and order_params.has_exits() and entry:
            ai_sl, ai_tp = order_exit_prices(order_params, float(entry), is_short)
            if ai_sl and ai_tp:
                stop_loss, take_profit = ai_sl, ai_tp

        # R:R floor — applied to WHICHEVER bracket won, AI or deterministic.
        # The rail exists because the fleet's own tier maths produced a 10:1
        # adverse geometry for a month (lock armed at 1/10th of the stop), and
        # a hand-edited risk_limits row can still express one. Refusing the
        # entry is correct: a bracket that risks more than it can win is not a
        # trade worth taking, whoever authored it.
        if action in ("buy", "short") and entry:
            violation = rr_floor_violation(stop_loss, take_profit,
                                           float(entry), is_short)
            if violation:
                result["skip_reason"] = violation
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "rr_floor",
                                      "reason": violation})
                return result

        # Plan 14 §6.7 depth (2): re-check the master hold immediately before
        # the trade write — a hold landing mid-cycle (past the pre-gate, during
        # the LLM call) turns this cycle into a journaled no-trade skip.
        try:
            if _master_held(run["agent_id"]):
                result["skip_reason"] = "account held (master switch, mid-cycle)"
                emit_telemetry_event(run_id, "gate_skip",
                                     {"cycle": seq, "stage": "master_hold",
                                      "reason": result["skip_reason"]})
                return result
        except Exception:  # noqa: BLE001
            result["skip_reason"] = "master-hold recheck unavailable"
            return result

        client_order_id = f"run:{run_id}:cyc:{seq}"
        signal_id, skip = execute_paper_trade(
            run["agent_id"], run["symbol"], run["market"], action,
            gate.quantity, float(entry),
            content=f"Trading run #{run_id} cycle {seq}",
            stop_loss=stop_loss, take_profit=take_profit,
            run_id=run_id, client_order_id=client_order_id,
            leverage=lev, fence=_fence(run_id))
        if signal_id:
            result.update({"executed": True, "signal_id": signal_id})
            _reset_infeasible(run_id)
            # Persist the rest of the desk's plan against the position it just
            # opened. Only on an OPEN: a reduce is not a new thesis, so it must
            # not restart the horizon clock on what remains — otherwise a desk
            # that trims once could hold the remainder past every re-decision.
            if action in ("buy", "short"):
                plan = _plan_stop_conditions(run, order_params, float(entry),
                                             float(gate.quantity or 0), lev)
                if plan:
                    _persist_order_plan(run_id, plan)
                    emit_telemetry_event(
                        run_id, "order_plan",
                        {"cycle": seq,
                         "horizon_until": plan.get("horizon_until"),
                         "trail": plan.get("trail")})
            # Per-trade alert only when the run opted in (notify_on_trade) —
            # the run_events journal carries the trade either way.
            if run.get("notify_on_trade"):
                try:
                    from alerts import send_alert
                    send_alert(run["agent_id"], "trade_executed", "run_trade_executed",
                               {"action_upper": str(action).upper(), "symbol": run["symbol"],
                                "run_id": run_id, "action": action,
                                "qty": f"{gate.quantity:.6f}",
                                "entry": f"{float(entry):.2f}", "confidence": confidence},
                               dedupe_key=f"run-exec:{signal_id}")
                except Exception:  # noqa: BLE001
                    logger.debug("run trade alert failed (run %s)", run_id)
        else:
            result["skip_reason"] = skip
            emit_telemetry_event(run_id, "gate_skip",
                                 {"cycle": seq, "stage": "execute", "reason": skip})
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("run cycle failed (run %s): %s", run_id, exc)
        result["skip_reason"] = f"error: {exc}"
        try:
            emit_telemetry_event(run_id, "gate_skip",
                                 {"stage": "error", "reason": str(exc)[:500]})
        except Exception:  # noqa: BLE001
            pass
        return result
    finally:
        if ctx_token is not None:
            from llm_client import reset_llm_context
            reset_llm_context(ctx_token)
        if run is not None:
            _release(run_id)


def _infeasible_limit() -> int:
    try:
        return max(2, int(os.getenv("RUN_INFEASIBLE_LIMIT", "10")))
    except ValueError:
        return 10


def _handle_infeasible_skip(run: dict, skip: str) -> None:
    """A run that can never trade must not burn scheduler attention forever:
    agent-deleted stops immediately; insufficient-cash skips are SKIPS, not
    errors — count them separately and auto-pause at the limit (the
    consecutive-error counter never fires on them)."""
    try:
        if skip == "agent deleted":
            _simple_transition(run, STATUS_STOPPED, "agent_deleted",
                               clear_active_key=True)
            return
        if not skip.startswith("insufficient cash"):
            return
        count = int(run.get("consecutive_infeasible") or 0) + 1
        if count >= _infeasible_limit():
            if _simple_transition(run, STATUS_PAUSED, "infeasible",
                                  extra_sets="consecutive_infeasible = ?, paused_reason = ?",
                                  extra_args=(count, "infeasible")):
                _alert_run(run, "run_stopped", "run_infeasible",
                           {"run_id": run["id"], "count": count},
                           dedupe=f"run:{run['id']}:infeasible")
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute(
                "UPDATE trading_runs SET consecutive_infeasible = ? WHERE id = ?",
                (count, run["id"]))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.debug("infeasible bookkeeping failed (run %s)", run.get("id"),
                     exc_info=True)


def _reset_infeasible(run_id: int) -> None:
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute(
                "UPDATE trading_runs SET consecutive_infeasible = 0 "
                "WHERE id = ? AND consecutive_infeasible != 0", (run_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass


def subscription_enforcer_tick() -> dict:
    """Pause (never delete) active runs whose owner's subscription lapsed —
    runs outlive 30-day plans by design; they resume after renewal. No-op
    unless ENTITLEMENTS_ENFORCED (Plan 10 D9)."""
    out = {"paused": 0}
    from entitlements import enforcement_enabled, limits_for_agent
    if not enforcement_enabled():
        return out
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # armed runs need no enforcement here: their cycles are blocked by
        # the pre-gate budget check the moment they would spend anything
        cursor.execute("SELECT * FROM trading_runs WHERE status = ?",
                       (STATUS_RUNNING,))
        runs = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
    for run in runs:
        try:
            conn = get_db_connection()
            try:
                _, limits = limits_for_agent(conn.cursor(), run["agent_id"])
                conn.commit()
            finally:
                conn.close()
            if int(limits["max_concurrent_runs"]) > 0:
                continue
            if _simple_transition(run, STATUS_PAUSED, "subscription_lapsed",
                                  extra_sets="paused_reason = ?",
                                  extra_args=("subscription_lapsed",)):
                out["paused"] += 1
                _alert_run(run, "run_stopped", "run_sub_lapsed",
                           {"run_id": run["id"]},
                           dedupe=f"run:{run['id']}:sub_lapsed")
        except Exception:  # noqa: BLE001
            logger.warning("subscription enforcement failed for run %s",
                           run["id"], exc_info=True)
    return out


# ── async tick (called by tasks.trading_run_loop) ──────────────────────────

async def _dispatch(run_id: int) -> None:
    sem = _get_semaphore()
    async with sem:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(_get_executor(), run_cycle, run_id)
            if result.get("executed"):
                print(f"[TradingRuns] run {run_id} executed signal "
                      f"{result.get('signal_id')}")
        finally:
            _in_flight.discard(run_id)


async def tick() -> dict:
    """One scheduler tick: control pass + dispatch of due cycles."""
    if not auto_trading_enabled():
        return {"enabled": False}
    counters = await asyncio.to_thread(control_pass)
    due = await asyncio.to_thread(due_run_ids)
    dispatched = 0
    for run_id in due:
        if run_id in _in_flight:
            continue  # already queued/executing in this process
        _in_flight.add(run_id)
        asyncio.get_running_loop().create_task(_dispatch(run_id))
        dispatched += 1
    counters.update({"enabled": True, "due": len(due), "dispatched": dispatched})
    # The desk corpus rides this tick rather than running its own loop. It is
    # throttled internally and is never allowed to fail a trading tick: a
    # corpus that cannot be written is a lost lesson, a tick that dies is a
    # position nobody is managing.
    try:
        ingested = await asyncio.to_thread(desk_memory_ingest.maybe_ingest)
        if ingested:
            counters["memory_ingested"] = ingested
    except Exception:  # noqa: BLE001
        logger.warning("desk memory ingest failed", exc_info=True)
    # Daily compounding of the fleet's working capital rides the same tick,
    # throttled to once per UTC day and equally forbidden from failing it:
    # a budget that does not compound is a missed adjustment, a dead tick is
    # an unmanaged position. It only moves the allocation budget, never a
    # position.
    try:
        import fleet_budget_daily
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        compounded = await asyncio.to_thread(fleet_budget_daily.maybe_compound, today)
        if compounded and compounded.get("changed"):
            counters["budget_compounded"] = compounded["changed"]
    except Exception:  # noqa: BLE001
        logger.warning("fleet budget compound failed", exc_info=True)
    # AI auto-tuning of slot count + take-profit goal rides the same tick,
    # AFTER the compound so slots scale to the fresh budget. Throttled, isolated
    # per fleet, and never allowed to fail the tick: it only moves allocation
    # config (never a position).
    try:
        import fleet_auto_tune
        now_epoch = datetime.now(timezone.utc).timestamp()
        tuned = await asyncio.to_thread(fleet_auto_tune.maybe_tune, now_epoch)
        if tuned and tuned.get("changed"):
            counters["auto_tuned"] = tuned["changed"]
    except Exception:  # noqa: BLE001
        logger.warning("fleet auto-tune failed", exc_info=True)
    return counters
