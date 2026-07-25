"""Personal watch functions (Plan 06 C3).

A user defines conditions over LIVE metrics; when one crosses, an alert fires
through alerts.py (in-app always, email/SMS per opt-in). Supported metrics:

    price            last perp price for `symbol`            (OKX)
    fear_greed       Fear & Greed index 0..100               (alternative.me)
    kimchi_premium   Upbit vs global BTC premium %           (cross-market)
    whale_net_flow   ETH exchange net flow, USD (+ = inflow) (whale feed)
    funding_rate     perp funding rate % for `symbol`        (OKX)
    rsi              RSI(14) for `symbol`                    (quant)
    basis            (swap-spot)/spot % for `symbol`         (OKX)

Every metric is REAL — a metric whose source is unavailable evaluates to None
and the watch simply does not fire (never a fabricated value). Each watch has
a cooldown (default 60 min) so a hovering condition can't spam.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

METRICS = ("price", "fear_greed", "kimchi_premium", "whale_net_flow",
           "funding_rate", "rsi", "basis")
COMPARATORS = ("above", "below")
NEEDS_SYMBOL = ("price", "funding_rate", "rsi", "basis")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────── metric resolution (all real) ───────────────────────────

def resolve_metric(metric: str, symbol: Optional[str] = None) -> Optional[float]:
    """Current value of a metric, or None when its source is unavailable.
    Fail-soft per metric — never invents a number."""
    try:
        if metric == "price":
            from crypto_feed import fetch_ticker
            return float(fetch_ticker(symbol)["last_price"])
        if metric == "fear_greed":
            from psych_feed import get_psych_payload
            fng = (get_psych_payload() or {}).get("fear_greed")
            return float(fng["value"]) if fng and fng.get("value") is not None else None
        if metric == "kimchi_premium":
            from cross_market import build_cross_market_payload, cross_market_enabled
            if not cross_market_enabled():
                return None
            kimchi = (build_cross_market_payload() or {}).get("kimchi")
            return float(kimchi["premium_pct"]) if kimchi else None
        if metric == "whale_net_flow":
            from whale_feed import get_whale_payload
            w = get_whale_payload()
            if not w.get("available"):
                return None
            v = (w.get("totals") or {}).get("eth_net_flow_usd")
            return float(v) if v is not None else None
        if metric == "funding_rate":
            from crypto_feed import fetch_funding_rate
            return float(fetch_funding_rate(symbol)["funding_rate"]) * 100.0
        if metric == "rsi":
            from quant_crypto import build_crypto_analysis
            a = build_crypto_analysis(symbol) or {}
            v = a.get("rsi")
            return float(v) if v is not None else None
        if metric == "basis":
            from crypto_feed import fetch_spot_ticker, fetch_ticker
            swap = float(fetch_ticker(symbol)["last_price"])
            spot = float(fetch_spot_ticker(symbol)["last_price"])
            return (swap - spot) / spot * 100.0 if spot > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("watch metric %s(%s) unavailable: %s", metric, symbol, exc)
    return None


def crosses(value: float, comparator: str, threshold: float) -> bool:
    return value > threshold if comparator == "above" else value < threshold


def _cooling_down(watch: dict[str, Any]) -> bool:
    last = watch.get("last_fired_at")
    if not last:
        return False
    try:
        fired = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if fired.tzinfo is None:
            fired = fired.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return _now() - fired < timedelta(minutes=int(watch.get("cooldown_min") or 60))


def run_watch_tick() -> dict[str, Any]:
    """Evaluate every enabled watch once; fire alerts on crossings.
    Metric values are cached per (metric, symbol) within the tick so 50 watches
    on the same metric cost one fetch. Fail-soft per watch."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_watches WHERE enabled = 1")
        watches = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    if not watches:
        return {"checked": 0, "fired": 0}

    cache: dict[tuple, Optional[float]] = {}
    fired = 0
    for w in watches:
        if _cooling_down(w):
            continue
        key = (w["metric"], w.get("symbol") or "")
        if key not in cache:
            cache[key] = resolve_metric(w["metric"], w.get("symbol"))
        value = cache[key]
        if value is None:
            continue  # source unavailable — never fire on a missing metric
        if not crosses(value, w["comparator"], float(w["threshold"])):
            continue
        try:
            unit = "%" if w["metric"] in ("kimchi_premium", "funding_rate", "basis") else ""
            where = f" {w['symbol']}" if w.get("symbol") else ""
            from alerts import send_alert
            send_alert(w["agent_id"], "custom", "watch",
                       {"name": w["name"], "metric": w["metric"], "where": where,
                        "value": f"{value:,.2f}", "unit": unit,
                        "comparator": w["comparator"],
                        "threshold": f"{float(w['threshold']):,.2f}"},
                       dedupe_key=f"watch:{w['id']}:{int(_now().timestamp() // 3600)}")
            fired += 1
            conn = get_db_connection()
            conn.execute("UPDATE user_watches SET last_fired_at = ? WHERE id = ?",
                         (_now_iso(), w["id"]))
            conn.commit()
            conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.exception("watch %s failed to fire: %s", w["id"], exc)
    return {"checked": len(watches), "fired": fired}
