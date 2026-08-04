"""US market breadth feed — keyless public CSV (tradermonty mining).

Mined from tradermonty/claude-trading-skills (MIT): its market-breadth
skills run on a freely published S&P 500 breadth dataset (GitHub Pages,
updated daily). Per the standing method-only rule the source's scoring
engine stays out; what lands here is the DATA the us-stock desks lack —
the catalogue already teaches distribution counting and follow-through
confirmation, but every desk read only its own symbol's candles, with no
market-wide evidence to apply the methods to. This feed supplies the
fraction of S&P 500 stocks above their 200-/50-day MAs plus the dataset's
own trend and bearish flags, advisory only.

Degraded mode is the contract: a fetch failure serves the last good
snapshot (stale beats absent), a cold failure or a dataset older than
MAX_AGE_DAYS returns None, and nothing here may ever raise into a trading
cycle. The CSV is one individual's pipeline, so continuity is not
guaranteed — BREADTH_FEED_ENABLED=0 kills the feed outright.
"""

from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_CSV_URL = ("https://tradermonty.github.io/market-breadth-analysis/"
                   "market_breadth_data.csv")

# The pipeline lags the market by a trading day or two; a week of silence
# means the source has stopped and the snapshot must not keep advising.
MAX_AGE_DAYS = 7

_CACHE_TTL_SECONDS = 6 * 3600.0
_cache: dict[str, Any] = {"at": 0.0, "row": None}


def breadth_enabled() -> bool:
    return os.getenv("BREADTH_FEED_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on")


def _csv_url() -> str:
    return os.getenv("BREADTH_CSV_URL", "").strip() or DEFAULT_CSV_URL


def _today() -> datetime:
    return datetime.now(timezone.utc)


def _fetch() -> Optional[dict[str, Any]]:
    resp = requests.get(_csv_url(), timeout=15)
    resp.raise_for_status()
    last: Optional[dict[str, str]] = None
    for raw in csv.DictReader(resp.text.splitlines()):
        if (raw.get("Date") or "").strip():
            last = raw
    if last is None:
        return None
    row = {
        "date": last["Date"].strip(),
        "above_ma200": float(last["Breadth_Index_Raw"]),
        "above_ma200_8ema": float(last["Breadth_Index_8MA"]),
        "above_ma200_200ema": float(last["Breadth_Index_200MA"]),
        # 1 = long-term breadth trend rising, -1 = falling, 0 = bootstrap.
        "trend200": int(float(last["Breadth_200MA_Trend"])),
        "bearish": (last.get("Bearish_Signal") or "").strip().lower() == "true",
        "above_ma50": float(last["Breadth_50_Index_Raw"]),
    }
    # The source's "pink zone": long-term trend falling AND short-term
    # breadth below the long-term average — a structural defensive regime
    # distinct from the momentum-based bearish flag.
    row["pink_zone"] = (row["trend200"] == -1
                        and row["above_ma200_8ema"] < row["above_ma200_200ema"])
    return row


def latest_breadth(force: bool = False) -> Optional[dict[str, Any]]:
    """Latest breadth snapshot, or None when disabled, unavailable, or stale."""
    if not breadth_enabled():
        return None
    now = time.monotonic()
    row = _cache["row"]
    if force or row is None or now - _cache["at"] >= _CACHE_TTL_SECONDS:
        try:
            row = _fetch()
            _cache["row"] = row
            _cache["at"] = now
        except Exception as exc:  # noqa: BLE001
            logger.debug("breadth feed unavailable: %s", exc)
            row = _cache["row"]
    if not row:
        return None
    try:
        latest = datetime.strptime(row["date"], "%Y-%m-%d").date()
    except ValueError:
        return None
    if (_today().date() - latest).days > MAX_AGE_DAYS:
        return None
    return row
