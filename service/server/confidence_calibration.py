"""confidence_calibration.py — the desk's confidence, scored against reality.

Steps 0+1 of the calibration plan (2026-08-01, docs/reports/
2026-08-01-confidence-calibration-solution.html). Measured problem: the run
engine gates on a verbalized confidence scalar that is quantized (3 values
cover 63% of 1,522 decisions), uncalibrated (claims 55–75%, delivers 0–33%)
and INVERTED at the top (conf ≥ 0.70 wins 14% against a 21% base rate).

Step 0 — scoreboard. brier_score() + calibration_curve() computed nightly
from the journaled decisions and their realized outcomes, logged as one
`[Calibration]` line. Pure measurement; every later idea is judged by
whether Brier falls.

Step 1 — Platt map. fit_platt() learns p(win) = sigmoid(a·conf + b) from the
platform's OWN closed-run outcomes (Platt, not isotonic: n≈100 and isotonic
overfits small samples). calibrated_confidence() exposes the mapped
probability behind RUN_CONF_CALIBRATED — off by default, "shadow" logs the
mapped value alongside the raw one, "apply" is reserved for the gate change
which ships separately. Fail-soft everywhere: any error returns None and the
caller keeps the raw scalar.

Deliberately dependency-free (plain-Python Newton iterations on 2 params —
98 points make this trivial) and read-only against the ledger.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from database import get_db_connection

logger = logging.getLogger(__name__)

# A fit on fewer outcomes than this is noise wearing a coefficient.
MIN_FIT_N = 30
_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_CACHE_TTL_SECONDS = 600

CURVE_BUCKETS = ((0.0, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 1.01))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def calibrated_mode() -> str:
    """off | shadow | apply — read at call time so tests/env can flip it."""
    mode = (os.getenv("RUN_CONF_CALIBRATED", "off") or "off").strip().lower()
    return mode if mode in ("off", "shadow", "apply") else "off"


# ── pure scoring functions ──────────────────────────────────────────────────

def brier_score(pairs: "list[tuple[float, bool]]") -> Optional[float]:
    """Mean squared error of claimed probability vs outcome. Lower is better;
    always quoting the base rate scores (base·(1−base))."""
    if not pairs:
        return None
    return sum((p - (1.0 if won else 0.0)) ** 2 for p, won in pairs) / len(pairs)


def calibration_curve(pairs: "list[tuple[float, bool]]") -> "list[dict[str, Any]]":
    """Win rate by confidence bucket — the claimed-vs-delivered table."""
    out = []
    for lo, hi in CURVE_BUCKETS:
        rows = [(p, won) for p, won in pairs if lo <= p < hi]
        out.append({
            "lo": lo, "hi": min(hi, 1.0), "n": len(rows),
            "mean_conf": round(sum(p for p, _ in rows) / len(rows), 4) if rows else None,
            "win_rate": round(sum(1 for _, won in rows if won) / len(rows), 4) if rows else None,
        })
    return out


def fit_platt(pairs: "list[tuple[float, bool]]", iterations: int = 200,
              lr: float = 1.0) -> "Optional[tuple[float, float]]":
    """Fit p(win) = sigmoid(a·conf + b) by Newton-damped gradient descent on
    log-loss. Returns (a, b) or None when the sample is too thin or single-
    class (a fit with no losers — or no winners — is a constant, not a map)."""
    n = len(pairs)
    wins = sum(1 for _, won in pairs if won)
    if n < MIN_FIT_N or wins == 0 or wins == n:
        return None
    # Platt's target smoothing: pulls targets off exactly 0/1, which both
    # regularizes the small sample and stops b from running away.
    t_pos = (wins + 1.0) / (wins + 2.0)
    t_neg = 1.0 / ((n - wins) + 2.0)
    a, b = 0.0, 0.0
    for _ in range(iterations):
        ga = gb = 0.0
        for conf, won in pairs:
            p = 1.0 / (1.0 + math.exp(-(a * conf + b)))
            err = p - (t_pos if won else t_neg)
            ga += err * conf
            gb += err
        a -= lr * ga / n
        b -= lr * gb / n
    return (a, b)


def platt_apply(fit: "tuple[float, float]", conf: float) -> float:
    a, b = fit
    return 1.0 / (1.0 + math.exp(-(a * conf + b)))


# ── ledger read ─────────────────────────────────────────────────────────────

def entry_outcomes(cursor=None) -> "list[tuple[float, bool]]":
    """(entry confidence, won) per CLOSED run that made an entry decision.

    Same population as the monitoring analysis: the run's max entry-decision
    confidence, outcome = realized_pnl_usd > 0. Read-only; [] on any error."""
    own = cursor is None
    conn = None
    try:
        if own:
            conn = get_db_connection()
            cursor = conn.cursor()
        cursor.execute(
            """SELECT t.id, t.realized_pnl_usd, e.payload
               FROM trading_runs t
               JOIN run_events e ON e.run_id = t.id AND e.event_type = 'decision'
               WHERE t.status = 'stopped'""")
        best: dict[int, float] = {}
        outcome: dict[int, bool] = {}
        for row in cursor.fetchall():
            try:
                payload = json.loads(row["payload"] or "{}")
            except (ValueError, TypeError):
                continue
            if str(payload.get("action") or "").lower() not in (
                    "buy", "sell", "short", "cover"):
                continue
            conf = payload.get("confidence")
            if not isinstance(conf, (int, float)) or isinstance(conf, bool):
                continue
            rid = int(row["id"])
            best[rid] = max(best.get(rid, 0.0), float(conf))
            outcome[rid] = float(row["realized_pnl_usd"] or 0.0) > 0
        return [(best[r], outcome[r]) for r in best]
    except Exception:  # noqa: BLE001 — scoreboard must never break a caller
        logger.warning("entry_outcomes read failed", exc_info=True)
        return []
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


# ── the scoreboard ──────────────────────────────────────────────────────────

def build_scoreboard(pairs: "Optional[list[tuple[float, bool]]]" = None) -> dict:
    """One pass: raw Brier, base-rate Brier, Platt fit + calibrated Brier,
    and the curve. `pairs` is injectable for tests; production reads the DB."""
    if pairs is None:
        pairs = entry_outcomes()
    n = len(pairs)
    wins = sum(1 for _, won in pairs if won)
    base = (wins / n) if n else None
    fit = fit_platt(pairs)
    calibrated_pairs = ([(platt_apply(fit, c), won) for c, won in pairs]
                        if fit else None)
    return {
        "at": _now_iso(),
        "n": n,
        "base_rate": round(base, 4) if base is not None else None,
        "brier_raw": round(brier_score(pairs), 4) if n else None,
        # what always quoting the base rate would score — the bar to beat
        "brier_base": round(base * (1 - base), 4) if base is not None else None,
        "brier_platt": (round(brier_score(calibrated_pairs), 4)
                        if calibrated_pairs else None),
        "platt": {"a": round(fit[0], 4), "b": round(fit[1], 4)} if fit else None,
        "curve": calibration_curve(pairs),
    }


def get_scoreboard(force_refresh: bool = False) -> dict:
    now = time.monotonic()
    if not force_refresh and _CACHE["payload"] is not None \
            and (now - _CACHE["at"]) < _CACHE_TTL_SECONDS:
        return _CACHE["payload"]
    payload = build_scoreboard()
    _CACHE.update(at=now, payload=payload)
    return payload


def calibrated_confidence(conf: "Optional[float]") -> "Optional[float]":
    """The Platt-mapped win probability for a raw confidence — or None
    whenever the feature is off, the fit is missing, or the input is not a
    number, so every caller can fall back to the raw scalar unchanged."""
    if calibrated_mode() == "off" or conf is None \
            or not isinstance(conf, (int, float)) or isinstance(conf, bool):
        return None
    try:
        fit = get_scoreboard().get("platt")
        if not fit:
            return None
        return round(platt_apply((fit["a"], fit["b"]), float(conf)), 4)
    except Exception:  # noqa: BLE001 — never let calibration break a decision
        return None
