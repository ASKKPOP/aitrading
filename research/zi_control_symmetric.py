"""P2 — SYMMETRIC zero-intelligence control.

Fixes the asymmetry found in reading #64: the original took the AI arm from
the LEDGER (`net_usd`) and the ZI arm from simulate_trip(). Real fills carry
real slippage/fees; simulated trips carry modelled ones, so the two arms were
not comparable. Here BOTH arms run through identical rails and differ ONLY in
entry selection (and, for arm 3, in side).

Pre-registered before the run:
  H0: AI entry selection has no edge over random entry in the same symbols.
  Falsifier: CI90 of (AI mean trip - ZI mean trip) excludes 0.
             Above 0 -> AI has edge. Below 0 -> AI is WORSE than random.
             Contains 0 -> INCONCLUSIVE (report as such, do not round).
  Reported with AND without the largest |contributor|, and — per reading #64's
  method finding — also as median / trimmed mean, because the top two trips
  in this cohort are a nearly-offsetting pair that makes strip-1 misleading.
"""
import json, random, sys
sys.path.insert(0, sys.argv[1])
from zi_orig import fetch_candles, iso_to_epoch, simulate_trip, BAR_SEC, MAX_HOLD_SEC

TRIPS, CACHE, OUT = sys.argv[2], sys.argv[3], sys.argv[4]
DRAWS, SEED = 400, 20260828

trips = [t for t in json.load(open(TRIPS)) if t["closed"]]
t0 = min(iso_to_epoch(t["entry_ts"]) for t in trips) - BAR_SEC
t1 = max(iso_to_epoch(t["exit_ts"]) for t in trips) + MAX_HOLD_SEC
candles = {}
for s in sorted({t["symbol"] for t in trips}):
    candles[s] = fetch_candles(s, t0, t1, CACHE)
usable = {s for s, c in candles.items() if len(c) > 300}
cohort = [t for t in trips if t["symbol"] in usable]
print(f"cohort n={len(cohort)} of {len(trips)}; symbols usable {len(usable)}", flush=True)

def idx_at(sym, ts):
    e = iso_to_epoch(ts); c = candles[sym]
    lo, hi = 0, len(c) - 1
    while lo < hi:                       # first candle at/after entry
        mid = (lo + hi) // 2
        if c[mid][0] < e: lo = mid + 1
        else: hi = mid
    return lo

def stats(v):
    v = sorted(v); n = len(v)
    tr = v[max(1, n//10):n - max(1, n//10)]
    return {"mean": sum(v)/n, "median": v[n//2], "trimmed_mean": sum(tr)/len(tr),
            "total": sum(v),
            "strip1": sum(v) - max(v, key=abs),
            "strip2": sum(sorted(v, key=lambda x: -abs(x))[2:])}

rng = random.Random(SEED)
pool = {s: max(1, len(candles[s]) - MAX_HOLD_SEC//BAR_SEC - 1) for s in usable}
res = {}
for slip in (0.0003, 0.0016):
    ai = [simulate_trip(candles[t["symbol"]], idx_at(t["symbol"], t["entry_ts"]),
                        t["side"], t["notional_usd"], slip) for t in cohort]
    # ZI: same symbol + notional, random entry index and random side
    zi_per_trip = [[] for _ in cohort]
    zi_sideonly = [[] for _ in cohort]   # AI's OWN side, random time
    for _ in range(DRAWS):
        for i, t in enumerate(cohort):
            s = t["symbol"]; j = rng.randrange(pool[s])
            side = "long" if rng.random() < 0.5 else "short"
            zi_per_trip[i].append(simulate_trip(candles[s], j, side, t["notional_usd"], slip))
            zi_sideonly[i].append(simulate_trip(candles[s], j, t["side"], t["notional_usd"], slip))
    zi_exp = [sum(v)/len(v) for v in zi_per_trip]
    zs_exp = [sum(v)/len(v) for v in zi_sideonly]
    diff = [a - z for a, z in zip(ai, zi_exp)]
    # bootstrap CI90 of the mean paired difference
    boots = []
    for _ in range(2000):
        smp = [diff[rng.randrange(len(diff))] for _ in diff]
        boots.append(sum(smp)/len(smp))
    boots.sort()
    lo, hi = boots[int(.05*len(boots))], boots[int(.95*len(boots))]
    res[f"slip_{slip}"] = {
        "n": len(cohort), "ai": stats(ai), "zi_random_side": stats(zi_exp),
        "zi_ai_side": stats(zs_exp),
        "mean_paired_diff": sum(diff)/len(diff), "diff_CI90": [lo, hi],
        "verdict": ("AI EDGE" if lo > 0 else "AI WORSE THAN RANDOM" if hi < 0
                    else "INCONCLUSIVE"),
    }
    print(f"slip={slip}: AI mean {sum(ai)/len(ai):+.4f} | ZI(rand side) {sum(zi_exp)/len(zi_exp):+.4f} "
          f"| ZI(AI side) {sum(zs_exp)/len(zs_exp):+.4f} | diff CI90 [{lo:+.4f},{hi:+.4f}] "
          f"-> {res[f'slip_{slip}']['verdict']}", flush=True)
json.dump(res, open(OUT, "w"), indent=1)
print("written", OUT)
