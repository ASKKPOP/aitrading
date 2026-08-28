#!/usr/bin/env python3
"""Ratchet cadence replay v2 — difference-in-difference on the archive tape.

v1 failure (documented): prod fills sit OUTSIDE the OKX archive candle ranges
on all 12 spot-checks (systematic 0.03-0.16% basis between prod's feed marks
and OKX history). Absolute replay against prod USD thresholds is invalid.
v2 simulates BOTH the live 300s-mark cadence and the counterfactuals on the
SAME archive series, rebased to the archive entry price; the basis cancels in
delta = counterfactual - simulated_live. Simulated-live is validated against
the actual fire minute/overshoot per episode.
"""
import json, math
from datetime import datetime, timezone

DATA = "/private/tmp/claude-501/-Users-desirey-Programming-src-ai-trade/d45363c2-66ff-4058-ab2c-acf93b39cdcb/scratchpad/monitoring-wt/docs/reports/data/ratchet-replay-candles"
FEE = 0.00045

EP = [
 dict(run=1335, f="1335-AVAXUSDT-2026-08-17.json", side=-1, Q=31.39369085,  era="pre",  C_cash=+0.080608, anchor_mult=1.0, live_net=-0.141443, live_exit=6.3388,  E_prod=6.340),
 dict(run=1358, f="1358-FILUSDT-2026-08-17.json",  side=-1, Q=42.02759448,  era="pre",  C_cash=None, anchor_mult=1.0, live_net=+0.002502, live_exit=0.66614, E_prod=0.6668),
 dict(run=1367, f="1367-SOLUSDT-2026-08-17.json",  side=-1, Q=0.69102106,   era="pre",  C_cash=None, anchor_mult=1.0, live_net=-0.113988, live_exit=75.607,  E_prod=75.51),
 dict(run=1392, f="1392-ZECUSDT-2026-08-18.json",  side=+1, Q=0.92065396,   era="pre",  C_cash=None, anchor_mult=1.0, live_net=-0.960242, live_exit=514.13,  E_prod=514.71),
 dict(run=1489, f="1489-UNIUSDT-2026-08-19.json",  side=-1, Q=3.03582271,   era="post", C_cash=None, anchor_mult=1.0, live_net=-0.020205, live_exit=3.2977,  E_prod=3.294),
 dict(run=1556, f="1556-LTCUSDT-2026-08-20.json",  side=+1, Q=7.45997786,   era="post", C_cash=None, anchor_mult=1.0, live_net=-0.300487, live_exit=46.976,  E_prod=46.974),
 dict(run=1710, f="1710-LTCUSDT-2026-08-23.json",  side=-1, Q=10.10814042,  era="post", C_cash=None, anchor_mult=1.0, live_net=-0.577374, live_exit=52.36,   E_prod=52.35),
 dict(run=1712, f="1712-CRVUSDT-2026-08-23.json",  side=-1, Q=1584.81392557,era="post", C_cash=None, anchor_mult=1.0, live_net=-0.507401, live_exit=0.33352, E_prod=0.3335),
 dict(run=1721, f="1721-SOLUSDT-2026-08-23.json",  side=-1, Q=5.08514633,   era="post", C_cash=None, anchor_mult=1.0, live_net=-0.137179, live_exit=95.50,   E_prod=95.559),
]
# 1417 handled separately (phantom-baseline fire, R21 bug — not cadence).

def iso2ms(s):
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()*1000)

def load(ep):
    j = json.load(open(f"{DATA}/{ep['f']}"))
    ep["entry_ms"] = iso2ms(j["entry_ts"]); ep["fire_ms"] = iso2ms(j["fire_ts"])
    ep["candles"] = [(int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4])) for c in j["candles"]]
    # entry minute index and archive entry price (minute open, closest to fill)
    for i, c in enumerate(ep["candles"]):
        if c[0] <= ep["entry_ms"] < c[0] + 60000:
            ep["i0"] = i; ep["E"] = c[1]; break
    for i, c in enumerate(ep["candles"]):
        if c[0] <= ep["fire_ms"] < c[0] + 60000:
            ep["ifire"] = i; break
    if ep["C_cash"] is not None:
        ep["C"] = ep["C_cash"]
    else:
        ep["C"] = -ep["E"] * ep["Q"] * FEE
    return ep

