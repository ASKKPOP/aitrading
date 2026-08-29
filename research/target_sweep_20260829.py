"""TARGET-level sweep on the demoted-proposal replay (owner order: 'targets
never reached -> lower the target so orders complete').

Pre-registered before running:
  H0: no target level in {0.3,0.5,0.75,1.0,1.5,2.0,3.0,4.5}% lifts the
      replay book's mean net bp/trip CI90 above zero (fees+slip dominate).
  Falsifier: any level whose bootstrap CI90 lower bound > 0.

Method (identical mechanics to fee_sweep.py / research/zi_control_replay.py):
  * Same cohort build (demoted holds, buy->long, futures sell w/ no long
    inventory -> short), same 5m candles (all cached), same entry = first
    close at/after proposal ts +/- 0.03% slip, stop 1.5%, stop-first
    adjudication, breakeven ratchet (taker-anchored: floor 9bp notional,
    arm 2.2x, lock 0.5, on 5m closes), 24h horizon, exit slip 0.03%.
  * ONLY the target level varies. Each level also run with ratchet OFF
    (stop/target/horizon only).
  * Fees realistic basis: crypto taker 4.5bp/leg, futures 0.5bp, forex
    0.8bp, us-stock 0.5bp per leg. entry leg on 1.0 notional, exit leg on
    |qty*exit_px|.
  * Common-trip set: only entries that resolve under EVERY config, so all
    rows compare the same trips.
  * MFE: max favorable extreme (hi for long / lo for short) vs slipped
    entry, candles from entry+1 through the 24h-horizon candle, ENDING
    BEFORE the candle where the 1.5% stop trips (stop-first: that
    candle's favorable extreme is NOT credited). Optimistic variant
    including the stop candle's extreme reported as a bound.
  * Adversarial: per level, count exit candles where BOTH stop and target
    were inside the candle range; re-run everything target-first as the
    upper bound. Regime split: cohort halves by entry-ts median.
  * Bootstrap CI90 of the mean: 10k resamples, seed 20260829 (same as
    fee_sweep). Book $: convention $1 notional per trip (blocked orders
    were never sized) -> total $ = sum(net_frac).
"""
from __future__ import annotations
import json, os, random, statistics
from collections import Counter
from datetime import datetime, timezone

SP = os.path.dirname(os.path.abspath(__file__))
BAR = 300
STOP_PCT = 0.015
RATCHET_ARM_X, RATCHET_FRAC = 2.2, 0.5
MAX_HOLD = 24 * 3600
SLIP = 0.0003
TAKER_LEG = 0.00045
MARKET_LEG = {"crypto": 0.00045, "futures": 0.00005, "forex": 0.00008,
              "us-stock": 0.00005}
TARGETS = [0.003, 0.005, 0.0075, 0.010, 0.015, 0.020, 0.030, 0.045]

def iso_ep(ts):
    return int(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=timezone.utc).timestamp())

def load_candles(mk, sym):
    if mk == "crypto":
        path = f"{SP}/candles/okx_{sym[:-4]}-USDT.json"
    else:
        suf = {"futures": "=F", "forex": "=X", "us-stock": ""}[mk]
        path = f"{SP}/candles/y_{(sym + suf).replace('=', '_')}.json"
    if not os.path.exists(path):
        return []
    return json.load(open(path))

