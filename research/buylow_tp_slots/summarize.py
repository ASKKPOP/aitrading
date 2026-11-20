"""Summarise results_<kind>.json against the PREREG hypotheses -> summary_<kind>.json + stdout."""
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone

KIND = sys.argv[1]
d = json.load(open(f"results_{KIND}.json"))
B = d["bench"]
R = defaultdict(list)
for r in d["runs"]:
    R[(r["cohort"], r["exit"], r["tp"], r["rule"], r["fee"])].append(r)
F = max(r["fee"] for r in d["runs"])
COH = sorted({k[0] for k in R})
TPS = sorted({k[2] for k in R})
EXITS = ["tp_only", "tp_stop15", "tp_time30d"]
DIPS = ["dip", "drop", "rsi"]


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def dist(c, ex, tp, rule, seeded=True):
    rs = R[(c, ex, tp, rule, F)]
    if rule != "random" and seeded:
        rs = [x for x in rs if x["seed"] > 0]
    return rs


def ref(c):
    """Second benchmark: BTC hold (crypto) / SPY hold (stock)."""
    if KIND == "crypto":
        b = B[c]["btc"]
        return b[0] if b else None
    rows = json.load(open("data/bench_SPY_1d.json"))
    ms = int(datetime.strptime(c, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    first = next(r for r in rows if r[0] >= ms)
    return 10000 * rows[-1][4] / first[1]


out = {"kind": KIND, "fee": F, "cohorts": {}, "h2": [], "h4": {}, "h5": {}}
print(f"# {KIND}  fee/leg={F*1e4:.1f}bp   end={datetime.fromtimestamp(d['end']/1000, timezone.utc).date()}")

# ---------- headline: TP 10% / 12%, spec exit (tp_only)
for tp in (0.10, 0.12):
    print(f"\n## TP {tp:.0%}, spec (no stop) — final equity of $10,000")
    print("| start | random p10 | random p50 | random p90 | dip p50 | drop p50 | rsi p50 | EW hold | "
          + ("BTC hold" if KIND == "crypto" else "SPY hold") + " | realized p50 | unrealized p50 | slots stuck at end p50 | worst stuck slot p50 | MTM max DD p50 |")
    print("|---" * 15 + "|")
    for c in COH:
        rnd = dist(c, "tp_only", tp, "random")
        fin = [x["final"] for x in rnd]
        dps = [st.median(x["final"] for x in dist(c, "tp_only", tp, k)) for k in DIPS]
        rl = st.median(x["realized"] for x in rnd)
        ur = st.median(x["unrealized"] for x in rnd)
        stuck = st.median(len(x["open"]) for x in rnd)
        worst = st.median(min((o[2] for o in x["open"]), default=0) for x in rnd)
        dd = st.median(x["max_dd"] for x in rnd)
        print(f"| {c} | {q(fin,.1):,.0f} | {q(fin,.5):,.0f} | {q(fin,.9):,.0f} | "
              + " | ".join(f"{v:,.0f}" for v in dps)
              + f" | {B[c]['ew'][0]:,.0f} | {ref(c):,.0f} | {rl:+,.0f} | {ur:+,.0f} | {stuck:.0f}/10 | {worst:.0%} | {dd:.0%} |")
        out["cohorts"].setdefault(c, {})[f"tp{tp}"] = {
            "random_p10": q(fin, .1), "random_p50": q(fin, .5), "random_p90": q(fin, .9),
            "dip_p50": dps, "ew": B[c]["ew"][0], "ref": ref(c), "realized_p50": rl,
            "unrealized_p50": ur, "stuck_p50": stuck, "worst_stuck_p50": worst, "dd_p50": dd}

# ---------- trip anatomy (random, TP 10%, tp_only, first cohort)
c0 = COH[0]
rnd = dist(c0, "tp_only", 0.10, "random")
print(f"\n## Trip anatomy, random entry, TP 10%, no stop, start {c0}")
print(f"closed trips p50 {st.median(x['trips'] for x in rnd):.0f}; closed-trip win rate p50 "
      f"{st.median(x['wins']/max(1,x['trips']) for x in rnd):.1%}; days to TP p50 "
      f"{st.median(x['med_hold_tp_days'] for x in rnd if x['med_hold_tp_days'] is not None):.1f}, "
      f"p90 {st.median(x['p90_hold_tp_days'] for x in rnd if x['p90_hold_tp_days'] is not None):.1f}; "
      f"capital deployed p50 {st.median(x['deployed'] for x in rnd):.0%}")

# ---------- H2: dip vs random, every cell
cells = 0
beat_p50 = 0
beat_p90 = 0
below_p10 = 0
for c in COH:
    for ex in EXITS:
        for tp in TPS:
            rnd = [x["final"] for x in dist(c, ex, tp, "random")]
            for k in DIPS:
                m = st.median(x["final"] for x in dist(c, ex, tp, k))
                cells += 1
                beat_p50 += m > q(rnd, .5)
                beat_p90 += m > q(rnd, .9)
                below_p10 += m < q(rnd, .1)
                out["h2"].append([c, ex, tp, k, m, q(rnd, .1), q(rnd, .5), q(rnd, .9)])
print(f"\n## H2 dip vs random: {cells} cells; dip median > random median in {beat_p50} "
      f"({beat_p50/cells:.0%}); > random p90 in {beat_p90}; < random p10 in {below_p10}")
for k in DIPS:
    rows = [h for h in out["h2"] if h[3] == k]
    print(f"   {k}: > p50 {sum(h[4] > h[6] for h in rows)}/{len(rows)}, > p90 {sum(h[4] > h[7] for h in rows)}, < p10 {sum(h[4] < h[5] for h in rows)}")

# ---------- H4: target sweep (random p50, every cohort)
print("\n## H4 target sweep — random-entry p50 final equity")
for ex in EXITS:
    print(f"\n{ex}: | start | " + " | ".join(f"{t:.0%}" for t in TPS) + " | seed p10–p90 width at 10% |")
    for c in COH:
        meds = [q([x["final"] for x in dist(c, ex, t, "random")], .5) for t in TPS]
        r10 = [x["final"] for x in dist(c, ex, 0.10, "random")]
        print(f"| {c} | " + " | ".join(f"{m:,.0f}" for m in meds) + f" | {q(r10,.9)-q(r10,.1):,.0f} |")
        out["h4"].setdefault(ex, {})[c] = meds

# ---------- H5: exit variant, worst cohort, TP 10 / 12
print("\n## H5 exits — random p50 final by cohort (TP 10%)")
print("| start | " + " | ".join(EXITS) + " | EW hold |")
for c in COH:
    vals = [q([x["final"] for x in dist(c, ex, 0.10, "random")], .5) for ex in EXITS]
    print(f"| {c} | " + " | ".join(f"{v:,.0f}" for v in vals) + f" | {B[c]['ew'][0]:,.0f} |")
    out["h5"][c] = vals

# ---------- fee sensitivity (crypto)
fees = sorted({r["fee"] for r in d["runs"]})
if len(fees) > 1:
    lo = fees[0]
    print(f"\n## fee sensitivity: dip-rule seed-0 final, {F*1e4:.0f}bp vs {lo*1e4:.1f}bp (TP 10%)")
    for c in COH:
        for ex in EXITS:
            a = [R[(c, ex, 0.10, k, F)][0]["final"] for k in DIPS]
            b = [R[(c, ex, 0.10, k, lo)][0]["final"] for k in DIPS]
            print(f"{c} {ex:11s} " + "  ".join(f"{k} {x:,.0f}->{y:,.0f}" for k, x, y in zip(DIPS, a, b)))

json.dump(out, open(f"summary_{KIND}.json", "w"), indent=1)
