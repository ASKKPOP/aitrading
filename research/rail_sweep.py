"""P3 — rail sweep. Reading #65 measured that RANDOM entries lose -0.23/trip
through the current house rails, i.e. the structure is negative-expectancy
before entry skill enters. This asks whether ANY rail configuration makes a
zero-intelligence entry non-negative on the same tape.

PRE-REGISTERED (before the run):
  H-RAILS: there exists a (stop, target, ratchet_frac) setting under which
           random entries are non-negative on this tape.
  FALSIFIER: no configuration in the grid is non-negative -> the tape and fee
           floor dominate, rail tuning alone cannot fix it, and P3 must target
           something other than bracket geometry.
  Reported as MEDIAN per trip as well as mean, because reading #64 established
  that this cohort's totals are outlier-fragile while its central tendency is not.
"""
import json, random, sys
sys.path.insert(0, sys.argv[1])
import zi_orig as Z

trips = [t for t in json.load(open(sys.argv[2])) if t["closed"]]
t0 = min(Z.iso_to_epoch(t["entry_ts"]) for t in trips) - Z.BAR_SEC
t1 = max(Z.iso_to_epoch(t["exit_ts"]) for t in trips) + Z.MAX_HOLD_SEC
candles = {s: Z.fetch_candles(s, t0, t1, sys.argv[3])
           for s in sorted({t["symbol"] for t in trips})}
usable = {s for s, c in candles.items() if len(c) > 300}
cohort = [t for t in trips if t["symbol"] in usable]
pool = {s: max(1, len(candles[s]) - Z.MAX_HOLD_SEC // Z.BAR_SEC - 1) for s in usable}
SLIP, DRAWS = 0.0003, 120
BASE = (Z.STOP_PCT, Z.TARGET_PCT, Z.RATCHET_FRAC)
print(f"cohort {len(cohort)}  base stop={BASE[0]} target={BASE[1]} frac={BASE[2]}", flush=True)

def run(stop, target, frac, seed):
    Z.STOP_PCT, Z.TARGET_PCT, Z.RATCHET_FRAC = stop, target, frac
    rng = random.Random(seed); nets = []
    for _ in range(DRAWS):
        for t in cohort:
            s = t["symbol"]
            nets.append(Z.simulate_trip(candles[s], rng.randrange(pool[s]),
                                        "long" if rng.random() < .5 else "short",
                                        t["notional_usd"], SLIP))
    nets.sort()
    return sum(nets)/len(nets), nets[len(nets)//2]

rows = []
for stop in (0.005, 0.010, 0.015, 0.025, 0.040):
    for target in (0.010, 0.020, 0.045, 0.080):
        if target <= stop: continue
        for frac in (0.0, 0.5, 0.9):
            m, md = run(stop, target, frac, 20260828)
            rows.append((stop, target, frac, m, md))
            print(f"stop {stop:.3f} tgt {target:.3f} frac {frac:.1f} -> mean {m:+.4f}  median {md:+.4f}", flush=True)
Z.STOP_PCT, Z.TARGET_PCT, Z.RATCHET_FRAC = BASE
rows.sort(key=lambda r: -r[3])
print("\n=== BEST 5 BY MEAN ===")
for r in rows[:5]: print(f"  stop {r[0]:.3f} tgt {r[1]:.3f} frac {r[2]:.1f}  mean {r[3]:+.4f} median {r[4]:+.4f}")
pos = [r for r in rows if r[3] >= 0]
print(f"\nconfigurations with NON-NEGATIVE mean: {len(pos)} of {len(rows)}")
print("H-RAILS:", "SUPPORTED" if pos else "REFUTED — no rail setting is non-negative on this tape")
json.dump([{"stop": r[0], "target": r[1], "frac": r[2], "mean": r[3], "median": r[4]} for r in rows],
          open(sys.argv[4], "w"), indent=1)