# ---------- walker: parameterized target, ratchet on/off, adjudication ----------
def walk(candles, ep, side, target_pct, use_ratchet, target_first=False):
    i0 = None
    for i, c in enumerate(candles):
        if c[0] >= ep:
            i0 = i; break
    if i0 is None or i0 + 1 >= len(candles):
        return None
    entry = candles[i0][4] * (1 + SLIP if side == "long" else 1 - SLIP)
    if entry <= 0:
        return None
    qty = 1.0 / entry
    sgn = 1.0 if side == "long" else -1.0
    stop = entry * (1 - sgn * STOP_PCT)
    target = entry * (1 + sgn * target_pct)
    fee_floor = 2 * TAKER_LEG * 1.0
    arm = RATCHET_ARM_X * fee_floor
    armed, peak = False, 0.0
    t_end = candles[i0][0] + MAX_HOLD
    exit_px, tag = None, "eod"
    both = 0
    for j in range(i0 + 1, len(candles)):
        ts, _o, hi, lo, cl = candles[j]
        stop_in = (lo <= stop) if side == "long" else (hi >= stop)
        targ_in = (hi >= target) if side == "long" else (lo <= target)
        if stop_in and targ_in:
            both = 1
        first, second = (("target", "stop") if target_first else ("stop", "target"))
        hit = None
        for name in (first, second):
            if name == "stop" and stop_in: hit = ("stop", stop); break
            if name == "target" and targ_in: hit = ("target", target); break
        if hit:
            tag, exit_px = hit[0], hit[1]; break
        pnl = sgn * (cl - entry) * qty
        peak = max(peak, pnl)
        if use_ratchet:
            if not armed and peak >= arm:
                armed = True
            if armed:
                floor = fee_floor + RATCHET_FRAC * max(0.0, peak - fee_floor)
                if pnl <= floor:
                    exit_px, tag = cl, "ratchet"; break
        if ts >= t_end:
            exit_px, tag = cl, "horizon"; break
    else:
        return None
    exit_px *= (1 - SLIP) if side == "long" else (1 + SLIP)
    gross = sgn * (exit_px - entry) * qty
    return dict(gross=gross, exitfrac=abs(qty * exit_px), tag=tag,
                both=both if tag in ("stop", "target") else 0)

# ---------- MFE ----------
def mfe(candles, ep, side):
    i0 = None
    for i, c in enumerate(candles):
        if c[0] >= ep:
            i0 = i; break
    if i0 is None or i0 + 1 >= len(candles):
        return None
    entry = candles[i0][4] * (1 + SLIP if side == "long" else 1 - SLIP)
    sgn = 1.0 if side == "long" else -1.0
    stop = entry * (1 - sgn * STOP_PCT)
    t_end = candles[i0][0] + MAX_HOLD
    best, best_opt = 0.0, 0.0
    stopped = False
    for j in range(i0 + 1, len(candles)):
        ts, _o, hi, lo, _cl = candles[j]
        fav = (hi - entry) / entry if side == "long" else (entry - lo) / entry
        stop_in = (lo <= stop) if side == "long" else (hi >= stop)
        if stop_in:
            best_opt = max(best_opt, fav)   # optimistic: credit stop candle
            stopped = True
            break
        best = max(best, fav)
        best_opt = max(best_opt, fav)
        if ts >= t_end:
            break
    return dict(mfe=best * 100, mfe_opt=best_opt * 100, stopped=stopped)

# ---------- stats ----------
def boot_ci(vals, n=10000, seed=20260829):
    rng = random.Random(seed); m = len(vals); means = []
    for _ in range(n):
        means.append(sum(vals[rng.randrange(m)] for _ in range(m)) / m)
    means.sort()
    return means[int(0.05 * n)], means[int(0.95 * n)]

def pct(vals, p):
    s = sorted(vals); k = (len(s) - 1) * p / 100.0
    f = int(k); c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)

def net_bp(r, market):
    leg = MARKET_LEG[market]
    fees = leg * 1.0 + leg * r["exitfrac"]
    return (r["gross"] - fees) * 1e4

