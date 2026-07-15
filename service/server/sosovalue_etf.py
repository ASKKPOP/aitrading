"""
sosovalue_etf.py — Real US spot-ETF net flows via the SoSoValue open API
(signal-collection plan, card 08 upgrade).

The existing ETF-flow snapshot estimates direction from price x volume of the
spot-BTC-ETF tickers (flagged is_estimated). This module replaces the
*summary* with real aggregate dollar flows when SOSOVALUE_API_KEY is set:
daily total net inflow, 5-day sum, cumulative net inflow, total net assets,
and the current inflow/outflow streak — for BTC and ETH ETF complexes.

Endpoint (verified live 2026-07-15):
  GET {base}/etfs/summary-history?symbol=btc&country_code=us
  header x-soso-api-key: <key>
  -> {"code":0,"data":[{"date","total_net_inflow","total_value_traded",
                        "total_net_assets","cum_net_inflow"}, ...]}  newest-first

Fails soft: any error returns None and the caller keeps the estimated proxy.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

logger = logging.getLogger("sosovalue_etf")

_TIMEOUT = 12.0
SOSOVALUE_BASE_URL = os.getenv("SOSOVALUE_BASE_URL",
                               "https://openapi.sosovalue.com/openapi/v1").rstrip("/")


def _api_key() -> str:
    return os.getenv("SOSOVALUE_API_KEY", "").strip()


def sosovalue_enabled() -> bool:
    return bool(_api_key())


def fetch_summary_history(symbol: str = "btc", country_code: str = "us",
                          days: int = 10) -> list[dict[str, Any]]:
    """Newest-first daily aggregate flow rows for one ETF complex."""
    r = requests.get(
        f"{SOSOVALUE_BASE_URL}/etfs/summary-history",
        params={"symbol": symbol, "country_code": country_code},
        headers={"x-soso-api-key": _api_key()},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    body = r.json() or {}
    if body.get("code") != 0:
        raise RuntimeError(f"sosovalue error code={body.get('code')} msg={body.get('message') or body.get('msg')}")
    rows = body.get("data") or []
    rows.sort(key=lambda x: x.get("date") or "", reverse=True)
    return rows[:days]


def _streak(rows: list[dict[str, Any]]) -> int:
    """Consecutive days (from latest) with the same flow sign. Positive value
    for an inflow streak, negative for an outflow streak, 0 when flat."""
    if not rows:
        return 0
    first = float(rows[0].get("total_net_inflow") or 0)
    if first == 0:
        return 0
    sign = 1 if first > 0 else -1
    n = 0
    for row in rows:
        v = float(row.get("total_net_inflow") or 0)
        if v == 0 or (v > 0) != (sign > 0):
            break
        n += 1
    return n * sign


def _complex_block(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not rows:
        return None
    latest = rows[0]
    latest_flow = float(latest.get("total_net_inflow") or 0)
    return {
        "latest_net_inflow_usd": round(latest_flow, 0),
        "flow_5d_usd": round(sum(float(r.get("total_net_inflow") or 0) for r in rows[:5]), 0),
        "cum_net_inflow_usd": round(float(latest.get("cum_net_inflow") or 0), 0),
        "total_net_assets_usd": round(float(latest.get("total_net_assets") or 0), 0),
        "streak_days": _streak(rows),
        "as_of": latest.get("date"),
    }


def _fmt_musd(v: float) -> str:
    return f"${abs(v) / 1e6:,.0f}M"


def build_real_flow_summary() -> Optional[dict[str, Any]]:
    """Real aggregate-flow summary, or None when unavailable (caller keeps
    the estimated proxy). BTC decides the headline direction; ETH rides along."""
    if not sosovalue_enabled():
        return None

    btc = eth = None
    try:
        btc = _complex_block(fetch_summary_history("btc"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("sosovalue btc flow fetch failed: %s", exc)
    try:
        eth = _complex_block(fetch_summary_history("eth"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("sosovalue eth flow fetch failed: %s", exc)

    if not btc:
        return None

    flow = btc["latest_net_inflow_usd"]
    streak = btc["streak_days"]
    if flow > 0:
        direction = "inflow"
        summary_text = f"US spot BTC ETFs took in {_fmt_musd(flow)} on {btc['as_of']}"
        summary_text_zh = f"美国现货 BTC ETF 于 {btc['as_of']} 净流入 {_fmt_musd(flow)}"
    elif flow < 0:
        direction = "outflow"
        summary_text = f"US spot BTC ETFs shed {_fmt_musd(flow)} on {btc['as_of']}"
        summary_text_zh = f"美国现货 BTC ETF 于 {btc['as_of']} 净流出 {_fmt_musd(flow)}"
    else:
        direction = "mixed"
        summary_text = f"US spot BTC ETF flows were flat on {btc['as_of']}"
        summary_text_zh = f"美国现货 BTC ETF 于 {btc['as_of']} 资金基本持平"
    if abs(streak) >= 3:
        word = "inflows" if streak > 0 else "outflows"
        summary_text += f" — {abs(streak)} consecutive days of {word}"

    return {
        "direction": direction,
        "summary": summary_text,
        "summary_zh": summary_text_zh,
        "is_estimated": False,
        "source": "sosovalue",
        "btc": btc,
        "eth": eth,
    }
