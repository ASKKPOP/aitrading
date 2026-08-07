"""Global symbol research engine (Plan 14 §4–§5).

One platform-global loop produces ranked "trade theses" that every fleet's
builder consumes — LLM cost is O(1 batched call)/refresh regardless of user
count. Three-stage funnel:

  Stage 0  universe   (~198 symbols across markets.automatable_markets())
  Stage 1  factor screen — deterministic, ZERO LLM, ZERO external calls
           (candles come through price_fetcher.get_daily_candles; every other
           input is a snapshot read with an age gate)
  Stage 2  ONE batched LLM thesis call over the ≤16 survivors, per-thesis
           deterministic clamps (THESIS_BOUNDS), rule-based fallback

The engine publishes batches to research_theses; fleets pick via
select_targets(). Concurrency: batch_id is deterministic per refresh window
and a research_batches sentinel row (UNIQUE) is inserted BEFORE any LLM call
— the Redis lock is only a best-effort fast path (cache.acquire_lock returns
None without Redis).

House pattern (agent_planner.py): the LLM proposes inside a deterministic
box; code disposes. Every thesis — fallback and negative-EV included — is a
journaled row.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import cache
import markets
from database import begin_write_transaction, get_db_connection
from order_params import RR_FLOOR

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ── env gates ────────────────────────────────────────────────────────────────

def research_enabled() -> bool:
    return os.getenv("FLEET_RESEARCH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def research_interval_seconds() -> int:
    return max(900, int(os.environ.get("FLEET_RESEARCH_INTERVAL", "3600")))


MAX_LLM_CALLS_PER_REFRESH = max(1, int(os.environ.get("FLEET_RESEARCH_MAX_LLM_CALLS", "2")))


# Stage 2 sizing (2026-07-28). The batch was ONE call over all survivors with
# max_tokens=2000. Measured on prod: one thesis object costs ~300 tokens, so 14
# survivors need ~4,200 and the reply was cut mid-object at candidate ~11 every
# single time. With no closing `]` the array parse returned [] and all 14 fell
# back — 2,099 of 2,099 theses ever written carry planner='fallback'. The LLM
# research layer had never once run. Two independent fixes, either sufficient:
# chunk small enough to finish, and salvage whatever did finish.
def _thesis_batch_size() -> int:
    try:
        return max(1, int(os.environ.get("FLEET_RESEARCH_BATCH_SIZE", "5")))
    except ValueError:
        return 5


def _thesis_max_tokens() -> int:
    try:
        return max(500, int(os.environ.get("FLEET_RESEARCH_MAX_TOKENS", "4000")))
    except ValueError:
        return 4000


def _chunked(items: "list[Any]", n: int) -> "list[list[Any]]":
    return [items[i:i + n] for i in range(0, len(items), n)]

# ── Stage 1 constants (unvalidated priors — journaled for later tuning) ─────

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "crypto":   {"technical": .30, "psych": .20, "social": .15, "news": .15, "flows": .10, "macro": .10},
    "us-stock": {"technical": .35, "news": .25, "macro": .15, "policy": .10, "social": .10, "psych": .05},
    "futures":  {"technical": .40, "macro": .35, "news": .15, "psych": .10},
    "forex":    {"technical": .40, "macro": .40, "news": .20},
}

# top-K per market keeps cross-market diversity (a hot crypto tape must not
# starve every other market out of the survivor set).
#
# SIZING (2026-08-06, cycles 97-101). These were 4/4/2/2 = TWELVE survivors,
# and a 10-slot fleet starved on that: measured on prod, batch research:496122
# yielded ZERO buildable candidates and the fleet fell from 8 running runs to
# 2 in a single day, unable to replenish. The arithmetic is unforgiving —
# every retire adds a 24h symbol cooldown, so the fleet's own losses subtract
# from the same pool it must rebuild from:
#
#     12 survivors − 4 not selectable (un-shortable spot / sub-R:R moves)
#                  − 5 in cooldown (retired earlier that day)
#                  − 2 already running
#                  − ZBTUSDT unpriceable            =  0 buildable
#
# The screen already SCORES the whole universe (129 candidates that day); this
# cap only decides how many of those already-paid-for scores survive. Raising
# it costs no extra candle fetches — it stops discarding 117 finished results.
#
# ⚠️ Stage 2 interaction: fresh theses are chunked (FLEET_RESEARCH_BATCH_SIZE,
# default 5) and capped at MAX_LLM_CALLS_PER_REFRESH (default 2), so at most
# ~10 survivors get a FRESH LLM thesis per refresh; beyond that they reuse an
# unchanged prior thesis or fall back. A wider survivor set therefore widens
# the fleet's choice without widening LLM spend — but watch `'llm': N` in the
# [SymbolResearch] log line: if it collapses toward zero the reuse/fallback
# mix has shifted and FLEET_RESEARCH_MAX_LLM_CALLS is the knob.
_SURVIVOR_DEFAULTS = {"crypto": 8, "us-stock": 8, "futures": 4, "forex": 4}


def _research_mandate() -> str:
    """The same purpose the desk is given, in the verb research works in.

    WHY (owner, 2026-08-07): "AI Analysis & Macro & Desk & all project target
    is make plus profit. Think always make plus profit."

    This prompt asked for a DESCRIPTION — direction, expected move, horizon,
    confidence — and never once said what the description is FOR. It picks the
    fleet's entire universe, so an analyst optimising for "what will move"
    rather than "what will pay" sets a ceiling on everything downstream that no
    desk skill can lift.

    The cost clause is not rhetoric: measured on this book the round trip is
    0.053% of notional, and one live run's largest favourable excursion was
    0.055% — exactly 1.0x its own fee, a "correct" thesis worth nothing.
    """
    return (
        "YOUR PURPOSE IS REALIZED PROFIT. Every thesis you emit is a PROFIT "
        "CASE, not a description of something that might move: a move that "
        "does not comfortably clear its own round-trip cost is not an "
        "opportunity, however well you have called it. Prefer fewer candidates "
        "you would actually pay to hold over a full list of plausible ones.\n\n")


def _survivors_per_market() -> dict[str, int]:
    """Per-market survivor cap, env-overridable so the pool can be tuned
    against fleet size without a deploy."""
    out: dict[str, int] = {}
    for market, default in _SURVIVOR_DEFAULTS.items():
        key = "FLEET_RESEARCH_SURVIVORS_" + market.replace("-", "_").upper()
        try:
            out[market] = max(1, int(os.environ.get(key, default)))
        except ValueError:
            out[market] = default
    return out


# Back-compat alias: the defaults as a plain dict.
SURVIVORS_PER_MARKET = dict(_SURVIVOR_DEFAULTS)

LIQUIDITY_FLOOR_USD = {"crypto": 5_000_000.0}   # curated lists elsewhere are exempt
MIN_CANDLES = 30

# volatility sweet spot per market class: %/day realized vol band that a run
# horizon can actually harvest (too low = nothing to trade, too high = SL churn)
VOL_BAND = {"crypto": (1.5, 5.0), "us-stock": (0.8, 2.5), "futures": (0.5, 2.5),
            "forex": (0.2, 1.2)}

SPREAD_PROXY_PCT = {"crypto": 0.05, "us-stock": 0.02, "futures": 0.02,
                    "forex": 0.02}

THESIS_BOUNDS = {
    "expected_move_pct_min": 0.3,
    "expected_move_vol_mult": 3.0,     # ≤ 3 × σ_daily × √horizon_days
    "horizon_hours": (4.0, 168.0),
    "confidence": (0.40, 0.95),
}

FEE_LEG_PCT = 0.1                      # matches fees.TRADE_FEE_RATE (0.1%/leg)
SNAPSHOT_AGE_FACTOR = 2.0              # snapshot older than 2× its cadence ⇒ None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(TS_FMT)


# ── Stage 0: universe ───────────────────────────────────────────────────────

def build_universe() -> list[dict[str, str]]:
    """[{symbol, market}] across automatable markets. Pure list assembly —
    the only network call is the crypto top-volume read, which fails soft."""
    out: list[dict[str, str]] = []
    autom = set(markets.automatable_markets())

    if "crypto" in autom:
        crypto: list[str] = []
        try:
            import top_symbols
            rows = top_symbols.get_top_symbols() or []
            crypto = [s.get("symbol") for s in rows[:50]
                      if isinstance(s, dict) and s.get("symbol")]
        except Exception:  # noqa: BLE001
            pass
        if not crypto:
            crypto = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        try:  # scanner candidates are crypto's discovery channel
            import scanner
            payload = scanner.get_scanner_payload() or {}
            for cand in (payload.get("candidates") or []):
                sym = cand.get("symbol") if isinstance(cand, dict) else None
                if sym and sym not in crypto:
                    crypto.append(sym)
        except Exception:  # noqa: BLE001
            pass
        # A symbol the venue does not list can never be priced, so it can
        # never be built — but it still eats a survivor slot and an LLM
        # thesis in every batch. ZBTUSDT did exactly that for two days.
        # Fails open: an unreadable listed-set leaves the universe intact.
        try:
            from price_fetcher import crypto_symbol_listed
            kept = [s for s in crypto if crypto_symbol_listed(s)]
            if kept:
                crypto = kept
        except Exception:  # noqa: BLE001
            pass
        out.extend({"symbol": s, "market": "crypto"} for s in crypto)

    import routes_market
    if "us-stock" in autom:
        stocks = list(routes_market.US_STOCK_SYMBOLS)
        try:
            import market_intel
            for s in market_intel._get_hot_us_stock_symbols():
                if s not in stocks:
                    stocks.append(s)
        except Exception:  # noqa: BLE001
            pass
        out.extend({"symbol": s, "market": "us-stock"} for s in stocks)
    if "futures" in autom:
        out.extend({"symbol": s, "market": "futures"} for s in routes_market.FUTURES_SYMBOLS)
    if "forex" in autom:
        out.extend({"symbol": s, "market": "forex"} for s in routes_market.FOREX_SYMBOLS)
    return out


# ── Stage 1: pure factor math (unit-testable, zero I/O) ─────────────────────

def candle_factors(candles: list[dict[str, Any]], market: str) -> Optional[dict[str, Any]]:
    """Deterministic technical factors from daily candles.

    Returns None when the hard data-sufficiency gate fails. All outputs are
    raw values; normalization happens across the candidate set.
    """
    closes = [float(c["close"]) for c in candles if c.get("close") is not None]
    vols = [float(c.get("volume") or 0) for c in candles]
    if len(closes) < MIN_CANDLES:
        return None
    last = closes[-1]

    def _ret(days: int) -> Optional[float]:
        if len(closes) <= days or closes[-1 - days] == 0:
            return None
        return (last / closes[-1 - days] - 1.0) * 100.0

    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None

    # realized vol: stdev of daily returns, %/day
    rets = [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes)) if closes[i - 1]]
    tail = rets[-14:]
    if len(tail) >= 5:
        mean = sum(tail) / len(tail)
        var = sum((r - mean) ** 2 for r in tail) / len(tail)
        vol_daily_pct = math.sqrt(var) * 100.0
    else:
        vol_daily_pct = None

    vol_ratio = None
    if len(vols) >= 8 and sum(vols[-8:-1]) > 0:
        vol_ratio = vols[-1] / (sum(vols[-8:-1]) / 7)

    dollar_vol = None
    if len(vols) >= 20:
        dollar_vol = sum(v * c for v, c in zip(vols[-20:], closes[-20:])) / 20

    return {
        "last": last,
        "mom_5d": _ret(5), "mom_20d": _ret(20),
        "sma20_dist": ((last / sma20 - 1.0) * 100.0) if sma20 else None,
        "sma50_dist": ((last / sma50 - 1.0) * 100.0) if sma50 else None,
        "vol_daily_pct": vol_daily_pct,
        "vol_ratio": vol_ratio,
        "dollar_vol_20d": dollar_vol,
    }


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def technical_subscore(f: dict[str, Any]) -> Optional[float]:
    """Blend candle factors into one technical subscore ∈ [−1, +1]."""
    parts: list[float] = []
    if f.get("mom_5d") is not None:
        parts.append(_clip(math.tanh(f["mom_5d"] / 8.0)))
    if f.get("mom_20d") is not None:
        parts.append(_clip(math.tanh(f["mom_20d"] / 20.0)))
    if f.get("sma20_dist") is not None:
        parts.append(_clip(f["sma20_dist"] / 10.0))
    if f.get("vol_ratio") is not None:
        parts.append(_clip((f["vol_ratio"] - 1.0) / 3.0))
    if not parts:
        return None
    return _clip(sum(parts) / len(parts))


def vol_fit_score(vol_daily_pct: Optional[float], market: str) -> Optional[float]:
    """Peak score inside the market's harvestable-vol band, decaying outside.
    Not directional — used as a multiplicative shaping term on |score|."""
    if vol_daily_pct is None:
        return None
    lo, hi = VOL_BAND.get(market, (0.5, 3.0))
    if lo <= vol_daily_pct <= hi:
        return 1.0
    if vol_daily_pct < lo:
        return max(0.2, vol_daily_pct / lo) if lo else 0.2
    return max(0.2, hi / vol_daily_pct)


def composite_score(subscores: dict[str, Optional[float]], market: str) -> dict[str, Any]:
    """Renormalize over AVAILABLE factor families with √coverage shrinkage.

    Missing factor == None, NEVER a fabricated 0 — thin markets compete on
    what they have without pretending sentiment data exists.
    """
    profile = WEIGHT_PROFILES.get(market) or WEIGHT_PROFILES["crypto"]
    avail = {k: v for k, v in subscores.items() if v is not None and k in profile}
    wsum = sum(profile[k] for k in avail)
    if wsum <= 0:
        return {"eps_raw": None, "coverage": 0.0, "rank_score": None}
    eps_raw = sum(profile[k] * avail[k] for k in avail) / wsum
    coverage = wsum  # Σ weights of available families (profile sums to 1.0)
    return {"eps_raw": _clip(eps_raw), "coverage": coverage,
            "rank_score": _clip(eps_raw) * math.sqrt(coverage)}


def apply_gates(score: float, *, event_window: bool, regime_blocks_longs: bool,
                direction: str, session_open: bool) -> float:
    """Multiplicative veto gates (never additive — these are amplitude events)."""
    if event_window:
        return 0.0
    if regime_blocks_longs and direction == "long":
        return 0.0
    return score * (1.0 if session_open else 0.85)


def expected_value(expected_move_pct: float, confidence: float, horizon_hours: float,
                   vol_daily_pct: Optional[float], market: str) -> dict[str, float]:
    """Fee-adjusted, horizon-normalized, vol-scaled EV (§4.5)."""
    round_trip = 2 * FEE_LEG_PCT + SPREAD_PROXY_PCT.get(market, 0.05)
    ev_pct = expected_move_pct * confidence - round_trip
    ev_per_day = ev_pct / max(horizon_hours / 24.0, 1e-6)
    denom = max(vol_daily_pct or 1.0, 0.1)
    return {"ev_pct": ev_pct, "ev_per_day_pct": ev_per_day,
            "final_score": ev_per_day / denom}


# An invalidation level further than this from the current price is not a level,
# it is a recalled number — the model naming $30,500 for BTC at $63,361.
INVALIDATION_MAX_DIST = 0.5

# ...and one too CLOSE is not a level either. Handed `last`, the model began
# answering with `last`: batches research:496034/:496035 (2026-08-03) put BTC's
# short invalidation 0.03% above spot and SOL's 0.07%, so ordinary noise voided
# the thesis within the hour. The floor follows the tape — half a day's realized
# volatility — because 0.5% is noise on 4%/day crypto and a real level on
# 0.2%/day forex. The flat floor only applies when vol is unknown.
INVALIDATION_MIN_DIST = 0.003
INVALIDATION_MIN_VOL_MULT = 0.5

# Numbers that are plainly not prices: percentages, and durations/periods.
_PCT_OR_PERIOD = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:%|percent|[-‑\s]*(?:min|minute|hour|hr|h|day|d|"
    r"week|wk|month|session|bar|candle)s?\b)", re.I)
_NUMBER = re.compile(r"\$?\s*(\d[\d,]*(?:\.\d+)?)")

_RELATIVE_INVALIDATION = {
    "short": "Break above the recent swing high, or a flip to positive 5-day momentum.",
    "long": "Break below the recent swing low, or a flip to negative 5-day momentum.",
}


def invalidation_is_coherent(text: str, direction: str, last: Optional[float],
                             vol_daily_pct: Optional[float] = None) -> bool:
    """Does an absolute price level in `text` sit where it could actually fire?

    Three ways it cannot. **Wrong side**: a short dies on a break UP and a long
    on a break DOWN, so a short's level must be above the current price and a
    long's below it — a level on the wrong side is breached the moment it is
    written (prod runs 933/934/938, 2026-08-03). **Too far**: a level beyond
    `INVALIDATION_MAX_DIST` is a recalled number, not a level. **Too close**: a
    level inside noise distance is a restatement of spot and ordinary drift
    voids the thesis within the hour, which lands the desk in the same place by
    a different route.

    Relative wording ("above the 20-day moving average") carries no number and is
    always coherent. Percentages and durations are not price levels. With no
    `last` there is nothing to check against, so we never guess.
    """
    if not text or last is None or last <= 0:
        return True
    min_dist = INVALIDATION_MIN_DIST
    if vol_daily_pct:
        min_dist = max(min_dist, INVALIDATION_MIN_VOL_MULT * vol_daily_pct / 100.0)
    scrubbed = _PCT_OR_PERIOD.sub(" ", text)
    for match in _NUMBER.finditer(scrubbed):
        try:
            level = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        if level <= 0:
            continue
        dist = abs(level / last - 1.0)
        if dist > INVALIDATION_MAX_DIST or dist < min_dist:
            return False
        if direction == "short" and level < last:
            return False
        if direction == "long" and level > last:
            return False
    return True


def invalidation_distance_pct(text: str, last: Optional[float]) -> Optional[float]:
    """Distance from `last` to the nearest absolute level in `text`, in percent.

    Feasibility wants the level a desk would actually lean its stop on — the
    nearest one. Returns None when there is no numeric level (relative wording),
    no `last`, or every number is a percentage/period rather than a price, so a
    caller can only ever gate on a level it can actually see.
    """
    if not text or last is None or last <= 0:
        return None
    best: Optional[float] = None
    scrubbed = _PCT_OR_PERIOD.sub(" ", text)
    for match in _NUMBER.finditer(scrubbed):
        try:
            level = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        if level <= 0:
            continue
        dist = abs(level / last - 1.0) * 100.0
        if best is None or dist < best:
            best = dist
    return best


def thesis_rr_feasible(thesis: dict, last: Optional[float]) -> bool:
    """Can this thesis EVER clear the house R:R floor at the desk?

    The desk's stop leans on the thesis's own invalidation level and its honest
    target is capped by the thesis's own expected move, so a thesis whose
    invalidation sits farther than expected_move_pct / RR_FLOOR away is
    unexpressible: prod 948 (ZC long, 2.5% move vs a stop ~3% away) burned 8
    idle cycles refusing to bracket it and retired; 947/943 idled on the same
    geometry, and the 2026-08-04 batch had HG long 2.0% with its level 4.3%
    away marked selectable — loaded to rebuild the same idle run. Judged at
    build time because the desk-side skills are right to refuse: the fix is to
    stop selecting the unexpressible, not to teach the desk looser stops.
    A thesis with no extractable level passes — there is nothing to judge.
    """
    dist = invalidation_distance_pct(str(thesis.get("invalidation") or ""), last)
    if dist is None:
        return True
    try:
        move = float(thesis.get("expected_move_pct") or 0)
    except (TypeError, ValueError):
        return True
    if move <= 0:
        return True
    return move >= RR_FLOOR * dist


def thesis_market_type(market: str, direction: str) -> str:
    """The venue a thesis will be written to.

    Only crypto has a futures book in this system, so a short anywhere else
    lands on spot — which has no inventory to sell.
    """
    return "futures" if (direction == "short" and market == "crypto") else "spot"


def thesis_is_expressible(market: str, direction: str) -> bool:
    """Can the venue this thesis lands on actually hold the position?

    `markets.supports_short()` answers at the MARKET level — forex is
    supports_short=True — but the run is created with a market_type, and a spot
    book cannot short regardless of market. Prod 2026-08-03: run 938 carried a
    forex short on market_type 'spot' and spent ten cycles reporting "Short
    thesis matches recent yen rally but entry is unfavourable and we cannot
    short, so we hold." Run 928 did the same on crypto spot the day before.
    Neither could ever have traded.
    """
    return direction != "short" or thesis_market_type(market, direction) != "spot"


def clamp_thesis(raw: dict[str, Any], market: str, vol_daily_pct: Optional[float],
                 momentum_sign: float,
                 last: Optional[float] = None) -> dict[str, Any]:
    """Deterministic THESIS_BOUNDS clamps — the LLM chooses inside the box."""
    direction = str(raw.get("direction") or "").strip().lower()
    if direction not in ("long", "short") or not markets.supports_short(market):
        if direction != "long":
            direction = "long" if momentum_sign >= 0 or not markets.supports_short(market) else "short"
    h_lo, h_hi = THESIS_BOUNDS["horizon_hours"]
    try:
        horizon = float(raw.get("horizon_hours") or 24)
    except (TypeError, ValueError):
        horizon = 24.0
    horizon = max(h_lo, min(h_hi, horizon))
    c_lo, c_hi = THESIS_BOUNDS["confidence"]
    try:
        confidence = float(raw.get("confidence") or c_lo)
    except (TypeError, ValueError):
        confidence = c_lo
    confidence = max(c_lo, min(c_hi, confidence))
    vol = max(vol_daily_pct or 1.0, 0.1)
    move_cap = THESIS_BOUNDS["expected_move_vol_mult"] * vol * math.sqrt(horizon / 24.0)
    try:
        move = float(raw.get("expected_move_pct") or 0)
    except (TypeError, ValueError):
        move = 0.0
    move = max(THESIS_BOUNDS["expected_move_pct_min"], min(move_cap, abs(move)))
    # floor at 4dp — plain round() can nudge the value past the vol cap
    move = math.floor(move * 10000) / 10000
    invalidation = str(raw.get("invalidation") or "")[:300]
    if not invalidation_is_coherent(invalidation, direction, last, vol_daily_pct):
        logger.warning("thesis invalidation incoherent (last=%s, dir=%s): %r",
                       last, direction, invalidation)
        invalidation = _RELATIVE_INVALIDATION[direction]
    return {
        "direction": direction,
        "expected_move_pct": move,
        "horizon_hours": round(horizon, 2),
        "confidence": round(confidence, 4),
        "thesis": str(raw.get("thesis") or "")[:1000],
        "risks": str(raw.get("risks") or "")[:500],
        "invalidation": invalidation,
    }


def fallback_thesis(market: str, vol_daily_pct: Optional[float],
                    momentum_sign: float, score_percentile: float) -> dict[str, Any]:
    """No-LLM / parse-failure thesis (`planner='fallback'`) — degrades, never blanks."""
    vol = max(vol_daily_pct or 1.0, 0.1)
    direction = "short" if (momentum_sign < 0 and markets.supports_short(market)) else "long"
    return clamp_thesis({
        "direction": direction,
        "expected_move_pct": 1.5 * vol,
        "horizon_hours": 48,
        "confidence": 0.45 + 0.25 * max(0.0, min(1.0, score_percentile)),
        "thesis": "rule-based: momentum + volume + volatility fit",
    }, market, vol_daily_pct, momentum_sign)


# ── snapshot readers (fail-soft, age-gated — NEVER a live external call) ─────

def _read_overlays() -> dict[str, Any]:
    """Market-level overlay inputs from cached/snapshotted modules only."""
    overlays: dict[str, Any] = {"event_window": False, "regime_blocks_longs": False,
                                "policy": {}, "fng": None, "cnn_fng": None}
    try:
        import market_events
        overlays["event_window"] = market_events.active_event_window() is not None
    except Exception:  # noqa: BLE001
        pass
    try:
        import regime
        snap = regime.evaluate_market_regime(persist=False) or {}
        overlays["regime_blocks_longs"] = snap.get("allow_new_buys") is False
        overlays["regime"] = snap.get("regime")
        overlays["crypto_composite"] = snap.get("crypto_composite")
    except Exception:  # noqa: BLE001
        pass
    try:
        import policy_feed
        overlays["policy"] = policy_feed.get_policy_signals()
    except Exception:  # noqa: BLE001
        pass
    return overlays


# ── Stage 1 driver ──────────────────────────────────────────────────────────

def screen_universe(universe: list[dict[str, str]],
                    fetch_candles=None,
                    overlays: Optional[dict[str, Any]] = None,
                    pace_seconds: float = 0.0) -> list[dict[str, Any]]:
    """Score every candidate; return survivors (top-K per market).

    fetch_candles is injectable for tests; defaults to the cooldown-subordinate
    price_fetcher primitive. pace_seconds spreads the cold sweep so a cache-cold
    refresh cannot burst Yahoo (cross-process protection — §4.2).
    """
    if fetch_candles is None:
        import price_fetcher
        fetch_candles = lambda s, m: price_fetcher.get_daily_candles(s, m, days=60)  # noqa: E731
    overlays = overlays if overlays is not None else _read_overlays()

    scored: list[dict[str, Any]] = []
    for cand in universe:
        sym, market = cand["symbol"], cand["market"]
        try:
            candles = fetch_candles(sym, market) or []
        except Exception:  # noqa: BLE001
            candles = []
        if pace_seconds:
            time.sleep(pace_seconds)
        f = candle_factors(candles, market)
        if f is None:
            continue
        floor = LIQUIDITY_FLOOR_USD.get(market)
        if floor and (f.get("dollar_vol_20d") or 0) < floor:
            continue
        subs: dict[str, Optional[float]] = {
            "technical": technical_subscore(f),
            "psych": None, "social": None, "news": None,
            "flows": None, "macro": None,
        }
        if market in ("crypto", "us-stock") and overlays.get("policy", {}).get(market):
            # attention flag only — direction comes from the LLM reading titles
            subs["policy"] = 0.2
        comp = composite_score(subs, market)
        if comp["rank_score"] is None:
            continue
        vfit = vol_fit_score(f.get("vol_daily_pct"), market)
        direction = "long" if (f.get("mom_5d") or 0) >= 0 else "short"
        session_open = True
        try:
            session_open = markets.is_market_open(market)
        except Exception:  # noqa: BLE001
            pass
        gated = apply_gates(abs(comp["rank_score"]) * (vfit or 0.5),
                            event_window=bool(overlays.get("event_window"))
                            and market in ("us-stock", "futures", "forex"),
                            regime_blocks_longs=bool(overlays.get("regime_blocks_longs"))
                            and market == "crypto",
                            direction=direction, session_open=session_open)
        if gated <= 0:
            continue
        scored.append({
            "symbol": sym, "market": market,
            "factors": f, "subscores": subs,
            "eps_raw": comp["eps_raw"], "coverage": comp["coverage"],
            "screen_score": gated, "momentum_sign": 1.0 if direction == "long" else -1.0,
            "session_open": session_open,
        })

    survivors: list[dict[str, Any]] = []
    for market, k in _survivors_per_market().items():
        pool = sorted((s for s in scored if s["market"] == market),
                      key=lambda s: s["screen_score"], reverse=True)
        survivors.extend(pool[:k])
    return survivors


# ── Stage 2: one batched LLM thesis call ────────────────────────────────────

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _salvage_objects(text: str) -> list[dict[str, Any]]:
    """Every complete {...} in a truncated array, by brace balance.

    A reply cut off mid-object has no closing `]`, so the whole-array parse
    returns nothing and EVERY symbol in the batch falls back — which is what
    happened on prod for seven days straight. The objects that DID arrive are
    perfectly good; take them and let the tail fall back on its own.
    String-aware so a brace inside a thesis sentence cannot unbalance the scan.
    """
    out: list[dict[str, Any]] = []
    depth = start = 0
    in_str = esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except (ValueError, TypeError):
                        continue
                    if isinstance(obj, dict):
                        out.append(obj)
    return out


def _parse_thesis_array(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    m = _JSON_ARRAY_RE.search(text)
    if m:
        try:
            arr = json.loads(m.group(0))
        except (ValueError, TypeError):
            pass
        else:
            if isinstance(arr, list):
                return [x for x in arr if isinstance(x, dict)]
    # Truncated or otherwise unparseable as a whole — salvage what completed.
    return _salvage_objects(text)


def generate_theses(survivors: list[dict[str, Any]],
                    generate_text=None) -> list[dict[str, Any]]:
    """One batched LLM call over all survivors; per-symbol clamp + fallback.

    Thesis reuse: a survivor whose Stage-1 inputs are unchanged since the last
    batch keeps its previous thesis (zero LLM on quiet tapes).
    """
    if generate_text is None:
        import llm_client
        generate_text = llm_client.generate_text

    reuse: dict[tuple[str, str], dict[str, Any]] = {}
    fresh_needed: list[dict[str, Any]] = []
    for s in survivors:
        prev = _previous_thesis(s["market"], s["symbol"])
        cur_key = _stage1_key(s)
        # Reuse keeps a stored thesis verbatim, so an incoherent one would
        # survive every quiet-tape refresh (a frozen weekend us-stock price
        # holds stage1_key steady indefinitely). Re-derive those instead.
        if prev and prev.get("stage1_key") == cur_key and prev.get("planner") == "llm" \
                and invalidation_is_coherent(
                    (prev.get("thesis") or {}).get("invalidation") or "",
                    (prev.get("thesis") or {}).get("direction") or "",
                    s["factors"].get("last"),
                    s["factors"].get("vol_daily_pct")):
            reuse[(s["market"], s["symbol"])] = prev
        else:
            fresh_needed.append(s)

    # Plan 21 P3: one compact backdrop line for crypto candidates, from the
    # composite CACHE only (screen_universe's overlay read just warmed it —
    # a cold cache renders nothing rather than fetching on this path).
    composite_line = ""
    try:
        import regime as _regime
        comp = _regime.evaluate_crypto_composite(cached_only=True)
        if comp and comp.get("score") is not None:
            composite_line = (
                f"CRYPTO MARKET BACKDROP: composite {comp['score']}/100 "
                f"({comp['zone']}; 100 = broad risk-on health). Use as "
                "backdrop for crypto candidates only — judge each candidate "
                "on its own data.\n")
    except Exception:  # noqa: BLE001
        composite_line = ""

    parsed: dict[tuple[str, str], dict[str, Any]] = {}
    for chunk in _chunked(fresh_needed, _thesis_batch_size()):
        rows = []
        for s in chunk:
            f = s["factors"]
            row = {
                "symbol": s["symbol"], "market": s["market"],
                "last": f.get("last"),
                "mom_5d": f.get("mom_5d"), "mom_20d": f.get("mom_20d"),
                "vol_daily_pct": f.get("vol_daily_pct"), "vol_ratio": f.get("vol_ratio"),
                "eps_raw": s["eps_raw"],
            }
            # Plan 21 P6: FMP earnings proximity for us-stock candidates.
            # Key-gated and fail-soft — without FMP_API_KEY the field is
            # simply absent and the prompt is byte-identical to before.
            if s["market"] == "us-stock":
                try:
                    import fmp_feed
                    dte = fmp_feed.days_to_earnings(s["symbol"])
                    if dte is not None:
                        row["days_to_earnings"] = dte
                except Exception:  # noqa: BLE001
                    pass
            rows.append(row)
        prompt = (
            _research_mandate() +
            "You are a trading research analyst. For EACH candidate below, emit one JSON "
            "object with keys: symbol, market, direction ('long'|'short'), "
            "expected_move_pct (percent, e.g. 2.5 means 2.5%), horizon_hours (4-168), "
            "confidence (0.40-0.95), thesis (<=2 sentences), risks, invalidation. "
            "Keep thesis, risks and invalidation to one short sentence each. "
            "`last` is the candidate's CURRENT price — use it, never a price you "
            "recall. If invalidation names an absolute level it MUST be able to "
            "fire: ABOVE `last` for a short, BELOW `last` for a long, within 50% "
            "of `last`, and at least half of `vol_daily_pct` away from `last` — "
            "a level sitting on top of the current price is a restatement of it, "
            "and ordinary noise voids the thesis within the hour. An absolute "
            "level must ALSO sit within expected_move_pct / 2 of `last`: the "
            "desk trades at 2:1 reward-to-risk, so a stop farther than half "
            "the expected move can never be bracketed and the thesis will be "
            "discarded. When unsure of "
            "the number, describe the level relatively (e.g. 'below the recent "
            "swing low') instead of inventing one. "
            + ("`days_to_earnings` counts calendar days to that us-stock "
               "candidate's next earnings print — weigh holding-through-print "
               "risk in the horizon and confidence you assign. "
               if any("days_to_earnings" in r for r in rows) else "")
            + "Respond with ONLY a JSON array covering every candidate.\n\n"
            + (composite_line if any(r["market"] == "crypto" for r in rows) else "")
            + f"CANDIDATES:\n{json.dumps(rows, default=str)}"
        )
        for _attempt in range(MAX_LLM_CALLS_PER_REFRESH):
            try:
                text = generate_text(prompt, max_tokens=_thesis_max_tokens(),
                                     temperature=0.3, tier="decision")
            except Exception:  # noqa: BLE001
                text = None
            got = _parse_thesis_array(text or "")
            if got:
                for item in got:
                    key = (str(item.get("market") or ""), str(item.get("symbol") or ""))
                    parsed[key] = item
                # A salvaged partial covers only part of the chunk. Retrying
                # the whole chunk would re-bill the symbols already in hand, so
                # accept and let the remainder take the rule-based fallback —
                # a partial batch is strictly better than the all-or-nothing
                # behaviour this replaces.
                break

    out: list[dict[str, Any]] = []
    n = max(len(survivors), 1)
    for rank, s in enumerate(survivors):
        key = (s["market"], s["symbol"])
        percentile = 1.0 - rank / n
        vol = s["factors"].get("vol_daily_pct")
        if key in reuse:
            thesis, planner = dict(reuse[key]["thesis"]), "llm"
        elif key in parsed:
            thesis, planner = clamp_thesis(parsed[key], s["market"], vol,
                                           s["momentum_sign"],
                                           last=s["factors"].get("last")), "llm"
        else:
            thesis, planner = fallback_thesis(s["market"], vol, s["momentum_sign"],
                                              percentile), "fallback"
        ev = expected_value(thesis["expected_move_pct"], thesis["confidence"],
                            thesis["horizon_hours"], vol, s["market"])
        session_factor = 1.0 if s.get("session_open", True) else 0.85
        expressible = thesis_is_expressible(s["market"], thesis["direction"])
        feasible = thesis_rr_feasible(thesis, s["factors"].get("last"))
        out.append({**s, "thesis": thesis, "planner": planner,
                    "ev_per_day_pct": ev["ev_per_day_pct"],
                    "final_score": ev["final_score"] * session_factor,
                    "selectable": 1 if (ev["ev_pct"] > 0 and expressible
                                        and feasible) else 0,
                    "stage1_key": _stage1_key(s)})
    out.sort(key=lambda t: t["final_score"], reverse=True)
    return out


def _stage1_key(s: dict[str, Any]) -> str:
    """Reuse key: same last candle + composite within 0.1σ ⇒ inputs unchanged."""
    f = s["factors"]
    return f"{f.get('last')}|{round((s.get('eps_raw') or 0) * 10)}"


def _previous_thesis(market: str, symbol: str) -> Optional[dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT thesis, risks, invalidation, direction, expected_move_pct,
                      horizon_hours, confidence, planner, factor_scores_json
               FROM research_theses WHERE market = ? AND symbol = ?
               ORDER BY id DESC LIMIT 1""", (market, symbol))
        row = cur.fetchone()
        if not row:
            return None
        try:
            fs = json.loads(row["factor_scores_json"] or "{}")
        except (ValueError, TypeError):
            fs = {}
        return {
            "planner": row["planner"],
            "stage1_key": fs.get("stage1_key"),
            "thesis": {
                "direction": row["direction"],
                "expected_move_pct": float(row["expected_move_pct"] or 0),
                "horizon_hours": float(row["horizon_hours"] or 24),
                "confidence": float(row["confidence"] or 0.4),
                "thesis": row["thesis"] or "", "risks": row["risks"] or "",
                "invalidation": row["invalidation"] or "",
            },
        }
    finally:
        conn.close()


