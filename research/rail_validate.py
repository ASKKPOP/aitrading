"""P3 validation — the three checks reading #66 required before any rail change.

  (1) bootstrap CI90 on the candidate cells
  (2) a second, NON-OVERLAPPING window (tape split in half)
  (3) the AI's ACTUAL entries, not random ones

PRE-REGISTERED: the #66 lead (far target + ratchet OFF beats the live config)
survives only if its advantage over the live cell holds with CI90 excluding 0
in BOTH half-windows AND on real entries. Any of those failing -> the lead is
regime- or method-specific and must NOT be shipped.
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
SLIP = 0.0003
HOLD_BARS = Z.MAX_HOLD_SEC // Z.BAR_SEC
CELLS = {"LIVE (0.015/0.045/0.5)": (0.015, 0.045, 0.5),
         "BEST (0.015/0.080/0.0)": (0.015, 0.080, 0.0),
         "ALT  (0.025/0.080/0.0)": (0.025, 0.080, 0.0)}

def idx_at(sym, ts):
    e = Z.iso_to_epoch(ts); c = candles[sym]; lo, hi = 0, len(c) - 1
    while lo < hi:
        m = (lo + hi) // 2
        if c[m][0] < e: lo = m + 1
        else: hi = m
    return lo

def set_cell(c): Z.STOP_PCT, Z.TARGET_PCT, Z.RATCHET_FRAC = c

def boot_ci(v, rng, n=2000):
    b = sorted(sum(v[rng.randrange(len(v))] for _ in v) / len(v) for _ in range(n))
    return b[int(.05*n)], b[int(.95*n)]

def rand_nets(cell, lo_frac, hi_frac, draws, seed):
    set_cell(cell); rng = random.Random(seed); out = []
    for _ in range(draws):
        for t in cohort:
            s = t["symbol"]; L = len(candles[s]) - HOLD_BARS - 1
            a, b = int(L*lo_frac), max(int(L*lo_frac)+1, int(L*hi_frac))
            out.append(Z.simulate_trip(candles[s], rng.randrange(a, b),
                       "long" if rng.random() < .5 else "short", t["notional_usd"], SLIP))
    return out

def ai_nets(cell):
    set_cell(cell)
    return [Z.simulate_trip(candles[t["symbol"]], idx_at(t["symbol"], t["entry_ts"]),
            t["side"], t["notional_usd"], SLIP) for t in cohort]

rng = random.Random(20260828)
res = {}
print(f"cohort {len(cohort)}\n")
for name, cell in CELLS.items():
    r = {}
    for lbl, (a, b, d) in (("full", (0.0, 1.0, 120)), ("H1", (0.0, 0.5, 200)), ("H2", (0.5, 1.0, 200))):
        v = rand_nets(cell, a, b, d, 20260828)
        lo, hi = boot_ci(v, rng)
        r[lbl] = {"mean": sum(v)/len(v), "ci90": [lo, hi], "n": len(v)}
    av = ai_nets(cell); lo, hi = boot_ci(av, rng)
    r["ai_entries"] = {"mean": sum(av)/len(av), "ci90": [lo, hi], "n": len(av),
                       "median": sorted(av)[len(av)//2]}
    res[name] = r
    print(f"{name}")
    for k in ("full", "H1", "H2", "ai_entries"):
        c = r[k]
        print(f"   {k:11s} mean {c['mean']:+.4f}  CI90 [{c['ci90'][0]:+.4f},{c['ci90'][1]:+.4f}]  n={c['n']}")
    print(flush=True)

print("=== BEST minus LIVE (paired on the same seed/draws) ===")
for lbl in ("full", "H1", "H2", "ai_entries"):
    d = res["BEST (0.015/0.080/0.0)"][lbl]["mean"] - res["LIVE (0.015/0.045/0.5)"][lbl]["mean"]
    bc = res["BEST (0.015/0.080/0.0)"][lbl]["ci90"]; lc = res["LIVE (0.015/0.045/0.5)"][lbl]["ci90"]
    overlap = not (bc[0] > lc[1] or lc[0] > bc[1])
    print(f"   {lbl:11s} delta {d:+.4f}   CIs overlap: {overlap}")
json.dump(res, open(sys.argv[4], "w"), indent=1)
