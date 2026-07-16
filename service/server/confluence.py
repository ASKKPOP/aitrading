"""Confluence engine (parameter-upgrade plan Phase 1).

Deterministic B1–B6 / S1–S6 checklist from the verified hybrid framework
(docs/research/parameters/): act only when independent-ish conditions agree.
No LLM anywhere in this module. Display/API-only until the Phase-4 flip —
the automation gate consumes it only when CONFLUENCE_GATE_ENABLED.

Buy checklist                            Sell checklist
  B1 price > MA200                         S1 price < MA200
  B2 12-1 momentum > 0                     S2 12-1 momentum < 0
  B3 technical trigger + volume ≥ min      S3 bearish trigger + volume ≥ min
  B4 sentiment ≥ 0 or recovering,          S4 euphoria: F&G ≥ 80, or ≥ 75
     no negative news z-spike                 with L/S ≥ 2.0
  B5 fear recovering: F&G < 30 with        S5 shock/policy state unresolved
     Δ3d > 0, or shock cleared ≤ 72h          (no expiry while flagged)
  B6 no macro event within 24h             S6 SL/TP/vol-target hit — positional,
                                              enforced by the watcher, not scored

Null semantics: a condition whose data is unavailable is None — it never
counts as satisfied and the threshold stays /6, so missing data makes the
engine MORE conservative for entries. Every null carries a reason so a dead
feed is distinguishable from market conditions (observability requirement).

Vetoes override counts: a negative news z-spike within 24h vetoes buys
("sentiment collapsing on real news beats a stale chart"); an active macro
release window vetoes both sides.

The count IS the score. No probability-formatted confidence is emitted —
calibrated accuracy estimates come later from telemetry buckets, never from
an invented linear map (verification panel, statistics lens).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import strategy_config as scfg

logger = logging.getLogger(__name__)

BUY_CUTOFFS = {"crypto": 2.0, "us-stock": 3.0}
SELL_CUTOFFS = {"crypto": -2.0, "us-stock": -3.0}

_NEWS_CATEGORY = {"crypto": "crypto", "us-stock": "equities"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ─────────────────────────── pure condition math ───────────────────────────

def compute_conditions(
    market: str,
    *,
    analysis: Optional[dict[str, Any]],
    sentiment: Optional[dict[str, Any]],
    psych: Optional[dict[str, Any]],
    shock_hist: Optional[list[dict[str, Any]]],
    next_event_hours: Optional[float],
    event_window_active: Optional[bool],
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Compute every condition from already-fetched data. Pure — no I/O.

    analysis:  quant_crypto / stock-analysis payload (price_above_ma200,
               momentum_12_1_pct, signal_score, volume_ratio, long_short_ratio)
    sentiment: {"tilt": float, "n": int, "prev_tilt": float|None} or None
    psych:     psych_feed payload ({"fear_greed": {...}, "spikes": [...],
               "shock": [...], "created_at": ...}) or None
    shock_hist: psych_feed.shock_history() rows or None
    next_event_hours: hours until the next macro event, None = calendar unavailable
    event_window_active: True/False, None = unavailable
    """
    now = now or _utc_now()
    market = (market or "crypto").lower()
    conditions: dict[str, Optional[bool]] = {}
    nulls: dict[str, str] = {}
    vetoes: list[str] = []

    def set_cond(key: str, value: Optional[bool], null_reason: str = "") -> None:
        conditions[key] = value
        if value is None:
            nulls[key] = null_reason or "data unavailable"

    # ── B1/S1 — price vs MA200, B2/S2 — 12-1 momentum ──────────────────────
    above_ma200 = (analysis or {}).get("price_above_ma200")
    if above_ma200 is None:
        set_cond("B1", None, "MA200 unavailable (needs 200+ daily closes)")
        set_cond("S1", None, "MA200 unavailable (needs 200+ daily closes)")
    else:
        set_cond("B1", bool(above_ma200))
        set_cond("S1", not above_ma200)

    momentum = (analysis or {}).get("momentum_12_1_pct")
    if momentum is None:
        set_cond("B2", None, "12-1 momentum unavailable (needs ~1y of closes)")
        set_cond("S2", None, "12-1 momentum unavailable (needs ~1y of closes)")
    else:
        set_cond("B2", momentum > 0)
        set_cond("S2", momentum < 0)  # momentum == 0 satisfies neither (half-open)

    # ── B3/S3 — technical trigger WITH volume confirmation ─────────────────
    score = (analysis or {}).get("signal_score")
    volume_ratio = (analysis or {}).get("volume_ratio")
    buy_cutoff = BUY_CUTOFFS.get(market, 2.0)
    sell_cutoff = SELL_CUTOFFS.get(market, -2.0)
    if score is None:
        set_cond("B3", None, "technical score unavailable")
        set_cond("S3", None, "technical score unavailable")
    elif volume_ratio is None:
        # research: no volume = no trade, EVER — an unconfirmable trigger is null
        set_cond("B3", None, "volume ratio unavailable — trigger unconfirmable")
        set_cond("S3", None, "volume ratio unavailable — trigger unconfirmable")
    else:
        volume_ok = volume_ratio >= scfg.volume_confirm_min()
        set_cond("B3", score >= buy_cutoff and volume_ok)
        set_cond("S3", score <= sell_cutoff and volume_ok)

    # ── B4 — sentiment non-negative or recovering, no negative spike ───────
    psych_age_ok = False
    negative_spike_active = False
    if psych and psych.get("available"):
        created = _parse_ts(psych.get("created_at"))
        psych_age_ok = created is not None and (now - created).total_seconds() <= 24 * 3600
        category = _NEWS_CATEGORY.get(market)
        negative_spike_active = psych_age_ok and any(
            s.get("spike") and s.get("direction") == "negative"
            and (s.get("category") == category or category is None)
            for s in psych.get("spikes", [])
        )

    tilt = (sentiment or {}).get("tilt")
    prev_tilt = (sentiment or {}).get("prev_tilt")
    if tilt is None:
        set_cond("B4", None, "crowd sentiment unavailable (StockTwits)")
    elif negative_spike_active:
        set_cond("B4", False)
    else:
        recovering = prev_tilt is not None and tilt > prev_tilt
        set_cond("B4", tilt >= 0 or recovering)

    if negative_spike_active:
        vetoes.append("buy_veto: negative news sentiment spike in "
                      f"{_NEWS_CATEGORY.get(market, 'market')} within 24h")

    # ── B5 — fear recovering (crypto F&G / shock cleared) ──────────────────
    if market != "crypto":
        set_cond("B5", None, "crypto fear index not applicable to this market")
    else:
        fng = (psych or {}).get("fear_greed") if (psych or {}).get("available") else None
        legs: list[bool] = []
        if fng and fng.get("value") is not None and fng.get("delta_3d") is not None:
            legs.append(fng["value"] < scfg.fng_fear_max() and fng["delta_3d"] > 0)
        current_shocks = [s for s in (psych or {}).get("shock", []) if s.get("shock")] \
            if (psych or {}).get("available") else []
        if shock_hist is not None:
            had_shock = any(entry.get("shocks") for entry in shock_hist)
            legs.append(had_shock and not current_shocks)
        if not legs:
            set_cond("B5", None, "psych feed unavailable (F&G / shock history)")
        else:
            set_cond("B5", any(legs))

    # ── B6 — no macro event within the confluence window ───────────────────
    if next_event_hours is None:
        set_cond("B6", None, "event calendar unavailable")
    else:
        set_cond("B6", next_event_hours > scfg.event_confluence_hours())
    if event_window_active:
        vetoes.append("entry_veto: macro release window active (both sides)")

    # ── S4 — euphoria extreme ───────────────────────────────────────────────
    if market != "crypto":
        set_cond("S4", None, "crypto fear index not applicable to this market")
    else:
        fng = (psych or {}).get("fear_greed") if (psych or {}).get("available") else None
        ls_ratio = (analysis or {}).get("long_short_ratio")
        if not fng or fng.get("value") is None:
            set_cond("S4", None, "F&G unavailable")
        else:
            value = fng["value"]
            primary = value >= scfg.fng_euphoria_min()
            secondary = (ls_ratio is not None
                         and value >= scfg.fng_euphoria_ls_min()
                         and ls_ratio >= scfg.ls_euphoria_min())
            set_cond("S4", primary or secondary)

    # ── S5 — shock/policy state unresolved (no expiry while flagged) ───────
    if market != "crypto":
        set_cond("S5", None, "shock proxy not applicable to this market")
    elif not (psych or {}).get("available"):
        set_cond("S5", None, "psych feed unavailable")
    else:
        active = [s for s in psych.get("shock", []) if s.get("shock")]
        set_cond("S5", bool(active) or negative_spike_active)

    # ── S6 — positional, watcher-enforced ───────────────────────────────────
    set_cond("S6", None, "positional — enforced by the SL/TP watcher, not scored")

    buy_confluence = sum(1 for k in ("B1", "B2", "B3", "B4", "B5", "B6") if conditions.get(k) is True)
    sell_confluence = sum(1 for k in ("S1", "S2", "S3", "S4", "S5", "S6") if conditions.get(k) is True)

    if conditions.get("B1") and conditions.get("B2"):
        direction_bias = "long"
    elif conditions.get("S1") and conditions.get("S2"):
        direction_bias = "short"
    else:
        direction_bias = "none"

    return {
        "buy_confluence": buy_confluence,
        "sell_confluence": sell_confluence,
        "threshold": scfg.confluence_min(),
        "conditions": conditions,
        "nulls": nulls,
        "vetoes": vetoes,
        "direction_bias": direction_bias,
    }


