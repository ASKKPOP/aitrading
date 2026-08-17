# Automation monitoring — 2026-08-17 (UTC day), newest-first

Continued from [2026-08-16](2026-08-16-automation-monitoring.md) (day
closed **+$5.65 realized, resid 0.00**; 15 code/skill PRs + 4 docs
merges shipped). Target: **info@askkpop.com — user 5 / agent 6 /
FLEET 35**. Open items: `BREAKEVEN_FEE_RATE` (needs fleet-wide replay),
prospective #443 warning, outlook intent-vs-execution defect,
arm-reachability rail.

## Cycle 19 — 11:4xZ (anchor 11:49:31): **H4 refuted — the fee-hurdle ratio predicts nothing, which kills a remedy before it was built**

**PROFIT-OR-LOSS FIRST.** No closes. Book flat. Day 08-17 **+$4.26**. 12
decisions, **0 no-verdicts** — fourth consecutive clean window.

### H4 — "the fee-hurdle ratio at entry predicts which legs land in the fee-scale scratch band" → **REFUTED**

*Falsifier: scratch and non-scratch legs show the same ratio distribution.*
Ratio = the desk's own `target_pct` ÷ the round-trip fee as a % of notional.
36 closed legs since the reset carried a desk target:

| | n | median ratio | mean ratio | total net |
|---|---|---|---|---|
| **SCRATCH** (\|net\| < own round-trip fee) | 14 | **34.81** | 37.99 | −$0.0828 |
| **NON-SCRATCH** | 22 | **36.63** | 43.79 | +$8.2962 |

**The medians are 34.8 versus 36.6 — indistinguishable.** By band, the
scratch rate runs 50% / 57% / 29% / 36% across increasing ratios: no
monotone relationship, and the 0–10 band is not worse than the 50+ band.

**The falsifier is met. The ratio carries no information about the outcome.**

### Why this result matters more than a confirmation would have

Cycle 18 ended by proposing exactly this test before suppressing churn, and
said plainly: *"If it does not predict, suppressing small trades would cut
winners too and must not be attempted."* **It does not predict.** So:

* **A `min_edge`-style gate raised to suppress the scratch band is not
  supported.** It would cut across both groups — the non-scratch legs hold
  **+$8.30** of the account's **+$9.65** and sit at the *same* ratios as the
  scratches.
* This is a remedy that would have looked obviously correct in a plan
  document and would have removed profit. It is now struck before anyone
  built it.

### The finding hiding inside the negative result

**Every leg's target is enormous relative to its fee hurdle — median ~35×.**
The desk always claims a target far above the cost of trading, and 36% of
legs still finish inside the fee band. Combined with cycle 16 (SUI 1356 moved
its target 2.5× solely to clear the 2:1 R:R floor, `basis.discussion: null`),
the reading is that **`target_pct` is not a forecast — it is a number that
satisfies a gate.** A field with no predictive content cannot be used to size
or select, and should not be trusted by anything downstream that treats it as
an expectation.

That is a hypothesis in its own right, not a conclusion: it predicts that
`target_pct` has no correlation with realized move in ANY band, not merely
with scratch membership. Worth testing next.

### Honest limits

n=36. I used the last `parsed` `order_params` target before each close, which
is not guaranteed to be the entry cycle's target on every leg. Non-crypto fee
rates were assumed per market rather than read from each fill. Neither
weakness plausibly manufactures a null result — both would add noise, and
noise cannot create the near-identical medians observed — but the numbers
should be re-derived from per-fill fees before anything is built on them.

### Recommendations

1. **Do not raise the min-edge / fee-feasibility gate to suppress churn.**
   Struck by this experiment.
2. **Next experiment: does `target_pct` correlate with realized move at
   all?** If it does not, every downstream consumer that treats it as an
   expectation — R:R gating, sizing, the outlook's `exit.target_px` — is
   built on a number that means nothing.
3. Unchanged and still gated: ratchet baseline + round-trip package, fleet
   slot-ledger over-commitment, panel-fallback governance item.

## Cycle 18 — 11:1xZ (anchor 11:19:32): **H3 — the account's profit is two trades, and only one of them is a defect**

**PROFIT-OR-LOSS FIRST.** No closes. Book flat. Day 08-17 **+$4.26**. 11
decisions, **0 no-verdicts** — third consecutive clean window, consistent
with cycle 17's finding that the 06h–08h spike was episodic.

### H3 — "realized P&L is dominated by a few outliers; the median trade is a fee-scale scratch" → **CONFIRMED**

*Falsifier: removing the top contributor leaves the total materially
unchanged.* Every closed leg for agent 6 since the 08-15 09:00Z reset:

| | |
|---|---|
| closed legs | **39** |
| **TOTAL net** | **+$9.6509** |
| median net | **+$0.0093** — under one cent |
| mean net | +$0.2475 |
| wins | 23 (59%) |
| **TOTAL ex-top-1** | **+$4.4791** |
| **TOTAL ex-top-3** | **+$0.4630** |
| legs whose \|net\| is smaller than their OWN round-trip fee | **14 / 39 (36%)** |

**Three trades are 95% of everything. The other 36 legs made $0.46
between them** — across 36 round trips. The median leg nets under a cent
against round-trip fees of $0.04–$0.43, so **the median trade does not cover
a tenth of its own fee.**

### The provenance test — and it refutes the darker reading I was heading toward

I expected both top contributors to trace to the `order_params: absent`
sizing defect, which would have meant the account's profit was essentially a
bug. **It does not.**

| rank | leg | net | `order_params` on the entry cycle | authored |
|---|---|---|---|---|
| 1 | run 1322 FIL, 02:24:43Z | **+$5.17** | **`absent`** (cyc 39) | default sizing — **the defect** |
| 2 | run 1305 FIL, 00:17:32Z | **+$3.04** | **`parsed`, size_frac 0.2** (cyc 5) | **desk-authored, desk-sized, desk-closed** (`run:1305:cyc:9`) |

**#2 is a clean trade.** Short 304 FIL @ 0.687 → cover @ 0.6764 on ~$209
notional, **+1.46% on notional**, with the desk choosing 0.2 size_frac and
closing it on its own cycle. That is what a working desk trade looks like,
and it is the counter-example to the "the desk only wins by accident"
reading I have been circling for several cycles.

So the corrected picture: **profit is real but concentrated on two pillars,
one of which is a defect and one of which is legitimate.** Strip the defect
and the account is **+$4.48 over 38 legs** — still positive, still carried by
a single genuine win.

### WHY this matters more than the winners

The problem this exposes is not the tail, it is the body. **36 of 39 legs
together produce $0.46**, and **36% of all legs are fee-scale scratches**
whose entire outcome is smaller than the fees they paid. A positive-skew
distribution is a legitimate profile — but a body of 36 trades that nets
nothing while paying ~36 round trips is pure churn, and it is where the
fee-hurdle findings from cycles 13 and 16 land.

### Recommendation

**Test whether the churn is predictable before trying to suppress it.** The
next experiment: does the fee-hurdle ratio at entry (expected move ÷
round-trip fee) predict which legs land in the fee-scale band? If it does,
the gate already exists conceptually — the `min_edge`/fee-infeasible check in
the fleet build path — and the question becomes why 36% of legs still clear
it. If it does not predict, suppressing small trades would cut winners too
and must not be attempted.

I am not proposing a change on this cycle's evidence. H3 tells us where the
money is, not what to do about it.

## Cycle 17 — 10:5xZ (anchor 10:50:29): **first cycle under the experimental rule — three hypotheses stated, three refuted, including my own cycle-12 conclusion**

**PROFIT-OR-LOSS FIRST.** No closes since 10:15:05Z. Book flat. Day 08-17
**+$4.26**. 11 decisions, **0 no-verdicts**.

Per the owner rule added this session, hypotheses were written before the
data and each carries its falsifier.

### H1 — "the no-verdict rate fell because I stopped probing the host" → **REFUTED**

*Falsifier: the rate stays low across a window with no probes and unchanged
call volume.* Measured the hourly rate for the whole day:

| hour | no_verdict / decisions | rate |
|---|---|---|
| 00h–05h | 0/21, 1/21, 2/24, 0/21, 0/20, 1/20 | **~3% baseline** |
| **06h** | **5/25** | **20.0%** |
| **07h** | **4/23** | **17.4%** |
| **08h** | **3/23** | **13.0%** |
| 09h | 0/19 | **0%** |
| 10h | 0/18 | **0%** |

**My first probe ran at ~07:0x. The 06h hour — the worst of the day at 20% —
predates every probe I made.** My probing cannot explain the spike. It may
have prolonged 07h/08h; it did not start it.

### The bigger refutation: my own cycle-12 root cause does not survive re-measurement

Cycle 12 concluded the local model host was **~5× oversubscribed**, from
`178 calls/h × ~100s per call = 17,800 GPU-seconds demanded vs 3,600
available`. **The ~100s input was sampled during the 06h–08h anomaly.**

Re-measured now, call volume unchanged:

```
cycle-12 claim: 178 calls/h x ~100s = 17,800s vs 3,600  =>  4.9x oversubscribed
re-measured   : 189 calls/h x  ~5.5s =  1,040s vs 3,600  =>  0.29x
```

Two decision-tier calls just now: **7.0s and 3.9s.** Call volume is if
anything *higher* (189/h vs 178/h) and the host is **not oversubscribed at
all**.

**So the structural explanation is wrong.** What actually happened was a
**transient latency episode spanning 06h–08h** — during which the
timeouts-matched-to-the-second finding still holds — against a ~3% baseline
before it and 0% after. Cause of the episode: still unknown, and I am not
going to invent one. It is now bounded as *episodic, not structural*, which
is a different problem from the one I reported.

**What survives from cycles 10–12:** #468 did not reduce the rate (measured,
still true); the four earlier hypotheses stay refuted; the timeouts during
the episode were real. **What does not survive:** the oversubscription
arithmetic and the "reduce call volume or add capacity" recommendation built
on it. #468 remains cheap and plausibly protective against a repeat episode,
but it is **not established as effective** and should not be described as
such.

### H2 — "panel-fallback exits realize worse than panel-authored exits" → **REFUTED**

Cycle 16 found 10 closes/reduces authored by a path labelled *"panel
fallback (not the AI)"* and I implied that was costing money. Tested across
every closed leg on the platform:

| | n | total | mean | win rate |
|---|---|---|---|---|
| fallback-authored closes | 16 | **−$4.206** | **−$0.263** | 31% |
| all other closes | 225 | −$180.417 | **−$0.802** | 42% |

**Fallback closes realize BETTER on the mean, not worse.** The hypothesis is
refuted on P&L. Caveats I will not hide: n=16 against 225, the win rate is
lower, and book size is an obvious confound I have not controlled for — so
this is "no evidence of harm", not "the fallback is good".