def X(ep, p):
    return ep["side"] * (p - ep["E"]) * ep["Q"]

def fee_term(ep, mark):
    return ep["Q"] * mark * (0.001 if ep["era"] == "pre" else 0.0009)

def arm_usd(ep, mark):
    return ep["Q"] * ep["anchor_mult"] * mark * 0.002

def m_fire(ep, mark):
    return (ep["C"] if ep["era"] == "pre" else 0.0) + X(ep, mark)

def m_peak(ep, xp):
    return (ep["C"] if ep["era"] == "pre" else 0.0) + xp

def net(ep, p):
    return X(ep, p) - ep["E"]*ep["Q"]*FEE - abs(ep["Q"])*p*FEE

def floor_price(ep):
    E, Q, s = ep["E"], ep["Q"], ep["side"]
    if ep["era"] == "pre":
        C, r = ep["C"], 0.001
        return (C/Q + E)/(1+r) if s < 0 else (E - C/Q)/(1-r)
    r = 0.0009
    return E/(1+r) if s < 0 else E/(1-r)

def fav(ep, c): return c[3] if ep["side"] < 0 else c[2]
def adv(ep, c): return c[2] if ep["side"] < 0 else c[3]
def crossed(ep, c, pf):
    return (c[2] >= pf) if ep["side"] < 0 else (c[3] <= pf)

def sim_grid(ep, step, phase):
    """Sampled-mark simulation: marks = closes of minutes i0+phase+k*step.
    Returns (fire_idx, exit_price) or (None, last_close)."""
    peak_x = -1e18
    i = ep["i0"] + phase
    while i < len(ep["candles"]):
        c = ep["candles"][i]
        mark = c[4]
        peak_x = max(peak_x, X(ep, mark))
        if m_peak(ep, peak_x) >= arm_usd(ep, mark) and m_fire(ep, mark) <= fee_term(ep, mark):
            return i, mark
        i += step
    return None, ep["candles"][-1][4]

def sim_A_intra(ep, mode):
    """Intrabar bound for the 60s counterfactual: peak from favorable extremes,
    fire at first candle crossing the floor while armed (arm eval at floor).
    mode: 'floor' (exit at level) | 'adv' (exit at adverse extreme)."""
    pf = floor_price(ep)
    peak_x = -1e18
    for i in range(ep["i0"], len(ep["candles"])):
        c = ep["candles"][i]
        peak_x = max(peak_x, X(ep, fav(ep, c)))
        if m_peak(ep, peak_x) >= arm_usd(ep, pf) and crossed(ep, c, pf) and i > ep["i0"]:
            return i, (pf if mode == "floor" else adv(ep, c))
    return None, ep["candles"][-1][4]

def sim_B(ep, mode, peak_src):
    """Resting stop at pf placed at first armed 1m evaluation; fills at level.
    mode: 'floor' | 'slip' (level worsened by the crossing candle's range,
    capped at its adverse extreme)."""
    pf = floor_price(ep)
    peak_x = -1e18
    placed = False
    for i in range(ep["i0"], len(ep["candles"])):
        c = ep["candles"][i]
        p_pk = c[4] if peak_src == "close" else fav(ep, c)
        peak_x = max(peak_x, X(ep, p_pk))
        mark = c[4] if peak_src == "close" else fav(ep, c)
        if not placed:
            if m_peak(ep, peak_x) >= arm_usd(ep, mark):
                placed = True
            continue
        if crossed(ep, c, pf):
            if mode == "floor":
                return i, pf
            rng = c[2] - c[3]
            p = pf + rng if ep["side"] < 0 else pf - rng
            p = min(p, c[2]) if ep["side"] < 0 else max(p, c[3])
            return i, p
    return None, ep["candles"][-1][4]

