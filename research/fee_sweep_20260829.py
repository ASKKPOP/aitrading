"""Fee-sensitivity sweep on the demoted-proposal replay + realized ledger.

Pre-registered (reading #77 top-of-queue):
  Sweep round-trip crypto fee in {0bp, 3bp maker, 9bp taker}.
  Falsifier: headline replay verdict (net mean/CI90) flips sign at 3bp.

Method (stated before running):
  * Cohort: run_events order_discussion, final.action='hold',
    proposed.action in (buy, sell), ts <= 2026-08-28T21:13Z (reading #73's
    data cutoff). buy -> long entry. sell -> short entry ONLY on a
    futures-capable book (market_type=='futures' or market=='futures')
    with net held qty <= 0 at proposal ts (else it was an exit proposal
    -> excluded).
  * Price paths: 5m candles. Crypto: OKX. forex/futures/us-stock: Yahoo.
  * Exit rule (primary): the committed house rails of
    research/zi_control_replay.py -- stop 1.5%, target 4.5%, breakeven
    ratchet (floor = 2 x 0.045% x notional, arm = 2.2x floor, lock 0.5,
    5m closes), 24h max hold, stop-first, slip 0.03%/side.
    PATHS ARE COMPUTED ONCE at the taker-anchored ratchet ("same trips,
    only the fee constant varies"); the swept fee enters the terminal
    deduction only. A fully fee-endogenous variant (ratchet re-anchored
    per fee level) is reported as secondary.
  * Secondary exit rule: no ratchet (pure stop/target/24h) as robustness.
  * Fees: per-market per-leg. Crypto swept {0, 1.5bp, 4.5bp}/leg; other
    markets pinned at fees.py rates (futures 0.5bp, forex 0.8bp,
    us-stock 0.5bp per leg) at every sweep level (realistic basis), AND
    an "all-swept" basis where every market gets the swept rate (the
    literal 'only the fee constant varies' basis).
  * Stats per level: mean net bp/trip equal-weighted (notional cancels:
    simulate_trip is homogeneous degree 1, so bp/trip is notional-free;
    a notional-weighted mean over blocked proposals has no defined
    notional -- blocked orders were never sized; reported as N/A),
    median, bootstrap CI90 of mean (10k, seed 20260829), % positive.
  * Realized ledger: signals FIFO per run_id since 2026-08-13T00Z;
    gross from prices (never signals.pnl -- agent-6 zeroing), fees from
    fee_usd at taker; maker/zero recompute crypto legs at 1.5bp/0 of leg
    notional; non-crypto legs keep booked fees.
"""
from __future__ import annotations
import json, os, random, statistics, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

SP = os.path.dirname(os.path.abspath(__file__))
BAR = 300
STOP_PCT, TARGET_PCT = 0.015, 0.045
RATCHET_ARM_X, RATCHET_FRAC = 2.2, 0.5
MAX_HOLD = 24 * 3600
SLIP = 0.0003
TAKER_LEG = 0.00045
MARKET_LEG = {"crypto": 0.00045, "futures": 0.00005, "forex": 0.00008,
              "us-stock": 0.00005}
SWEEP_LEGS = [0.0, 0.00015, 0.00045]   # per-leg: 0 / maker 1.5bp / taker 4.5bp

def iso_ep(ts): return int(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                           .replace(tzinfo=timezone.utc).timestamp())

