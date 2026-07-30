"""liquidation.py — margin-state oracle, health scalar, and tier classifier.

Plan 16 (docs/plan/16-liquidation-defense-daemon.html). Every open position in
production carries 2x-3x leverage, and until this module the entire liquidation
defence was ONE fixed threshold inside run_engine._evaluate_stop: the cushion
stop at ``entry x (1 -+ c/L)`` with ``c = RUN_LIQ_CUSHION_FRAC = 0.85``. Work
out what that means in normalised terms and it is exactly ``health = 1 - c =
0.15`` for both directions (see ``health()`` and the algebra in the plan doc) —
leverage-independent, instrument-independent, and blind to how FAST the
position is travelling. health 0.40 falling 0.15/min is an emergency; health
0.22 flat for six hours is not, and one threshold cannot tell them apart.

What this module adds:

  * a margin-state oracle with two sources — a real broker when one can answer
    (``Broker.get_margin_state``), and a synthetic model otherwise. The source
    is carried on every reading and shown to the desk verbatim, because a desk
    told a modelled number as though it were a venue fact will act with
    unearned precision.
  * ``health`` — 1.0 at your entry, 0.0 when the margin is gone — plus its
    velocity and the implied time-to-liquidation.
  * a four-tier classifier with hysteresis.

TWO CORRECTIONS TO THE PLAN DOC, both found while implementing:

  1. **Liquidation distance is size-invariant.** The doc's T3 spec said "reduce
     enough to restore health 0.45". That is not achievable. Under isolated
     margin a position of size q at entry E on leverage L posts ``q*E/L`` and
     liquidates when ``q*|P-E| = q*E/L`` — the q cancels, so the liquidation
     PRICE does not depend on size at all. Selling half cuts what you can lose;
     it does not buy a single tick of distance. The only actions that move the
     line are closing (removes it) and deleveraging (our ledger has no
     add-margin primitive — leverage is fixed at open). So the reflex here
     FLATTENS, and ``survival_brief`` tells the desk this outright, because a
     desk that believes trimming buys room will trim instead of exiting.
  2. **The synthetic model was optimistic.** ``entry x (1 -+ 1/L)`` ignores the
     maintenance-margin rate, so real liquidation arrives EARLIER than the
     shipped formula predicts. ``liquidation_price`` carries an ``mmr`` term.

Not modelled, deliberately, and stated rather than faked: funding accrual (no
feed), cross-margin coupling (unbounded error — refuse rather than half-model),
and mark-vs-last price divergence. ``funding_per_unit`` exists as a parameter
so the caller can supply it once a feed does.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

# ── tiers ──────────────────────────────────────────────────────────────────
TIER_NOMINAL = "T0"
TIER_WATCH   = "T1"
TIER_DEFEND  = "T2"
TIER_REFLEX  = "T3"

TIER_ORDER = (TIER_NOMINAL, TIER_WATCH, TIER_DEFEND, TIER_REFLEX)


def _tier_rank(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return 0


# ── flags ──────────────────────────────────────────────────────────────────
def _truthy(name: str, default: str) -> bool:
    return (os.getenv(name, default) or default).strip().lower() in (
        "1", "true", "yes", "on")


def oracle_enabled() -> bool:
    """Measure and journal margin state. Pure observation — safe by default."""
    return _truthy("LIQ_ORACLE", "true")


def desk_brief_enabled() -> bool:
    """Show the desk its own margin state. This is the half of Plan 16 that
    follows the standing rule (the AI decides); default ON."""
    return _truthy("LIQ_DESK_BRIEF", "true")


def reflex_enabled() -> bool:
    """T3 auto-flatten. Default **OFF**.

    This is the one rail in Plan 16 that acts without asking the desk, and an
    unproven auto-flatten is the most dangerous thing this change could ship.
    Nothing in production is near T3 (every live position sits at health ~1.0),
    so there is no urgency to enable it and no live sample to validate it
    against. Turn it on only after the replay in the plan doc's phase 3."""
    return _truthy("LIQ_REFLEX", "false")


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        return min(hi, max(lo, float(os.getenv(name, str(default)) or default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return min(hi, max(lo, int(os.getenv(name, str(default)) or default)))
    except (TypeError, ValueError):
        return default


def watch_interval_seconds() -> int:
    """Nominal cadence. Tighter than risk_watcher's 30s and the ~60s run
    control scan, because this is the one loop whose tail cost is the whole
    margin rather than one stop."""
    return _env_int("LIQ_WATCH_INTERVAL", 20, 5, 600)


def watch_interval_hot_seconds() -> int:
    """Cadence once any position is at T2 or worse."""
    return _env_int("LIQ_WATCH_INTERVAL_HOT", 5, 1, 120)


def deescalate_samples() -> int:
    """Consecutive better readings required before a tier relaxes.

    Not a nicety: without it a single wick flaps the tier, and a flapping tier
    wakes the desk repeatedly for the same position — which trains everyone,
    model and human, to ignore the alert."""
    return _env_int("LIQ_DEESCALATE_SAMPLES", 3, 1, 20)


def desk_deadline_seconds() -> int:
    """How long the desk gets to answer a T2 wake before T3 would take over."""
    return _env_int("LIQ_DESK_DEADLINE_S", 45, 5, 600)


# Tier thresholds. Expressed as env-overridable so a replay can sweep them
# without a redeploy; the defaults are the plan doc's.
def _t1_health() -> float:   return _env_float("LIQ_T1_HEALTH", 0.60, 0.0, 1.0)
def _t2_health() -> float:   return _env_float("LIQ_T2_HEALTH", 0.35, 0.0, 1.0)
def _t3_health() -> float:   return _env_float("LIQ_T3_HEALTH", 0.15, 0.0, 1.0)
def _t1_ttl_h() -> float:    return _env_float("LIQ_T1_TTL_HOURS", 6.0, 0.0, 720.0)
def _t2_ttl_h() -> float:    return _env_float("LIQ_T2_TTL_HOURS", 0.75, 0.0, 720.0)
def _t3_ttl_h() -> float:    return _env_float("LIQ_T3_TTL_HOURS", 0.0833, 0.0, 720.0)


# ── maintenance margin ─────────────────────────────────────────────────────
# Per-market maintenance-margin rate as a fraction of notional. These are
# order-of-magnitude figures for the SYNTHETIC model, not venue truth — a real
# broker reading always wins. Binance USD-M tiers MMR by notional from 0.4%
# upward; exchange futures use SPAN, which at retail size behaves like a low
# single-digit percentage; a fully-funded spot book cannot liquidate at all.
MMR_BY_MARKET: dict[str, float] = {
    "crypto":  0.005,
    "futures": 0.010,
    "forex":   0.005,
    "us-stock": 0.25,     # Reg-T style maintenance on a margin equity account
}
MMR_DEFAULT = 0.005


def maintenance_margin_rate(market: Optional[str]) -> float:
    return MMR_BY_MARKET.get((market or "").strip().lower(), MMR_DEFAULT)


# ── the geometry ───────────────────────────────────────────────────────────
def liquidation_price(entry: float, leverage: float, is_long: bool, *,
                      mmr: float = 0.0,
                      funding_per_unit: float = 0.0) -> Optional[float]:
    """Isolated-margin liquidation price.

    ``mmr = 0`` reproduces the shipped ``entry x (1 -+ 1/L)`` exactly, so the
    existing stop behaviour is a special case of this function rather than a
    parallel implementation. A positive mmr moves the line CLOSER (real
    liquidation arrives before the naive formula says), which is the whole
    point of carrying the term.

    Returns None when the position cannot liquidate: a fully-funded long
    (L = 1) has nothing to wipe. A fully-funded SHORT still can — price is
    unbounded above — which is why only the long case short-circuits.
    """
    try:
        e = float(entry)
        lev = max(1.0, float(leverage or 1.0))
    except (TypeError, ValueError):
        return None
    if e <= 0:
        return None
    span = 1.0 / lev - max(0.0, float(mmr or 0.0))
    # A maintenance requirement heavier than the whole posting means the
    # position is liquidatable on any adverse tick; clamp rather than invert.
    span = max(0.0, span)
    if is_long:
        if lev <= 1.0:
            return None
        return e * (1.0 - span) + float(funding_per_unit or 0.0)
    return e * (1.0 + span) - float(funding_per_unit or 0.0)


def cushion_price(entry: float, leverage: float, is_long: bool, *,
                  frac: float) -> Optional[float]:
    """The protective stop INSIDE the liquidation line — the line run_engine
    already ships as ``stop_event:liq_cushion``. Reproduced here so tests can
    assert the invariant ``health(cushion) == 1 - frac`` and catch any future
    drift between the two."""
    try:
        e = float(entry)
        lev = max(1.0, float(leverage or 1.0))
        c = float(frac)
    except (TypeError, ValueError):
        return None
    if e <= 0 or lev <= 1.0:
        return None
    return e * (1.0 - c / lev) if is_long else e * (1.0 + c / lev)


def health(entry: float, mark: float, liq: Optional[float],
           is_long: bool) -> Optional[float]:
    """Distance to a margin wipe, normalised: 1.0 at your entry, 0.0 at
    liquidation, >1 when the position is in profit.

    Normalising is what lets one set of bands govern MNQ at 3x and USDZAR at
    2x without per-market tuning. Returns None when the position cannot
    liquidate (nothing to measure distance to)."""
    if liq is None:
        return None
    try:
        e, m, liq_p = float(entry), float(mark), float(liq)
    except (TypeError, ValueError):
        return None
    denom = (e - liq_p) if is_long else (liq_p - e)
    if denom <= 0:
        return None
    return ((m - liq_p) if is_long else (liq_p - m)) / denom


def time_to_liquidation_hours(h: Optional[float],
                              velocity_per_hour: Optional[float]) -> Optional[float]:
    """Hours to health 0 at the current rate. None when not decaying —
    an improving or flat position has no meaningful ETA."""
    if h is None or velocity_per_hour is None:
        return None
    if velocity_per_hour >= -1e-9:
        return None
    return max(0.0, h / -velocity_per_hour)


# ── velocity ───────────────────────────────────────────────────────────────
# In-process, bounded, keyed by position id. Deliberately not persisted: a
# worker restart should re-learn the slope from fresh readings rather than
# resume acting on a trend measured before an outage it knows nothing about.
# 30 samples at the 20s nominal cadence is a 10-minute window. The earlier 12
# spanned only 4 minutes, and a 4-minute regression projected onto the 6-hour
# T1 threshold is a ~90x extrapolation — noisy enough to flap the tier on its
# own. Ten minutes is still a big extrapolation and the ttl figure should be
# read as an order of magnitude, not a countdown; that is a real limit of the
# method, stated rather than engineered away.
_SAMPLE_CAP = 30
_samples: dict[Any, list[tuple[float, float]]] = {}


def sample_max_age_seconds() -> int:
    """How far back the slope may reach. A worker that pauses and resumes must
    not fit a line across the outage — the gap is not a price move."""
    return _env_int("LIQ_SAMPLE_MAX_AGE_S", 1800, 60, 86400)


def record_sample(key: Any, h: Optional[float],
                  now: Optional[float] = None) -> None:
    """Append a health reading, dropping anything the slope must not see.

    Two guards, both found by printing a real series rather than by a passing
    test. Least squares has no defence against a bad abscissa: ONE sample with
    a wild timestamp dominates the fit and drags the slope to ~0, which
    silently suppresses the velocity warning at exactly the moment it matters.

      * out-of-order time resets the series — a timestamp older than the newest
        retained sample means the clock moved backwards or this key was reused
        by a different position, and neither is a trend.
      * samples older than sample_max_age_seconds() are pruned, so a resumed
        worker does not fit a line across its own downtime.
    """
    if h is None:
        return
    t = float(now if now is not None else time.time())
    series = _samples.setdefault(key, [])
    if series and t < series[-1][0]:
        series.clear()
    series.append((t, float(h)))
    cutoff = t - sample_max_age_seconds()
    if series[0][0] < cutoff:
        _samples[key] = series = [s for s in series if s[0] >= cutoff]
    if len(series) > _SAMPLE_CAP:
        del series[:len(series) - _SAMPLE_CAP]


def forget(key: Any) -> None:
    """Drop a closed position's series so a reopened one starts clean."""
    _samples.pop(key, None)


def velocity_per_hour(key: Any) -> Optional[float]:
    """Least-squares slope of health over the retained samples, per hour.

    Least squares rather than last-minus-first: a single wick at either end of
    the window would otherwise dominate, and the wick is exactly the artefact
    this is meant to see through."""
    series = _samples.get(key) or []
    if len(series) < 3:
        return None
    n = len(series)
    mt = sum(t for t, _ in series) / n
    mh = sum(h for _, h in series) / n
    var = sum((t - mt) ** 2 for t, _ in series)
    if var <= 0:
        return None
    cov = sum((t - mt) * (h - mh) for t, h in series)
    return (cov / var) * 3600.0


# ── classifier ─────────────────────────────────────────────────────────────
def classify_tier(h: Optional[float], ttl_hours: Optional[float]) -> str:
    """Raw tier from health and time-to-liquidation, worst-case of the two.

    A position can be far from the line but arriving fast, or close to it and
    stationary; both deserve attention and only one of them is visible to a
    pure threshold."""
    if h is None:
        # No liquidation risk to measure (fully-funded long). Not an alarm —
        # an unleveraged book genuinely cannot be wiped.
        return TIER_NOMINAL
    tier = TIER_NOMINAL
    if h < _t1_health():
        tier = TIER_WATCH
    if h < _t2_health():
        tier = TIER_DEFEND
    if h < _t3_health():
        tier = TIER_REFLEX
    if ttl_hours is not None:
        by_ttl = TIER_NOMINAL
        if ttl_hours < _t1_ttl_h():
            by_ttl = TIER_WATCH
        if ttl_hours < _t2_ttl_h():
            by_ttl = TIER_DEFEND
        if ttl_hours < _t3_ttl_h():
            by_ttl = TIER_REFLEX
        if _tier_rank(by_ttl) > _tier_rank(tier):
            tier = by_ttl
    return tier


def apply_hysteresis(previous: Optional[str], raw: str,
                     better_streak: int) -> tuple[str, int]:
    """Escalate immediately, de-escalate only after N consecutive better reads.

    Returns ``(effective_tier, new_streak)``. Escalation is never delayed —
    waiting for confirmation to get WORSE is how a fast move outruns its own
    alarm."""
    if previous is None:
        return raw, 0
    if _tier_rank(raw) >= _tier_rank(previous):
        return (raw, 0) if _tier_rank(raw) > _tier_rank(previous) else (previous, 0)
    streak = better_streak + 1
    if streak >= deescalate_samples():
        return raw, 0
    return previous, streak


# ── the oracle ─────────────────────────────────────────────────────────────
def margin_state(position: dict, *, cushion_frac: float,
                 broker_reading: Optional[dict] = None,
                 now: Optional[float] = None) -> Optional[dict]:
    """One position's margin facts, from a broker when available and a
    labelled model otherwise. Returns None for a position that cannot be
    liquidated at all."""
    try:
        qty = float(position.get("quantity") or 0)
        entry = float(position.get("entry_price") or 0)
    except (TypeError, ValueError):
        return None
    if qty == 0 or entry <= 0:
        return None
    mark = position.get("current_price")
    if mark is None:
        return None
    try:
        mark = float(mark)
        lev = max(1.0, float(position.get("leverage") or 1.0))
    except (TypeError, ValueError):
        return None
    if mark <= 0:
        return None

    is_long = qty > 0
    market = position.get("market")
    source = "synthetic"
    mmr = maintenance_margin_rate(market)
    liq: Optional[float]

    if broker_reading and broker_reading.get("liquidation_price"):
        try:
            liq = float(broker_reading["liquidation_price"])
            source = "broker"
            mmr = float(broker_reading.get("maintenance_margin") or mmr)
        except (TypeError, ValueError):
            liq = liquidation_price(entry, lev, is_long, mmr=mmr)
    else:
        liq = liquidation_price(entry, lev, is_long, mmr=mmr)

    if liq is None:
        return None

    h = health(entry, mark, liq, is_long)
    key = position.get("id", (position.get("symbol"), position.get("market")))
    record_sample(key, h, now=now)
    v = velocity_per_hour(key)
    ttl = time_to_liquidation_hours(h, v)

    notional = abs(qty) * mark
    return {
        "position_id": position.get("id"),
        "run_id": position.get("run_id"),
        "symbol": position.get("symbol"),
        "market": market,
        "side": "long" if is_long else "short",
        "quantity": qty,
        "entry_price": entry,
        "mark_price": mark,
        "leverage": lev,
        "mmr": mmr,
        "liq_price": liq,
        "cushion_price": cushion_price(entry, lev, is_long, frac=cushion_frac),
        "health": h,
        "velocity_per_hour": v,
        "ttl_hours": ttl,
        "tier": classify_tier(h, ttl),
        "notional_usd": notional,
        "margin_usd": notional / lev,
        "source": source,
        "confidence": "venue" if source == "broker" else "modelled",
    }


# ── the survival brief ─────────────────────────────────────────────────────
def survival_brief(state: Optional[dict], *,
                   has_run_stop: bool = True) -> str:
    """What the desk is told. Empty string when there is nothing to say.

    This is the half of Plan 16 that follows the standing rule: the daemon
    measures, the AI decides. The desk's prompt currently contains no leverage,
    no liquidation price and no margin at all — it cannot reason about survival
    because it does not know it is leveraged.
    """
    if not state or not desk_brief_enabled():
        return ""
    h = state.get("health")
    if h is None:
        return ""
    bits: list[str] = []
    src = "reported by your broker" if state.get("source") == "broker" else (
        "MODELLED from leverage and an assumed maintenance margin, not "
        "reported by a venue")
    bits.append(
        f"MARGIN STATE ({src}). Leverage {state['leverage']:.1f}x, isolated. "
        f"Liquidation at {state['liq_price']:,.4f}; mark {state['mark_price']:,.4f}. "
        f"Health {h:.2f} (1.0 = your entry price, 0.0 = margin fully wiped).")
    v = state.get("velocity_per_hour")
    if v is not None and abs(v) > 1e-4:
        bits.append(f"Health velocity {v:+.3f} per hour.")
    ttl = state.get("ttl_hours")
    if ttl is not None:
        bits.append(f"At that rate liquidation is about {ttl:.1f} hour(s) away."
                    if ttl >= 1 else
                    f"At that rate liquidation is about {ttl * 60:.0f} minute(s) away.")
    # The correction that matters most for the desk's action choice. A desk
    # that believes trimming buys distance will trim instead of exiting, and
    # trimming buys NO distance whatsoever — see the module docstring.
    bits.append(
        "Reducing this position cuts what you can lose but does NOT move the "
        "liquidation price — under isolated margin that price depends only on "
        "your entry and leverage, not on size. Only closing removes the risk.")
    if not has_run_stop:
        bits.append(
            "This run has no max-loss stop configured. Your decision to exit "
            "is the only thing between this position and a full margin wipe.")
    tier = state.get("tier")
    if tier == TIER_DEFEND:
        bits.append(
            f"You are in a DEFEND state. Answer within {desk_deadline_seconds()}s.")
    elif tier == TIER_REFLEX and reflex_enabled():
        bits.append("You are inside the reflex band; the risk daemon may close "
                    "this position without waiting for you.")
    return " ".join(bits) + "\n"


# ── T3 reflex ──────────────────────────────────────────────────────────────
def reflex_action(state: Optional[dict]) -> Optional[str]:
    """What the daemon does at T3, with no LLM call.

    Returns "flatten" or None. It is FLATTEN or nothing — see correction 1 in
    the module docstring: a partial reduce cannot move the liquidation price,
    so "reduce until healthy" is not an available action however much the plan
    doc wanted it to be. Deleveraging would work but the ledger has no
    add-margin primitive.
    """
    if not state or not reflex_enabled():
        return None
    if state.get("tier") != TIER_REFLEX:
        return None
    return "flatten"


# ── the watch tick ─────────────────────────────────────────────────────────
# Effective tier per position, with its de-escalation streak. Same rationale as
# the sample store: in-process and not persisted.
_tiers: dict[Any, tuple[str, int]] = {}


def _cushion_frac_default() -> float:
    """Read the cushion fraction run_engine already ships, so the two never
    drift. Imported lazily — liquidation.py must stay importable by tests that
    do not want run_engine's whole dependency tree."""
    try:
        from run_engine import _liq_cushion_frac
        return _liq_cushion_frac()
    except Exception:  # noqa: BLE001
        return 0.85


def leveraged_positions() -> list[dict]:
    """Every position that can be liquidated, attached to a run or not.

    Scoped on POSITIONS rather than runs on purpose: run_engine._evaluate_stop
    only ever sees a position owned by a *running* run, so prod positions 67
    (SOLUSDT, 2x) and 69 (USDZAR, 2x) — both run_id NULL — were liquidation-
    checked by nothing whatsoever. This is the only scope that covers the whole
    book: attached, orphaned, and manual alike.
    """
    from database import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, agent_id, run_id, symbol, market, quantity,
                      entry_price, current_price, price_updated_at, leverage
               FROM positions
               WHERE quantity <> 0 AND leverage > 1""")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def watch_tick(cushion_frac: Optional[float] = None,
               positions: Optional[list[dict]] = None) -> dict:
    """One pass of the liquidation watch. Pure of asyncio so it unit-tests.

    Returns counters plus the worst tier seen, which the caller uses to decide
    whether to drop to the hot cadence.
    """
    out: dict[str, Any] = {"checked": 0, "measured": 0, "escalations": 0,
                           "worst": TIER_NOMINAL, "reflex": 0, "states": []}
    if not oracle_enabled():
        return out
    frac = cushion_frac if cushion_frac is not None else _cushion_frac_default()
    rows = positions if positions is not None else leveraged_positions()
    live: set[Any] = set()
    for row in rows:
        out["checked"] += 1
        key = row.get("id")
        live.add(key)
        state = margin_state(row, cushion_frac=frac)
        if not state:
            continue
        out["measured"] += 1
        previous, streak = _tiers.get(key, (None, 0))
        effective, streak = apply_hysteresis(previous, state["tier"], streak)
        _tiers[key] = (effective, streak)
        state["tier_raw"] = state["tier"]
        state["tier"] = effective
        if previous is not None and _tier_rank(effective) > _tier_rank(previous):
            out["escalations"] += 1
            state["escalated_from"] = previous
        if _tier_rank(effective) > _tier_rank(out["worst"]):
            out["worst"] = effective
        if reflex_action(state):
            out["reflex"] += 1
        out["states"].append(state)
    # A closed position must not leave its tier and sample history behind, or a
    # reopened one inherits a trend measured on a book that no longer exists.
    for stale in [k for k in _tiers if k not in live]:
        _tiers.pop(stale, None)
        forget(stale)
    return out
