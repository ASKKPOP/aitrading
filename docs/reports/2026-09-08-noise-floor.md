# 2026-09-08 — three mechanisms proposed, three refuted, and what survived

Monitoring resumed 2026-09-08 09:11Z after a three-day gap (last record
2026-09-05). Prod unchanged throughout: `sooppiy-backend:20260905-farm-refuted-revert`,
`RestartCount 0`, no code or config change since 09-05 13:26Z.

## The money

Window 09-05 00:00Z → 09-08 10:40Z, agent 6, by the platform's own net
formula (`COALESCE(pnl, -COALESCE(fee_usd,0))`, `routes_trading.py:995`):

    net -16.20 over 642 legs      09-05  -1.49
    gross before fees   +3.21     09-06  +7.06
    fees               -24.25     09-07 -20.21
    fee rate 4.50 bps/leg, flat, verified min=max on every leg

Throughput is restored: 620+ legs in four days against ZERO for the 19 days
08-17 → 09-04. Per-leg loss improved ~8x versus the pre-hold-wall regime
(08-13: 215 legs, -$144.40 = -$0.672/leg; 09-07: 236 legs, -$20.21 =
-$0.086/leg). Still a loss; not a regression.

**The gross-positive result does not survive.** +$3.21 across 326 trips
flips sign on dropping the best TWO trades (-$1.03). There is no
demonstrated entry edge on this window.

## Three hypotheses, all refuted by measurement

### 1. "Enforcing the price stop would help" — REFUTED

The mechanism is real: a stop hit is routed to the desk (`risk_engine.py:760`),
`run_cycle` then calls `stop_router.clear()`, which sets
`_SUPPRESS_UNTIL = now + renote_min()*60` = 1800s (`stop_router.py:119`).
Measured over the container's 168h life: **1258 hits routed, 0 fail-safe
fires, 1 watcher close (a take-profit)**. The price stop effectively does
not execute.

Replay of 218 clean single-entry trips, stop applied to EVERY position
including winners (the sample discipline the F-ARM revert taught):

    as authored, fill at sampled mark   -5.79
    as authored, fill AT the stop       -3.68   (generous)
    uniform 0.25% / 0.75% / 1.00%       -4.34 / -9.90 / -6.01
    uniform 1.50% / 2.00% / 4.00%       -1.94 / -0.76 / -0.07
    uniform 5.00% (never fires)          0.00   <- best

**No stop distance tested improves the window.** The unenforced stop is
worth +$5.79 on this tape. It is accidentally the best available policy.

### 2. "The desk widens its stop on losers" — REFUTED, and it was my own relay

Reported in the 09:15Z reading from the data agent. `positions.stop_loss` is
write-once at open; run 2989 re-authored 1.5 -> 2.0 -> 0.75 -> 1.7 -> 5.0%
while the position kept its 56.894 stop throughout. Proposed stops were read
as installed ones. Verified directly: run 2989 has exactly two
`bracket_reanchor` events, both at fills.

### 3. "The ratchet leaks $22-23 below its own floor" — REFUTED as a defect

The shortfall is real and correctly sized (2-leg runs only, where baseline is
provably 0): **$22.44 across 180 fires, mean $0.125, 41 of 180 landing <= $0
despite a strictly positive floor; realized $14.22 against an intended
$36.65 = 38.8% of intent.**

But it is not recoverable engineering. Two tests:

- **Detection lag: none.** With a RUNNING peak and the armed condition
  enforced, median delay from first genuine breach to fire is **0.0s**; 78%
  fire within 60s, 94% within 300s. (My first pass measured 755s median —
  wrong, because it applied the run's FINAL peak retroactively to samples
  taken before that peak existed. Retracted within the same cycle.)
- **The overshoot is smaller than one tick.** Median leak $0.0976 against a
  median last-sample price move of $0.1554 before the fire — **0.63x**, and
  82% of leaks are smaller than the last observed sample move.

A poll-based threshold cannot do better than this without a resting order.

## What survived: the book trades inside its own noise

    per-sample price move (median, pre-fire)   $0.1554
    ratchet arm (median)                       $0.1503   <- smaller than one tick
    peak reached (median)                      $0.2451   = 1.60x the arm
    result banked (median)                     $0.0729
    round-trip fee                             $0.0778