def tmin(ep, i):
    if i is None: return "none"
    return datetime.fromtimestamp(ep["candles"][i][0]/1000, tz=timezone.utc).strftime("%H:%M")

def main():
    out = {}
    print(f"{'run':>5} {'liveSIM range (5 phases)':>34} {'actual':>9} | {'A60':>9} {'A_best':>8} {'A_worst':>8} | {'B_best':>8} {'B_worst':>8} | validation")
    for ep in EP:
        load(ep)
        # simulated live: 300s grid, 5 phases
        live_sims = []
        for ph in range(5):
            i, p = sim_grid(ep, 5, ph)
            if i is not None:
                live_sims.append((ph, i, p, net(ep, p)))
        # counterfactual A (60s): close-sampled
        iA, pA = sim_grid(ep, 1, 0)
        A60 = net(ep, pA) if iA is not None else None
        iAf, pAf = sim_A_intra(ep, "floor")
        iAw, pAw = sim_A_intra(ep, "adv")
        A_best = net(ep, pAf) if iAf is not None else None
        A_worst = net(ep, pAw) if iAw is not None else None
        if A60 is not None and A_worst is not None:
            A_worst = min(A_worst, A60)
        if A60 is not None and A_best is not None:
            A_best = max(A_best, A60) if False else A_best  # floor exit is the best bound
        # counterfactual B
        Bs = []
        for src in ("close", "extreme"):
            for mode in ("floor", "slip"):
                i, p = sim_B(ep, mode, src)
                Bs.append((src, mode, i, p, net(ep, p) if i is not None else None))
        B_nets = [b[4] for b in Bs if b[4] is not None]
        B_best = max(B_nets) if B_nets else None
        B_worst = min(B_nets) if B_nets else None
        # validation vs actual
        act_fire_min = tmin(ep, ep["ifire"])
        sim_range = f"[{', '.join(f'{s[3]:.3f}@{tmin(ep,s[1])}' for s in live_sims)}]"
        # overshoot check: actual live overshoot (prod space) vs sim overshoots
        out[ep["run"]] = dict(
            E_arch=ep["E"], floor=floor_price(ep),
            live_sims=[(s[0], tmin(ep, s[1]), round(s[3], 4)) for s in live_sims],
            n_phases_fired=len(live_sims),
            actual_fire_min=act_fire_min, actual_live_net=ep["live_net"],
            A60=(tmin(ep, iA), round(A60, 4) if A60 is not None else None),
            A_best=(tmin(ep, iAf), round(A_best, 4) if A_best is not None else None),
            A_worst=(tmin(ep, iAw), round(A_worst, 4) if A_worst is not None else None),
            B=[(b[0], b[1], tmin(ep, b[2]), round(b[4], 4) if b[4] is not None else None) for b in Bs],
        )
        print(f"{ep['run']:>5} {sim_range:>34} {act_fire_min:>9} | "
              f"{A60 if A60 is not None else float('nan'):>9.4f} "
              f"{A_best if A_best is not None else float('nan'):>8.4f} "
              f"{A_worst if A_worst is not None else float('nan'):>8.4f} | "
              f"{B_best if B_best is not None else float('nan'):>8.4f} "
              f"{B_worst if B_worst is not None else float('nan'):>8.4f} | "
              f"actual_net={ep['live_net']:.4f}")
    json.dump(out, open("/private/tmp/claude-501/-Users-desirey-Programming-src-ai-trade/d45363c2-66ff-4058-ab2c-acf93b39cdcb/scratchpad/replay2_out.json", "w"), indent=1)

if __name__ == "__main__":
    main()
