"""Run the pre-registered grid. python3 run.py [crypto|stock] -> results_<kind>.json"""
import json, sys, time, multiprocessing as mp
import numpy as np
import engine as E
KIND = sys.argv[1]
SEEDS = int(sys.argv[2]) if len(sys.argv) > 2 else 50
ts, names, O, H, L, C = E.load_panel(KIND)
Cf = E.ffill(C)
PANEL = (ts, names, O, H, L, C, Cf)
SIG = E.signals(KIND, O, H, L, C)
BPD = 24 if KIND == "crypto" else 1
TIME_BARS = 720 if KIND == "crypto" else 21
FEE = 0.0010 if KIND == "crypto" else 0.0001
COHORTS = (["2020-01-01", "2021-11-10", "2022-06-01", "2024-01-01", "2025-01-01"]
           if KIND == "crypto" else
           ["2016-01-04", "2020-02-19", "2021-11-10", "2022-06-01", "2024-01-02", "2025-01-02"])
TPS = [0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30]
EXITS = {"tp_only": {}, "tp_stop15": {"stop": 0.15}, "tp_time30d": {"time_bars": TIME_BARS}}
def t_of(d):
    import datetime as dt
    ms = int(dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    return int(np.searchsorted(ts, ms))
def job(a):
    coh, ex, tp, rule, seed, fee = a
    t0 = t_of(coh); t1 = len(ts)
    cfg = E.Cfg(tp=tp, fee=fee, rule=rule, seed=seed, **EXITS[ex])
    r = E.replay(PANEL, SIG, cfg, t0, t1, BPD)
    tr = r.trips
    holds = sorted(x[5] for x in tr if x[3] == "tp")
    return {"cohort": coh, "exit": ex, "tp": tp, "rule": rule, "seed": seed, "fee": fee,
            "final": r.final_equity, "realized": r.realized, "unrealized": r.unrealized,
            "trips": len(tr), "wins": sum(1 for x in tr if x[4] > 0),
            "by_reason": {k: sum(1 for x in tr if x[3] == k) for k in ("tp", "stop", "time", "delist")},
            "med_hold_tp_days": (holds[len(holds)//2] / BPD) if holds else None,
            "p90_hold_tp_days": (holds[int(len(holds)*0.9)] / BPD) if holds else None,
            "open": [(n, e, round(ret, 4), round(b / BPD, 1)) for n, e, ret, b in r.open_pos],
            "max_dd": E.max_dd(r.eq_daily), "deployed": r.deployed_frac,
            "eq_daily": r.eq_daily[::7] if seed == 0 else None,
            "trip_list": tr if (seed == 0 and tp in (0.10, 0.12)) else None}
if __name__ == "__main__":
    jobs = []
    for coh in COHORTS:
        for ex in EXITS:
            for tp in TPS:
                for rule in ("dip", "drop", "rsi"):
                    for s in range(SEEDS + 1):
                        jobs.append((coh, ex, tp, rule, s, FEE))
                for s in range(SEEDS):
                    jobs.append((coh, ex, tp, "random", s, FEE))
    if KIND == "crypto":   # fee sensitivity at the platform's simulated 4.5 bp
        for coh in COHORTS:
            for ex in EXITS:
                for tp in (0.10, 0.12):
                    for rule in ("dip", "drop", "rsi"):
                        jobs.append((coh, ex, tp, rule, 0, 0.00045))
    t = time.time()
    with mp.get_context("fork").Pool(max(2, mp.cpu_count() - 2)) as p:
        out = p.map(job, jobs, chunksize=4)
    bench = {}
    for coh in COHORTS:
        t0 = t_of(coh)
        ew = E.buy_hold(PANEL, t0, len(ts))
        b1 = E.buy_hold(PANEL, t0, len(ts), only={"BTCUSDT"} if KIND == "crypto" else {"__none__"})
        bench[coh] = {"ew": ew, "btc": b1}
    json.dump({"kind": KIND, "names": names, "end": int(ts[-1]), "bench": bench, "runs": out},
              open(f"results_{KIND}.json", "w"))
    print(KIND, len(jobs), "runs", round(time.time() - t), "s")
