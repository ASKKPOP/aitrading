"""Adversarial check (b): would maker (limit) orders actually fill?

For each replay entry (crypto cohort), place a hypothetical limit at the
entry candle's close. Long limit buy fills if a subsequent candle low <=
limit; short limit sell fills if a subsequent high >= limit. Report the
% filled within 5m/15m/30m/60m, and the % where the *exit* leg (the walk's
exit price) is touched again within the same windows after the exit bar
(both legs must be maker to pay 2x maker; exit-at-market keeps one taker
leg).
"""
import json, os
from datetime import datetime, timezone

SP = os.path.dirname(os.path.abspath(__file__))
BAR = 300

def iso_ep(ts): return int(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                           .replace(tzinfo=timezone.utc).timestamp())

events = []
for line in open(f"{SP}/demoted_events.tsv"):
    p = line.rstrip("\n").split("\t")
    events.append(dict(run_id=int(p[1]), ts=p[2], act=p[3], symbol=p[5],
                       market=p[6], mtype=p[7], ep=iso_ep(p[2])))

# same classification as fee_sweep (recompute held from fills)
fills = []
for line in open(f"{SP}/fills.tsv"):
    p = line.rstrip("\n").split("\t")
    fills.append(dict(run_id=int(p[1]), side=p[5], qty=float(p[7]), ep=int(p[10])))
byrun = {}
for f in fills: byrun.setdefault(f["run_id"], []).append(f)
def held(run_id, ep):
    return sum((f["qty"] if f["side"] in ("buy", "cover") else -f["qty"])
               for f in byrun.get(run_id, []) if f["ep"] < ep)

cohort = []
for e in events:
    if e["market"] != "crypto": continue
    fut = e["mtype"].lower() == "futures"
    h = held(e["run_id"], e["ep"])
    if e["act"] == "buy":
        if h < 0: continue
        e["side"] = "long"
    else:
        if not fut or h > 0: continue
        e["side"] = "short"
    cohort.append(e)

windows = [1, 3, 6, 12]  # bars: 5m, 15m, 30m, 60m
hit = {w: 0 for w in windows}
n = 0
for e in cohort:
    inst = e["symbol"][:-4] + "-USDT"
    path = f"{SP}/candles/okx_{inst}.json"
    if not os.path.exists(path): continue
    c = json.load(open(path))
    i0 = next((i for i, b in enumerate(c) if b[0] >= e["ep"]), None)
    if i0 is None or i0 + 1 >= len(c): continue
    limit = c[i0][4]
    n += 1
    for w in windows:
        seg = c[i0 + 1: i0 + 1 + w]
        if e["side"] == "long":
            ok = any(b[3] <= limit for b in seg)
        else:
            ok = any(b[2] >= limit for b in seg)
        if ok: hit[w] += 1
print(f"crypto replay entries with candles: n={n}")
for w in windows:
    print(f"  limit at entry close touched within {w*5:3d} min: {hit[w]}/{n} = {100*hit[w]/n:.1f}%")