# ── persistence + refresh driver ────────────────────────────────────────────

def current_batch_id(now: Optional[float] = None) -> str:
    """Deterministic per refresh window — the dedupe key (§4.3)."""
    now = time.time() if now is None else now
    return f"research:{int(now // research_interval_seconds())}"


def claim_batch(batch_id: str) -> bool:
    """Insert the sentinel row FIRST. False ⇒ another runner owns this window
    (abort before any LLM spend). Works with or without Redis."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        begin_write_transaction(cur)
        cur.execute("INSERT INTO research_batches (batch_id, created_at) VALUES (?, ?)",
                    (batch_id, _now_iso()))
        conn.commit()
        return True
    except Exception:  # noqa: BLE001 — unique violation on either dialect
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def persist_batch(batch_id: str, theses: list[dict[str, Any]]) -> int:
    expires = datetime.now(timezone.utc).timestamp() + 2 * research_interval_seconds()
    expires_iso = datetime.fromtimestamp(expires, timezone.utc).strftime(TS_FMT)
    n = 0
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        begin_write_transaction(cur)
        for t in theses:
            th = t["thesis"]
            market_type = thesis_market_type(t["market"], th["direction"])
            fs = {"factors": t["factors"], "subscores": t["subscores"],
                  "coverage": t["coverage"], "stage1_key": t.get("stage1_key")}
            cur.execute(
                """INSERT INTO research_theses
                   (batch_id, market, symbol, market_type, direction,
                    factor_scores_json, thesis, risks, invalidation,
                    expected_move_pct, horizon_hours, confidence,
                    ev_per_day_pct, final_score, selectable, planner, llm_model,
                    created_at, expires_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (batch_id, t["market"], t["symbol"], market_type, th["direction"],
                 json.dumps(fs, default=str), th["thesis"], th["risks"],
                 th["invalidation"], th["expected_move_pct"], th["horizon_hours"],
                 th["confidence"], round(t["ev_per_day_pct"], 6),
                 round(t["final_score"], 6), t["selectable"], t["planner"], None,
                 _now_iso(), expires_iso))
            n += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return n


