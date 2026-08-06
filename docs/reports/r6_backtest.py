#!/usr/bin/env python3
"""R6 breakeven-ratchet counterfactual backtest.

Replays recorded per-run `equity.total` trajectories (no lookahead) and asks:
if a breakeven ratchet armed once peak >= T and then exited the first time
total <= F (breakeven floor), what would realized P&L have been vs actual?

Honest accounting:
- Only runs that actually opened a position + have a peak are in the set.
- If the ratchet never arms (peak < T) or never crosses F after arming, the
  run keeps its ACTUAL realized outcome (the ratchet changed nothing).
- If it fires at seq s, counterfactual = total[s] - close_fee_est (one extra
  taker fee to flatten). We DON'T get the entry fee back; total already nets it.
- 'clipped' = ratchet fired but actual realized was HIGHER (we exited a winner
  early). This is the exact failure mode the team cited when rejecting it.
"""
import sys, collections

SP = "/private/tmp/claude-501/-Users-desirey-Programming-src-ai-trade/540a75dc-2f03-434b-af06-8aac3915a082/scratchpad"

runs = {}
for line in open(f"{SP}/r6_runs.tsv"):
    p = line.rstrip("\n").split("\t")
    if len(p) < 4: continue
    rid = int(p[0])
    def f(x):
        try: return float(x)
        except: return None
    runs[rid] = {"realized": f(p[1]), "peak": f(p[2]), "max_loss": f(p[3]),
                 "target": f(p[4]) if len(p) > 4 else None}

traj = collections.defaultdict(list)
for line in open(f"{SP}/r6_equity.tsv"):
    p = line.rstrip("\n").split("\t")
    if len(p) < 3: continue
    rid = int(p[0])
    try: total = float(p[2])
    except: continue
    traj[rid].append((int(p[1]), total))
for rid in traj: traj[rid].sort()

CLOSE_FEE = 0.10  # conservative per-exit taker fee to flatten at BE

def simulate(frac, floor=0.0):
    """frac: arm threshold as fraction of max_loss. Returns aggregate stats."""
    actual_sum = cf_sum = 0.0
    fired = clipped = helped = 0
    clip_cost = help_gain = 0.0
    for rid, r in runs.items():
        actual = r["realized"] or 0.0
        actual_sum += actual
        ml = r["max_loss"] or 0.0
        T = frac * ml
        pts = traj.get(rid, [])
        peak = -1e9; armed = False; cf = None
        for _, tot in pts:
            if tot > peak: peak = tot
            if not armed and peak >= T and T > 0:
                armed = True
            if armed and tot <= floor:
                cf = tot - CLOSE_FEE
                break
        if cf is None:
            cf_sum += actual  # ratchet changed nothing
        else:
            cf_sum += cf
            fired += 1
            if cf > actual + 1e-9:
                helped += 1; help_gain += (cf - actual)
            elif cf < actual - 1e-9:
                clipped += 1; clip_cost += (actual - cf)
    return dict(frac=frac, actual=actual_sum, cf=cf_sum, delta=cf_sum-actual_sum,
                fired=fired, helped=helped, clipped=clipped,
                help_gain=help_gain, clip_cost=clip_cost)

print(f"Population: {len(runs)} closed runs w/ position, "
      f"{sum(len(v) for v in traj.values())} equity points\n")
print(f"Actual total realized (baseline): {sum((r['realized'] or 0) for r in runs.values()):+.2f}\n")
print(f"{'arm=f*maxloss':>14} {'fired':>6} {'helped':>7} {'clipped':>8} "
      f"{'help$':>8} {'clip$':>8} {'NET Δ vs actual':>16}")
for frac in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
    s = simulate(frac)
    print(f"{frac:>14.2f} {s['fired']:>6} {s['helped']:>7} {s['clipped']:>8} "
          f"{s['help_gain']:>8.2f} {s['clip_cost']:>8.2f} {s['delta']:>+16.2f}")

print("\n=== what dominates the -57.60 baseline? (worst 5 runs) ===")
worst = sorted(runs.items(), key=lambda kv: (kv[1]['realized'] or 0))[:5]
for rid, r in worst:
    print(f"  run {rid}: realized {r['realized']:+.2f}  peak {r['peak']:+.2f}  "
          f"max_loss {r['max_loss']:.1f}  ({'never positive' if (r['peak'] or 0)<=0.5 else 'gave back peak'})")

print("\n=== per-run effect at best frac=0.20, floor=0 ===")
for rid, r in sorted(runs.items()):
    ml=r['max_loss'] or 0; T=0.20*ml; pts=traj.get(rid,[]); peak=-1e9; armed=False; cf=None
    for _,tot in pts:
        if tot>peak: peak=tot
        if not armed and peak>=T and T>0: armed=True
        if armed and tot<=0.0: cf=tot-0.10; break
    if cf is not None and abs(cf-(r['realized'] or 0))>0.5:
        tag = 'HELP' if cf>(r['realized'] or 0) else 'CLIP'
        print(f"  {tag} run {rid}: actual {r['realized']:+.2f} -> ratchet {cf:+.2f}  (peak {r['peak']:+.2f}, armT {T:.1f})")

print("\n=== floor sensitivity at frac=0.20 (lock small profit instead of pure BE) ===")
for floor in [0.0, 0.25, 0.5, 1.0]:
    s=simulate(0.20, floor=floor); print(f"  floor=+{floor:.2f}: net delta {s['delta']:+.2f} (fired {s['fired']}, clipped {s['clipped']})")
