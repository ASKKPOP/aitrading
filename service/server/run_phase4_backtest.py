"""Phase-4 walk-forward runner (parameter-upgrade plan §4) — the go/no-go gate.

Usage:  .venv/bin/python service/server/run_phase4_backtest.py

Design (pre-registered before the OOS windows were opened):
  PRIMARY row   — the deployment-faithful default config (confluence_min=4,
                  volume_confirm_min=1.5), NEVER tuned, evaluated on the four
                  out-of-sample test windows. Zero snooping by construction.
  SECONDARY row — anchored walk-forward: per fold, a small grid
                  (confluence_min {3,4} × volume_confirm_min {1.2,1.5,2.0} =
                  6 configs; count reported) is tuned on the training window
                  (everything before the test window minus a 14-day purge) by
                  pooled train profit factor (min 30 trades), then the frozen
                  winner runs on the untouched test window.
  SENSITIVITY   — confluence_min=3 fixed (B4 is null historically, so the
                  live 4-of-6 has only 5 achievable conditions; ≥3/5 shows
                  how much the strictness costs).

Folds (test windows; train = asset start → test_start − 14d purge):
  F1 2021-07-01 → 2022-12-31   (bear + Luna/FTX)
  F2 2023-01-01 → 2024-03-31   (recovery)
  F3 2024-04-01 → 2025-06-30   (post-halving)
  F4 2025-07-01 → 2026-07-15   (current cycle)

Assets & windows (per verified listing dates): BTC/ETH bars from 2019-01-01
(400-bar warmup → signals from ~2020-02); SOL bars from 2020-04-10 (signals
from ~2021-05). No cross-asset averaging over unequal windows — per-asset
tables + pooled trade stats.

Go/no-go: evaluate_go_no_go() on the PRIMARY row's pooled OOS trades.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from backtest_strategy import (
    DEFAULT_PARAMS,
    SimResult,
    evaluate_go_no_go,
    simulate,
    summarize,
)

ASSETS = {
    "BTC": ("BTC-USD", "2019-01-01"),
    "ETH": ("ETH-USD", "2019-01-01"),
    "SOL": ("SOL-USD", "2020-04-10"),
}
END_DATE = "2026-07-15"

FOLDS = [
    ("F1", "2021-07-01", "2022-12-31"),
    ("F2", "2023-01-01", "2024-03-31"),
    ("F3", "2024-04-01", "2025-06-30"),
    ("F4", "2025-07-01", END_DATE),
]
PURGE_DAYS = 14

TUNING_GRID = [
    {"confluence_min": cm, "volume_confirm_min": vc}
    for cm in (3, 4) for vc in (1.2, 1.5, 2.0)
]


def _load_data():
    from historical_data import get_bars
    from market_events import _CALENDAR
    from market_events_history import all_historical_events
    from psych_feed import fetch_fear_greed_full_history

    bars_by_asset = {}
    for asset, (ticker, start) in ASSETS.items():
        raw = get_bars(ticker, "1d", start, END_DATE)
        bars_by_asset[asset] = [
            {"date": b.date, "open": b.open, "close": b.close, "volume": b.volume}
            for b in raw
        ]

    fng_rows = fetch_fear_greed_full_history()
    fng_by_date = {r["date"]: r["value"] for r in fng_rows}

    et = ZoneInfo("America/New_York")
    events = []
    for etype, day, hhmm, _title in all_historical_events():
        events.append(datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=et)
                      .astimezone(timezone.utc))
    for etype, day, hhmm, _title in _CALENDAR:  # 2026–27 live calendar
        events.append(datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=et)
                      .astimezone(timezone.utc))
    return bars_by_asset, fng_by_date, sorted(events)


def _run_window(bars_by_asset, fng, events, params, start, end) -> list[SimResult]:
    results = []
    for asset, bars in bars_by_asset.items():
        p = dict(DEFAULT_PARAMS)
        p.update(params)
        results.append(simulate(asset, bars, fng, events, p,
                                signal_start=start, signal_end=end))
    return results


def _pooled_pf(results: list[SimResult]) -> tuple[float, int]:
    pnls = [t.pnl for r in results for t in r.trades if t.exit_reason != "end_of_data"]
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = sum(-p for p in pnls if p <= 0)
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win else 0.0)
    return pf, len(pnls)


def _purged(day: str, days: int = PURGE_DAYS) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(day) - timedelta(days=days)).isoformat()


def run(out_dir: Path) -> dict:
    print("loading data …")
    bars_by_asset, fng, events = _load_data()
    for asset, bars in bars_by_asset.items():
        print(f"  {asset}: {len(bars)} bars {bars[0]['date']} → {bars[-1]['date']}")
    print(f"  F&G days: {len(fng)}, events: {len(events)}")

    report: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pre_registered": {
            "primary_config": {"confluence_min": 4, "volume_confirm_min": 1.5},
            "tuning_grid_size": len(TUNING_GRID),
            "folds": FOLDS,
            "purge_days": PURGE_DAYS,
            "criteria": "≥400 pooled OOS trades; Wilson90 LB(win) > 0.50; "
                        "bootstrap90 LB(PF) > 1.0; worst-asset maxDD ≤ 30%",
        },
        "scope_note": "B4 null throughout (no sentiment archive); B3 degraded "
                      "(MA/RSI/volume only); B5 F&G leg only; S5 null — the "
                      "backtested gate is STRICTER than and different from the "
                      "live gate; only evaluated conditions earn default-on.",
    }

    # ── PRIMARY: fixed defaults on every OOS window ─────────────────────────
    primary_results: list[SimResult] = []
    per_fold_primary = {}
    for fold, start, end in FOLDS:
        res = _run_window(bars_by_asset, fng, events, {}, start, end)
        primary_results.extend(res)
        s = summarize(res)
        per_fold_primary[fold] = {"window": f"{start} → {end}", **s["pooled"],
                                  "per_asset": {a: v["trades"] for a, v in s["per_asset"].items()}}
        print(f"primary {fold}: trades={s['pooled']['trades']} "
              f"win={s['pooled']['win_rate']} pf={s['pooled']['profit_factor']}")
    primary_summary = summarize(primary_results)
    # per_asset keys collide across folds when pooling (one SimResult per
    # asset PER FOLD) — the pooled per_asset block would mislead; drop it.
    primary_summary.pop("per_asset", None)
    report["primary"] = {"per_fold": per_fold_primary, **primary_summary}
    report["go_no_go"] = evaluate_go_no_go(primary_summary["pooled"])

    # ── SECONDARY: anchored walk-forward with train-tuned config ───────────
    wf = {}
    for fold, start, end in FOLDS:
        train_end = _purged(start)
        best_cfg, best_pf, best_n = None, -1.0, 0
        for cfg in TUNING_GRID:
            train_res = _run_window(bars_by_asset, fng, events, cfg, None, train_end)
            pf, n = _pooled_pf(train_res)
            if n >= 30 and (pf > best_pf or (pf == best_pf and n > best_n)):
                best_cfg, best_pf, best_n = cfg, pf, n
        if best_cfg is None:
            wf[fold] = {"error": "no config reached 30 train trades"}
            continue
        test_res = _run_window(bars_by_asset, fng, events, best_cfg, start, end)
        s = summarize(test_res)
        wf[fold] = {"window": f"{start} → {end}", "tuned_config": best_cfg,
                    "train_pf": round(best_pf, 3), "train_trades": best_n,
                    **s["pooled"]}
        print(f"walk-forward {fold}: cfg={best_cfg} test_trades={s['pooled']['trades']} "
              f"win={s['pooled']['win_rate']} pf={s['pooled']['profit_factor']}")
    report["walk_forward"] = wf

    # ── SENSITIVITY: confluence_min=3 fixed on OOS windows ─────────────────
    sens_results: list[SimResult] = []
    for fold, start, end in FOLDS:
        sens_results.extend(_run_window(bars_by_asset, fng, events,
                                        {"confluence_min": 3}, start, end))
    report["sensitivity_min3"] = summarize(sens_results)["pooled"]

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "phase4-backtest-result.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\nwritten: {out_path}")
    print(f"GO/NO-GO: {report['go_no_go']}")
    return report


if __name__ == "__main__":
    project_root = SERVER_DIR.parents[1]
    run(project_root / "docs" / "research" / "parameters")