def main():
    events = []
    for line in open(f"{SP}/demoted_events.tsv"):
        p = line.rstrip("\n").split("\t")
        events.append(dict(eid=int(p[0]), run_id=int(p[1]), ts=p[2], act=p[3],
                           symbol=p[5], market=p[6], mtype=p[7],
                           agent=int(p[8]), ep=iso_ep(p[2])))
    fills = []
    for line in open(f"{SP}/fills.tsv"):
        p = line.rstrip("\n").split("\t")
        fills.append(dict(run_id=int(p[1]), side=p[5], qty=float(p[7]),
                          ep=int(p[10])))
    byrun = {}
    for f in fills:
        byrun.setdefault(f["run_id"], []).append(f)
    def held(run_id, ep):
        q = 0.0
        for f in byrun.get(run_id, []):
            if f["ep"] < ep:
                q += f["qty"] if f["side"] in ("buy", "cover") else -f["qty"]
        return q
    cohort, excluded = [], Counter()
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
    print("cohort", len(cohort), "excluded", dict(excluded))
    candles = {}
    for mk, sym in sorted({(e["market"], e["symbol"]) for e in cohort}):
        candles[(mk, sym)] = load_candles(mk, sym)

    # ---- simulate every config ----
    configs = []
    for t in TARGETS:
        configs.append((t, True, False))
        configs.append((t, False, False))
        configs.append((t, True, True))    # target-first bound (ratchet on)
        configs.append((t, False, True))   # target-first bound (ratchet off)
    sims = {}   # (eid) -> {config_key: result}
    for e in cohort:
        c = candles[(e["market"], e["symbol"])]
        if not c:
            continue
        row = {}
        ok = True
        for (t, ratch, tf) in configs:
            r = walk(c, e["ep"], e["side"], t, ratch, tf)
            if r is None:
                ok = False; break
            row[(t, ratch, tf)] = r
        if not ok:
            continue
        m = mfe(c, e["ep"], e["side"])
        sims[e["eid"]] = dict(e=e, row=row, mfe=m)
    trips = list(sims.values())
    n = len(trips)
    print(f"common-trip set n={n} (resolved under all {len(configs)} configs)")
    print("by market:", Counter(t["e"]["market"] for t in trips))
    print("by side:", Counter(t["e"]["side"] for t in trips))

    # ---- 1. MFE distribution ----
    print("\n===== 1. MFE (max favorable excursion, % of entry, pre-stop, 24h) =====")
    def mfe_stats(sel, label):
        vals = [t["mfe"]["mfe"] for t in sel]
        opts = [t["mfe"]["mfe_opt"] for t in sel]
        if not vals:
            print(f"  {label:28s}: n=0"); return
        print(f"  {label:28s}: n={len(vals):4d}  P25={pct(vals,25):.3f}%  "
              f"P50={pct(vals,50):.3f}%  P75={pct(vals,75):.3f}%  "
              f"P90={pct(vals,90):.3f}%  mean={sum(vals)/len(vals):.3f}%  "
              f"(optimistic P50={pct(opts,50):.3f}%)")
    mfe_stats(trips, "ALL")
    mfe_stats([t for t in trips if t["e"]["side"] == "long"], "ALL long")
    mfe_stats([t for t in trips if t["e"]["side"] == "short"], "ALL short")
    cr = [t for t in trips if t["e"]["market"] == "crypto"]
    mfe_stats(cr, "crypto")
    mfe_stats([t for t in cr if t["e"]["side"] == "long"], "crypto long")
    mfe_stats([t for t in cr if t["e"]["side"] == "short"], "crypto short")
    stopped_n = sum(1 for t in trips if t["mfe"]["stopped"])
    print(f"  stopped-out within 24h (1.5% stop): {stopped_n}/{n} = {100*stopped_n/n:.1f}%")
    # share of trips whose MFE clears each target
    print("  MFE >= target level (upper bound on reachability, pre-stop):")
    for t in TARGETS:
        c1 = sum(1 for x in trips if x["mfe"]["mfe"] >= t * 100)
        print(f"    {t*100:5.2f}%: {c1:4d}/{n} = {100*c1/n:5.1f}%")

    # ---- 2/3/4. sweep table ----
    def table(ratch, tf, label):
        print(f"\n===== {label} =====")
        print(f"{'target':>7s} {'n':>5s} {'tgt%':>6s} {'stp%':>6s} {'S:T':>7s} "
              f"{'ratch%':>6s} {'hor%':>6s} {'mean_bp':>8s} {'CI90':>18s} "
              f"{'med_bp':>8s} {'pos%':>6s} {'book$/1ea':>9s} {'both':>5s}")
        out = []
        for t in TARGETS:
            rs = [(x["row"][(t, ratch, tf)], x["e"]["market"]) for x in trips]
            tags = Counter(r["tag"] for r, _ in rs)
            nets = [net_bp(r, mk) for r, mk in rs]
            mean = sum(nets) / len(nets)
            lo, hi = boot_ci(nets)
            med = statistics.median(nets)
            pos = 100 * sum(1 for x in nets if x > 0) / len(nets)
            book = sum(x / 1e4 for x in nets)
            both = sum(r["both"] for r, _ in rs)
            st = tags.get("stop", 0); tg = tags.get("target", 0)
            ratio = f"{st}:{tg}" if tg else f"{st}:0"
            print(f"{t*100:6.2f}% {len(nets):5d} {100*tg/len(nets):6.1f} "
                  f"{100*st/len(nets):6.1f} {ratio:>7s} "
                  f"{100*tags.get('ratchet',0)/len(nets):6.1f} "
                  f"{100*tags.get('horizon',0)/len(nets):6.1f} "
                  f"{mean:+8.2f} [{lo:+7.2f},{hi:+7.2f}] {med:+8.2f} "
                  f"{pos:6.1f} {book:+9.2f} {both:5d}")
            out.append(dict(target=t, n=len(nets), tgt=tg, stp=st,
                            ratchet=tags.get("ratchet", 0),
                            horizon=tags.get("horizon", 0),
                            mean_bp=mean, ci90=[lo, hi], med_bp=med,
                            pos_pct=pos, book_usd_per_1ea=book, both=both))
        return out
    res = {}
    res["ratchet_stopfirst"] = table(True, False,
        "2a. SWEEP — house rails (ratchet ON, stop-first)  [PRIMARY]")
    res["noratchet_stopfirst"] = table(False, False,
        "2b. SWEEP — ratchet OFF (stop/target/24h, stop-first)")
    res["ratchet_targetfirst"] = table(True, True,
        "5a. BOUND — ratchet ON, TARGET-first adjudication")
    res["noratchet_targetfirst"] = table(False, True,
        "5b. BOUND — ratchet OFF, TARGET-first adjudication")

    # ---- 5. regime halves ----
    print("\n===== 5c. REGIME SPLIT (entry-ts median halves, primary config) =====")
    eps = sorted(t["e"]["ep"] for t in trips)
    mid = eps[len(eps) // 2]
    for half, sel in (("H1 (early)", [t for t in trips if t["e"]["ep"] < mid]),
                      ("H2 (late)", [t for t in trips if t["e"]["ep"] >= mid])):
        print(f"  {half}: n={len(sel)}")
        for t in TARGETS:
            rs = [(x["row"][(t, True, False)], x["e"]["market"]) for x in sel]
            nets = [net_bp(r, mk) for r, mk in rs]
            mean = sum(nets) / len(nets)
            lo, hi = boot_ci(nets)
            tg = sum(1 for r, _ in rs if r["tag"] == "target")
            print(f"    {t*100:5.2f}%: mean={mean:+7.2f}bp CI90=[{lo:+7.2f},{hi:+7.2f}] "
                  f"med={statistics.median(nets):+7.2f} tgt%={100*tg/len(nets):5.1f}")

    json.dump(dict(n=n, results=res), open(f"{SP}/target_sweep_results.json", "w"),
              indent=1)
    print(f"\nsaved {SP}/target_sweep_results.json")

if __name__ == "__main__":
    main()
