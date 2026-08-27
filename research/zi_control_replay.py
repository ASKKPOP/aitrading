"""Zero-intelligence control replay — research 07 §12.2(1), owner-ordered 2026-08-27.

THE QUESTION (pre-registered before first run):
    Do the AI's actual crypto entries (timing + direction) beat random
    entries under IDENTICAL rails, symbols, sizes and fees?

COHORT: every closed crypto round-trip by agents 6/60, 2026-08-15 →
2026-08-27 (n=57, ledger NET −$6.60 all-in, real fills — the AI side is
never simulated).

ZI ARM (per draw): 57 trips; trip i keeps AI trip i's SYMBOL and NOTIONAL
(controls for selection/sizing — the test isolates timing+direction);
entry time ~ Uniform(window), side ~ coin flip. Secondary arms: long-only
and short-only ZI (beta reference), reported but not the gate.

IDENTICAL RAILS (house bracket, from the tape's medians and #592):
    stop 1.5% · target 4.5% · breakeven ratchet: fee_floor = 2 legs ×
    0.045% × notional, arm = 2.2 × fee_floor, lock frac 0.5, checked on
    5m closes · max hold 24h (at_time) then close · stop-first on
    ambiguous candles · fees 0.045%/leg · fills at candle close ± slippage.

TWO FILL BASES: slippage 0.03% and 0.16% (both reported; a verdict must
hold on BOTH to count — research 07 rule).

STRATIFICATION: by BTC 6-day regime halves (rising/falling) computed from
BTC-USDT closes; every figure also reported with the largest |contributor|
stripped (owner outlier law).

PRE-REGISTERED VERDICT (written before any candle was fetched):
    "AI beats random-with-rails" IFF the bootstrap 90% CI of
    (AI mean trip NET − ZI mean trip NET) excludes 0 from above,
    on BOTH fill bases, and survives largest-contributor strip.
    "AI loses to random" IFF the same CI excludes 0 from below on both.
    Anything else: INCONCLUSIVE — say so, do not re-frame.

Usage:
    python3 research/zi_control_replay.py --trips ai_trips.json \
        --cache /tmp/zi_candles --draws 1000
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.parse
import urllib.request

BAR_SEC = 300  # 5m candles
FEE_LEG = 0.00045
STOP_PCT = 0.015
TARGET_PCT = 0.045
RATCHET_ARM_X = 2.2     # arm = 2.2 x fee_floor (trip-1 tape: 0.4486/0.2018)
RATCHET_FRAC = 0.5      # #592 RATCHET_LOCK_FRAC default
MAX_HOLD_SEC = 24 * 3600
OKX = "https://www.okx.com/api/v5/market/history-candles"


def iso_to_epoch(ts: str) -> int:
    from datetime import datetime, timezone
    return int(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=timezone.utc).timestamp())


def fetch_candles(symbol: str, t0: int, t1: int, cache_dir: str) -> list:
    """5m candles [epoch, open, high, low, close], ascending, cached."""
    inst = symbol[:-4] + "-USDT"  # TAOUSDT -> TAO-USDT
    path = os.path.join(cache_dir, f"{inst}_{t0}_{t1}_5m.json")
    if os.path.exists(path):
        return json.load(open(path))
    rows: dict[int, list] = {}
    after = (t1 + BAR_SEC) * 1000  # OKX pages backwards with `after`
    while True:
        q = urllib.parse.urlencode(
            {"instId": inst, "bar": "5m", "after": str(after), "limit": "100"})
        req = urllib.request.Request(f"{OKX}?{q}",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r).get("data", [])
        if not data:
            break
        for c in data:
            ts = int(c[0]) // 1000
            if t0 <= ts <= t1:
                rows[ts] = [ts, float(c[1]), float(c[2]), float(c[3]),
                            float(c[4])]
        oldest = int(data[-1][0]) // 1000
        if oldest <= t0:
            break
        after = int(data[-1][0])
        time.sleep(0.12)
    out = [rows[k] for k in sorted(rows)]
    os.makedirs(cache_dir, exist_ok=True)
    json.dump(out, open(path, "w"))
    return out


def simulate_trip(candles: list, start_i: int, side: str, notional: float,
                  slip: float) -> float:
    """One ZI trip on the house rails. Returns all-in NET USD."""
    entry = candles[start_i][4] * (1 + slip if side == "long" else 1 - slip)
    qty = notional / entry
    sgn = 1.0 if side == "long" else -1.0
    stop = entry * (1 - sgn * STOP_PCT)
    target = entry * (1 + sgn * TARGET_PCT)
    fee_floor = 2 * FEE_LEG * notional
    arm = RATCHET_ARM_X * fee_floor
    armed = False
    peak = 0.0
    t_end = candles[start_i][0] + MAX_HOLD_SEC
    exit_px = None
    for j in range(start_i + 1, len(candles)):
        ts, _o, hi, lo, cl = candles[j]
        # stop-first on ambiguous candles (pre-registered)
        if (side == "long" and lo <= stop) or (side == "short" and hi >= stop):
            exit_px = stop
            break
        if (side == "long" and hi >= target) or (side == "short" and lo <= target):
            exit_px = target
            break
        pnl = sgn * (cl - entry) * qty
        peak = max(peak, pnl)
        if not armed and peak >= arm:
            armed = True
        if armed:
            floor = fee_floor + RATCHET_FRAC * max(0.0, peak - fee_floor)
            if pnl <= floor:
                exit_px = cl
                break
        if ts >= t_end:
            exit_px = cl
            break
    if exit_px is None:
        exit_px = candles[-1][4]
    exit_px *= (1 - slip) if side == "long" else (1 + slip)
    gross = sgn * (exit_px - entry) * qty
    fees = FEE_LEG * notional + FEE_LEG * abs(qty * exit_px)
    return gross - fees


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips", required=True)
    ap.add_argument("--cache", default="/tmp/zi_candles")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    trips = [t for t in json.load(open(args.trips)) if t["closed"]]
    t0 = min(iso_to_epoch(t["entry_ts"]) for t in trips) - BAR_SEC
    t1 = max(iso_to_epoch(t["exit_ts"]) for t in trips) + MAX_HOLD_SEC
    symbols = sorted({t["symbol"] for t in trips}) + ["BTCUSDT"]
    candles: dict[str, list] = {}
    for s in symbols:
        candles[s] = fetch_candles(s, t0, t1, args.cache)
        print(f"candles {s}: {len(candles[s])}")
    usable = {s for s in symbols if len(candles.get(s, [])) > 300}
    cohort = [t for t in trips if t["symbol"] in usable]
    dropped = [t for t in trips if t["symbol"] not in usable]
    if dropped:
        print(f"DROPPED (no candles): {[t['symbol'] for t in dropped]} "
              f"— their ledger NET {sum(t['net_usd'] for t in dropped):+.2f} "
              f"is excluded from the AI side too (like-for-like).")

    ai_nets = [t["net_usd"] for t in cohort]
    ai_total = sum(ai_nets)
    print(f"AI cohort: n={len(cohort)} NET {ai_total:+.2f}")

    # regime split by BTC: first half vs second half of the window by BTC trend
    btc = candles["BTCUSDT"]
    mid_ts = btc[len(btc) // 2][0]
    r1 = (btc[len(btc) // 2][4] / btc[0][4]) - 1
    r2 = (btc[-1][4] / btc[len(btc) // 2][4]) - 1
    regime_of = lambda ts: ("H1" if ts < mid_ts else "H2")  # noqa: E731
    print(f"BTC half-window returns: H1 {r1:+.2%}  H2 {r2:+.2%}")

    rng = random.Random(args.seed)
    # entry index pool per symbol: any candle with >= 24h of tape after it
    pool = {s: max(1, len(candles[s]) - MAX_HOLD_SEC // BAR_SEC - 1)
            for s in usable}

    results = {}
    for slip in (0.0003, 0.0016):
        draw_means, draw_totals = [], []
        arm_long, arm_short = [], []
        per_trip_zi = [[] for _ in cohort]  # for stratification
        for _d in range(args.draws):
            tot = 0.0
            tot_l = 0.0
            tot_s = 0.0
            for i, t in enumerate(cohort):
                s = t["symbol"]
                idx = rng.randrange(pool[s])
                side = "long" if rng.random() < 0.5 else "short"
                net = simulate_trip(candles[s], idx, side,
                                    t["notional_usd"], slip)
                per_trip_zi[i].append(net)
                tot += net
                tot_l += simulate_trip(candles[s], idx, "long",
                                       t["notional_usd"], slip)
                tot_s += simulate_trip(candles[s], idx, "short",
                                       t["notional_usd"], slip)
            draw_totals.append(tot)
            draw_means.append(tot / len(cohort))
            arm_long.append(tot_l)
            arm_short.append(tot_s)
        draw_totals.sort()
        zi_mean_trip = sum(draw_means) / len(draw_means)
        pct = sum(1 for v in draw_totals if v < ai_total) / len(draw_totals)

        # bootstrap 90% CI of (AI mean − ZI mean) : resample AI trips,
        # pair with the ZI per-trip expectation
        zi_trip_exp = [sum(v) / len(v) for v in per_trip_zi]
        diffs = []
        n = len(cohort)
        for _b in range(10_000):
            idxs = [rng.randrange(n) for _ in range(n)]
            d = (sum(ai_nets[k] for k in idxs)
                 - sum(zi_trip_exp[k] for k in idxs)) / n
            diffs.append(d)
        diffs.sort()
        lo, hi = diffs[500], diffs[9499]

        # largest-contributor strip (owner outlier law)
        big = max(range(n), key=lambda k: abs(ai_nets[k]))
        ai_strip = ai_total - ai_nets[big]
        zi_strip = sum(zi_trip_exp) - zi_trip_exp[big]

        # regime stratification of the AI side vs ZI expectation
        strat = {}
        for reg in ("H1", "H2"):
            ks = [k for k, t in enumerate(cohort)
                  if regime_of(iso_to_epoch(t["entry_ts"])) == reg]
            strat[reg] = {
                "n": len(ks),
                "ai_net": round(sum(ai_nets[k] for k in ks), 2),
                "zi_exp": round(sum(zi_trip_exp[k] for k in ks), 2),
            }

        results[f"slip_{slip}"] = {
            "ai_total": round(ai_total, 2),
            "zi_draw_total_mean": round(sum(draw_totals) / len(draw_totals), 2),
            "zi_draw_total_p05_p95": [round(draw_totals[int(0.05 * len(draw_totals))], 2),
                                      round(draw_totals[int(0.95 * len(draw_totals))], 2)],
            "ai_percentile_vs_zi": round(pct, 3),
            "mean_trip_diff_CI90": [round(lo, 4), round(hi, 4)],
            "beats_random": bool(lo > 0),
            "loses_to_random": bool(hi < 0),
            "strip_largest": {"ai": round(ai_strip, 2), "zi": round(zi_strip, 2),
                              "stripped_trip_net": ai_nets[big]},
            "zi_long_only_mean": round(sum(arm_long) / len(arm_long), 2),
            "zi_short_only_mean": round(sum(arm_short) / len(arm_short), 2),
            "regimes": strat,
            "zi_mean_trip": round(zi_mean_trip, 4),
        }
        print(json.dumps({f"slip_{slip}": results[f'slip_{slip}']}, indent=1))

    out = args.out or "zi_control_result.json"
    json.dump({"cohort_n": len(cohort), "draws": args.draws,
               "seed": args.seed, "results": results}, open(out, "w"), indent=1)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