def prune_batches(keep: int = 200) -> None:
    """Two-step cutoff (MySQL rejects LIMIT-in-IN-subquery / DELETE-from-target)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        begin_write_transaction(cur)
        cur.execute(
            "SELECT batch_id FROM research_batches ORDER BY batch_id DESC LIMIT 1 OFFSET ?",
            (keep,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return
        cutoff = row["batch_id"]
        cur.execute("DELETE FROM research_theses WHERE batch_id <= ?", (cutoff,))
        cur.execute("DELETE FROM research_batches WHERE batch_id <= ?", (cutoff,))
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        logger.info("[SymbolResearch] prune failed: %s", exc)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        conn.close()


def refresh_research_batch(generate_text=None, fetch_candles=None) -> dict[str, Any]:
    """One full refresh. Returns a summary dict (never raises)."""
    batch_id = current_batch_id()
    # Redis lock is a best-effort fast path (None without Redis); the
    # deterministic batch sentinel below is the actual guarantee.
    redis_lock = None
    try:
        redis_lock = cache.acquire_lock("fleet_research:refresh", timeout_seconds=300)
        if redis_lock is not None and not redis_lock.acquire(blocking=False):
            return {"batch_id": batch_id, "skipped": "redis_lock_held"}
    except Exception:  # noqa: BLE001
        redis_lock = None
    if not claim_batch(batch_id):
        return {"batch_id": batch_id, "skipped": "batch_exists"}
    try:
        universe = build_universe()
        # pace the sweep: spread across ~60% of the interval when cache-cold
        pace = 0.0
        if len(universe) > 0:
            pace = min(1.0, (research_interval_seconds() * 0.6) / max(len(universe), 1))
        survivors = screen_universe(universe, fetch_candles=fetch_candles,
                                    pace_seconds=0.0 if fetch_candles else pace)
        theses = generate_theses(survivors, generate_text=generate_text)
        n = persist_batch(batch_id, theses)
        prune_batches()
        return {"batch_id": batch_id, "universe": len(universe),
                "survivors": len(survivors), "persisted": n,
                "llm": sum(1 for t in theses if t["planner"] == "llm")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SymbolResearch] refresh crashed: %s", exc)
        return {"batch_id": batch_id, "error": str(exc)}
    finally:
        if redis_lock is not None:
            try:
                redis_lock.release()
            except Exception:  # noqa: BLE001
                pass


# ── selection (builder-side) ────────────────────────────────────────────────

# Per market (a correlated asset class), the majority direction may lead the
# minority by at most this many in the diversity pass — so a single broad tape
# move can't sweep the whole sleeve of one market in lockstep (Finding L2).
_DIR_IMBALANCE_MAX = 1


def _dir_balance_enabled() -> bool:
    """Default-on kill switch for the directional-balance guard."""
    return os.getenv("FLEET_DIR_BALANCE", "true").strip().lower() in {"1", "true", "yes", "on"}


def _select_from_eligible(eligible: list[dict[str, Any]], n: int,
                          dir_balance: bool = True) -> list[dict[str, Any]]:
    """Two-pass pick from pre-filtered eligible theses (highest score first).

    Pass 1 is a PREFERENCE pass: caps ceil(n/2) per market AND, when
    dir_balance is on, keeps each market directionally balanced (majority −
    minority ≤ _DIR_IMBALANCE_MAX) so a correlated sleeve can't stack one way.
    Pass 2 fills any remaining slots from leftovers regardless of market OR
    direction — reaching N always outranks balance (a bearish-only batch still
    fills). Non long/short directions are never constrained.
    """
    per_market_cap = max(1, math.ceil(n / 2))
    picked: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    dir_counts: dict[tuple[str, str], int] = {}
    for t in eligible:
        m = t["market"]
        if counts.get(m, 0) >= per_market_cap:
            continue
        d = str(t.get("direction") or "").lower()
        if dir_balance and d in ("long", "short"):
            other = "short" if d == "long" else "long"
            if (dir_counts.get((m, d), 0) + 1) - dir_counts.get((m, other), 0) > _DIR_IMBALANCE_MAX:
                continue
        picked.append(t)
        counts[m] = counts.get(m, 0) + 1
        if d in ("long", "short"):
            dir_counts[(m, d)] = dir_counts.get((m, d), 0) + 1
        if len(picked) >= n:
            return picked
    chosen = {(t["market"], t["symbol"]) for t in picked}
    for t in eligible:
        if (t["market"], t["symbol"]) in chosen:
            continue
        picked.append(t)
        if len(picked) >= n:
            break
    return picked


def select_targets(cursor, agent_id: int, n: int,
                   exclude: Optional[set[tuple[str, str]]] = None,
                   markets_scope: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Top-n selectable theses from the latest non-expired batch, minus:
    (a) symbols with any non-terminal run for this agent (exclusivity),
    (b) fleet_symbol_cooldowns rows (the feedback loop's retire list),
    (c) caller-supplied exclusions; with per-market diversity ceil(n/2)."""
    now = _now_iso()
    # Newest batch that actually HAS live theses — an empty refresh (LLM or
    # feed failure) must not blank the universe while the previous batch's
    # theses are still unexpired (2026-07-26: batch 495847 came up empty and
    # every fleet replacement went no_candidates for an hour).
    cursor.execute(
        "SELECT batch_id FROM research_theses WHERE selectable = 1 "
        "AND expires_at > ? ORDER BY batch_id DESC LIMIT 1", (now,))
    row = cursor.fetchone()
    if not row:
        return []
    batch_id = row["batch_id"]
    cursor.execute(
        """SELECT * FROM research_theses
           WHERE batch_id = ? AND selectable = 1 AND expires_at > ?
           ORDER BY final_score DESC""", (batch_id, now))
    theses = [dict(r) for r in cursor.fetchall()]
    if not theses:
        return []

    cursor.execute(
        """SELECT market, symbol FROM trading_runs
           WHERE agent_id = ? AND status IN ('armed','running','paused','stopping')""",
        (agent_id,))
    busy = {(r["market"], r["symbol"]) for r in cursor.fetchall()}
    cursor.execute(
        "SELECT market, symbol FROM fleet_symbol_cooldowns WHERE agent_id = ? AND until_ts > ?",
        (agent_id, now))
    busy |= {(r["market"], r["symbol"]) for r in cursor.fetchall()}
    if exclude:
        busy |= set(exclude)

    # Diversity + directional balance are PREFERENCES, not hard caps: pass 1
    # caps ceil(n/2) per market and keeps each market directionally balanced;
    # pass 2 fills remaining slots from leftovers regardless (perpetual N
    # outranks spread — see _select_from_eligible).
    eligible = [t for t in theses
                if (t["market"], t["symbol"]) not in busy
                and (not markets_scope or t["market"] in markets_scope)]
    return _select_from_eligible(eligible, n, _dir_balance_enabled())