**The governance point stands on its own terms** — an unreviewed path
labelling itself "not the AI" closes positions, and §7b says the panel is
the final author. But it must be argued as governance, **not** as a P&L
defect, because the P&L evidence does not support that.

### What this cycle produced

Three refutations and no new claim. Under the old habit I would have carried
"the host is 5× oversubscribed" and "the fallback is losing money" forward
into the next session's recommendations; both are now struck by measurement.
**A cycle whose entire output is killed hypotheses is a good cycle** — the
alternative was two confident wrong answers propagating into the corpus.

### Recommendations

1. **Do not act on the oversubscription finding.** Struck. If the episode
   repeats, `no_response` (#466) counts it and the hourly-rate query above
   is the instrument.
2. **Re-state the fallback item as governance**, with the P&L refutation
   attached, so nobody re-derives a money argument for it.
3. Unchanged and still gated: the ratchet baseline + round-trip package
   (arithmetic, not statistics), and the fleet slot-ledger over-commitment.

## Cycle 16 — 10:1xZ (anchor 10:19:26): **an unreviewed fallback closed the book, and the arm replay's answer is one outlier**

**PROFIT-OR-LOSS FIRST.** SUI run 1356 closed 10:15:05Z: `signals.pnl`
+$0.04999261, open fee $0.02943504 → **true net +$0.02055757** (matches
`realized_pnl_usd` to 8dp). Day 08-17 **+$4.26**, resid 0.05, 3 flattens.
Book flat.

On $65.41 notional the gross move was $0.0794 and the round trip took
**$0.0588 — 74.1% of gross.** It cleared the fee hurdle by **0.031
percentage points**. A 0.03% adverse tick at the close instant makes it a
loss. That is a fee-hurdle graze, not an edge.

### FAILED — the close was authored by a rule fallback, not the desk

Both agents converged independently: **no rail fired** (`client_order_id
run:1356:cyc:9`, zero `stop_mechanism` on the run, and only two on the whole
platform today — 1335 and 1358). But the closing cycle's discussion event
reads:

```json
{"proposed": {"action": "buy", "confidence": 0.55},
 "error": "panel fallback (not the AI): decision json unparseable"}
```

`_order_discussion` **fails open**. The 4-analyst panel — the mandated final
author of every order under §7b — crashed on unparseable JSON, and the cheap
tier's unreviewed proposal closed the book. The OPEN (cycle 7) *was*
panel-authored, raised 0.55 → 0.68. **The exit that ended the trade bypassed
the final author.**

I measured how often this happens: **29 panel fallbacks all time, 10 of them
on a `close` or `reduce` intent.** Ten positions have been exited or trimmed
by a path that explicitly labels itself "not the AI".

### WHY the trade produced almost nothing

Agent A's finding, checked against the tape: **the target existed to pass a
gate, not as a forecast.** Cycle 6 refused the trade at 0.67551 because
*"risk-reward fails the 2:1 rule"*. With `stop_pct 1.24` the floor demands a
target ≥2.48%; every target the desk had published failed it (2.14%, 1.35%,
2.01%, 2.31%). Cycle 7 entered at 0.6756 — **0.013% higher, materially the
same price** — after moving the target 0.662 → **0.640**, the first value
that clears the floor, at 5.27% depth. The `basis.verdict` for that change is
`"adjusted"` with **`discussion: null`**.

0.640 required **1.32%/hour for 4 hours**. SUI's entire realized range over
the 60-minute hold was **0.21%**. The desk sized on a 4-hour thesis it had
called unreachable one cycle earlier, then closed at 25% of that horizon
citing a "stall" — while its own equity tape ran +0.011 → +0.057 → **+0.091
(the trade's peak)**. It called an accelerating position stalled on a single
0.018% uptick.

### The two agents disagreed on the counterfactual, and the disagreement IS the finding

* Agent B, live mark 0.67402 at 10:24:58Z: holding = **+$0.0942**, so the
  close **forfeited $0.0736**.
* Agent A, live mark 0.67615 at 10:31:13Z: holding = **−$0.1121**, so the
  close **saved $0.133**.

Both obeyed the live-mark rule. **The counterfactual flipped sign in seven
minutes.** On a trade whose whole P&L range was $0.14 wide, the counterfactual
carries no signal — which is itself the verdict on a 60-minute 0.12% noise
capture. I am recording both numbers rather than picking the one that suits.

### The arm replay — the follow-through I promised, and the answer is one run

For the 4 crossings found in cycle 15, what a half-reduce at the arm level
would have realized versus letting the rail's exit take the whole book:

| run | side | rail net | half at arm | delta |
|---|---|---|---|---|
| 1175 SOL | buy | −0.28620 | −0.26924 | **−0.12614** |
| 1293 UNI | short | −0.09489 | −0.06128 | **−0.01384** |
| 1304 JTO | buy | −0.04620 | +0.10601 | **+0.12911** |
| 1305 FIL | short | −0.72777 | +1.50032 | **+1.86421** |
| | | | **TOTAL** | **+$1.85334** |

**Strip FIL 1305 and the other three sum to −$0.011.** The entire case for
arm precedence rests on one run. That is the same shape as the FIL oversize
that was 100% of a day's P&L — and it means the honest answer to "should arms
outrank rails" is still **not demonstrated**, on 4 observations with one
outlier. I will not carry this forward as "arms would have made $1.85".

### Also confirmed

* **The 5-minute mark blindness is designed, not degraded.**
  `POSITION_REFRESH_INTERVAL=300` is explicitly set on prod (verified). Marks
  changed 13 times in the 60.4-minute hold — **4.69 min cadence**, matching
  FIL 1358's 4.74. The whole favourable excursion occupied the last 3 marks.
* **Ratchet: did not fire and was not close** — peak $0.0616 against a
  $0.1306 arm (47%). But at the true round-trip rate the arm is $0.0588 and
  **it would have armed**, with a floor never breached — so the position
  would still be open. Its inertness did not save this trade.
* **Ratchet running total unchanged at −$0.13891** over 2 fires.
* **Today's exits by author: rails +$4.694 (1322, 1335, 1358); desk −$0.431
  (1344, 1356).** Every dollar of the day came from rail-authored exits. n=5,
  not a distribution — but it is the opposite of the story the arm-precedence
  case needs.

### Recommendations

1. **Decide whether `_order_discussion` may fail open on EXITS.** 10 closes
   or reduces have been authored by a path labelled "not the AI". This is a
   governance question, not a tuning one.
2. **Validate `plan_adherence` instead of accepting the desk's self-stamp** —
   against `position_qty`, the prior cycle's published band, and the prior
   cycle's target. Cycle 4 of this run asserted *"we keep the current short
   position"* with `position_qty: 0.0` and stamped itself `followed`.
3. **A target expansion that newly clears the R:R floor should require a
   non-null `basis.discussion`.** Cycle 7 moved the target 2.5× with none.

## Cycle 15 — 09:4xZ (anchor 09:49:28): quiet; **the arm replay ran, and it partly refutes my own cycle-14 framing**

**PROFIT-OR-LOSS FIRST.** No closes. SUI run 1356 short still open at
**−$0.0019**. Day 08-17 **+$4.24**. **0 no-verdicts in 10 decisions.** One more
`verdict_salvaged` fire (#462). Docs #469 merged.

### I did the measurement I specified — and my specification was wrong

Cycle 14 ended: *"computable from stored marks."* **It is not.** There is no
price-history table (only `market_news_snapshots` and
`polymarket_settlements`), and `equity` payloads carry only
`realized/unrealized/total/trades` — no mark. Anyone taking that spec at
face value would have found nothing.

The real source is `price_fetcher._hyperliquid_post` with a
`candleSnapshot` request — **1-minute candles**, which is finer than the
~4.7-minute mark cadence the rails themselves run on.

### The replay

For every crypto run that ever armed and was then closed by a rail: take the
LAST arm before the close, and ask whether its level was touched between the
close and the run's **own original `at_time` horizon**.

18 armed crypto runs closed by a rail; 14 replayable (4 lacked a horizon,
level, or a usable window).

| | |
|---|---|
| arm level **crossed** inside the original horizon | **4 (29%)** |
| **not** crossed | **10 (71%)** |

The four that would have had their moment:

| run | symbol | arm | outcome |
|---|---|---|---|
| 1175 | SOLUSDT | price_below 75.0 | low 74.650 |
| 1293 | UNIUSDT | price_above 3.27 | high 3.3378 |
| 1304 | JTOUSDT | price_above 0.586 | high 0.59043 |
| 1305 | FILUSDT | price_below 0.667 | low 0.65785 |

### FAILED — my cycle-14 conclusion was over-stated

I wrote that *"the one instrument the desk is told to prefer is the one it is
least allowed to use"*, with the strong implication that rails were robbing
arms of their moment. **The replay says that is true for 29% of them and
false for 71%.** Most arms would never have fired even if the run had lived
to its own horizon. The 132-authored-2-fired ratio is therefore mostly
**arms that were never going to trigger**, not arms that were cut short.

That materially changes the size of the prize. A remedy that lets arms
outrank `at_time` would reach roughly 3 runs in 10, not 4 in 5.

### What the replay does NOT establish, and I will not imply it does

**Crossing a level is not the same as profiting from it.** For a short,
`price_below → reduce` banks profit while `price_above → reduce` cuts a
loser; the P&L of firing versus the rail's actual exit needs each run's side
and the mark at the crossing. I have the tooling now and not the answer.

Nor does 4-of-14 constitute a distribution. It is a bound: **at most ~29% of
armed runs had a live trigger taken from them.**

### Recommendations

1. **Next layer of the same replay:** for the 4 crossings, compute what the
   half-reduce would have realized at the crossing versus what the rail's
   exit actually realized. That is the number that decides whether any
   arm-precedence change is worth making, and it is now one script away.
2. **Correct the framing in any downstream reading of cycle 14** — the
   starvation is real but bounded at ~29%, not the 77% rail-closure rate.
   The 77% is how often a rail ended the run; it is not how often that cost
   the desk anything.

### Method note worth keeping

Two SQL traps cost me a cycle of tooling time and both are worth recording:
an **unquoted heredoc** (`<<PYEOF`) let the shell eat `$.at_time` inside JSON
paths, and the DB wrapper **mangles a quoted `IN (...)` list** — filtering in
Python instead of SQL was the fix.

## Cycle 14 — 09:1xZ (anchor 09:19:30): quiet; **the arm is structurally starved — 132 authored, 2 ever fired**

**PROFIT-OR-LOSS FIRST.** No closes since 08:28:15Z. One new position: SUI
run 1356 short, opened 09:14:43Z, **−$0.033 unrealized**. Day 08-17 **+$4.24**.
No-verdict **1 of 12 decisions (8.3%)** — down from 23.1%, and I have also
stopped probing the host, so I am not crediting the fall to anything.

### Following the empty-why arm finding to the profit question nobody had asked

Cycle 13 corrected my watch: 131 of 132 arms carry `why: ""`. The obvious
next question is not *why is the field empty* — it is **does the arm earn
anything at all.**

| | |
|---|---|
| `intent:arm` events authored, all time | **132** |
| `armed_exit` events, all time | **2 (1.5%)** |
| both fired on | 2026-08-13 and 08-14 — **none in 3+ days** |
| runs with `armed_order_json` persisted | 10, **all `stopped`** |

Both fires were mechanically clean — `reduce 0.5` with slippage −0.08% and
+0.01%. The mechanism works. It just almost never runs.

### Two hypotheses of mine, both refuted before I could report them

1. **"The levels are unreachable."** This was the arm-reachability spec
   already sitting in my backlog. **Refuted.** Measured every arm's level
   against its run's entry price: distances cluster at **0.1%–1.5%** — well
   inside an ordinary day for these symbols. Only one outlier (CL, 4.4%).
   The desk is not setting fantasy levels.
2. **"Arms are authored once and forgotten."** Refuted — the desk **re-arms
   every cycle** (run 1122 armed 11 times, run 1147 11, run 1123 9), mostly
   at the same or a walked level.

### What the data actually shows: the platform closes the book first

Of the **44 runs that ever armed**, the close reasons are:

| close reason | runs | authored by |
|---|---|---|
| `stop_event:at_time` | **14 (32%)** | platform |
| `desk_retired` | 9 (20%) | **desk** |
| `adapt_retired` | 7 (16%) | platform |
| `fleet_stop_all` | 7 (16%) | platform/owner |
| `stop_event:trailing_lock` | 6 (14%) | platform |
| `positions_held` | 1 | — |

**Only 20% of armed runs ended by the desk's own choice. 77% were ended by a
rail or a fleet action before the arm could act.** Twelve of those closes
were `flatten`s.

The light prompt explicitly instructs: *"prefer arm over hold whenever you
can name the level that would change your mind, because your next cycle is
far away and the market is not."* The desk complies — 132 times, at
reachable levels, re-armed every cycle — and the platform closes the book on
its own schedule 4 times out of 5. **The single instrument the desk is told
to prefer is the one it is least allowed to use.**

This is the same shape as cycle 13's FIL sequence: rail covers → replacement
run spawns → replacement defers → thesis intact, position gone, move
captured by nobody. And `at_time` at 32% means the largest single killer of
armed runs is the run simply reaching its hard expiry with a live
conditional exit pending.

### ISSUE — not shipping, and this time the reason is scope not doubt

The candidate remedies are all behaviour changes to money paths: let a live
arm outrank `at_time`, or lengthen horizons, or make `adapt_retired` yield to
a pending arm. Each changes when real positions close. On my own standard
that needs the P&L of the counterfactual, which I do not have — 2 fires is
not a distribution, and the 130 that never fired have no outcome to compare.

**The measurement that would settle it:** for each armed run closed by a
rail, whether the arm's level was subsequently hit inside the run's original
horizon, and what the reduce would have been worth at that level. That is
computable from stored marks and is the right next piece of work.

### Standing watch corrections carried forward

* **empty-why arms: 131/132, not n=6** (corrected cycle 13).
* **arm-reachability: refuted as a defect** — levels are 0.1–1.5% away, not
  unreachable. The spec in the backlog should be struck; the real problem is
  arm *starvation*, not arm placement.

## Cycle 13 — 08:4xZ (anchor 08:49:25): **a scratch that hides two proven arithmetic defects, and a standing watch of mine that was wrong by 22x**

**PROFIT-OR-LOSS FIRST.** FIL run 1358 closed 08:28:15Z. `signals.pnl`
+$0.01513989, open fee $0.0126108 → **true net +$0.00252909** (matches
`trading_runs.realized_pnl_usd` to 8dp). Day 08-17 **+$4.24**, resid 0.00.
Book flat. **No-verdict since 08:18Z: 0 of 13 decisions** — down from 23.1%,
n too small to credit, and I have also stopped probing the host.

On $28.02 notional the round trip took **90.9% of gross**. The trade cleared
breakeven by **$0.00006 per unit**. This is not a win to bank; it is a loss
avoided by rounding.

### FAILED — my own standing watch was wrong by a factor of 22

I have carried "empty-why arms (n=6)" on the watch list for days. Verified
myself this cycle:

| arm intents, all time | **132** |
|---|---|
| with `why: ""` | **131 (99.24%)** |
| with a real why | **1** |

**An empty why is not an anomaly — it is the default behaviour of the arm
path**, 131 times out of 132. The single exception proves the field can be
populated, so this is an unreliable desk emission, not a schema that drops
it. My watch was scoped to a handful of instances I happened to notice and
never counted. Corrected here.

### The arm this cycle was dead three ways

08:29:58Z, run 1358: `intent: arm, {"if":"price_above","level":0.68,
"then":"reduce","size_frac":0.5}`, `why: ""`.

1. **The run stopped at 08:28:15Z** — the arm was authored **103 seconds
   after the run ended** (verified directly).
2. **`position_qty: 0.0`** — the only one of 132 arms in history with no
   position. It armed a half-reduce of nothing.
3. **0.68 was 2.08% away** at arm time; the run's worst adverse print all
   session was 0.66943.

It was still persisted to `trading_runs.armed_order_json`. Dead config
written onto a stopped run, with no stated reason to audit it against.

### WHY the trade was a scratch — the desk broke its own rule at the entry tick

Agent A's finding, which I have checked against the tape:

* **Cycle 1 (06:55:53Z)** published an entry band **0.668945–0.676471** and
  **refused to trade at 0.6691 — inside its own band** — on an explicit
  negative-expectancy argument: a defensible stop was >10% away, breaking
  its 2:1 R:R. It bound itself: re-enter *only on a pullback into the zone*.
* **Cycle 2 (07:12:27Z)**, 17 minutes later, entered at **0.6668 — 0.3207%
  BELOW the band floor.** For a short that is not a pullback into the zone;
  it is a worse fill in the wrong direction. Nothing resolved cycle 1's
  objection — the swing high had not moved. The desk swapped the defensible
  stop for an arbitrary 2% stop and re-declared ">2:1 R:R".

Entering at its own band floor with the identical exit nets **+$0.09264**
against the actual **+$0.00253**. **The desk gave away $0.0902 at entry — 36x
the entire realized profit — by breaking a rule it had written 17 minutes
earlier.**

### Plan 26 — the adherence stamp is INVERTED on this run

* Cycle 1 held flat, correctly honouring its own risk rail → stamped
  **`deviated`**.
* Cycle 2 entered outside its published band, contradicting cycle 1's
  explicit re-entry condition → stamped **`followed`**.

**The stamp rewarded the rule-break and penalised the rule-keep.** As a
§3.7 control that is worse than absent — it is actively misleading. Note
this is a *content* defect in what the desk emits, not the fabrication bug
#463 fixed.

Also: outlook published on 3 of 5 cycles, with the 40% silence concentrated
exactly on the stress window (07:48–08:03, unrealized −$0.1105, margin
T0→T1). The desk never once asked to exit.

### #449's second fire — the rail is 0-for-2 and its ceiling is $0.00 by design

| fire | position net |
|---|---|
| AVAX 1335 pos-2, 02:23:39Z | **−$0.14144302** |
| FIL 1358, 08:28:14Z | **+$0.00252909** |
| **running total** | **−$0.13891393** |

Two defects, both **arithmetic and provable from code** — not statistical
claims needing a distribution:

**(a) unit mismatch, unfixed.** `_breakeven_floor_hit` takes no
`baseline_pnl`, so `peak`/`current` are run-cumulative while `arm`/`exit_fee`
are position-scoped. Its sibling `_trailing_lock_hit` does take a baseline.
**Proven decisive on AVAX:** position 2's own peak excursion was
0.4228 − 0.0806 = **$0.3422 against a $0.398 arm → it would never have
armed.** It armed on $0.0806 banked by the desk's earlier covers, then
flattened at $0.0377 gross against an already-paid $0.0896 open fee — **a
guaranteed loss the instant it triggered.**

**(b) one leg at an inflated rate, unfixed.** `exit_fee` 0.028 =
notional × **0.001** × 1 leg (verified: 28.024 × 0.001 = 0.028024). The true
crypto rate is 0.00045, so a true single leg is $0.012598 — exactly the
close fee charged. **Proven binding on FIL:** `total` at the fire was
0.015127, which sits *between* the two floors. At the true rate
`0.015127 ≤ 0.012598` is **false — the rail would not have fired at all.**

**FIL was a clean test and AVAX was not.** Run 1358 had $0.00 banked before
this position (2 trade events, verified), so defect (a) had nothing to bite
on. Same rail, same defects, same day — the only difference in outcome was
whether there were prior closes to corrupt the baseline.

**Correcting my own cycle-4 record:** I reported AVAX run 1335 as a loss.
The run as a whole was **+$0.0287** — the desk's two partial covers made
money; only the ratchet-flattened position 2 lost $0.1414.

### ISSUE — I am NOT shipping the rail fix, and the reason is specific

The diagnosis is solid and arithmetic. The *correction* carries a trap Agent
B named explicitly: **adding `baseline_pnl` alone moves the best case from
$0.00 to −1 open fee**, because a position-scoped current is gross while the
floor is one leg. The floor must move to a full round trip in the same
change, or every future fire lands one open fee under water.

I have already shipped one fix today that did not work (#468). Shipping a
money rail whose correction has a named failure mode, in the tail of a
monitoring cycle, without a replay harness, is how that happens twice.

**Specification for the focused session that should do it:**

1. `_breakeven_floor_hit(peak, current, arm, baseline_pnl, exit_fee)` —
   mirror `_trailing_lock_hit`; baseline is the banked P&L that cannot
   round-trip.
2. In the SAME change, the floor becomes the **round trip**, and the rate
   comes from `fees.fee_rate(market)`, not `BREAKEVEN_FEE_RATE=0.001`.
3. Replay both live fires as fail-before tests: **AVAX must not arm**
   (0.3422 < 0.398 baseline-corrected) and **FIL must not fire**
   (0.015127 > 0.012598 at the true rate).
4. Note the residual: even on a single-position run the comparison is off by
   one open fee, because `total` is net of it while `arm` is gross.

### Also measured

**~4.7-minute mark staleness is the binding constraint, not the threshold.**
The FIL mark refreshed 16 times in 75.8 minutes; the peak existed for
**exactly one observation**; the rail armed and fired on **consecutive
marks**. The $0.0458 giveback happened entirely inside one refresh and was
invisible to any rail at this resolution. No floor tuning fixes that.

Counterfactuals at the live mark only (FIL 0.66388, AVAX 6.3121): holding
FIL was worth **+$0.0976**, holding AVAX **+$0.6971** — **0-for-2 on
realized net and 0-for-2 on opportunity cost.** Two observations is not a
distribution and I will not present it as one; the case against the rail is
the arithmetic, not the two outcomes.

## Cycle 12 — 08:1xZ (anchor 08:18:48): **the timeout fix did NOT work, and the measurement says why**

**PROFIT-OR-LOSS FIRST.** Day 08-17 **+$4.23** (ledger, resid 0.00). One new
position: FIL run 1358 short, opened 07:12:27Z, **+$0.024 unrealized** — the
first entry in ~5 hours. 10 running runs.

### FAILED — my own #468, and the rate is the verdict

| window | decisions | no_verdict | rate |
|---|---|---|---|
| PRE-fix 06:00–07:05 | 27 | 5 | **18.5%** |
| POST-fix 07:05–08:18 | 26 | 6 | **23.1%** |

**The 120s → 300s decision-tier timeout did not reduce the no-verdict rate.**
It is marginally worse, which at these n is noise — but it is certainly not
better. The fix has not delivered.

Post-fix kinds: `no_response` x4, `empty` x2.

### Three hypotheses, all mine, all refuted by measurement

1. **"The model is too slow for a 120s cap."** Refuted last cycle — it
   answers in **4.9–7.4s idle**.
2. **"Concurrent cycles queue at a single Ollama endpoint."** Refuted last
   cycle — 4 concurrent calls cost **79.2s wall vs 78.2s for one**.
3. **"Plan 26's outlook object inflates the schema and the latency."** My
   leading theory going into this cycle. Refuted by A/B on the live host:

   | prompt | latency |
   |---|---|
   | WITHOUT outlook | **146.7s, 132.4s** |
   | WITH outlook | **80.6s, 135.3s** |

   Without the outlook block it was *slower*. The outlook is not the driver.

### What the data actually supports

Raw-API probe with `finish_reason` exposed:

* `max_tokens=460` → **`finish_reason: "length"`**, 460 completion tokens,
  716 chars — cut off mid-object. That is the `truncated` class, and #462
  now salvages it.
* `max_tokens=2000` → `finish_reason: "stop"`, 444 tokens, **124.2s**.

And the load, from `llm_usage` (no extra GPU cost to measure):

```
mean total LLM calls/hour today: 178   (decision 85-144/h + brief 63-85/h)
at ~100s per decision call:      ~17,800 GPU-seconds demanded per hour
available:                        3,600 seconds of wall clock per hour
                                  => ~5x oversubscribed
```

Journaled decisions run **20–25/hour**, so the platform is making roughly
**6 decision-tier LLM calls per journaled decision** (panel, discussion,
brief, retries).

**That reconciles every observation, including the ones that refuted me.**
Idle 5s versus loaded 80–150s is a ~20× queueing multiplier on a saturated
host. My "4 concurrent = same wall as 1" probe measured marginal cost
against a queue that was *already* deep — which is why adding calls looked
free. And it is why the cap does not matter: at ~5× oversubscription, calls
breach 120s and 300s alike.

**I fixed a symptom.** The reasoning behind #468 was sound for the data I had
— the tail genuinely was breaching 120s — but the tail is a consequence of
oversubscription, not of a cap set too tight. #468 buys headroom and should
stay; it does not solve this.

### ISSUE — the real lever is call volume or host capacity, and both are the owner's

Nothing in the timeout, token, or concurrency settings fixes a 5×
oversubscribed model host. The two honest levers:

1. **Reduce calls per decision.** ~6 decision-tier calls per journaled
   decision is the multiplier. `order_discussion` alone adds a second
   decision-tier call per cycle — cycle 9 measured it adding 2m43s between
   light analysis and the journal. Cutting it on light cycles would roughly
   halve decision-tier volume. **This changes desk behaviour, so it is an
   owner call, and I have not made it.**
2. **Add host capacity**, or route the decision tier to a second provider.

**Recommended measurement before either:** realized-P&L contribution of
`order_discussion` cycles versus light-only cycles. If the discussion call is
not earning its ~100s, it is the obvious cut.

### Note

I have now shipped three diagnostics and one fix against this single
problem. The diagnostics were each justified — they are what turned an
argument into these numbers — but the fix did not work, and saying so is the
point of the loop.

## OWNER ORDER "fix" — 07:0xZ: **the timeout is fixed, after the probe overturned both of my hypotheses**

Owner instructed the fix directly, overriding my "not mine to change" from
cycle 10. Measured first, then changed.

### The probe killed both theories I was carrying

| condition | latency |
|---|---|
| idle, 4 calls | **4.9s, 4.9s, 5.9s, 7.4s** |
| single call while the fleet was cycling | **78.2s** |
| 4 concurrent calls while cycling | **79.2s wall**, per-call 69–79s, **4/4 succeeded** |

* **"The model is too slow for 120s"** — refuted. It answers in ~5s idle.
* **"Concurrency is queueing at a single Ollama endpoint"** — refuted, and
  this was my stated hypothesis going in. Four concurrent calls cost the
  same wall-clock as one; the endpoint parallelises.

What is actually there is a **latency tail**: the same call costs ~78s under
live fleet load, so a 120s cap sits ~1.5× loaded latency and the tail clears
it several times an hour. **Had I shipped the concurrency limiter I was
reaching for, it would have cut throughput and fixed nothing.**

### Shipped [#468] — tier-scoped, not global

`_llm_timeout_seconds(tier)`: the decision tier gets 300s
(`LLM_TIMEOUT_SECONDS_DECISION`), never below the general cap.

**The 120s default is untouched on purpose.** It exists because one stalled
call took the research loop offline for 30+ minutes while the provider
answered a fresh probe in 5.7s. Only the decision tier can afford to wait —
it runs on its own dedicated pool, sized so a slow LLM call cannot starve
the SL/TP watcher.

### The test break was the finding, not an obstacle

`test_local_token_floor`'s fake generator did not accept `tier`, so the new
kwarg raised `TypeError` — which `generate_text`'s bare `except` swallows
into a `None` return, **the same shape a provider timeout takes.** That is
exactly the confusion #466 was written about, reproduced inside the suite. I
fixed the fake and added a test asserting the pass-through rather than
loosening the assertion.

3 mutants killed. Full suite **4,435 passed + 1,346 subtests**.

### Deploy note — a parallel session is active

#468's rollback target is `20260817-monitor-panel`, **not** my previous
`20260817-no-response-class`. Another session deployed between my two
deploys. Verified all six of my live changes survived, in-container:

```
decision timeout: 300.0      general: 120.0
no_response class: no_response    empty class: empty
salvage present: True        adherence silent: {}
loss floor cfg: 10.3149
```

0 tracebacks. **On a shared box, "my deploy succeeded" is not the same as
"my change is running" — check the feature, not the chain.**

### What decides whether this worked

`no_response` (#466) is now the counter. If the tail moves past 300s the
losses return and the tape will say so. This buys headroom against the
observed tail; it does not make the model faster.

**Session ship count: 22 PRs.**

## Cycle 10 — 06:4xZ (anchor 06:49:33): **the no-verdict cause is settled — local-provider timeouts — and #465 was mine to correct**

**PROFIT-OR-LOSS FIRST.** No closes since 02:24:43Z — book flat **4h25m**.
Day 08-17 unchanged at **+$4.24** (ledger, resid 0.00).

### The question is answered, and not by inference

Four `no_verdict` events since #465 deployed (06:12:09Z), all `kind:
"empty"`. Each matches, **to the second**, a worker warning:

| no_verdict | worker log |
|---|---|
| 06:18:27Z run 1352 | `06:18:27,285 LLM generation failed (provider=local): Request timed out.` |
| 06:23:44Z run 1344 | `06:23:44,438 …Request timed out.` |
| 06:23:49Z run 1355 | `06:23:49,164 …Request timed out.` |
| 06:25:25Z run 1353 | `06:25:25,957 …Request timed out.` |

**The dominant no-verdict class is the local model timing out.** Not
truncation, not a silent model, not a prompt problem. Measured rate in the
covered window: **7 timeouts in 37 minutes, and 4 of 15 decisions (27%)
produced no verdict.**

Config, all read from prod: `LLM_TIMEOUT_SECONDS` defaults to **120s** with
`max_retries=1`; provider is `local` at an Ollama endpoint; and local calls
are floored at `max_tokens = max(max_tokens, 2000)` because the reasoning
model spends budget on hidden chain-of-thought before any visible content.
So the shape is: **a reasoning model asked for ≥2000 tokens does not always
finish inside 120 seconds under load.**

### FAILED — my own #465, one cycle after shipping it

#465 split `error` from `empty` inside `_light_analysis`. That is **one layer
too high.** `generate_text` catches provider errors itself and returns None
— its own docstring says so: *"Returns None on any failure so callers can
fall back to their own deterministic summary."* The caller's `except`
therefore almost never fires, and the class I added to catch infrastructure
failures could not see the infrastructure failure that dominates the tape.

I shipped a diagnostic that classified 4 provable timeouts as a silent model.

**Corrected as [#466].** The signal was already in the return value: `None`
means the call never came back, `""` means the model answered with nothing.
`None` now files as **`no_response`**. Two existing tests — one from #459,
one from #465 — asserted `None → "empty"` and so encoded the mistake; both
are corrected in place with a comment saying why, rather than quietly
edited.

Why this is worth a PR rather than a note: **container logs are lost on every
deploy** — I hit exactly that last cycle chasing the salvage timestamps — so
a failure class that can only be resolved from logs cannot be resolved at
all. The tape has to carry it.

3 mutants killed (branch removed; branch swallowing `""` too; `no_response`
beating a named error).

### ISSUE — the timeout itself is NOT mine to change

The obvious remedies all trade against each other, and the code says so:

* **Raise `LLM_TIMEOUT_SECONDS`** — the 120s cap exists because a stalled
  call once took the research loop offline for 30+ minutes while the
  provider answered a fresh probe in 5.7s.
* **Lower local `max_tokens`** — the `max(max_tokens, 2000)` floor exists
  because starving a reasoning model produces *exactly* the empty output
  this is about.
* **Lower cycle concurrency** — reduces the fleet's decision throughput.

This is capacity on the owner's own local model host, and every lever has a
documented reason for its current value. **Reporting it with numbers;
changing nothing.**

### Recommendations

1. **The 27% figure is the one to act on, and it is an owner decision.**
   Roughly a quarter of decision cycles currently produce no verdict, each
   one a held book that got no management look. The three levers above are
   the choice; the measurement to make it with is p50/p99 local call latency
   against the 120s cap.
2. Still open from cycle 9: whether a salvaged verdict's fields reach the
   journal (`plan_adherence` disagreed on run 1346). Not settled this cycle.

## Cycle 9 — 06:1xZ (anchor 06:13:29): quiet on trades; **#462 fired twice and worked — after I nearly recorded it as a bug of my own**

**PROFIT-OR-LOSS FIRST.** No closes since 02:24:43Z — book flat **3h49m**.
Day 08-17 unchanged at **+$4.24** (ledger, resid 0.00). 16 decisions, all
`hold`. 10 running runs, **9 idle-retires today**.

### WORKED — the salvage caught two real verdicts

`verdict_salvaged` fired for the first time, **twice**, both `truncated`:

| run | ts | chars | cut at |
|---|---|---|---|
| 1346 (GBPUSD) | 05:33:25Z | 921 | inside `"report"`, after a complete `plan_adherence` |
| 1351 (NZDUSD) | 05:38:19Z | **254** | inside `outlook.bias` — very early |

Both cycles then journaled **real decisions with real confidence** — 1346
cycle 11 at conf 0.48 with full component scores, 1351 cycle 8 at conf 0.57 —
instead of the `conf 0.0 / "light cycle: no LLM verdict"` those truncations
produced before #462. That is precisely the outcome the salvage exists to
prevent, twice in five minutes.

### The near-miss I want on the record

My first read of this tape was that **#462 had broken the cycle**: the
salvage event at 05:33:25Z had no decision, no `order_params` and no
`gate_skip` beside it, and the next decision was 2m43s later. That is what a
crashed cycle looks like.

It was wrong. The decision sequence for run 1346 is cycle 10 at 05:02:41,
**cycle 11 at 05:36:08**, cycle 12 at 06:03:51 — so the 05:33:25 salvage
belongs to cycle 11, and the gap is the `order_discussion` LLM call sitting
between light analysis and the journal. Same shape on 1351 (salvage 05:38:19
→ cycle 8 decision 05:42:08).

I could not settle it from logs — the worker was recreated at 06:12:09Z and
`docker logs` lost the previous instance's output — so it had to be settled
from the decision-cycle numbering. **Recording it because the failure mode is
mine: a telemetry event that lands minutes before the decision it belongs to
reads exactly like a crash, and I will meet this again.**

### Corrected: #465 has produced NO tape yet

I was about to read the 06:11:17Z `no_verdict` — `{"kind": "empty"}` with no
`err` field — as evidence that the call did not raise, and therefore that
infrastructure is exonerated. **The worker started at 06:12:09Z. That event
came from the OLD image**, where no `err` field existed to begin with. It
proves nothing. Kind mix stands at **empty x4, truncated x1**, all pre-split.

### ISSUE — an open question I am not resolving by assumption

Run 1346's salvaged object carried `"plan_adherence": "revised"` (complete in
the recovered prefix), but the journaled decision reads `adh=followed`. So
the value the salvage recovered is **not** what reached the journal —
something downstream, most likely the discussion/full-path merge, supplied
its own. I will not claim the salvaged fields flow through when the one
field I can observe disagrees. One query next cycle settles it.

Also logged, unresolved: run 1351's salvaged prefix carried
`"stop_pct": 0.0046, "target_pct": 0.0210` — fraction-shaped values in a
percent field, which is the #446 unit-slip watch. That cycle held, so nothing
was sized from them. Unit-slip fires all time: **4**.

### Recommendations

1. **Check whether a salvaged verdict's fields survive to the journal**
   (`plan_adherence`, `order_intent`, `scores`). If the merge discards them,
   #462 prevents a conf-0.0 hold but does not deliver the desk's actual
   decision — a materially smaller win than claimed.
2. **9 idle-retires today against 0 positions held for 3h49m.** The fleet is
   now retiring runs faster than it trades. Worth measuring against the
   cycle-5 finding (budget funds 10 of 20 slots) before anyone concludes the
   retires are the problem — they may be the correct response to a book with
   no positive-expectancy entries.

---

### #465 DEPLOYED and verified — image `20260817-noverdict-error-class` (merge `19f5d55`)

All four branches replayed against the deployed function in the container:

```
raised    -> {'kind': 'error', 'err': 'TimeoutError: read timed out', 'chars': 0, 'tail': ''}
empty     -> empty
text wins -> no_json          (a successful retry is never filed as an error)
bounded   -> 200              (err note capped)
```

#463's stamp rule, #462's salvage, #460's corrected loss floor and the Plan
26 flag all survived the from-main rebuild. 0 tracebacks.

**The open question is now answerable rather than arguable.** Next cycle
reads the kind mix with `error` in it. Two outcomes, two different
investigations, and I will not pre-commit to either:

* `error` dominates → llm_client timeouts/retries; an infrastructure fix.
* `empty` survives the split → the prompt or the model returned nothing on
  a healthy call; a decision-path fix.

**Session ship count: 20 PRs.**

---

## Cycle 8 — 05:2xZ (anchor 05:27:14): quiet on trades; **#463 proved itself live, and the no-verdict tape is now decisive enough to act on**

**PROFIT-OR-LOSS FIRST.** No closes since 02:24:43Z — book flat **3h03m**.
Day 08-17 unchanged at **+$4.24** (ledger, resid 0.00). 10 decisions, all
`hold`. 0 salvage fires.

### WORKED — #463's branch fired live, exactly as designed

Last cycle I refused to call #463 verified because the branch it changes had
never executed on prod. It has now:

> **run 1347, 05:11:45Z** — `"confidence": 0.0, "conviction": null,
> "scores": null` and **no `plan_adherence` key at all**. The paired
> `no_verdict` event fired at the same second.

Before the fix that cycle would have been journaled `plan_adherence:
"revised"` — a plan revision by a desk that said nothing. Adherence since
#463: **followed x14, deviated x1, NONE x1** — and the NONE is the silent
cycle, where it belongs.

### The measurement that unblocks the last unexplained class

Diagnostic fires since #459, n=4:

| kind | count |
|---|---|
| **empty** | **3 (75%)** |
| truncated | 1 (25%) |

Truncation — the class #462 now salvages — explains a quarter. **`empty` is
the dominant class, and my own instrument could not tell what it meant.** The
light path's decision call sits in a bare `except` that sets `text = None`,
so a call that RAISED and a model that RETURNED NOTHING file as the same
event. Those need opposite fixes: one is infrastructure, one is prompt or
model behaviour.

**Shipped as [#465]**: a raised call files as `kind: "error"` with a bounded
note naming the exception class; a genuinely empty response is still
`empty`; and **text always wins** — a retry that succeeded is never filed as
an error. 6 tests fail-before, **4 mutants killed** (err ignored → red;
note unbounded → red; err checked before text → red; capture unwired → red).

Why this clears the bar when three findings last cycle did not: this changes
**no decision and no order**. The bar I have been holding is for behaviour —
rails, sizing, funding — where a wrong fix costs money. An instrument that
cannot distinguish its own dominant failure class costs nothing to sharpen
and is the only thing standing between me and an answer. Same reasoning as
#459 itself.

### Recommendation

**Read the kind mix again once `error` has fired.** If `error` dominates,
the next question is llm_client timeouts/retries and it is an infrastructure
fix; if `empty` survives the split, it is the prompt or the model and the
fix is on that side. **I will not propose either until the tape says which.**

## Cycle 7 — 04:5xZ (anchor 04:59:02): quiet; **the three "lost sells" dissolved into three rare causes — no fix shipped, and that is the correct outcome**

**PROFIT-OR-LOSS FIRST.** No closes since 02:24:43Z — book flat **2h35m**.
Day 08-17 unchanged at **+$4.24**. 13 decisions, all `hold`. 0 salvage fires,
0 new no-verdicts.

### I chased what I said I would chase, and it did not become a defect

Last cycle I flagged three authored sells that produced no realized leg. All
three runs have **zero `signals` rows** — no order was ever created — and all
three were then stopped `idle_retired` with realized $0.00. They have **three
different causes, none systemic**:

**1. run 1336 (BNBUSDT) — the retire/in-flight race.** The clearest of the
three:

| time | event |
|---|---|
| 00:27:55Z | `idle_retired` → running → stopping → **stopped** |
| **00:29:24Z** | cycle 12 completes: `order_params outcome: parsed`, `action: sell`, size_frac 0.05, stop 2.0%, target 5.0%; `order_intent: open`, *"Open a modest short position now; stop at $612 protects against a breakout, target $570 captures expect…"* |
| 00:29:24Z | `gate_skip {"stage":"execute","reason":"fence: run is stopped"}` |

**The run was retired for not trading, and 89 seconds later the cycle it had
already dispatched produced a fully-formed order that was discarded because
of that retirement.** The fence itself is correct — a stopped run must not
trade. The wrong-ordered part is upstream: the idleness verdict is reached
without regard to a cycle already in flight.

Frequency fleet-wide, **all time: 2**.

**2. run 1341 (AUDUSD) — `fence: lease expired`** on its cycle 1. All time: 12.

**3. run 1338 (WLDUSDT) — `spot sell with no inventory — treated as hold`.**
The run is `market_type: spot`; the desk authored a short (outlook bias
`short`, trigger entry, target 0.33, stop 2.5%) and the risk gate correctly
refused it. Notably the verb came from the **discussion** path —
`order_discussion {proposed: buy 0.65, final: sell 0.58}` — while the light
prompt already withholds `sell` from a flat spot book.

**But the frequency refutes the alarming reading.** Spot-sell refusals all
time: **2** — one 08-13, one 08-17. The prompt-side fix (whose own comment
cites *33 refusals across 16 runs between 2026-07-27 and 2026-08-03*) cut
this from ~33/week to 2 in a fortnight. It is working; this is a leak, not a
hole.

### ISSUE — nothing shipped, deliberately

Every one of the three is a real ordering or gating flaw, and **not one of
them clears the bar I have held all session.** n=2, n=12, n=2, and in no case
do I have evidence the blocked trade would have made money. Shipping the
idle-retire reordering on "it is plainly wrong-ordered" is exactly the
reasoning I refused for the ratchet baseline (cycle 4) and the slot-ledger
renormalisation (cycle 5). Consistency is not optional when the argument
happens to favour acting.

Logged, with the specific measurement each would need:

1. **Idle-retire vs in-flight cycle** — needs the count of retires where a
   cycle was already dispatched, and the realized outcome of the orders those
   cycles produced. n=2 today.
2. **`fence: lease expired`** (12) — is the lease TTL short relative to
   p99 cycle time? One query against cycle durations settles it.
3. **Spot `sell` via the discussion path** — whether the discussion prompt
   receives the same `can_sell` gate the light prompt has. n=1.

### WORKED — #463 on live tape, with the limit stated

6 decisions since deploy, **6 carry an adherence key, 0 were conf-0.0**. That
is consistent with the fix but **does not prove it**: the branch it changes
(a silent cycle recording nothing) has not been exercised live yet, because
no silent cycle has occurred. The functional proof remains the in-container
replay from last cycle. I am not counting an unexercised branch as verified.

### Also on tape

`gate_skip` census, all time — the second-largest category is **`market
closed — flatten queued to the next open` at 1,477**, against 769 plain
`market closed`. Worth understanding what fraction of the fleet's cycles are
spent deciding for markets that cannot trade, but not this cycle.

---

### #463 DEPLOYED and verified — image `20260817-adherence-stamp` (merge `a26b685`)

All four branches confirmed against the deployed function in the container:

| decision | stamp |
|---|---|
| silent cycle (no verdict) | **`{}`** — nothing recorded |
| real verdict, key missing | `{'plan_adherence': 'revised'}` |
| authored `followed` | `{'plan_adherence': 'followed'}` |
| salvaged verdict (#462) | `{'plan_adherence': 'revised'}` — still counted |

Salvage (#462), the corrected loss floor (#460) and the no-verdict diagnostic
(#459) all survived the from-main rebuild. Plan 26 flag on, 0 tracebacks.

**From here the §3.7 table is measuring the desk and not the fallback.** The
115/24/16 baseline recorded above is the last reading taken on contaminated
data and must not be compared with what follows — the next clean table starts
now.

**Session ship count: 19 PRs.**

---

## Cycle 6 — 04:1xZ (anchor 04:19:23): quiet on trades; **the first §3.7 measurement of Plan 26, and it is not flattering**

**PROFIT-OR-LOSS FIRST.** No closes since 02:24:43Z — book flat **1h55m**.
Day 08-17 unchanged at **+$4.24** (ledger, resid 0.00). 10 decisions, all
`hold`. #462: still **0 salvage fires**.

### WORKED — the holds are disciplined, not idle

All ten reports give a specific, checkable reason to stand down, and seven of
ten cite the standing plan by name:

> *"the required stop is too tight, so we remain flat"* (1348) ·
> *"price has not yet breached the 0.595 breakout level required by the
> standing plan"* (1351) · *"the market has moved out of our short entry
> window and is perilously close to the invalidation point, removing positive
> expectancy"* (1344) · *"a low-expectancy trade with insufficient time to
> meet its target"* (1347)

That is the fee/expectancy discipline the platform has been trying to teach,
and it is visibly the forward book doing the steering. Nothing was
gate-blocked — the desk chose this.

### The §3.7 measurement the owner asked for

Since the flag went on (155 stamped decisions from 2026-08-16T21:00Z):

| adherence | cycles | trades authored |
|---|---|---|
| **followed** | **115 (74%)** | **1** |
| revised | 24 | 3 |
| deviated | 16 | 4 |

**Plan-following cycles have authored exactly one trade — and it lost.** That
was run 1344's TRUMP short (23:23:20Z, `followed`, conf 0.66), realized
**−$0.6251** true net, the trade cycle 3 dissected. Every other trade in the
window came from a cycle that revised or deviated from its own plan.

**I am not calling the flag a failure on n=1, and I am not calling deviation
better either** — the deviated bucket's profit is ~entirely the FIL
`order_params: absent` oversize, a defect, not skill. The honest verdict:
**after 588 outlook events and 155 adherence stamps, the forward book has
authored one trade. It is not yet judgeable — and that is itself the
finding.** A plan that almost never authorises action cannot be measured on
the P&L of the action it authorises.

Also on tape: **3 of the 8 traded decisions (runs 1341, 1336, 1338) produced
no realized leg at all** — a `sell` was authored and nothing was ever closed.
Worth chasing next cycle.

### FAILED — the adherence statistic was measuring the fallback

**15 of the 24 `revised` stamps (63%) sat on conf-0.0 cycles where the desk
produced no verdict at all.** `run_cycle` stamped `plan_adherence` on every
decision while the flag is on, and `_parse_plan_adherence` degrades a missing
key to `"revised"` — so a cycle where the desk never spoke was recorded as
having *revised its plan*. Genuine revised stamps: **9, not 24.**

This corrupts the exact number §3.7 judges the flag on, and it corrupts it in
the direction that makes the plan look more contested than it is.

**Shipped as [#463]**: a cycle with no verdict records no adherence. A junk or
missing key on a REAL verdict still degrades to `"revised"` — that desk did
speak. Salvaged verdicts (#462) keep counting, because they are authored.
Fail-before red on 5 tests, 3 mutants killed, wiring test scoped to
`run_cycle` so it cannot pass by matching the helper's own body.

### Recommendations

1. **Re-run the §3.7 table after a day of clean stamps.** Today's numbers are
   the last ones computed on contaminated data; treat 115/24/16 as the
   baseline to be replaced, not as a result.
2. **Chase the 3 authored sells with no realized leg** (1341, 1336, 1338).
   Either the fill never happened or the position closed outside the signal
   path — both matter for attribution.
3. Unchanged and still replay-gated: the fleet slot-ledger over-commitment
   (cycle 5) and the ratchet/fee-rate/round-trip package (cycle 4).

## Cycle 5 — 03:5xZ (anchor 03:50:58): quiet on trades; **fleet 35's slot ledger over-commits its budget by 40%**

**PROFIT-OR-LOSS FIRST.** No closes since 02:59Z. Book **flat** — 0 open
positions across 10 running runs. Day 08-17 unchanged at **+$4.24** (ledger,
resid 0.00). 18 decisions, all `hold` at avg conf 0.494 — the desk chose to
stand down, nothing was gate-blocked (`gate_skip` reason on all 18 is
"decision is 'hold'"). #462 deployed mid-cycle: **0 `verdict_salvaged`, 0 new
`no_verdict` in 18 decisions.** Too small to mean anything either way.

### The thing worth reporting on a quiet cycle

Fleet 35 has advertised **`replenishing:10/20` since 2026-08-16T21:36:36Z —
6h14m, 15 status writes.** It is not replenishing. It cannot.

| | |
|---|---|
| fleet budget | **$10,009.75** |
| 10 filled slots, `original_allocation_usd` | **$9,999.96** (99.9%) |
| 10 empty slots, stamped | **$400.00 each = $4,000** |
| **slot ledger total** | **$13,999.96 — over-committed by $3,990 (39.9%)** |
| live headroom | **$9.79** |

`slot_floor = min(B/2N, own_alloc/2) = min($250.24, $200.00) = $200.00`.
Headroom $9.79 < $200 → `slot_dormant`, **every tick, forever**. 45 such
events already recorded.

**I checked the obvious false alarm first and it was false.** Slots 10–14 are
missing from the table not through a bug but because a resize drained them at
21:36:36Z (`slot_removed`, reason `fleet_resized`) — correct behaviour, empty
slots only.

**The real defect is that the resize drained the slots and never renormalised
the survivors' allocations.** Replacement funding is
`min(slot.original_allocation_usd, headroom)`, so each of the 50 rotations
re-funds at the stale, pre-resize allocation. The over-commitment is
self-perpetuating.

This is the exact state the build path's own comment says the under-fill
reserve was added to prevent:

> *"handing the WHOLE budget to the few composable theses leaves the E3
> backfill zero headroom — the fleet advertises replenishing:k/N but can
> never grow (fleet #26 live: 3/10 slots held all $10k, headroom −$1.25 vs a
> $500 floor)."*

The reserve exists in `build_fleet`. **The replacement path has no
equivalent**, so a fleet can reach the forbidden state after build.

**Effect in profit terms:** the fleet runs **10 theses at ~2× their per-slot
share** ($1,000 average against a $500.49 share) instead of 20 at 1×. That is
a permanent halving of diversification — and today is the day that mattered:
one oversized position was 100% of the day's P&L.

### ISSUE — I am NOT shipping the fix, and the reason is not caution theatre

The consistency defect is unambiguous. **The remedy is not.** Renormalising
would halve future book sizes, and today's own tape argues both ways: AVAX at
a $199 book paid **fees worth 475% of its gross move**. Thinner slots make
the fee hurdle worse. I have no evidence that 20 × $500 beats 10 × $1,000,
and shipping a money-sizing change on a hunch is precisely what the owner law
forbids.

What would settle it: replay the fleet's closed trades bucketed by book size
against the per-market fee floor, and measure realized expectancy per bucket.
That is the same replay already gating the ratchet/fee-rate package — one
measurement now unblocks two decisions.

**Unambiguous regardless of the sizing question:** the status string. A fleet
that cannot grow should not report `replenishing`. The owner reads that
number; "replenishing" implies progress where the truth is "budget-capped at
10/20". Holding it only because it should ship together with whatever the
replay decides, rather than as two changes to the same code.

### Watches

`House floor` briefs since #460: **0** — the corrected floor still untested,
as expected; the −$0.99…−$13.07 band has not been entered. All 136 fleet gate
events ever are context `replacement`; **zero growth attempts**, so the
replenish path is not burning research cycles — a waste claim I checked
before making and did not make.

---

### #462 DEPLOYED and verified — image `20260817-salvage-verdict` (merge `1fb233a`)

Replayed the real severed payload through the deployed function in the
container:

```
recovered: sell 0.66 {'intent': 'reduce', 'size_frac': 0.5}
no verb -> None: True
junk    -> None: True
```

**The exact decision AVAX 1335 cycle 16 lost — a half-position reduce — now
survives the truncation.** The corrected loss floor (#460), the no-verdict
diagnostic (#459) and the Plan 26 flag all survived the from-main rebuild.
0 tracebacks.

Next cycle reads the `verdict_salvaged` tape: every fire is a decision the
platform would previously have thrown away, so the count is a direct measure
of what the truncation was costing.

**Session ship count: 18 PRs.**

---

## Cycle 4 — 02:5xZ (anchor 02:59:50): **the day's +$4.24 is one sizing defect, and the desk's exit was eaten by a truncation**

**PROFIT-OR-LOSS FIRST.** Day 08-17 realized **+$4.24** (pnl_audit ledger,
resid 0.00, 2 flattens). Three closes. Book now flat — 0 open positions.

Both agents agree on the verdict and it is not a good one: **strip one
defect and the fleet made about zero on the day.**

### WHY the +$5.22 FIL win is not an edge

FIL 1322 shorted $857 at 02:18:13Z and covered 6m30s later, **true net
+$4.833** (`signals.pnl` +5.219 omits the $0.386 open fee).

`order_params` came back **`absent`** on that cycle. With no desk-authored
size, sizing fell through to the engine default — `max_bet 522.27 × 0.8208
× leverage 2 = $857.36`, matching the trade to 3dp. Every cycle where the
desk **did** author size on this run:

| cycle | size_frac | notional | confidence |
|---|---|---|---|
| 7 | 0.10 | $104 | 0.68 |
| 11 | 0.05 | $52 | 0.78 |
| 22 | 0.10 | $104 | 0.68 |
| **39** | **absent** | **$857** | **0.66** |

**The run's largest bet — 8.2× anything the desk ever chose — landed on its
second-weakest conviction, purely because the JSON carried no size.** At the
desk's own habitual 0.1 the identical trade nets **+$0.589**. So
**$4.24 of the day's $4.24 is the parse-failure oversize.** Worse: the R10
stop-coherence clamp is gated on `order_params is not None`, so an absent
block bought maximum size **and** disabled the size clamp. Today the most
aggressive sizing path in the engine is the one where the desk authored
nothing.

The desk also chased. Cycle 38 refused this exact trade citing the crowded-
long ratio as *"squeeze risk that could hurt a short position"*; cycle 39,
26 minutes and −0.43% later, cited the same ratio as *"squeeze risk for
longs"* and shorted. Nothing changed but price.

### WHY the AVAX loss happened — the desk asked to exit and was silenced

AVAX 1335, true net **−$0.141**. Notional $199, gross move **+0.0189%**,
round-trip fee $0.179 — **fees were 475% of gross.** It needed 0.090% and
caught 0.019%; fee-dominated from the first second.

**Cycle 16 (02:16:03Z) authored a partial reduce and it was thrown away.**
The `no_verdict` diagnostic shipped as #459 last cycle caught it exactly:

```
{"kind": "truncated", "chars": 1052,
 "tail": "…the invalidation level.\", \"basis\": {\"verdict\": \"adjusted\",
  \"discussion\": \"partial reduction secures gains and respects the planned
  invalidation trigger\"}}, \"plan_adherence\":"}
```

The light prompt orders its keys **action → confidence → scores →
stop/target → order_intent → outlook → plan_adherence → report**. The cut
landed at `plan_adherence`, so **the entire traded decision — `order_intent`
with the reduce included — was already on the wire.** The platform discarded
all of it and journaled `hold, confidence 0.0`. 7m36s later a rail flattened
the book at a worse price.

**Shipped as [#462] this cycle**: salvage the verdict from the last complete
top-level pair; refuse anything missing `action` or `confidence`; journal a
`verdict_salvaged` event. It only ever runs where the alternative is no
verdict at all, so it can convert a discarded decision into an executed one
and never degrade one the parser already accepted.

This also settles the 5.4× no-verdict regression I measured at cycle 1 — but
only partly, and I will not overstate it: of 3 diagnostic fires, **1 was
`truncated` and 2 were `empty` (chars 0)**. The token budget explains a
third of the observed cases at most. The `empty` class is still unexplained.

### The two agents disagreed twice; both resolved against Agent A

1. **A flagged an unreconcilable $0.45 ledger gap** and honourably refused to
   invent a reason. B resolved it: A omitted the TRUMP 1344 close from
   earlier today. `+4.83296 − 0.14144 − 0.45108 = 4.24044` against a ledger
   of 4.24. I verified the arithmetic myself. **A's caution was right; its
   conclusion was wrong.**
2. **A called FIL's exit "the classic trailing lock", B agreed** — and both
   noted it is a *different* rail from AVAX's breakeven ratchet despite the
   identical `reason: "trailing_lock"` string. Any analysis treating the two
   closes as the same rail is wrong. Worth knowing for every future cycle:
   **the discriminator is the presence of a `stop_mechanism` event.**

### #449's first live fire — the rail lost money, and should never have armed

The fee-aware ratchet floor fired for the first time (standing watch, unfired
for days): `{"peak":0.4228,"total":0.11828,"arm":0.398,"exit_fee":0.199}` →
realized **−$0.141**.

B's decomposition, which I have verified against the code: `peak_pnl` and
`current_pnl` are `pnl["total"]` — **run-cumulative**, realized plus
unrealized — while `arm_usd` and `exit_fee_usd` are **position-scoped**. The
units do not match. The position's own gross peak was **$0.342**, below the
$0.398 arm: **baseline-corrected, this rail would never have armed.** It
armed on $0.081 banked by four earlier trades.

I confirmed the asymmetry in the source: `_trailing_lock_hit(peak_pnl,
current_pnl, trail, baseline_pnl=0.0, exit_fee_usd=0.0)` takes a baseline;
`_breakeven_floor_hit(peak_pnl, current_pnl, arm_usd, exit_fee_usd=0.0)`
does not. #450 fixed one and left the other.

### ISSUE — three defects are currently cancelling, so I did NOT ship the rail fix

B's finding, and it is the reason the ratchet fix is not in this cycle's PR.
Priced at live marks, the 2.22×-inflated `BREAKEVEN_FEE_RATE` was worth
**+$0.83 on AVAX and +$4.33 on FIL**. Correcting the rate alone turns a
+$4.24 day into roughly **−$0.46**. And the floor computes **one leg at the
inflated rate** ($0.199) where it should be a **round trip at the true rate**
($0.179) — within 11% by accident. **Setting the rate to 0.00045 without
also doubling the floor puts every fire at −1 exit fee**, which is the
failure the fee-awareness was written to prevent.

That is not an argument the rate is right. It is an argument that these must
move together, gated on the fleet-wide replay already in the backlog. **I am
not shipping a rail change that arithmetic says would have cost money today.**

### Also on tape

- **Stale-mark resolution.** `HYPERLIQUID_SYMBOL_CACHE_TTL_SECONDS = 300`
  under a ~64s equity poll: AVAX's unrealized moved in five discrete steps of
  ≈$0.10 — **half the $0.199 floor** — so the rail fired $0.081 below the
  level it was defending while `mark_age_ok` read True throughout. The
  effective resolution of every exit rail is 5 minutes, not 64 seconds. The
  timestamp-vs-value staleness gap is already documented at
  `run_engine.py:3243` and still unfixed on the exit path.
- **FIL's lock fired on the exact tick that set the peak.** Threshold
  (lock + modelled exit fee) sat **$0.011 above** the peak, so the first tick
  that armed it also satisfied it. General condition: fires immediately
  whenever excursion < ~0.667% of notional.
- **Corrected loss floor (#460) has altered no brief yet** — 13 decisions
  since deploy, 0 containing "House floor", 0 equity reads below −$0.99. Zero
  occurrences is not evidence it works; it is evidence it is untested. The
  behavioural difference only shows in the −$0.99 to −$13.07 band.
- Other rails: idle_retire ×5, at_time ×1, all on flat runs; dust clamp 0,
  max_loss 0, adapt-retire 0. Both flattens replaced their slots within ~60s.

### Plan 26

- **FIL c39 opened an $857 market short while its own `outlook.entry.kind`
  was `"none"` with `trigger: null`** — the published plan declared no entry
  at the instant of the run's largest position. AVAX c14 shows the desk can
  express a market entry, so this is an inconsistency, not a schema limit.
- **`stop_ref_px` is null on both opens** while both reports quote explicit
  stop levels. The actionable field is empty; the number lives only in prose.
- **`plan_adherence` is fabricated when the desk is silent.** All four
  confidence-0.0 cycles on 1335 carry `"revised"` — a stamp emitted by the
  fallback, not by any desk. Any adherence metric over those cycles measures
  the fallback. (#462 removes one source of this by recovering the real
  stamp where it exists.)
- **`decision.action` still does not report the executed verb** — five
  AI-authored partial exits across both runs stamp `hold` while
  `order_intent` compiled to a cover that executed.

### Recommendations (ranked by profit impact)

1. **`order_params: absent` must not be the most aggressive path in the
   engine.** Clamp to the desk's own median authored size, or refuse the
   trade. Today it buys max size and bypasses the R10 clamp. Worth $4.24 of
   $4.24 today — in our favour by luck.
2. **[SHIPPED #462]** salvage the truncated verdict.
3. **`_breakeven_floor_hit` needs `baseline_pnl`**, mirroring
   `_trailing_lock_hit`. Gated on the replay, with (4).
4. **Floor must be a round trip (×2) BEFORE the rate is corrected to
   0.00045.** Never the rate alone.
5. **Cap `exit_fee` in `_trailing_lock_hit`** at a fraction of
   `giveback × excursion`, or the lock is pre-tripped at the peak for any
   excursion under ~0.667% of notional.
6. **Gate exit rails on value-staleness, not timestamp-staleness.**

## Cycle 3 — 01:4xZ (anchor 01:41:43): **the budget-proportional loss floor has NEVER executed in production**

**PROFIT-OR-LOSS FIRST.** Day 08-17 realized **−$0.54** (pnl_audit ledger,
resid 0.00, 0 flattens) on **one** closed trade. Book: 1 open position
(AVAX short, run 1335, −$0.32 unrealized), 20 running runs, 10 in fleet 35.

### FAILED — a fix that shipped four days ago is a dead code path on every run

Run 1344 (TRUMPUSDT, fleet 35) closed at **13% of its 11.5h horizon**,
realized **−$0.6251** true net (`signals.pnl` −0.4511 omits the open fee).
**55.7% of the loss was fees** on a 7.2 bps adverse move. The desk's own
report gives the reason verbatim:

> "…breached the house loss floor ($-1.25 > $-0.99) and the net loss exceeds
> its round-trip cost, triggering the mandatory exit rule."

`_loss_floor_usd()` reads the run budget off the **run row** — but
`run_budget_usd` is **not a column on `trading_runs`**. It lives in
`config_snapshot_json`, reached through `cfg`; every other read site in the
file uses `cfg["run_budget_usd"]`. The budget was always 0, so the floor was
always `max(0.99, 0)`. **I verified this live on prod, independently of both
subagents:**

```
running runs: 20   LOSS_FLOOR_FRAC = 0.006
1323 actual=0.99  budget=2179.02  intended=13.0741
1344 actual=0.99  budget=1719.15  intended=10.3149
1333 actual=0.99  budget= 400.00  intended= 2.4000
MISJUDGED: 20 / 20
```

On run 1344's $387 book, $0.99 is **0.26% of notional** against an ordinary
TRUMPUSDT day of **1.10%** — 23% of one ordinary day. The round-trip fee
($0.348) is 35% of the floor; **the entry fee alone put the run 18% of the
way to its own close-me trigger before price moved.** This is verbatim the
failure the function's own docstring claims was fixed on 2026-08-13.

**Shipped as [#460] this cycle** (fail-before red ×2, behavioural brief test,
3 mutants killed, ruff clean, 4,411 passed + 1,346 subtests).

### The two agents disagreed on authorship — the disagreement is the finding

Agent A: *"AI-DECIDED. No rail fired."* Agent B: *"algorithm-authored,
desk-executed."* **Both halves are true and neither excuses the other:**

- **B is right about the premise.** B reproduced `_loss_verdict_line()` on
  prod and got the text the desk paraphrased **byte-for-byte**. B's evidence
  is the stronger method — an event census plus a *positive control* (run
  1308 emitted `stop_event:at_time` in the same window, so the rail channel
  was demonstrably live and its silence is real).
- **A is right about the verb, and found the part that is not the platform's
  fault.** The same brief carried `young_exit`: *"the move against you
  (−0.28%) is INSIDE this symbol's ordinary daily range (~1.10%) — noise-
  sized… If you still exit, your report MUST state why a FULL close beats a
  HALF reduce; and if your component scores disagree with your stated
  confidence, trust the scores."* The desk's report says **nothing** about a
  half reduce, and it trusted confidence 0.78 over conviction 0.5385
  (risk_context 0.39). It also ignored the floor rule's own escape hatch
  (*"unless you can name the condition that reverses it"*) after naming those
  conditions in the same paragraph.

**Verdict: the platform authored a false premise at 10× the intended scale;
the desk authored the verb while violating two explicit instructions in the
same prompt.** The platform half ships today. The desk half is a skills
question, logged below.

### The exit was profit-correct — and that must not launder the mechanism

At the live mark (TRUMPUSDT 1.4075) holding would have cost **$2.63 more**.
Both agents priced it at the live mark only, and **neither treated it as
vindication** — correct. It fired on a threshold 10× too tight and happened
to land right. Not repeatable; the same defect was live on 19 other runs.

### WORKED — #459's diagnostic fired and already refutes the token hypothesis

First `no_verdict` row, 01:51:23Z run 1335: **`{"kind": "empty", "chars": 0}`**.
Not truncated, not malformed — the decision call returned **nothing at all**.
That is a second, independent refutation of the token-budget theory (the
first was code: `max_tokens += 180` already guards the outlook). n=1; I will
not act on it. Note the diagnostic conflates "call raised" with "returned
empty" — worth splitting if `empty` dominates.

Deploy timing note: the worker restarted **01:37:44Z** (RestartCount 0). The
two conf-0.0 decisions at 01:26:16Z and 01:37:14Z predate it, which is the
whole reason `no_verdict` read 0 at first look. Not a defect — no qualifying
cycle had run yet.

### Plan 26 — two defects on this run

1. **Cycle 4 published `decision.action: "hold"` on the cycle that COVERED
   the book.** `order_discussion` proposed buy (0.48) → decision hold (0.78)
   → executed cover. Three verbs, one cycle. Anyone reading `decision.action`
   sees a hold. Only the `outlook` (bias flat) tells the truth. This is the
   same class as the intent-vs-execution defect already logged from the
   owner's panel screenshot.
2. **A light cycle with no LLM verdict still stamped `plan_adherence:
   "revised"`** (cycle 3: confidence 0.0, `conviction_missing: true`, no
   outlook). An un-authored cycle is being counted as a revision, which
   silently inflates the deviation statistics the flag will be judged on.

### Recommendations (ranked by profit impact)

1. **[SHIPPED #460]** loss floor reads the budget from `cfg`.
2. **Re-gate the floor at order-emit, not brief-build.** A's timing table:
   at brief-build (00:48:30) the run was −$1.2539 (past the floor); at the
   fill (00:52:38) it was **−$0.4509 — 45% of the floor, not past it**. The
   desk fired on a 4-minute-stale number that had already un-breached.
3. **`BREAKEVEN_FEE_RATE` 0.001 vs the true crypto 0.00045.** B supplies the
   fleet-relevant instance the backlog gate was waiting for: at the true
   rate the breakeven arm is $0.3484 and this run's peak of **+$0.546 cleared
   it 1.57×** — the ratchet **would have armed** and locked a net-positive
   peak. Second independent measurement; the replay is now the only blocker.
4. **`young_exit` and `loss_verdict` must not render un-reconciled.** When the
   adverse move is inside the ordinary day, the floor line should say its own
   threshold is noise-scale for this book.
5. **adapt ladder is magnitude-blind and half-blind.** `if o["win"]` is a pure
   sign test; its input nets only the close fee (saw −$0.4511 vs a true
   −$0.6251, understating by 27.8%). It charged the desk −25% size and
   +0.05 confidence for a loss worth **0.036% of the run budget** — caused by
   a platform bug.
6. **`leg_outcomes` emits `signals.id` labelled `signal_id`.** For this trade
   id 1420 ↔ signal_id 1425; joining `adapt.signal_id: 1420` on
   `signals.signal_id` lands on **run 1329's +$1.064 winner**. A live
   mis-attribution trap for this very two-agent protocol.

### Watches

AUDCHF 1147 **stopped** and fleet 33 **stopped** — both closed, dropping off
the list. Unit-slip converter 3 fires, dust clamp 1 fire, `no_verdict` 1 fire.

### #460 DEPLOYED and verified — 02:31:57Z, image `20260817-loss-floor-cfg` (merge `80460a3`)

Re-ran the exact measurement that found the defect: **20/20 running runs now
floor correctly, 0 mismatches.** Run-1344-class floor is **$10.3149**, and the
brief no longer renders the wound line on run 1344's exact numbers.

Second pass, boundary behaviour (guarding against having simply disabled the
floor):

| run total | wound rendered? |
|---|---|
| −$1.25 | no |
| −$9.99 | no |
| **−$10.32** | **yes** — "past the $-10.31 floor. That is 241% of one ordinary day" |
| −$25.00 | yes — 584% of one ordinary day |

No-budget fallback still fires at $0.99; a $50 budget still keeps the owner's
dollar floor. #459 diagnostic, dust clamp and the Plan 26 flag all survived
the from-main rebuild. 0 tracebacks, RestartCount 0.

**Process defect found in my own chain script:** it ran `scripts/deploy.sh`
from the primary working tree, which sits on `feat/i18n-followups` and has no
`scripts/` directory — the merge landed and the deploy silently did not run.
Prod sat on the old image until I checked the running container rather than
trusting the chain's exit code. Deploys must run from the `wt-recall`
worktree. **A green exit code from a chain is not evidence that the deploy
happened; the running image is.**

**Session ship count: 17 PRs.**

---

## #459 DEPLOYED — 01:1xZ: the no-verdict diagnostic is live and discriminating

PR MERGED (`32a66a8`), image `sooppiy-backend:20260817-no-verdict-diag`.
Verified in the running container — all four failure modes separate
correctly:

| input | classified |
|---|---|
| `None` | **empty** (chars 0) |
| `"I cannot answer"` | **no_json** (15) |
| `{"action": "hold", "sc` | **truncated** (22) |
| `{"a": x}` | **malformed** (8) |

Deploy-rebuild check applied: clamp (1), net-of-fees (2), Plan 26 flag
(on) all survived. 0 tracebacks. Rollback:
`SOOPPIY_IMAGE=sooppiy-backend:20260817-notes-0816-late`.

**What this buys:** from the next no-verdict cycle onward the tape says
WHICH failure occurred. The 5.4× regression stops being an argument and
becomes a count. **Next sweep reads the `no_verdict` kind mix** — that
is the deciding evidence, and I will not propose a fix before it.

**Session ship count: 16 PRs.**

---

## Cycle 2 — 00:4xZ (anchor 00:49:29): quiet on tape; **shipping the diagnostic I recommended last cycle**

12 decisions, 2 no-verdict (17%), no trades, no closes, clamp holds at
1, TRUMP $387 short still open (−$0.11 as price ticked to 1.4009),
0 tracebacks.

**Shipped rather than deferred:** a `no_verdict` telemetry event that
labels WHY a light cycle produced nothing — `empty` | `no_json` |
`truncated` | `malformed` — with the response length and a bounded
200-char tail. Today all four failure modes emit an identical event,
which is exactly why the 5.4× regression is still unexplained; one
field turns it into a decided question within a day of tape.
Diagnostic only: it changes no decision and no order, so it carries no
risk of masking the thing it is measuring. Fail-before red→green
(7 tests), mutants running.

---

## Cycle 1 — 00:1xZ (anchor 00:19:18): **MEASURED REGRESSION — the no-verdict rate rose 5.4× at the Plan 26 flip**

**FAILED (measured, not inferred).** The `conf 0.0 / "light cycle: no
LLM verdict"` rate, before vs after the 09:10Z flag flip:

| period | decisions | no-verdict | rate |
|---|---|---|---|
| BEFORE (08-15 09:00 → 08-16 09:10) | 405 | 8 | **2.0%** |
| AFTER (08-16 09:10 → now) | 240 | 26 | **10.8%** |

**5.4× on 645 decisions** — this is reproduced evidence, not a data
point. A no-verdict cycle fail-safes to HOLD, so each one is a
management look the desk never takes; on 08-16 that pattern preceded
FIL 1305's flatten three times.

**Not an outage:** the LLM endpoint is healthy — 16 × `HTTP 200`, zero
timeouts/refusals/rate-limits in the window.

**My first hypothesis was WRONG and I am recording it as such.** I
suspected the enlarged JSON contract truncating against a fixed token
budget. The deployed code already guards exactly that:
```
max_tokens = 280 if pos_qty else 200
if _outlook_enabled(): max_tokens += 180
```
with a comment reasoning "a cut-off JSON is not a smaller answer, it is
a lost one." So the obvious mechanism is anticipated, and **the cause
is UNEXPLAINED.**

**What the cohort split does show:** the failures concentrate on runs
that have ALREADY TRADED — **15.6% (20/128)** vs **6.2% (7/113)** for
never-traded runs. Held/traded books carry more brief lines (and now
`net_of_fees`, `reduce_geometry`, `standing_plan`), so the prompt is
longest exactly where the failure rate is highest. That is consistent
with a size-related failure that the +180 budget does not fully cover —
but consistent is not proven, and I will not ship on it.

**RECOMMENDATION (diagnostic before fix):** log the raw response length
and the first parse error on every no-verdict cycle. One field turns
this from "unexplained 5.4×" into a decided question — truncation vs
malformed-JSON vs empty response — in a single day of tape. Guessing
between them risks raising a token budget that is not the cause.

Otherwise: 8 decisions, adherence 8/8, `side_contradiction` 0, clamp
holds at 1, slots 9 crypto + 1 forex, TRUMP short $387 open (+$0.17),
0 tracebacks, no closes yet today.

