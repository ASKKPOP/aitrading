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

---

# CORRECTION, same day 12:20Z — six claims above are WRONG

An adversarial pass plus my own re-measurement refuted six claims in this
document. They are corrected here rather than deleted, because the pattern
matters more than any one of them.

**1. "The arm sits below one tick of noise" is BACKWARDS by ~4x.** The
$0.1554 "per-sample move" was the last sample *before a ratchet fire* —
conditioned on the trigger, which fires because price moved. The
UNCONDITIONAL per-sample move while holding is **$0.0369** (my own recount,
n=20,629; the adversary got $0.0354, n=32,225). The arm ($0.1503) sits at the
**89th percentile** of per-sample moves and is **4.07x** the median one.
Controls confirm the conditioning: last sample before a DESK close (not
price-triggered) is $0.0441, and within the same ratchet trips the non-final
samples median $0.0602 — the final sample is 2.55x that trip's own typical
move. The sampling instrument itself is sound: median interval 63s, 87% in
[55,70]s, max 188s.

**2. "Gives back 90% of its best moment" DOUBLE-COUNTS THE FEE.** It divided
a NET final by a GROSS peak. Like-for-like the giveback is **61.7%** (gross
final +0.116% vs peak +0.304%); the 29.7-point difference IS the 0.090% fee,
which the next clause then charged again as a separate burden. (The
ratio-of-medians objection does NOT apply — median-of-ratios 74.3% vs
ratio-of-medians 76.5% agree.)

**3. The reversion cliff is SIMPSON'S PARADOX.** Conditioned on exit author,
no population has a break between -1.0% and -1.5%:

    ratchet  -0.25:85% -0.5:86% -1.0:82% -1.5:70% -2.0:67%   gentle
    desk     -0.25:33% -0.5:37% -1.0:35% -1.5:49% -2.0:56%   RISING
    armed    -0.25:18% -0.5:19% -1.0:24% -1.5:16% -2.0:17%   flat

The aggregate cliff comes from the ratchet's share of each depth bin falling
55% -> 22%. Depth is a proxy for "the rails did not fire", not a market
property: of 36 trips held <= 30 minutes, ZERO ever reached -1.5%. The metric
is also non-monotone — extend one row and -3.00% reads 90.7% "recovered" on
trips whose median final is -2.24%.

**4. "~22 minute hold" is wrong and hides a bimodal population.** Median
28.5m, mean 95.9m, p90 242m; by author ratchet 14.6m, desk 112.4m, armed
126.7m. 26% of the book is held over two hours.

**5. "Only 3.3x the fee" is too GENEROUS.** A peak is not capturable. Mean
gross return per trip is **-0.067%** — negative. Median gross +0.116% =
1.29x the fee.

**6. "No exit-rail tuning fixes that" is OVER-REACH on this evidence.** Days
are the correct independence block. Day-block bootstrap on the window net:
**95% CI [-$60.08, +$5.86], P(net>0) = 7.6%** — the window's own sign is NOT
established at 95%. 09-07 is 89% of the loss; without it the other three days
are -$2.58. A mechanism-level negative cannot be asserted over that.

## The pattern behind all of them

**A quantity measured under a selection, then read as if it were
unconditional.** Five instances in two days, all mine:

- the retracted 755s detection lag — a run-level FINAL peak applied to
  sample-level moments before that peak existed;
- the retracted "desk widens its stop" — an AUTHORED value read as an
  INSTALLED one;
- the noise floor — a RAIL-TRIGGERED sample read as ambient noise;
- the reversion cliff — a MIXED-POPULATION aggregate read as a market
  property;
- the giveback — a NET quantity divided by a GROSS one.

