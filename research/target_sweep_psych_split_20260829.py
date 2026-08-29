"""Psych-regime split of the target sweep (owner addendum, 2026-08-29).
Run from a CLEAN cwd (scratchpad's re.py shadows stdlib) with
SWEEP_SP=<scratchpad dir>:  cd /tmp && SWEEP_SP=... python3 <scratchpad>/psych_split.py
Joins each replay trip to psych_snapshots F&G (nearest created_at <= entry),
bins by regime, re-runs the primary target sweep (ratchet ON, stop-first,
realistic fees) per bin. Outputs psych_split_results.json.
"""
import json, os, random, statistics, bisect
from collections import Counter
from datetime import datetime, timezone
SP = os.environ.get("SWEEP_SP") or os.path.dirname(os.path.abspath(__file__))
src = open(f"{SP}/target_sweep.py").read().replace(
    'SP = os.path.dirname(os.path.abspath(__file__))', f'SP = {SP!r}')
ns = {}
exec(compile(src.split('def main()')[0], "ts_lib", "exec"), ns)
walk, iso_ep, load_candles, mfe = ns["walk"], ns["iso_ep"], ns["load_candles"], ns["mfe"]
MARKET_LEG, TARGETS, boot_ci, pct = ns["MARKET_LEG"], ns["TARGETS"], ns["boot_ci"], ns["pct"]

psych = []
for line in open(f"{SP}/psych_series.tsv"):
    p = line.rstrip("\n").split("\t")
    if p[1] in ("NULL", ""): continue
    psych.append((iso_ep(p[0]), int(p[1])))
psych.sort()
peps = [e for e, _ in psych]
def fng_at(ep):
    i = bisect.bisect_right(peps, ep) - 1
    return (None, None) if i < 0 else (psych[i][1], ep - psych[i][0])
def bin_of(v):
    if v <= 25: return "extreme_fear<=25"
    if v <= 45: return "fear26-45"
    if v <= 55: return "neutral46-55"
    if v <= 75: return "greed56-75"
    return "extreme_greed>75"

events = []
for line in open(f"{SP}/demoted_events.tsv"):
    p = line.rstrip("\n").split("\t")
    events.append(dict(eid=int(p[0]), run_id=int(p[1]), ts=p[2], act=p[3],
                       symbol=p[5], market=p[6], mtype=p[7], ep=iso_ep(p[2])))
fills = []
for line in open(f"{SP}/fills.tsv"):
    p = line.rstrip("\n").split("\t")
    fills.append(dict(run_id=int(p[1]), side=p[5], qty=float(p[7]), ep=int(p[10])))
byrun = {}
for f in fills: byrun.setdefault(f["run_id"], []).append(f)
def held(rid, ep):
    return sum(f["qty"] if f["side"] in ("buy", "cover") else -f["qty"]
               for f in byrun.get(rid, []) if f["ep"] < ep)
cohort = []
for e in events:
    fb = e["mtype"].lower() == "futures" or e["market"] == "futures"
    h = held(e["run_id"], e["ep"])
    if e["act"] == "buy":
        if h < 0: continue
        e["side"] = "long"; cohort.append(e)
    else:
        if not fb or h > 0: continue
        e["side"] = "short"; cohort.append(e)
candles = {}
for mk, sym in sorted({(e["market"], e["symbol"]) for e in cohort}):
    candles[(mk, sym)] = load_candles(mk, sym)

configs = [(t, r, tf) for t in TARGETS for r in (True, False) for tf in (False, True)]
trips = []
maxgap = 0
for e in cohort:
    c = candles[(e["market"], e["symbol"])]
    if not c: continue
    row = {}; ok = True
    for cfg in configs:
        r = walk(c, e["ep"], e["side"], cfg[0], cfg[1], cfg[2])
        if r is None: ok = False; break
        row[cfg] = r
    if not ok: continue
    v, gap = fng_at(e["ep"])
    if v is None: continue
    maxgap = max(maxgap, gap)
    trips.append(dict(e=e, row=row, mfe=mfe(c, e["ep"], e["side"]), fng=v, bin=bin_of(v)))
print(f"joined n={len(trips)} max join gap={maxgap}s")
print("bin counts:", Counter(t["bin"] for t in trips))

def net_bp(r, market):
    leg = MARKET_LEG[market]
    return (r["gross"] - leg - leg * r["exitfrac"]) * 1e4

out = {}
for b in ["extreme_fear<=25", "fear26-45", "neutral46-55", "greed56-75", "extreme_greed>75"]:
    sel = [t for t in trips if t["bin"] == b]
    if not sel:
        print(f"--- {b}: n=0"); continue
    mfes = [t["mfe"]["mfe"] for t in sel]
    print(f"--- {b}: n={len(sel)} MFE median={pct(mfes,50):.3f}%")
    rows = []
    for tgt in TARGETS:
        rs = [(x["row"][(tgt, True, False)], x["e"]["market"]) for x in sel]
        nets = [net_bp(r, mk) for r, mk in rs]
        mean = sum(nets) / len(nets); lo, hi = boot_ci(nets)
        tg = sum(1 for r, _ in rs if r["tag"] == "target")
        st = sum(1 for r, _ in rs if r["tag"] == "stop")
        print(f"  {tgt*100:5.2f}%: mean={mean:+8.2f} CI90=[{lo:+8.2f},{hi:+8.2f}] "
              f"med={statistics.median(nets):+8.2f} tgt%={100*tg/len(nets):5.1f} S:T={st}:{tg}")
        rows.append(dict(target=tgt, n=len(nets), mean=mean, ci90=[lo, hi],
                         med=statistics.median(nets), tgt_hit_pct=100*tg/len(nets)))
    best = max(rows, key=lambda r: r["mean"])
    out[b] = dict(n=len(sel), mfe_median=pct(mfes, 50), rows=rows,
                  best_target=best["target"], best_mean=best["mean"], best_ci90=best["ci90"])
json.dump(out, open(f"{SP}/psych_split_results.json", "w"), indent=1)
print("saved psych_split_results.json")