# ---------- candles ----------
def okx_fetch(sym, t0, t1):
    inst = sym[:-4] + "-USDT"
    path = f"{SP}/candles/okx_{inst}.json"
    if os.path.exists(path): return json.load(open(path))
    rows = {}
    after = (t1 + BAR) * 1000
    while True:
        q = urllib.parse.urlencode({"instId": inst, "bar": "5m",
                                    "after": str(after), "limit": "100"})
        req = urllib.request.Request(
            "https://www.okx.com/api/v5/market/history-candles?" + q,
            headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.load(r).get("data", [])
        except Exception as e:
            print("OKX ERR", inst, e); data = []
        if not data: break
        for c in data:
            ts = int(c[0]) // 1000
            if t0 <= ts <= t1:
                rows[ts] = [ts, float(c[1]), float(c[2]), float(c[3]), float(c[4])]
        oldest = int(data[-1][0]) // 1000
        if oldest <= t0: break
        after = int(data[-1][0]); time.sleep(0.12)
    out = [rows[k] for k in sorted(rows)]
    os.makedirs(f"{SP}/candles", exist_ok=True)
    json.dump(out, open(path, "w")); return out

YMAP_SUFFIX = {"futures": "=F", "forex": "=X", "us-stock": ""}
def yahoo_fetch(sym, market, t0, t1):
    ysym = sym + YMAP_SUFFIX[market]
    path = f"{SP}/candles/y_{ysym.replace('=','_')}.json"
    if os.path.exists(path): return json.load(open(path))
    q = urllib.parse.urlencode({"period1": str(t0 - BAR), "period2": str(t1 + BAR),
                                "interval": "5m", "includePrePost": "false"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    out = []
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.load(r)
        res = j["chart"]["result"][0]
        tss = res.get("timestamp") or []
        qd = res["indicators"]["quote"][0]
        for i, ts in enumerate(tss):
            o, h, l, c = (qd["open"][i], qd["high"][i], qd["low"][i], qd["close"][i])
            if None in (o, h, l, c): continue
            out.append([ts, o, h, l, c])
    except Exception as e:
        print("YAHOO ERR", ysym, e)
    os.makedirs(f"{SP}/candles", exist_ok=True)
    json.dump(out, open(path, "w")); time.sleep(0.4); return out

# ---------- simulate: returns (gross_frac, exit_leg_notional_frac, path_tag)
# All per 1.0 notional. gross_frac = gross pnl / notional.
# exit_leg_frac = |qty*exit_px| / notional (exit-leg fee base).
def walk(candles, ep, side, anchor_leg):
    # entry at first close at/after ep
    i0 = None
    for i, c in enumerate(candles):
        if c[0] >= ep: i0 = i; break
    if i0 is None or i0 + 1 >= len(candles): return None
    entry = candles[i0][4] * (1 + SLIP if side == "long" else 1 - SLIP)
    if entry <= 0: return None
    qty = 1.0 / entry
    sgn = 1.0 if side == "long" else -1.0
    stop = entry * (1 - sgn * STOP_PCT)
    target = entry * (1 + sgn * TARGET_PCT)
    fee_floor = 2 * anchor_leg * 1.0
    arm = RATCHET_ARM_X * fee_floor
    armed, peak = False, 0.0
    t_end = candles[i0][0] + MAX_HOLD
    exit_px, tag = None, "eod"
    use_ratchet = anchor_leg > 0
    for j in range(i0 + 1, len(candles)):
        ts, _o, hi, lo, cl = candles[j]
        if (side == "long" and lo <= stop) or (side == "short" and hi >= stop):
            exit_px, tag = stop, "stop"; break
        if (side == "long" and hi >= target) or (side == "short" and lo <= target):
            exit_px, tag = target, "target"; break
        pnl = sgn * (cl - entry) * qty
        peak = max(peak, pnl)
        if use_ratchet:
            if not armed and peak >= arm: armed = True
            if armed:
                floor = fee_floor + RATCHET_FRAC * max(0.0, peak - fee_floor)
                if pnl <= floor: exit_px, tag = cl, "ratchet"; break
        if ts >= t_end: exit_px, tag = cl, "horizon"; break
    else:
        return None  # ran off the data before any exit condition -> unresolved
    exit_px *= (1 - SLIP) if side == "long" else (1 + SLIP)
    gross = sgn * (exit_px - entry) * qty
    return gross, abs(qty * exit_px), tag

# ---------- stats ----------
def boot_ci(vals, n=10000, seed=20260829):
    rng = random.Random(seed); m = len(vals); means = []
    for _ in range(n):
        means.append(sum(vals[rng.randrange(m)] for _ in range(m)) / m)
    means.sort()
    return means[int(0.05 * n)], means[int(0.95 * n)]

def stats_line(nets_bp):
    n = len(nets_bp)
    mean = sum(nets_bp) / n
    med = statistics.median(nets_bp)
    lo, hi = boot_ci(nets_bp)
    pos = 100.0 * sum(1 for x in nets_bp if x > 0) / n
    return f"n={n:5d}  mean={mean:+8.2f}bp  CI90=[{lo:+7.2f},{hi:+7.2f}]  median={med:+7.2f}bp  pos={pos:5.1f}%"

def main():
    events = []
    for line in open(f"{SP}/demoted_events.tsv"):
        p = line.rstrip("\n").split("\t")
        events.append(dict(eid=int(p[0]), run_id=int(p[1]), ts=p[2], act=p[3],
                           conf=p[4], symbol=p[5], market=p[6], mtype=p[7],
                           agent=int(p[8]), ep=iso_ep(p[2])))
    fills = []
    for line in open(f"{SP}/fills.tsv"):
        p = line.rstrip("\n").split("\t")
        fills.append(dict(id=int(p[0]), run_id=int(p[1]), agent=int(p[2]),
                          market=p[3], symbol=p[4], side=p[5],
                          px=float(p[6]), qty=float(p[7]), fee=float(p[8]),
                          pnl=(float(p[9]) if p[9] != "" else None),
                          ep=int(p[10])))
    # held qty per run at ts
    byrun = {}
    for f in fills: byrun.setdefault(f["run_id"], []).append(f)
    def held(run_id, ep):
        q = 0.0
        for f in byrun.get(run_id, []):
            if f["ep"] < ep:
                q += f["qty"] if f["side"] in ("buy", "cover") else -f["qty"]
        return q
    cohort, excluded = [], {"sell_spot": 0, "sell_close": 0, "buy_cover": 0}
    for e in events:
        futures_book = (e["mtype"].lower() == "futures" or e["market"] == "futures")
        h = held(e["run_id"], e["ep"])
        if e["act"] == "buy":
            if h < 0: excluded["buy_cover"] += 1; continue
            e["side"] = "long"; cohort.append(e)
        else:
            if not futures_book: excluded["sell_spot"] += 1; continue
            if h > 0: excluded["sell_close"] += 1; continue
            e["side"] = "short"; cohort.append(e)
    print("cohort", len(cohort), "excluded", excluded)
    from collections import Counter
    print("by market:", Counter(e["market"] for e in cohort))
    # fetch candles per symbol
    t_min = min(e["ep"] for e in cohort) - 2 * BAR
    t_max = max(e["ep"] for e in cohort) + MAX_HOLD + 3600
    csyms = sorted({(e["market"], e["symbol"]) for e in cohort})
    candles = {}
    for mk, sym in csyms:
        c = okx_fetch(sym, t_min, t_max) if mk == "crypto" else yahoo_fetch(sym, mk, t_min, t_max)
        candles[(mk, sym)] = c
        print(f"candles {mk} {sym}: {len(c)}")
    # simulate
    results = []   # each: dict(market, side, gross_bp, exitfrac, tag, variant grosses)
    miss = Counter()
    for e in cohort:
        c = candles[(e["market"], e["symbol"])]
        if not c: miss[e["symbol"] + ":nocandles"] += 1; continue
        r_tk = walk(c, e["ep"], e["side"], TAKER_LEG)      # taker-anchored path (primary)
        r_nr = walk(c, e["ep"], e["side"], 0.0)            # no-ratchet robustness
        r_mk = walk(c, e["ep"], e["side"], 0.00015)        # maker-anchored path (secondary endogenous)
        if r_tk is None: miss[e["symbol"] + ":unresolved"] += 1; continue
        results.append(dict(market=e["market"], side=e["side"], agent=e["agent"],
                            tk=r_tk, nr=r_nr, mk=r_mk))
    print("simulated", len(results), "missing", dict(miss))
    json.dump(results, open(f"{SP}/fee_sweep_trips.json", "w"))

    def net_bp(r, key, crypto_leg, all_swept):
        gross, exitfrac, _ = r[key]
        leg = crypto_leg if (all_swept or r["market"] == "crypto") else MARKET_LEG[r["market"]]
        fees = leg * 1.0 + leg * exitfrac
        return (gross - fees) * 1e4

    print("\n===== REPLAY SWEEP — PRIMARY (paths fixed at taker-anchored ratchet) =====")
    for basis, all_swept in (("realistic (crypto swept, others pinned)", False),
                             ("all-swept (every market at swept rate)", True)):
        print(f"--- basis: {basis}")
        for leg in SWEEP_LEGS:
            nets = [net_bp(r, "tk", leg, all_swept) for r in results]
            print(f"  RT fee {2*leg*1e4:4.1f}bp : {stats_line(nets)}")
        # crypto only
        cr = [r for r in results if r["market"] == "crypto"]
        for leg in SWEEP_LEGS:
            nets = [net_bp(r, "tk", leg, True) for r in cr]
            print(f"  [crypto-only] RT {2*leg*1e4:4.1f}bp : {stats_line(nets)}")
        if all_swept: break  # crypto-only identical across bases; print once

    print("\n===== SECONDARY — fee-ENDOGENOUS paths (ratchet re-anchored per level) =====")
    for leg, key in ((0.0, "nr"), (0.00015, "mk"), (0.00045, "tk")):
        sub = [r for r in results if r[key] is not None]
        nets = [net_bp(r, key, leg, False) for r in sub]
        print(f"  RT fee {2*leg*1e4:4.1f}bp (paths@{key}) : {stats_line(nets)}")

    print("\n===== ROBUSTNESS — NO-RATCHET rule (stop/target/24h only) =====")
    sub = [r for r in results if r["nr"] is not None]
    for leg in SWEEP_LEGS:
        nets = [net_bp(r, "nr", leg, False) for r in sub]
        print(f"  RT fee {2*leg*1e4:4.1f}bp : {stats_line(nets)}")

    # ---------------- realized ledger ----------------
    print("\n===== REALIZED LEDGER (signals FIFO, era >= 2026-08-13T00Z) =====")
    era0 = iso_ep("2026-08-13T00:00:00Z")
    trips = []  # (market, entry_notional, gross_usd, entry_legs, exit_legs) FIFO per run
    for run_id, fl in byrun.items():
        fl = sorted(fl, key=lambda f: (f["ep"], f["id"]))
        lots = []  # open lots: [qty_remaining, px, fee_per_unit, ep, sgn]
        for f in fl:
            opening = f["side"] in ("buy", "short")
            sgn = 1.0 if f["side"] in ("buy", "sell") else -1.0  # not used for sign of pos
            if opening:
                lots.append([f["qty"], f["px"], f["fee"] / f["qty"] if f["qty"] else 0.0,
                             f["ep"], 1.0 if f["side"] == "buy" else -1.0])
            else:
                want = 1.0 if f["side"] == "sell" else -1.0  # sell closes longs, cover closes shorts
                remaining = f["qty"]
                exit_fee_per_unit = f["fee"] / f["qty"] if f["qty"] else 0.0
                while remaining > 1e-12:
                    lot = next((l for l in lots if l[4] == want), None)
                    if lot is None: break
                    take = min(lot[0], remaining)
                    gross = lot[4] * (f["px"] - lot[1]) * take
                    trips.append(dict(market=f["market"], symbol=f["symbol"],
                                      notion=take * lot[1],
                                      gross=gross,
                                      efee=lot[2] * take, xfee=exit_fee_per_unit * take,
                                      exit_notion=take * f["px"],
                                      ep=f["ep"], agent=f["agent"]))
                    lot[0] -= take; remaining -= take
                    if lot[0] <= 1e-12: lots.remove(lot)
                if remaining > 1e-9:
                    print(f"  WARN run {run_id}: exit qty {remaining} unmatched")
    trips = [t for t in trips if t["ep"] >= era0]
    print(f"trips n={len(trips)}  (crypto {sum(1 for t in trips if t['market']=='crypto')})")
    for label, leg in (("0bp RT", 0.0), ("3bp RT maker", 0.00015), ("9bp RT taker(booked)", None)):
        nets_usd, nets_bp, notion = [], [], 0.0
        for t in trips:
            if leg is None or t["market"] != "crypto":
                fees = t["efee"] + t["xfee"]          # booked
            else:
                fees = leg * t["notion"] + leg * t["exit_notion"]
            net = t["gross"] - fees
            nets_usd.append(net)
            nets_bp.append(net / t["notion"] * 1e4)
            notion += t["notion"]
        tot = sum(nets_usd)
        nw = tot / notion * 1e4
        print(f"  {label:22s}: {stats_line(nets_bp)}  | total ${tot:+.2f} on ${notion:,.0f} notional traded, notional-wtd {nw:+.2f}bp")
    json.dump(trips, open(f"{SP}/realized_trips.json", "w"))

if __name__ == "__main__":
    from collections import Counter
    main()