# ─────────────────────────── data-fetching wrapper ───────────────────────────

def _fetch_sentiment(symbol: str, market: str) -> Optional[dict[str, Any]]:
    """Current StockTwits tilt + previous tilt from factor_snapshots (B4's
    'recovering' branch needs a prior reading)."""
    try:
        from analysis_sources import fetch_stocktwits_sentiment
        st_symbol = f"{symbol}.X" if market == "crypto" else symbol
        st = fetch_stocktwits_sentiment(st_symbol)
    except Exception:  # noqa: BLE001
        return None
    if not st or not st.get("messages_scored"):
        return None
    tilt = (st["bullish"] - st["bearish"]) / st["messages_scored"]

    prev_tilt = None
    try:
        from database import get_db_connection
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT stocktwits_tilt FROM factor_snapshots
                   WHERE symbol = ? AND stocktwits_tilt IS NOT NULL
                   ORDER BY created_at DESC, id DESC LIMIT 1 OFFSET 1""",
                (symbol,))
            row = cur.fetchone()
            if row is not None:
                prev_tilt = row["stocktwits_tilt"]
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass
    return {"tilt": tilt, "n": st["messages_scored"], "prev_tilt": prev_tilt}


def evaluate_confluence(
    symbol: str,
    market: str = "crypto",
    *,
    analysis: Optional[dict[str, Any]] = None,
    psych: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Full confluence read for one symbol. Pre-fetched analysis/psych payloads
    may be passed in (fusion shares them across symbols); everything else is
    fetched here, fail-soft per source."""
    symbol = (symbol or "").strip().upper()
    market = (market or "crypto").lower()

    if analysis is None and market == "crypto":
        try:
            from quant_crypto import build_crypto_analysis, quant_crypto_enabled
            if quant_crypto_enabled():
                analysis = build_crypto_analysis(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.debug("confluence: quant unavailable for %s: %s", symbol, exc)

    if psych is None:
        try:
            from psych_feed import get_psych_payload, psych_feed_enabled
            if psych_feed_enabled():
                psych = get_psych_payload()
        except Exception as exc:  # noqa: BLE001
            logger.debug("confluence: psych unavailable: %s", exc)

    shock_hist = None
    try:
        from psych_feed import psych_feed_enabled, shock_history
        if psych_feed_enabled():
            shock_hist = shock_history(hours=scfg.shock_clear_hours())
    except Exception as exc:  # noqa: BLE001
        logger.debug("confluence: shock history unavailable: %s", exc)

    sentiment = _fetch_sentiment(symbol, market)

    next_event_hours: Optional[float] = None
    event_window_active: Optional[bool] = None
    try:
        from market_events import active_event_window, upcoming_events
        nxt = upcoming_events(limit=1)
        next_event_hours = float(nxt[0]["hours_until"]) if nxt else float("inf")
        event_window_active = active_event_window() is not None
    except Exception as exc:  # noqa: BLE001
        logger.debug("confluence: event calendar unavailable: %s", exc)

    result = compute_conditions(
        market,
        analysis=analysis,
        sentiment=sentiment,
        psych=psych,
        shock_hist=shock_hist,
        next_event_hours=next_event_hours,
        event_window_active=event_window_active,
    )
    result.update({
        "symbol": symbol,
        "market": market,
        "as_of": _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "count-based; nulls never satisfy; no probability confidence emitted",
    })
    return result
