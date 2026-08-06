# R6 breakeven-ratchet backtest — result: DO NOT SHIP

**Task:** owner asked to build the R6 breakeven ratchet off `main` and bring it back verified.
**Method:** counterfactual replay of **28 closed runs / 10,644 recorded `equity.total` points** (last 7d, no lookahead). For each arm threshold `T = f × max_loss`, simulate: once peak ≥ T, move the effective stop to a breakeven floor F; exit the first time total ≤ F after arming; compare counterfactual realized vs actual. Script: `scratchpad/r6_backtest.py`.

## Result

Baseline actual realized (28 runs): **−$57.60**

| arm = f×max_loss | fired | helped | clipped | net Δ vs actual |
|---|---|---|---|---|
| 0.05 | 7 | 3 | 4 | **−30.93** |
| 0.10 | 5 | 3 | 2 | **−11.45** |
| 0.15–0.25 | 4 | 3 | 1 | **+5.00** (best) |
| 0.30 | 3 | 2 | 1 | −8.60 |
| 0.40–0.50 | 1 | 1 | 0 | +3.39 |

Floor F ∈ {0, +0.25, +0.5, +1.0}: no change (+5.00).

## Why it fails

At the best threshold the +$5.00 is **+$26 saved on 3 give-back runs minus one clipped real winner**:
- HELP 120 (−14.10→−0.50), 811 (−10.42→−1.43), 816 (−6.54→−3.14)
- **CLIP 125: +20.80 → −0.18** — run 125 peaked +28.76, dipped, then ran to a real +20.80 close; the ratchet scratches it on the dip.

A breakeven stop cannot tell a give-back-that-keeps-falling from a winner-that-dips-then-runs without lookahead, so it destroys real winners to save round-trips. This reproduces the codebase's prior rejection (`run_engine.py:1776`, `fleet_planner.FLEET_BOUNDS` note; memory `trailing-lock-never-arms`). Best case is +$5 over a week — noise, and negative outside a narrow band.

## The real lever (redirect → R7)

The P&L damage is **directional losers that never go positive**, which no exit-lock can touch:

| run | realized | peak | |
|---|---|---|---|
| 112 | −70.13 | +0.23 | never positive (also **overshot** the −66.6 stop by ~$3.5) |
| 104 | −38.62 | −0.46 | never positive |
| 113 | −20.87 | −1.70 | never positive |

**Conclusion:** R6 dropped on evidence. Effort should go to entry/position-selection quality (do never-positive entries share a signature in the `decision` events?) and the fee hurdle — tracked as **R7**.