def latest_batch_payload(limit: int = 40) -> dict[str, Any]:
    """Read API for the frontend 'why these symbols' panel."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT batch_id, created_at FROM research_batches "
                    "ORDER BY batch_id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return {"batch_id": None, "theses": []}
        cur.execute(
            """SELECT market, symbol, market_type, direction, thesis, risks,
                      invalidation, expected_move_pct, horizon_hours, confidence,
                      ev_per_day_pct, final_score, selectable, planner,
                      factor_scores_json, created_at, expires_at
               FROM research_theses WHERE batch_id = ?
               ORDER BY final_score DESC LIMIT ?""", (row["batch_id"], limit))
        theses = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["factor_scores"] = json.loads(d.pop("factor_scores_json") or "{}")
            except (ValueError, TypeError):
                d["factor_scores"] = {}
            theses.append(d)
        return {"batch_id": row["batch_id"], "created_at": row["created_at"],
                "theses": theses}
    finally:
        conn.close()


# ── background loop (registry key 'symbol_research', role 'settlement' — it
#    must share a process with run cycles so the Yahoo cooldown check works) ──

async def symbol_research_loop() -> None:
    import asyncio

    await asyncio.sleep(5)
    while True:
        if research_enabled():
            try:
                summary = await asyncio.to_thread(refresh_research_batch)
                print(f"[SymbolResearch] {summary}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("[SymbolResearch] loop crashed: %s", exc)
        await asyncio.sleep(research_interval_seconds())