The arm sits BELOW one sample of price movement. 63 of 180 fires had a peak
under 1.25x the arm.

Excursion shape over 223 trips, as % of notional:

    median peak    +0.300      median trough  -0.138
    median final   +0.029      mean final     -0.045
    round trip fee  0.090

**The median trip gives back 90% of its best moment, and the fee is 30% of
that best moment.**

Reversion, measured, with a cliff:

    reached -0.25% -> 73.0% ended above it     reached +0.25% -> 76.1% gave it back
    reached -0.50% -> 73.3%                    reached +0.50% -> 65.4%
    reached -1.00% -> 62.2%
    reached -1.50% -> 43.5%   median final -2.296%
    reached -2.00% -> 25.0%   median final -2.611%

Reversion holds to about -1.0% and breaks between -1.0% and -1.5%. This is
why tight stops are destroyed by reversion and wide stops fire too late, and
why the ratchet — which monetises the UPSIDE reversion — is the only
profitable component (240 closes, 76.3% WR, +$33.66 exit-fee-net).

**The unified statement: at a ~22 minute median hold the signal the desk is
trying to capture (~0.30% peak) is the same size as the sampling noise
(~0.17%) and only 3.3x the round-trip fee (0.090%). No exit-rail tuning
fixes that.** F-ARM (raise the arm), H-STOP (enforce the stop) and H-LEAK
(recover the floor shortfall) all failed for the same underlying reason.

## Exit attribution (verified twice, independently)

    author                    n    WR      avg loss   net (exit-fee-net)
    algorithm trailing lock  240  76.3%    -$0.19     +$33.66
    desk cycle close          64  40.6%    -$0.87     -$21.29
    desk armed exit           22  22.7%    -$1.50     -$21.12

This is a SELECTION effect, not a causal exoneration: the ratchet only fires
on positions that first reached +0.167% of notional. It is not evidence for
handing the desk's exits to the algorithm.

## Defects confirmed live, NOT shipped

- **Armed exit has no plausibility bound.** Run 2880 armed
  `price_below 6938.0` on a $6.93 coin (1000x scale slip); the executor
  computed -99.9% slippage, journalled it, and fired anyway
  (`run_engine.py:2045` — "Slippage is REPORTED, never a veto"). -$2.45.
- **Re-entry cooldown is exactly zero.** `interval x (leverage - 1.0)`
  (`run_engine.py:262`) with every fleet position at leverage 1.0. This is
  D-REENTRY-1X, pre-registered 08-30, now confirmed on live tape.
- **`RR_FLOOR=0.2` in prod** against a module default of 2.0: a 2.5% stop
  requires only a 0.5% target. The rail that exists to forbid adverse
  geometry is configured to permit 5:1 against.
- **Rail asymmetry 125:1.** Winner cap 0.167% of notional (ratchet arm);
  loss cap `max_loss_usd` = 20.8% of notional, because it is 5% of max_bet
  ($375) while positions are ~$90. `max_loss` fired 0 times in the window.

## Open

09-07 was NOT a regression — no code change, no config change, no restart;
the same process ran both days. It was a left-tail day (22 losses worse than
-2% vs 6 the day before) that a book with no working loss truncation converts
straight into P&L.

The next testable question is a HORIZON question, not an exit-rail question:
does the signal exceed noise+fee at any hold length this desk can reach?
Nothing in this window answers it.

## Method notes for the next session

- `signals.pnl` nets the EXIT fee only. Net = SUM(pnl) - SUM(entry fee_usd).
  Confirmed three ways incl. 253/253 run replay with zero residual.
- Two closes in this window carry `run_id IS NULL` with no entry leg
  anywhere in the tape (+$4.38 TAO, -$1.54 FIL). They inflate any
  signals-based gross by +$2.84 and are absent from `trading_runs`. That is
  the whole gap between the -$18.11 window-cash figure and the -$20.96
  run-ledger figure.
- `run_events.equity` carries `unrealized`, which makes a P&L-space replay
  possible without any price history.
- When replaying a peak-relative rail, use a RUNNING peak. Using the final
  peak retroactively produces a fake multi-minute detection lag.
