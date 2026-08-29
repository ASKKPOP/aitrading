"""QA-C: own walker. (a) ambiguous-candle count, (b) zero-slip sweep,
(c) differential vs reference simulate_trip (origin/main)."""
import json, os, random, statistics
from datetime import datetime, timezone
from collections import Counter

SP = os.path.dirname(os.path.abspath(__file__))
BAR = 300
STOP_PCT, TARGET_PCT = 0.015, 0.045
ARM_X, FRAC = 2.2, 0.5
MAX_HOLD = 24 * 3600
MARKET_LEG = {"crypto": 0.00045, "futures": 0.00005, "forex": 0.00008,
              "us-stock": 0.00005}

def iso_ep(s): return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
                          .replace(tzinfo=timezone.utc).timestamp())

# ---- my own cohort build from raw TSVs ----
events = []
for line in open(f"{SP}/demoted_events.tsv"):
    p = line.rstrip("\n").split("\t")
    events.append((int(p[0]), int(p[1]), iso_ep(p[2]), p[3], p[5], p[6], p[7], int(p[8])))
fills = []
for line in open(f"{SP}/fills.tsv"):
    p = line.rstrip("\n").split("\t")
    fills.append((int(p[1]), p[5], float(p[7]), int(p[10])))
byrun = {}
for rid, side, qty, fep in fills:
    byrun.setdefault(rid, []).append((fep, side, qty))
def held(rid, at):
    return sum(q if s in ("buy", "cover") else -q
               for fep, s, q in byrun.get(rid, []) if fep < at)

cohort = []
exc = Counter()
for eid, rid, ep, act, sym, mkt, mtype, agent in events:
    fut = (mtype.lower() == "futures" or mkt == "futures")
    h = held(rid, ep)
    if act == "buy":
        if h < 0: exc["buy_cover"] += 1; continue
        cohort.append((ep, "long", sym, mkt, agent))
    else:
        if not fut: exc["sell_spot"] += 1; continue
        if h > 0: exc["sell_close"] += 1; continue
        cohort.append((ep, "short", sym, mkt, agent))
print(f"events={len(events)} cohort={len(cohort)} excluded={dict(exc)}")

# ---- candles from cache ----
def load_c(mkt, sym):
    if mkt == "crypto":
        path = f"{SP}/candles/okx_{sym[:-4]}-USDT.json"
    else:
        suf = {"futures": "_F", "forex": "_X", "us-stock": ""}[mkt]
        path = f"{SP}/candles/y_{sym}{suf}.json"
    return json.load(open(path)) if os.path.exists(path) else []
cd = {}
for ep, side, sym, mkt, agent in cohort:
    if (mkt, sym) not in cd:
        cd[(mkt, sym)] = load_c(mkt, sym)

# ---- my walker: also reports ambiguity ----
def mywalk(c, ep, side, slip, anchor_leg):
    i0 = next((i for i, b in enumerate(c) if b[0] >= ep), None)
    if i0 is None or i0 + 1 >= len(c): return None
    entry = c[i0][4] * (1 + slip if side == "long" else 1 - slip)
    if entry <= 0: return None
    qty = 1.0 / entry
    sgn = 1.0 if side == "long" else -1.0
    stop = entry * (1 - sgn * STOP_PCT)
    target = entry * (1 + sgn * TARGET_PCT)
    ff = 2 * anchor_leg
    arm = ARM_X * ff
    armed, peak = False, 0.0
    t_end = c[i0][0] + MAX_HOLD
    amb = 0
    for j in range(i0 + 1, len(c)):
        ts, _o, hi, lo, cl = c[j]
        stop_hit = (lo <= stop) if side == "long" else (hi >= stop)
        tgt_hit = (hi >= target) if side == "long" else (lo <= target)
        if stop_hit and tgt_hit: amb += 1
        if stop_hit:
            return finish(stop, "stop", entry, qty, sgn, slip, side), amb, (stop_hit and tgt_hit)
        if tgt_hit:
            return finish(target, "target", entry, qty, sgn, slip, side), amb, False
        pnl = sgn * (cl - entry) * qty
        peak = max(peak, pnl)
        if anchor_leg > 0:
            if not armed and peak >= arm: armed = True
            if armed and pnl <= ff + FRAC * max(0.0, peak - ff):
                return finish(cl, "ratchet", entry, qty, sgn, slip, side), amb, False
        if ts >= t_end:
            return finish(cl, "horizon", entry, qty, sgn, slip, side), amb, False
    return None

def finish(px, tag, entry, qty, sgn, slip, side):
    px = px * ((1 - slip) if side == "long" else (1 + slip))
    return sgn * (px - entry) * qty, abs(qty * px), tag

res, res0 = [], []
amb_any, amb_at_exit, tags = 0, 0, Counter()
for ep, side, sym, mkt, agent in cohort:
    c = cd[(mkt, sym)]
    if not c: continue
    r = mywalk(c, ep, side, 0.0003, 0.00045)
    if r is None: continue
    (g, xf, tag), amb, exit_amb = r
    tags[tag] += 1
    if amb: amb_any += 1
    if exit_amb: amb_at_exit += 1
    res.append((mkt, g, xf))
    r0 = mywalk(c, ep, side, 0.0, 0.00045)
    if r0 is not None:
        res0.append((mkt, r0[0][0], r0[0][1]))
print(f"my resim n={len(res)} tags={dict(tags)}")
print(f"trips with ANY stop+target-in-one-candle bar: {amb_any}; "
      f"stop exits where target ALSO inside exit candle: {amb_at_exit}")

def rep(label, rows, leg_crypto, fee_on):
    nets = []
    for mkt, g, xf in rows:
        leg = (leg_crypto if mkt == "crypto" else MARKET_LEG[mkt]) if fee_on else 0.0
        nets.append((g - leg * (1 + xf)) * 1e4)
    n = len(nets)
    print(f"{label:30s} n={n} mean={sum(nets)/n:+7.2f} med={statistics.median(nets):+6.2f} "
          f"pos={100*sum(1 for x in nets if x>0)/n:.1f}%")

rep("MY resim RT9bp slip3bp", res, 0.00045, True)
rep("MY resim 0fee slip3bp", res, 0.0, False)
rep("MY resim 0fee 0slip (exact)", res0, 0.0, False)

# ---- differential: my/its walk vs reference simulate_trip ----
import importlib.util
spec = importlib.util.spec_from_file_location("ref", f"{SP}/qa_ref_zi.py")
ref = importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
spec2 = importlib.util.spec_from_file_location("fsw", f"{SP}/fee_sweep.py")
import types
fsw = importlib.util.module_from_spec(spec2)
fsw.__name__ = "fsw_nomain"
spec2.loader.exec_module(fsw)

rng = random.Random(7)
crypto_syms = [k for k in cd if k[0] == "crypto" and len(cd[k]) > 400]
maxd, trials = 0.0, 0
for _ in range(500):
    k = rng.choice(crypto_syms)
    c = cd[k]
    i = rng.randrange(0, len(c) - 300)
    side = rng.choice(["long", "short"])
    notional = rng.uniform(10, 1000)
    r_ref = ref.simulate_trip(c, i, side, notional, 0.0003)
    r_w = fsw.walk(c, c[i][0], side, 0.00045)
    if r_w is None:
        continue  # walk drops unresolved; ref prices at last close
    g, xf, _t = r_w
    net_w = (g - 0.00045 * (1 + xf)) * notional
    d = abs(net_w - r_ref)
    maxd = max(maxd, d); trials += 1
print(f"differential walk-vs-reference: trials={trials} max|diff|={maxd:.3e}")