The rule this document stated ("when replaying a peak-relative rail, use a
RUNNING peak") was too narrow. **The general rule: before any number becomes
a premise, state what had to be true for that sample to exist.**

Second bias, also mine: framing each experiment as "does mechanism X help?"
and filing "no" as REFUTED without reading the same grid backwards. H-STOP's
grid contains a surviving POSITIVE (widening/removing the stop is worth
+$5.79 on this tape) recorded under a heading that says REFUTED.

## What SURVIVED both the adversarial pass and re-measurement

- **H-STOP is still refuted**, and by a stronger test than mine: a stop
  applied ONLY to positions that never armed the ratchet — which dodges the
  "it stops the winners too" objection — loses at every distance
  (-$33.50 / -$32.49 / -$37.24 / -$33.23 / -$33.98 at 0.25/0.50/1.00/1.50/2.00%
  against -$22.42 actual). Right answer; my explanation for it was wrong.
- **No demonstrated entry edge**, now from three independent directions:
  rule-6 (+$3.21 flips on dropping the best two); gross day-block bootstrap
  P(gross>0) = **57.5%**, a coin flip; and the horizon experiment below.
- **09-07 was not a regression** — no code, config or restart change.
- The sampling instrument is regular (S1 above).

## H-HORIZON — REFUTED, and it is the load-bearing result

306 entries, 31 symbols, priced against Hyperliquid 1m candles (which proved
to be the platform's own feed: fill vs candle close agrees to a median
0.023%). Permutation null = same symbol, same side, RANDOM entry minute,
5000 shuffles.

    T      desk mean%   random same-mix%   desk - random    perm p
    5m       -0.032        +0.007            -0.039         0.974
    30m      -0.031        +0.044            -0.075         0.929
    2h       -0.004        +0.189            -0.193         0.975
    8h       +1.043        +0.784            +0.260         0.112
    24h      +1.874        +2.314            -0.439         0.913

**At every horizon the desk actually trades, its timing is WORSE than a
random entry minute in the same coins** (z = -1.98 at 5m, -1.90 at 2h).

The 8h figure is the only arguable one and does not survive: the window was a
rally (31 symbols +7.09% mean) and the desk is 83% long. Drift-adjusted
excess +0.291%, but dropping ARB alone takes it to **-0.0996%** — ARB is 133%
of the total excess, and 4 of its 9 trades fired inside a 3.3h band before a
+33% run, i.e. ONE event counted four times. Symbol-clustered 95% CI
[-0.592%, +1.175%] contains both the fee and zero. The shorts LOST while the
market rose (8h short -0.301%) — passive exposure, not a view.

## Where the money went (unambiguous), and what that does NOT prove

    run shape        runs   closes P&L   armed exits   armed P&L
    2 legs            202     +$28.28         0          $0.00
    3 legs             16      +$5.71         4         +$1.76
    4+ legs            48     -$44.17        20        -$23.32

**Single round trips have ZERO armed exits.** Every losing armed exit lives
in a run the desk kept working across multiple cycles. The adversary's
finding ("24 legs carry 99% of the net loss, clustered at a settable ~-2.6%")
and the leg-count split are the SAME population from two angles.

**This is conditioned and must not be read as causal.** A run becomes
multi-leg BECAUSE it went against the desk. Neither I nor the adversary can
run the counterfactual from this data — the price path ends at the close.
What CAN be said without that counterfactual, because it rests on the
permutation test rather than on the conditioned sample: **if entries carry no
directional information, then adding to a losing position has zero expected
edge and a certain additional fee.**

## Standing conclusion

Tuning an exit rail on this book is optimising the exit of a coin flip. Four
exit-side hypotheses (F-ARM, H-STOP, H-LEAK, and the armed-exit distance)
have produced no supported improvement, and H-VETO cannot even be tested
because the panel dissents on ALL 202 clean entries and is overridden every
time — a risk check that objects to everything carries no information.

The open question is entry SELECTION, and nothing in four days answers it.

---

# H-CONVICTION — INCONCLUSIVE (12:20Z). Do not re-run at this n.

Pre-registered: "`stop_event:conviction_collapse` destroys value by flattening
into reversion." It fires at roughly -0.65% of notional, inside the band where
positions were thought to revert.

All 7 fires in the window, priced against cached Hyperliquid 1m candles.
Signed in the position's OWN direction, so positive means holding would have
been better, i.e. the flatten destroyed value:

    run   symbol     dir     pnl      +30m     +1h      +2h      +4h
    2755  HYPEUSDT   short  -0.5047  -0.006  +0.083   -0.463   -0.475
    2846  HYPEUSDT   short  -0.1324  +0.272  +0.360   +0.102   +0.146
    2842  ARUSDT     long   -0.0139  +2.924  +2.699   +2.105   +1.138
    2895  ZENUSDT    long   -0.1753  -1.178  -0.218   +2.012   +4.942
    2939  INJUSDT    long   -1.4156  +1.213  +1.089   +1.269   +1.689
    2986  UNIUSDT    long   -0.0363  -0.014  -0.337   -1.306   -3.706
    3060  ICPUSDT    long   -1.8454     n/a     n/a      n/a      n/a

    horizon   n   mean     positive   mean ex-largest
    +30m      6  +0.535%     3/6         +0.057%
    +1h       6  +0.613%     4/6         +0.195%
    +2h       6  +0.620%     4/6         +0.323%
    +4h       6  +0.622%     4/6         -0.242%   <- SIGN FLIPS

**INCONCLUSIVE by rule 6.** The 4h mean flips sign on dropping one trade, the
hit rate is a coin flip, and n=6 (ICP had no forward data at measurement).
The direction weakly favours the hypothesis — ZEN reverted +4.94% at 4h, AR
+2.92% at 30m — but UNI ran -3.71% the other way, where the flatten genuinely
saved money. Not acted on. Do not re-run until n is materially larger.

Bookkeeping: conviction_collapse is 0-for-7 on realised P&L (-$4.12), but a
0% hit rate on a rail that fires ONLY on deteriorating theses is expected and
is NOT by itself evidence of a defect. That is the selection trap named above.

# Tape through 2026-09-08 13:25Z

    day     legs  closes    net        note
    09-05    116     56    -1.4856
    09-06    198    107    +7.0578     the only positive day
    09-07    236    128   -20.2121     left-tail day, no code/config change
    09-08    115     63   -10.2837     partial, 13h

    window net -24.92 over 665 legs

09-08 repeats 09-07's shape: concentrated, not diffuse. Hour 11 alone is
-$6.71 of the day's -$10.28, and both of that hour's losing closes are ONE
multi-leg run (UNI 3059 exited twice: cyc:7 -1.845 then flatten -1.278).
Consistent with the leg-count attribution already recorded; not a new finding.

# Standing methodological note for the next session

Five hypotheses tested this week: F-ARM, H-STOP, H-LEAK, H-HORIZON refuted;
H-CONVICTION inconclusive; H-VETO untestable (the panel dissents on ALL 202
clean entries and is overridden every time). Six further claims were retracted
in one cycle, all from one error class.

**The binding constraint is now sample size, not ideas.** A window whose own
net is not distinguishable from zero at 95% by day-blocks cannot support
another mechanism-level claim, and running three verification agents against
the same four days every hour is precisely how the six retracted artifacts
were generated. Continue hourly READINGS; hold further hypothesis testing
until the tape can answer something.
