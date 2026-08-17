# Automation monitoring — 2026-08-17 (UTC day), newest-first

Continued from [2026-08-16](2026-08-16-automation-monitoring.md) (day
closed **+$5.65 realized, resid 0.00**; 15 code/skill PRs + 4 docs
merges shipped). Target: **info@askkpop.com — user 5 / agent 6 /
FLEET 35**; from cycle 39 (owner directive) also
**forevery1969@gmail.com — user 25 / agent 60 / FLEET 36 (us-stock)**.
Open items: `BREAKEVEN_FEE_RATE` (needs fleet-wide replay),
prospective #443 warning, outlook intent-vs-execution defect,
arm-reachability rail.

## Cycle 39 addendum — 23:2xZ (anchor 23:24:06): **#475 SHIPPED to prod, verified 3×**

PR #475 merged (`71ecd1e7`) after full CI (5/5 checks); deployed as image
`sooppiy-backend:20260817-20260817-leaserenew` (deploy.sh prefixes the
date — the tag is double-dated but correct). Rollback:
`20260817-handoff-takeover`. Verified:

1. **Wired in the running worker** — `inspect.getsource` confirms
   `_renew_lease(run_id)` sits before `execute_paper_trade` in the live
   container.
2. **In-image tests 5/5 OK** — the 3 new renewal tests + the two existing
   fence-protection tests (zombie reclaim, stop-mid-cycle). ⚠️ NEW TRAP for
   the runbook: the first in-image run showed 5 setup failures because
   **prod sets `ENTITLEMENTS_ENFORCED=true`** and the fixtures use an
   unlinked agent — run in-image tests with
   `docker exec -e ENTITLEMENTS_ENFORCED=false …`. The failures were the
   fixture, not the fix.
3. **Live health** — events flowing (MAX(ts) 22s behind NOW), 0 tracebacks.

**The binding post-ship metric:** daily `fence: lease expired` count.
Baseline 8/1/3/9 (08-14..17). Expected ~0 from 08-18. If a fenced order
appears WITH the renewal live, the fix is FAILED and the residual mechanism
(a >TTL stall between renewal and the fence's own read) must be chased.

## Cycle 39 — 22:2xZ (anchor 22:27:10, NEW SESSION/ACCOUNT): scope now TWO users; **21 authored orders have been dying at the fence — fix built, in pipeline**

New session (account rotation). Crons re-armed (30-min `0961ff91`, 24h sweep
`06e43308`). Owner directive this session: monitor **two** users —
info@askkpop.com (user 5 / agent 6 / fleet 35) **and forevery1969@gmail.com
(user 25 / agent 60 / FLEET 36 — new: us-stock, 25 slots, $99,996.69,
started 2026-08-16T10:37:41Z; predecessor fleet 34 stopped 08-15)**.

State: prod image `20260817-handoff-takeover` (deployed ~22:17Z by the
prior session, matches origin/main e5d46994). No closes since cycle 38;
both books FLAT. Day 08-17 **+$3.84** (pnl_audit, resid −0.01, 4 flattens;
total since reset +$6.07). 0 tracebacks, 0 no-verdicts in the last 30 min.
Fleet 35 replenished 9 new runs (1387–1396) → 12 running. `_railed_params_line`
test: still 0 clamps since deploy — **still unanswerable**.

### Fleet 36 has NEVER executed a trade — and the reason is only half the desk's caution

151 decisions, 36 order intents since the fleet started. **147 hold, 2 buy,
2 retire.** Every hold intent compiles to `steps: []` — genuine desk
caution through a Monday NYSE session. But **both of the fleet's only two
entry attempts** (run 1324 "T", cycles 56/57, conf 0.73/0.78, parsed
params, compiled steps, $257 sized) were killed at the execute stage by
`gate_skip: "fence: lease expired"`. The fleet the owner just asked to
watch has a 100% entry-kill rate from infrastructure.

### The fence defect — measured, not inferred

**Hypothesis:** cycles whose LLM calls outlast the 300s lease TTL reach the
fenced trade transaction with their own expired lease and forfeit the order.
**Falsifier:** fenced cycles with wall time under 300s, or fences firing on
cycles that authored nothing.

**Result — confirmed:**

- **21 `fence: lease expired` kills, 2026-08-14..17 (8/1/3/9 by day). All 21
  carried real orders: 8 opens, 7 reduces, 1 close, 5 buy/sell cycles with
  no intent journal. ZERO were holds** — the fence only runs when there are
  steps to execute, so every fire is a discarded authored order.
- Run 1370's fenced cycle (18:51:28 → 18:58:45) measured **437s against the
  300s TTL** — mechanism proven on tape. 23 of 664 cycles today (3.5%) had
  event spans ≥300s.
- The module's own header states the invariant: *"Lease TTL exceeds the
  worst-case cycle."* **#468 (LLM timeout 120→300s) broke that arithmetic**
  — a single decision call may now legally consume the entire TTL — but the
  fires predate #468 (8 on 08-14), so slow multi-call cycles alone already
  breached it.
- **Counterfactual P&L, measured on the two reconstructable fenced exits:
  the fence accidentally HELPED both times** — 1370's fenced reduce would
  have covered ~$0.04 worse; 1322's fenced profit-bank ~$0.32 worse (both
  shorts, price kept falling during the delay). That is luck, not design.
  The 8 discarded opens are unknowable. **The fix's direct P&L effect is
  ≈$0 measured; the justification is §7b — the AI is the final author of
  every order, and here the plumbing un-authors ~9 orders/day** — plus
  fleet 36's total entry blackout.

### Fix built (in pipeline): renew our own lease before the trade txn

`_renew_lease(run_id)` — extends `claim_expires_at` only where
`status=running AND claimed_by=us`, called immediately before
`execute_paper_trade`. The fence's real protections are untouched (stop
pressed mid-cycle → status predicate blocks renewal AND the fence; reclaim
by another worker → claimed_by blocks renewal AND the fence). Fail-soft.
Verification so far: fail-before 1/1 (test reproduces the fence kill on an
expired-own-lease cycle), pass-after 267/267 in test_run_engine (incl. the
zombie-reclaim and stop-mid-cycle fences), **mutation 3/3** (no-op renewal,
ownership predicate dropped, status predicate dropped — each kills exactly
its test). Full suite + PR + deploy next; **post-ship metric: daily
`fence: lease expired` count must go to ~0 (baseline 9 on 08-17) — if it
does not, the fix is reported FAILED.**

## Cycle 38 — 21:4xZ (anchor 21:49:21): quiet; **the scheduled test still has not run, and I am not going to call that a result**

No closes. **Book flat.** Day 08-17 **+$3.84** (ledger, resid −0.01, 4
flattens). 5 decisions, **0 no-verdicts**. 9 running runs, fleet 35 at
**10/14** slots.

### Why the cycle was thin, checked rather than assumed

Only 5 decisions in 26 minutes. `gate_skip` in the window: **`market closed`
×10**, `decision is 'hold'` ×7, `loss cooldown` ×1. The fleet is
4 crypto / 2 futures / 2 forex / 1 us-stock, and it is **21:49Z on a Monday**
— equities and most futures are shut. The low count is the calendar, not a
stall.

### The test I scheduled: NOT ANSWERABLE

| | |
|---|---|
| `_railed_params_line` deployed | 21:22:13Z |
| decisions carrying `railed_params` | **0** |
| ceiling fires since deploy | **0** (total still 4) |

**No clamp has fired since the line went live, so the line has never
rendered.** Not passed, not failed. The two runs that produced all four
earlier fires are gone — 1375 was `idle_retired` at $0.00, 1370 closed.

I am recording this as *unanswerable* rather than letting it drift into
"deployed, presumably fine". The before-baseline (run 1375: 3.02% requested
three times in 95 minutes) is on tape and does not expire; the test simply
waits for the next clamp.

### Standing rails — unchanged, and two still not working

| rail | fires | honest status |
|---|---|---|
| R:R ceiling | 4 | **P&L effect $0.00** — every fire on `action=hold`, which compiles to `steps: []` |
| corrected loss floor | **0** all day | present and correct by replay; **unexercised** |
| arm classify | label only | nothing consumes it |
| `_railed_params_line` | 0 renders | **test pending** |
| breakeven ratchet | 3 | **−$0.252934, zero net gains** |

### Recommendation

Nothing to ship. The next clamp answers the open test, and the ratchet fix —
**defect (a) alone**, per the run-1335 recomputation that reversed my earlier
spec — is the one queued change with a proven dollar figure attached
(+$0.1414 on the single fire that lost real money).

## Cycle 37 — 21:2xZ (anchor 21:23:31): **AVAX 1370 closed −$0.305, and Agent B refuted my own R:R ceiling report**

**PROFIT-OR-LOSS FIRST.** AVAX run 1370 closed 20:24:05Z at **−$0.30509322**
true net (reconciles to `realized_pnl_usd` exactly). Day 08-17 now **+$3.84**
(ledger, resid −0.01, 4 flattens). Book flat.

Gross adverse price move is **86.03% of the loss**; fees are 13.97%. **This
was a directional loss, not a friction loss** — the fee-hurdle story that fits
so many trades today does not fit this one, and I am not going to force it.

### FAILED — my cycle-33 "the ceiling WORKED" was wrong

I reported the R:R ceiling's first fires as *"the mechanism doing precisely
what it was built to do, on live tape"* (cycle 33), then narrowed it to
*"entry-only"* (cycle 34). **Agent B went further and is correct.**

All four ceiling fires landed on **`action = hold`**, and I verified the
consequence in source:

```
order_intent.compile_intent:  if kind in ("hold", "arm"): return {"steps": [], "note": kind}
```

**A hold compiles to no order. The re-priced target is parsed, journalled,
and discarded.** Not one fire has shaped an entry, an exit, or a live
bracket.

| run | ts | clamp | action | effect |
|---|---|---|---|---|
| 1375 | 17:56:00 | 3.02 → 1.41 | hold | none |
| 1375 | 18:27:45 | 3.02 → 1.425 | hold | none |
| 1370 | 18:58:45 | 4.1 → 2.4 | hold | none |
| 1375 | 19:30:06 | 3.02 → 1.44 | hold | none |

**P&L effect of the R:R ceiling to date: exactly $0.00.** It is telemetry,
not a rail. "Entry-only" was still too generous — it has not reached an entry
either, because no fire has yet landed on a buy or sell cycle.

### And my cycle-13 fix specification is inverted by the numbers

I specified: *"do not fix defect (a) alone — the floor must move to a full
round trip in the same change."* Agent B recomputed run 1335 from `signals`
and I verified it independently:

```
pos-2 own peak = run-cum peak 0.422800 − banked 0.170175 = 0.252625
(a) fixed alone : 0.2526 < arm 0.3980  ->  NO ARM   (saves −$0.141443)
(a)+(b) fixed   : 0.2526 > arm 0.1791  ->  ARMS     (the loss stands)
```

**On the one fire where the ratchet lost real money, fixing (a) ALONE
prevents it and fixing (a)+(b) does not.**

Both statements can hold because they concern different halves: **(a) governs
whether it ARMS**, and the floor governs **what happens once armed**. Fixing
(a) alone gives fewer bad arms and a worse floor. My spec collapsed the two.
**Revised: fix (a) first, independently, and measure — the arming defect is
the one with a proven −$0.141 attached.**

### The trade itself — the desk's target was never reachable

Agent A's finding, which I accept: the planner said `expected_move_pct 2.5`
and the algo candidate proposed 6.1354; **the desk overrode both and set
3.6% → 6.06838, 44% beyond its own planner.** It never moved that target
across 15 cycles while the horizon decayed 8h → 1h. At cycle 13 it stamped
its **highest conviction of the run (0.78, `plan_adherence: followed`)** on a
plan needing **4% in under 2 hours** in an asset whose entire 7-hour range
was **0.94%**.

**The book was adverse on 356 of 369 samples (96.5%) and was never net-
profitable at a single sample.**

The arm at 6.25 was **correctly sided** (below breakeven 6.28934) and
**structurally unreachable** — 0.653% below the run's own best mark, in a
tape with a 0.94% total range, and never re-priced in 12 cycles where it
appeared in the brief. **A different failure from SOL 1367's losing-side arm:
right side, wrong place.**

### Where the agents agreed, and B's correction to me

Both: **the close was desk-authored** (`run:1370:cyc:15`), and
`stop_event:at_time` stamped a run that had been flat for **57 minutes**.
Zero rail contribution to the loss.

**B corrected my brief:** worst mark was **6.35020 (65.0% to stop)**, not the
6.3443/58% I supplied. The tick high was 6.35590 (66.9%).

**B also refused an easy defect:** the ratchet's non-arming was **correct
under every parameterisation**, including both defects fixed — the corrected
arm sits at 6.28934 and the true tick low was 6.28950, missing by 0.0026% of
price. B tested against real ticks rather than 5-minute marks before saying
so. Ratchet record unchanged: **3 fires, −$0.252934, zero net gains.**

### The scheduled test did not run

Cycle 36's brief line deployed at **21:22:13Z**. Run 1375's last parameter
cycle was **19:30**, and it has since been `idle_retired` at $0.00. **No
post-deploy cycle has rendered the line.** `railed_params` appears in **0**
brief arrays. The test is not answerable yet — not passed, not failed.

### Recommendations

1. **Stop describing the ceiling as working.** Until a fire lands on a
   buy/sell cycle its P&L effect is $0.00. Reported as such.
2. **Fix ratchet defect (a) alone, first** — reversing my cycle-13 spec, on
   the strength of the 1335 recomputation.
3. **`plan_adherence` measures obedience, not viability** (Agent A). A
   "followed" stamp certified a 4%-in-2h plan. It needs a reachability test
   or it will keep rubber-stamping dead plans.
4. The `fence: lease expired` that killed cycle 12's `reduce` was **+$0.020
   favourable here** — a real process defect that cost nothing on this tape,
   and I will not inflate it.

## Cycle 36 — 20:1xZ (anchor 20:19:35): **built the line that breaks the rails' silence — with the before-measurement already on tape**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.3045**. Day
08-17 **+$4.13**. 12 decisions, 1 no-verdict. Ceiling holds at 4 fires.

### The deferral ends because the cost became measurable

I put this off twice on the grounds it "needs its own measurement". Cycle 35
supplied one: run 1375 requested **`target_pct` 3.02% three times in 95
minutes** while its stop drifted 0.47 → 0.475 → 0.48. Clamped every time.
Request never moved. The clamped values it actually received were
**1.41, 1.425, 1.44** — and it went on asking for 3.02.

`order_params` notes are journalled and never reach the prompt. **The desk
was corrected and never told.**

### `_railed_params_line` — names the rule, not just the number

> *"A rail changed your last bracket: target_pct 3.02 pulled to R:R ceiling
> 1.41 (3x stop 0.47) — unreachable targets never fill. Propose your next
> bracket within that rule rather than re-sending the value it cut — the rail
> will cut it again."*

The design decision worth stating: **a desk shown "1.41" learns one value; a
desk shown "3× your stop" can derive the next one itself.** One of the four
tests exists solely to pin that — it fails if the line degrades to numbers
alone, and the mutant that stripped the rule was killed by it.

Wired into the brief parts list, so it renders on **flat books too** — which
matters, because run 1375 has no position and is exactly the run that needed
telling.

### Verification

* Fail-before red on all 5 tests; green after.
* **3 mutants, 3 killed** — unwired from the brief; renders when nothing was
  railed; rule stripped to bare numbers.
* 320 tests in the two affected files pass; ruff clean; full suite running.

### The after-measurement is already specified and its baseline exists

**Before:** run 1375, three cycles, identical 3.02% request, no notification.
**Test:** once this deploys, does its requested `target_pct` change?

That is a clean before/after on live tape with no new instrumentation. **If
the request stays at 3.02%, the line failed and I will report it as such** —
the same standard that removed #468 from the fixed column.

### Standing rails — one no longer silent

| rail | fires | tells the desk? |
|---|---|---|
| R:R ceiling | 4 | **yes, once this deploys** |
| arm classify | label only | **no — still silent** |
| corrected loss floor | 0 | unexercised |
| breakeven ratchet | 3 | −$0.25293, 0 net gains |

`classify_arm`'s label is still unconsumed. The mechanism to surface it now
exists and reuses this line's shape; that is the next candidate.

### Recommendations

1. **Deploy and watch run 1375's next requested target.** One number decides
   whether this worked.
2. **`RR_CEILING=2.0`** still stands — the 3× default lands above H7's p75.
3. AVAX 1370 remains the only open book.

## Cycle 35 — 19:4xZ (anchor 19:49:31): **the ceiling corrects the desk silently, and the desk has now asked for the same impossible target three times**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.3697**,
oscillating (−$0.3577 → −$0.1830 → −$0.3697) and now **58% of the way to its
stop**; a stop-out costs ≈**−$0.637**. Day 08-17 **+$4.13**. 26 decisions,
**0 no-verdicts**.

### ISSUE — a rail that corrects without informing

Four ceiling fires now, on two runs:

| ts | run | requested | clamped to |
|---|---|---|---|
| 17:56:00Z | 1375 | **3.02%** | 1.41 (3× stop 0.47) |
| 18:27:45Z | 1375 | **3.02%** | 1.425 (3× stop 0.475) |
| 18:58:45Z | 1370 | 4.1% | 2.4 (3× stop 0.8) |
| 19:30:06Z | 1375 | **3.02%** | 1.44 (3× stop 0.48) |

**Run 1375 has asked for exactly 3.02% three times in a row.** The clamp
fires, journals its note, and the desk asks for the identical unreachable
number on the next cycle. Its stop drifts (0.47 → 0.475 → 0.48) while the
target stays frozen — so the desk is not deriving the target from the stop at
all; it is repeating a fixed figure.

Confirmed in code: `order_params` notes **never reach the prompt**, and there
is **no brief line** for a clamped parameter. The desk is corrected and never
told.

**This is the same defect class as the arm label** — cycle 27 shipped
`classify_arm` and noted "nothing consumes the label yet". Now there are two
rails that know something the desk does not:

* the arm's protective/defensive class, and
* that its target was cut roughly in half.

A rail that silently corrects a repeated mistake converts a *learnable* error
into a *permanent* one. The desk will ask for 3.02% forever.

### What this changes about my own recommendation

I deferred the brief line twice — cycle 27 ("needs its own measurement"),
cycle 32 ("next code cycle"). **The deferral is now costing something
measurable: three identical wrong requests on one run in 95 minutes.** That
is not an argument that the brief line *works*; it is an argument that its
absence has an observable price, which is a different and better reason to
build it than the one I had.

The measurement it still needs is unchanged: whether telling the desk changes
what it asks for next cycle. **Run 1375 is now a ready-made before/after** —
three pre-notification cycles on record, all identical.

### Standing rails

| rail | fires | verdict |
|---|---|---|
| R:R ceiling | **4** | exercised, entry-only, **silent** |
| corrected loss floor | **0** all day | unexercised |
| arm classify | label only | **silent** |
| breakeven ratchet | 3 today | −$0.25293, 0 net gains |

### Recommendations

1. **Build the clamp/label brief line next.** Both rails are silent; one
   change can surface both, and run 1375 supplies the baseline.
2. **`RR_CEILING=2.0`** — at 1370's 0.8% stop the 3× default still lands
   above H7's p75.
3. **AVAX 1370 at 58% to stop** remains the only open book.

## Cycle 34 — 19:1xZ (anchor 19:19:31): **the ceiling fired on the LIVE book and changed nothing — it is an entry-only rail**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short recovered to
**−$0.1830** (from −$0.3577). Day 08-17 **+$4.13**. 24 decisions, 1
no-verdict.

### FAILED — a scope limit on my own change, found by following it

The ceiling now has **3 fires**, and the third landed on the open book:

| fire | run | note |
|---|---|---|
| 17:56:00Z | 1375 | `target_pct 3.02 pulled to 1.41 (3x stop 0.47)` |
| 18:27:45Z | 1375 | `target_pct 3.02 pulled to 1.425 (3x stop 0.475)` |
| **18:58:45Z** | **1370 (live short)** | `target_pct 4.1 pulled to 2.4 (3x stop 0.8)` |

**And AVAX 1370's actual take-profit is unchanged at 6.06838 (−3.60%),** the
value written at entry six hours ago.

Verified in code: `take_profit` is passed once at `open_position` and
**there is no path that revises it on a live book**. The R:R ceiling clamps
*parsed params*; parsed params reach a position only at entry.

**So the ceiling is an ENTRY-time rail, not a management rail.** On the one
fire against a live position — the very book that prompted the whole target
investigation — **it changed nothing.** Its value is confined to positions
opened after it shipped.

I described this yesterday as moving "a live watcher level into the range the
market actually trades" (cycle 24). **That is true only for new entries**,
and I did not say so at the time.

### Correcting cycle 24 as well: a second cause of the 0-in-210

Cycle 24 concluded the take-profit had never fired in 210 stopped runs
because the level was **unreachable**. There is a second mechanism I missed:

```
risk_engine.py:656
UPDATE positions SET stop_loss = ?, take_profit = NULL WHERE id = ?
```

**When the trailing stop engages, it DELETES the take-profit.** A position
that trails loses its profit target outright.

Scope of the correction, measured: **11 of 210 stopped runs** ended
`stop_event:trailing_lock`, so at most ~5% had their TP nulled this way.
**Unreachability remains the dominant cause** and cycle 24's conclusion
survives — but it was not the only one, and the second is a deliberate
`NULL` rather than a level the market never reached.

### The default is too generous against what the market offers

Even the clamped value is thin. At 1370's 0.8% stop the 3× ceiling gives
**2.4%**, and H7 measured available excursion at median **1.14%**, p75
**1.89%**. **2.4% is still above p75.**

`RR_CEILING=2.0` would give **1.6%** on that stop — inside the band. That is
the config change already documented; today's fires are the first live
argument for it rather than a replay argument.

### Standing rails

| rail | fires | verdict |
|---|---|---|
| R:R ceiling | 3 | behaves as specified, **entry-only**, no P&L yet |
| corrected loss floor | **0** all day | unexercised |
| arm classify | label only | nothing consumes it |
| breakeven ratchet | 3 | −$0.25293, 0 net gains |

Run 1375 (VZ, us-stock) carries the first two clamps and has **0 trades in 10
cycles** — the clamped target is still untested by a fill.

### Recommendations

1. **Say "entry-only" wherever the ceiling is described.** It cannot help an
   open book.
2. **`RR_CEILING=2.0`** now has a live argument, not just a replay one.
3. **The trailing stop nulling take-profit deserves its own look** — it is
   deliberate, but nothing tells the desk its target has been deleted.

## Cycle 33 — 18:4xZ (anchor 18:49:29): **the R:R ceiling fired — twice, on real tape, exactly as specified**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.3577**. Day
08-17 **+$4.13** realized, resid −0.00, 4 flattens. 21 decisions, 1
no-verdict.

### WORKED — first live exercise of a rail I refused to call working

Last cycle I wrote that neither the ceiling nor the loss floor could be
described as working until each had a live fire. **The ceiling has two.**

| fire | run | desk asked | pulled to | rule |
|---|---|---|---|---|
| 17:56:00Z | 1375 cyc 8 | **target 3.02%** at stop 0.47% (R:R 6.43) | **1.41%** | 3× stop |
| 18:27:45Z | 1375 | target > ceiling at stop 0.475% | **1.425%** | 3× stop |

The journalled note, verbatim:

> `target_pct 3.02 pulled to R:R ceiling 1.41 (3x stop 0.47) — unreachable
> targets never fill`

**Measured against the evidence that justified it:**

* **H6** — no target above **2.00%** has ever been reached, even given a
  run's own full horizon. **3.02% sat in the dead zone.**
* **H7** — available excursion inside a run's horizon is median **1.14%**,
  p75 **1.89%**. **1.41% is inside the reachable band.**

So the rail moved a target from a region the market has never once delivered
into one it delivers about half the time. **That is the mechanism doing
precisely what it was built to do, on live tape, within an hour of deploy.**

### What this is NOT evidence of, stated before it gets quoted

**A reachable target is not a profitable one.** No trade has closed on either
of these yet. n=2 fires, 0 closes.

And there is a tension I am not going to bury: **run 1375's stop is 0.47%,
which sits in exactly the band H8 measured as WORST** — at a 0.50% stop, 17
of 30 legs stop out and expectancy was **−0.11**. The ceiling did not set
that stop; the desk did. Pulling 3.02% → 1.41% should still help this pair
(per H6 a 3.02% target wins ~never, so the change trades ~0 wins for some
wins against the same stop count) — but that is **inference from H8's grid,
not a measurement of this run.**

**The stop itself is the larger problem here, and the ceiling does not touch
it.** H8 said tighter stops are strictly worse; a desk choosing 0.47% is
choosing the worst band in that table.

### Standing rails status

| rail | live fires | verdict |
|---|---|---|
| R:R ceiling (#471) | **2** | **exercised** — behaves as specified; P&L unmeasured |
| corrected loss floor (#460) | **0** all day | still unexercised, still not "working" |
| arm classify (#472) | label only, nothing consumes it | deployed, inert by design |
| breakeven ratchet (#449) | 3 | **−$0.25293, 0 net gains** — unchanged |

### Recommendations

1. **Follow run 1375 to close.** It is the first trade carrying a
   ceiling-clamped target and the cleanest available test of whether
   reachable targets convert.
2. **The 0.47% stop deserves its own look** — H8 puts that band at negative
   expectancy, and the ceiling cannot correct a stop.
3. AVAX 1370 remains the other open book at −$0.3577 with a correctly-sited
   protective arm.

## Cycle 32 — 18:1xZ (anchor 18:19:29): **#472 merged; AVAX 1370 deteriorating — and its arm is CORRECT, which matters**

**PROFIT-OR-LOSS FIRST.** No closes. **AVAX run 1370 short −$0.3502**, up
from −$0.2107 thirty minutes ago. Day 08-17 **+$4.13** realized. 23
decisions, **0 no-verdicts**.

### The open book is now the story

| | |
|---|---|
| entry / mark / stop | 6.2950 / **6.3417** / 6.37998 |
| travelled toward stop | **55%** (was 26% at 15:49Z) |
| unrealized | **−$0.3502** |
| loss if stopped | **≈ −$0.637** |
| take-profit | 6.06838 (−3.60%, in the never-reached band per H6) |

**But its arm is on the right side**, and that is worth stating because I
have spent two cycles criticising arms:

```
entry 6.2950   breakeven (round trip) 6.28933
arm   price_below 6.2500 -> reduce     =>  PROTECTIVE
```

6.25 sits **below** breakeven, so firing it banks money. **The desk placed a
correct protective arm on this position.** The market simply went the other
way — the arm now needs a 1.45% fall from the current mark to trigger.

**Not every loss is a defect.** SOL 1367 lost because its only arm was
guaranteed to lose; AVAX 1370 is losing with a properly-sited arm and a stop
it has not reached. Those are different failures and I am not going to blame
the same cause twice.

Two blemishes remain on it: the arm's `why` is **empty** (the 133/134
pattern), and **2 of its 10 cycles were conf-0.0** — 20%, against the 9.25%
held-book average from H9.

### WORKED — [#472] merged and deploying

All five checks green. Merged `ef2a66cd`, deploying as `arm-classify`. The
protective/defensive classifier and the implausible-level rail are now in
main. **Nothing consumes the label yet** — that remains a separate change
with its own measurement, as stated when it was built.

### The R:R ceiling has not fired

**0 fires in the ~20 minutes since deploy.** Expected: it binds only above
R:R 3.0, and it shipped inert against every existing case by design. **This
is not evidence it works** — it is evidence it has not been exercised, the
same status #460 has carried all day. It goes on the watch list under the
same rule: no claim of validation until a live parse is actually pulled.

### State

| item | state |
|---|---|
| #471 R:R ceiling | merged, deployed, **unexercised** |
| #472 arm classify | **merged, deploying** |
| AVAX 1370 | **55% to stop**, protective arm, empty why |
| dependency "red on main" | retracted (CI passes) |
| gitleaks on #471 | proved an outage artifact |

### Recommendations

1. **Watch AVAX 1370 to resolution** — it is the only open book and the only
   live test of whether a correctly-armed losing position exits better than
   the mis-armed ones did.
2. **Wire the arm label into the brief** — the measurement that turns 43%
   into behaviour. Next code cycle.
3. Neither ceiling nor loss-floor may be described as working until each has
   a live fire.

## Cycle 31 — 17:4xZ (anchor 17:49:33): **the gitleaks failure WAS an outage artifact — proved it, merged #471, and made a process mistake worth recording**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.2107**. Day
08-17 **+$4.13** realized. 22 decisions, **0 no-verdicts**.

### AVAX 1370's own cycle tape — both fixes visible on one live losing book

| time | conf | report |
|---|---|---|
| 16:21:23 | **0.57** | *"recovered from a truncated verdict — the desk's reasoning was cut off, the decision was not"* |
| 16:50:57 | **0.0** | `light cycle: no LLM verdict` |
| 17:22:36 | 0.58 | *"Holding the short position aligns with the standing plan; no action taken beyond existing arm."* |

**#462 earned its keep on a live held position**: 16:21 would have been a
discarded cycle before it. 16:50 is the one that still gets lost — the H9/H10
held-book penalty, on the only open book.

### Proved the hypothesis instead of leaving it as one

Cycle 30 said the #471 gitleaks failure was *"most likely an outage
artifact"* and named the test: re-run it once writes recover. Writes came
back mid-cycle, so I re-ran the **failed job on the identical SHA**:

```
Secret scan (gitleaks) -> completed/success
```

**Same commit, same config, opposite result.** The failure was the action
posting through the API at 15:06Z, mid-outage — not a leak. Hypothesis
confirmed by the test that was specified for it, not by argument.

### #471 MERGED and deploying

All five checks green on the identical SHA — pytest, frontend, npm audit,
**Python dependency audit**, gitleaks. Both reasons I held it for two cycles
are now gone:

* the dependency finding was **retracted** last cycle (CI passes; my local
  run could not be reconciled),
* the gitleaks failure is **proved** an outage artifact.

Merged as `05333d3b`, deploying as `rr-ceiling`. The R:R ceiling ships
**inert** (default 3.0); `RR_CEILING=2.0` takes H8's measured optimum as a
config change.

### ISSUE — I probed a write API with a real write

To test whether writes had recovered I ran `gh api -X POST .../pulls` with a
placeholder title. It succeeded, and **created a real PR #472 titled
"probe" with no body.** I repurposed it immediately as the proper `c27` PR
rather than leaving a junk artifact, but the mistake stands: **a probe of a
mutating endpoint is a mutation.** A read (`gh api repos/...`) had already
told me reads worked; the write test should have been the actual intended
write, or nothing.

`c27` is now [#472] with its real title and body.

### State

| item | state |
|---|---|
| #471 R:R ceiling | **merged, deploying** |
| #472 arm protective/defensive (`c27`) | open, awaiting CI |
| dependency "red on main" | **retracted** — CI passes |
| gitleaks on #471 | **outage artifact, proved** |
| AVAX 1370 | only open book, −$0.2107, 26%→ toward stop |

## Cycle 30 — 17:1xZ (anchor 17:19:33): **CI came back and refuted TWO of my outage-period conclusions, in opposite directions**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.2145** — the
deepest yet (−$0.022 → −$0.139 → −$0.167 → −$0.103 → **−$0.2145**). Day 08-17
**+$4.13** realized. 22 decisions, 1 no-verdict.

### The outage is NOT over, and the status page is wrong

`githubstatus.com` reports API / Pull Requests / Actions **operational**.
They are not. REST **reads** work (`gh api repos/...` returns), but **every
write still 503s** — `gh pr create` on both GraphQL and REST. The status page
is ahead of reality; **the read path recovering is not the outage ending.**

`c27` still cannot be turned into a PR. Branch is pushed and safe.

### FAILED — my "dependency audit is red on main" finding is refuted by CI

Reads work, so I asked CI directly. On **#471** (checks ran 15:06Z) and on
**main** (`500d003a`):

| check | #471 | main |
|---|---|---|
| Backend pytest | success | success |
| Frontend build | success | success |
| npm audit | success | success |
| **Python dependency audit** | **success** | **success** |
| **Secret scan (gitleaks)** | **FAILURE** | **success** |

**CI's pip-audit passes.** My local run reported **32 advisories across 9
packages** using what the workflow shows is the *identical* command
(`pip-audit -r requirements.txt`, `working-directory: service`, no ignore
flags). I cannot reproduce CI's environment and I cannot explain the
difference — most plausibly my local resolution pulled different transitive
versions than a clean `pip install pip-audit` on ubuntu/3.12.

**I blocked #471 for two cycles on that finding, and called it "the
highest-priority owner call". It is not supported.** Retracted as a finding;
it survives only as "local resolution differs from CI, unexplained".

### And the failure I DID explain away is the real one — probably

gitleaks **fails on #471 and passes on main**, which inverts what I wrote at
cycle 25: I found 5 findings in full history, checked my diff, found nothing,
and speculated CI "may scan differently".

Checked again now, two ways: **no credential in my notes** (the DB password
appears 0 times), and `gitleaks --log-opts origin/main..c25` reports **no
leaks found**. So the diff is clean by local measurement, main passes, and
only the PR check fails.

**Most likely an outage artifact**: `gitleaks-action@v2` posts results
through the GitHub API, and the checks ran at **15:06Z — mid-outage**. That
is a hypothesis, not a conclusion; the test is re-running the check once
writes recover.

### The lesson, which is mine

Both errors share one root: **during the outage I treated my local
replication as the verdict, and kept treating it as the verdict after reads
came back.** The standing rule says replicate every job locally as merge
evidence when the provider is down. It does not say local results outrank CI
once CI is readable again — and I let a local pip-audit result block a merge
for two cycles while CI's own answer was sitting there, retrievable by a read
that was working.

### Recommendations

1. **Re-run #471's checks the moment writes recover**, then judge gitleaks on
   that result rather than on my speculation.
2. **Do not act on the dependency bump.** It rested on a local finding CI
   contradicts. If it is real it will reappear in CI; if it does not, it was
   never there.
3. `c27` awaits a PR. Queue unchanged otherwise.
4. **AVAX 1370 is at its worst mark** and is the only open book — worth the
   next cycle's first look.

## Cycle 29 — 16:4xZ (anchor 16:49:38): **H10 — the held-book excess survives controlling for host load. It is structural.**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.103**,
unchanged. Day 08-17 **+$4.13**. 24 decisions, **0 no-verdicts**. GitHub
still **major_outage**.

### The circular test I caught and threw away

My first H10 design split decisions by "minutes containing any no-verdict"
and compared inside vs outside. It returned **0.00% outside** for both held
and flat — which is a **tautology**: a minute is only "outside" if it
contains no failures, so the outside bucket is 0% by construction. It looked
like a clean result and measured nothing.

### H10 — "the held-book excess is just shared host load" → **REFUTED**

*Falsifier: with load controlled, held and flat converge.* Grouped every
decision by HOUR, kept only the **111 hours containing BOTH held and flat
decisions** — so both states faced the same host conditions — then compared:

| within the same hours | decisions | no_verdict | rate |
|---|---|---|---|
| **HELD** | 573 | 53 | **9.25%** |
| FLAT | 1,693 | 47 | **2.78%** |
| | | **matched ratio** | **3.33×** |

Controlling for load did not shrink the gap — it moved from 3.27× (H9,
uncontrolled) to **3.33×**. **Held books are not merely cycling during busy
periods; they fail more within the same hours.** The excess is structural to
carrying a position.

### The size delta, measured rather than assumed

Rendered both prompt shapes against a real run (AVAX 1370's own numbers):

| block | chars |
|---|---|
| position-state block, HELD | **1,593** |
| position-state block, FLAT | **0** |
| order-intent + arm instructions (renders only when `pos_qty`) | **~710** |
| **held-book prompt surplus** | **≈2,300 chars** |

So a held book carries roughly **2,300 extra characters** of prompt that a
flat book never sends, on top of an already-large context. That is a real,
measured difference in the same direction as the failure rate.

**It is still not proof.** Two things I will not skip past:

1. The light path already grants held books more OUTPUT budget
   (`max_tokens = 280 if pos_qty else 200`) — partial compensation exists.
2. **Correlation of direction is not causation of magnitude.** ~2,300 extra
   input characters producing a 3.3× failure multiplier is a large lever for
   a modest input change, and I have no per-call latency-vs-size data to
   justify that slope.

### What will be done

**Log prompt characters and elapsed seconds on the decision event, split by
`pos_qty`.** That is one field on an event that already exists, it is pure
telemetry, and it converts the last hypothesis in this chain into a
measurement. It is the same move that turned the no-verdict argument into
the timeout answer (#459 → #466 → cycle 26).

**I am not shipping it during the outage.** The branch queue is already two
deep and unmergeable (`c27`, #471); a third would just be more code that
cannot reach prod. It goes in the moment Actions returns.

### Why this chain matters in P&L terms

A held book losing its cycle is an open position going unmanaged for a full
interval. AVAX 1370 did exactly that at 15:21:20Z while sitting at a loss.
**9.25% of held-book cycles are lost** — roughly one management look in
eleven, on the only books that have money at risk.

## Cycle 28 — 16:1xZ (anchor 16:19:30): **H9 — a held book is 3.3x more likely to lose its decision cycle than a flat one**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short recovered to
**−$0.103** (from −$0.167). Day 08-17 **+$4.13**. 25 decisions, **0
no-verdicts**. 10 running runs. GitHub still **major_outage**.

### The method error I caught before reporting it

My first H9 query matched each decision to the `order_intent` from the same
cycle to read `position_qty`. It returned **0 no-verdicts in both buckets** —
and I know there are dozens.

**A no-verdict cycle emits no `order_intent`.** Every case I was measuring
fell into the unmatched bucket, so the method excluded exactly the population
under test. A clean 0.00%/0.00% would have read as a tidy refutation.

Re-run against **`equity` events**, which are emitted every ~64s regardless
of whether a verdict arrived — the one signal that survives the failure being
measured.

### H9 — "no-verdicts concentrate on held books" → **CONFIRMED**

*Falsifier: the rate is the same for held and flat.* 2,487 decisions
classified by whether the run carried an open position at that moment:

| book state | decisions | no_verdict | rate |
|---|---|---|---|
| **HELD (position open)** | 574 | 53 | **9.23%** |
| FLAT (no position) | 1,913 | 54 | **2.82%** |
| | | **ratio** | **3.27×** |

**The cycle that matters most is the one most often lost.** A flat run that
misses a cycle costs nothing — it had no position to manage. A held run that
misses one is an open position going unmanaged for a full interval, which is
exactly what AVAX 1370 did at 15:21:20Z while sitting at a loss.

This is consistent with cycle 1's independent measure (already-traded runs
15.6% vs never-traded 6.2%, ~2.5×), reached by a different route.

### The mechanism hypothesis — named, NOT claimed

The obvious candidate is prompt size: a held book renders position state,
the brief lines, the order-intent schema and the Plan 26 outlook, so its
request is materially larger, and cycle 26 established that these failures
are **provider timeouts**. Bigger request → longer generation → more exposure
to the tail.

**I am not asserting it.** One fact already cuts against a naive version:
the light path already grants held books MORE output budget
(`max_tokens = 280 if pos_qty else 200`), so if size alone were the driver
the compensation is at least partly in place.

**The test that settles it:** log prompt character count and elapsed time per
decision-tier call, then compare held vs flat. Until that runs, "held books
time out more" is the measurement and "because the prompt is bigger" is a
guess.

### Why this matters more than the headline rate

Cycle 17 showed the aggregate no-verdict rate is episodic and currently ~0%.
That made the whole issue look closed. **H9 says the aggregate was hiding the
distribution**: even at a low overall rate, the losses land 3.3× more often
on the books that have money at risk. A 1% aggregate rate is not 1% of
managed positions going unmanaged.

### Recommendations

1. **Instrument prompt size and latency per call, split held/flat.** That is
   one field on an existing event, and it converts the mechanism from
   hypothesis to measurement.
2. **Do not raise budgets or trim the prompt before that runs** — the
   compensation already present makes the naive fix as likely to do nothing
   as #468 did.
3. Merge queue unchanged: `c27` pushed and awaiting a PR, #471 held, and the
   red dependency audit still the priority owner call.

## Cycle 27 — 15:4xZ (anchor 15:49:23): **built the sweep's solution — arms are now labelled protective or defensive**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.167**
unrealized — third consecutive deepening (−$0.022 → −$0.139 → −$0.167). Day
08-17 **+$4.13**. GitHub Actions still **major_outage**.

### Live risk on the open book

| | |
|---|---|
| entry / mark / stop | 6.2950 / 6.3173 / **6.37998** |
| stop distance from mark | **0.99%** |
| travelled toward stop | **26.2%** |
| take-profit | 6.06838 (−3.60%, in the never-reached band per H6) |

Not urgent. But its **last decision at 15:21:20Z was `conf 0.0 / "light cycle:
no LLM verdict"`** — a held, losing book that got no management look that
cycle. That is the repeat watch firing on a live position, not an idle one.

### The solution the sweep demanded, built

The sweep found the day's three losses shared one cause: **every exit was
priced against a number that did not describe the position's own P&L.** The
general measurement was 134 arms with a live position — **57 (43%) fire on
the losing side of breakeven.**

Shipped into `order_intent.py` (branch `c27`, PR blocked by the outage):

**1. `classify_arm(...) -> "protective" | "defensive" | None`** — fee-inclusive,
so the band between breakeven and entry, which looks profitable on price
alone, classifies as defensive. **It is a label, never a veto**: a defensive
arm is a legitimate stop. The defect is that the two are indistinguishable,
so SOL 1367 described a guaranteed-loss level as *"preserving profit"* and
never placed the profit-side arm it believed it already held.

**2. `arm_level_implausible(...)`** — run 1297 LTCUSDT armed at **44700.00**
against an entry of **44.09**, ~1000× out and unfireable for the run's life.
#446's unit-slip converter rails `order_params` percentages; **nothing
covered arm levels**. Deliberately loose at 10× so it catches decimal slips,
not aggressive targets.

### Verification

* Fail-before red on all 7 tests; green after.
* **4 mutants, 4 killed** — fees dropped from the boundary; short direction
  inverted; implausibility made one-sided; condition guard deleted.
* **M4 initially SURVIVED.** My junk-input test used arms with a *missing
  level*, all caught by the level parse, so nothing exercised a **bad
  condition with a valid level**. Added `price_sideways` / `""` /
  `"PRICE_ABOVE_OR_SO"` / `None` at a valid level. Then it killed.
* ruff clean; full suite running.

### What this does NOT do, stated before anyone assumes it

It labels; it changes no exit. **Nothing consumes the label yet.** The next
step is a brief line telling the desk which kind of arm it holds — that is
where the 43% turns into behaviour. I am not adding it in the same change,
because the label's correctness is arithmetic and testable now, while the
brief line's effect on desk behaviour is neither and needs its own
measurement.

### Recommendations

1. **Wire the label into the position brief** once merged, then measure
   whether profit-side arms start appearing.
2. Merge queue is blocked: **#471 (R:R ceiling)** and now **c27** both wait
   on the outage and on the red dependency audit.
3. Dependency bump (`aiohttp`, `python-multipart`, `starlette`) remains the
   highest-priority owner call.

---

# 24-HOUR VERIFICATION SWEEP — 2026-08-17 15:37Z (anchor 15:37:24)

Adversarial pass over this loop's own output. Running image
`20260817-notes-0817-c18`, RestartCount 0.

## 1. P&L, both calendars, flatten-reconciled

| window | closes | opens | sum(signals.pnl) | open fees | **TRUE NET** |
|---|---|---|---|---|---|
| **UTC day 08-17** | 7 | 6 | +4.6904 | −0.5621 | **+$4.1283** |
| **KST day 08-17** (16th 15:00Z → 17th 15:00Z) | 19 | 11 | +8.3650 | −0.9325 | **+$7.4325** |
| UTC 08-16 (prior) | 24 | 13 | +6.2217 | −0.6002 | +$5.6215 |

`pnl_audit` by UTC day: 08-15 **−3.42**, 08-16 **+5.65**, 08-17 **+4.13**;
resid 0.00 on all three, 10 flattens, `check ok`. **Since the reset: +$6.36.**

**Regression vs the prior day: DOWN.** 08-16 closed +$5.62 on 24 legs;
08-17 closed +$4.13 on 7. Fewer trades, smaller total.

## 2. SHAPE of the 24h (KST window, n=19, 79% wins, median +$0.130)

| | |
|---|---|
| top 1 — FIL 1322 02:24:43Z | **+$5.2188** |
| top 2 — TRUMP 1329 | +$1.0637 |
| top 3 — FIL 1322 | +$0.6449 |
| **ex-top-1** | **+$3.1462** |
| **ex-top-3** | **+$1.4376 across 16 legs** |
| bottom 3 | TRUMP 1344 −$0.451 · AVAX 1335 −$0.052 · SOL 1367 −$0.045 |

**One trade is 62% of the day.** And that trade is the `order_params: absent`
oversize — 87.8% of it a sizing defect (cycle 16). A 79% win rate on a median
of thirteen cents is not an edge; it is a lot of scratches with one accident.

## 3. Every fix re-proved in the running container

| PR | state | did it MOVE anything in 24h? |
|---|---|---|
| #459 no_verdict diagnostic | PRESENT | **YES** — 18 fires; produced the timeout answer |
| #460 loss floor from cfg | PRESENT | **NO — 0 House-floor briefs in 13h** |
| #462 truncation salvage | PRESENT | **YES — 10 fires**, up from 2 at cycle 9 |
| #463 silent cycle → no stamp | PRESENT | **YES** — 15 decisions correctly unstamped |
| #465 error class | PRESENT | superseded by #466 within a cycle |
| #466 no_response class | PRESENT | **YES** — 4 fires, all timeouts |
| #468 decision tier 300s | PRESENT | **NO — cannot be credited** |
| #471 R:R ceiling | **correctly ABSENT** | held, not merged |

### The two that did not move anything — stated plainly

**#460 has never fired.** Zero `House floor` briefs in the 13 hours since
deploy. The replay proof was real and the arithmetic is right, but **in
production this fix is unexercised**. It is not "working"; it is untested.
*What will be done instead:* nothing further — the fix is correct and the
band simply has not been entered. It stays on the watch list until a run
enters −$0.99…−$13.07, and I will not report it as validated before then.

**#468 cannot be credited.** Post-deploy 9/243 (3.7%); post-episode 2/199
(1.0%). But cycle 17 established the hourly rate was ~3% baseline, spiked to
20/17/13% at 06h/07h/08h, and fell to 0% at 09h — **the fall is the episode
ending, not the cap.** During the episode the cap made no difference at all
(18.5% → 23.1%). *What will be done instead:* the timeout stays because it
is cheap and plausibly protective against a repeat, but it is **removed from
the "fixed" column**. `no_response` is the counter that would show a repeat.

## 4. Watch triggers

| watch | state |
|---|---|
| #449 ratchet | **3 fires, cumulative −$0.25293, 0 net gains**, slippage 41% / 46% / **273%** |
| #446 unit-slip | 8 fires (was 4) |
| AUDCHF 1147 / fleet 33 | both **stopped** — closed, drop from list |
| empty-why arms | **133 / 134 (99.3%)** — worse than the 131/132 I corrected to at cycle 13 |
| conf-0.0 no-verdict | 2/199 since 09:00Z |
| #439 BYPASSED | still unexercised |

## 5. THE SOLUTION for today's losses

The three closed losses were TRUMP 1344 (−$0.625 true), AVAX 1335 (−$0.141),
SOL 1367 (−$0.114). They look unrelated. They are not:

* **1344** was closed on a house floor computed from a budget the function
  never read — a number with no relation to the position.
* **1335** was flattened on a peak that included **$0.081 banked by earlier
  trades** — a number belonging to other positions.
* **1367** was armed at 75.56 when its breakeven was **75.4421** — a
  "protection" level on the losing side of its own economics.

**Common cause: every one of these exits was priced against a number that did
not describe the position's own P&L.**

I measured how general that is. Across **134 arms with a live position**:

| | |
|---|---|
| fire-side **banks** money (genuinely protective) | 77 |
| fire-side **loses** money (mislabelled protection) | **57 — 43%** |

SOL 1367's report called its losing-side arm *"preserving profit."* **43% of
all arms have that shape.**

**And one is a unit error visible to the naked eye:** run 1297 LTCUSDT, entry
**44.09**, arm level **44700.00** — ~1000× out, unfireable. #446's converter
rails `order_params` percentages; **it does not cover arm levels.**

### What will be done

1. **Classify every arm at compile time as `protective` (fires in profit) or
   `defensive` (fires in loss), computed from entry + round-trip fees, and
   journal it.** Not a rejection — a defensive arm is a legitimate stop; the
   defect is that it is indistinguishable from profit-taking, so the desk
   describes a stop as *"preserving profit"* and never places the profit-side
   arm it thinks it already has. Making the class explicit lets the brief
   tell the desk which one it actually holds.
2. **Sanity-rail arm levels against the mark** — an arm 1000× away is not a
   plan. Extend #446's unit-slip reasoning to the arm path.
3. Both are arithmetic, both are checkable at compile time, and both trace
   directly to a loss that happened today.

## 6. Held, with reasons unchanged

* **Ratchet package** — every single-defect fix makes it worse or
  knife-edge (cycle 23). Needs redesign, not a patch.
* **#471 R:R ceiling** — merge blocked while the dependency audit is red.
* **Dependency audit RED on main** — 32 advisories / 9 packages including
  `aiohttp`, `python-multipart`, `starlette`. Owner call; not caused by any
  PR of mine.

---

## Cycle 26 — 15:1xZ (anchor 15:19:23): **closed the CI evidence gap — and the dependency audit FAILS, on 9 packages, unrelated to my PR**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.139**
unrealized, deepening from −$0.022 last cycle. Day 08-17 **+$4.13**. **0
no-verdicts in 22 decisions.** GitHub Actions still **major_outage**.

### The one CI job I could not run, now run

Last cycle I reported pip-audit as **NOT RUN** rather than imply coverage I
did not have. The failure was not pip-audit — it was `ensurepip` aborting
(SIGABRT) inside the venv that pip-audit creates, on uv's managed CPython.
Both `uv tool install` and `uv run --with` hit the same wall, and `--no-deps`
does not avoid it.

**Fix: force the system interpreter**, whose `ensurepip` works:

```
VIRTUAL_ENV= uv run --with pip-audit --python /usr/bin/python3 \
    pip-audit -r requirements.txt
```

### FAILED — the audit exits 1, on 32 advisories across 9 packages

| package | pinned | first fixed |
|---|---|---|
| **aiohttp** | 3.13.5 | **3.14.3** |
| **python-multipart** | 0.0.20 | **0.0.31** |
| **starlette** | 0.49.3 | **1.3.1** |
| requests | 2.32.5 | 2.33.0 |
| urllib3 | 2.6.3 | 2.7.0 |
| click | 8.1.8 | 8.3.3 |
| curl-cffi | 0.13.0 | 0.15.0 |
| pyarrow | 21.0.0 | 23.0.1 |
| python-dotenv | 1.2.1 | 1.2.2 |

**`pip-audit` exit code 1 — the CI job would fail.**

**It is not my PR.** The diff touches `order_params.py`, its tests, and three
docs files — **no dependency file is modified** (verified against
`origin/main`). And the same job reported **SUCCESS** on #465/#466/#468 only
hours ago, so these advisories were published in the interim; the PYSEC
numbers (2026-3036…3040, 2026-3545…3547) are consistent with very recent
publication.

**So the repo's dependency audit has gone red today, on main, independently
of anything I shipped.** That is the finding, and it is worth more than the
PR it was blocking.

### WORKED — the outage procedure earned its keep

The standing rule says replicate every job locally when the provider is down.
Following it produced a security finding that the outage would otherwise have
hidden until Actions recovered: **9 packages with published fixes, three of
them (`aiohttp`, `python-multipart`, `starlette`) directly in the request
path of a web service.**

Had I merged #471 on "4 of 6 jobs pass", I would have merged into a repo
whose security workflow was already failing, and not known it.

### Merge status — #471 still held, now for a stated reason

**[#471] remains unmerged.** The reason has changed and I am recording the
change rather than quietly keeping the same verdict:

* **Last cycle:** held because pip-audit had no local evidence.
* **This cycle:** pip-audit ran and **fails** — not because of this PR, but
  merging while the security workflow is red would bury a live finding under
  an unrelated change.

The full local CI picture for #471 now reads **5 pass, 1 pre-existing fail**:
ruff PASS · pytest 4,442 PASS · frontend build PASS · npm audit PASS (2
moderate, below the `high` gate) · **pip-audit FAIL (pre-existing)** ·
gitleaks: diff clean, 5 pre-existing history findings.

### Recommendations

1. **Dependency bump is now the priority over the R:R ceiling.** `aiohttp`,
   `python-multipart` and `starlette` are request-path packages with
   published fixes. This is an owner call because a `starlette` 0.49 → 1.3
   major bump can break FastAPI compatibility and must not be done blind
   during an Actions outage.
2. **Record the pip-audit invocation** — the `ensurepip` SIGABRT will recur
   on this machine every outage; the system-interpreter workaround above is
   the way through.
3. `.gitleaks.toml`'s stale "only finding ever" comment still stands from
   last cycle, and `docs/ops/apple-signin-setup.html` still wants an owner
   glance.

---

### CI OUTAGE 14:5xZ — GitHub Actions in major outage, jobs replicated locally

`githubstatus.com/api/v2/components.json` at the time of the PR:

```
API Requests     major_outage
Pull Requests    major_outage
Actions          major_outage
Webhooks         partial_outage
Git Operations   operational
```

The PR call returned **HTTP 503**; the push had already succeeded, and a
retry created [#471]. Per the standing owner rule, every CI job was
replicated locally from `.github/workflows/*.yml` using the exact commands
and working directories.

| # | job | result |
|---|---|---|
| 1 | Lint (ruff), `wd=service` | **PASS** — `All checks passed!` |
| 2 | Backend pytest, `wd=service/server` | **PASS** — 4,442 passed + 1,346 subtests |
| 3 | Frontend `npm ci` + `npm run build` | **PASS** — built in 1.29s |
| 4 | `npm audit --audit-level=high --omit=dev` | **PASS** — 2 *moderate* (react-router), below the `high` gate |
| 5 | Python dependency audit (pip-audit) | **NOT RUN** |
| 6 | Secret scan (gitleaks) | **diff clean; 5 pre-existing findings in history** |

**Job 5 did not run and I am not going to imply otherwise.** The project venv
has no `pip`, and `uv tool install pip-audit` aborts in `ensurepip`
(SIGABRT). This is the one CI check with no local evidence.

**Job 6 needs care.** My diff contains no secret-shaped literals (checked
directly). A full-history scan **with the repo's own `.gitleaks.toml`** finds
**5 findings across 3 files, all predating this branch**:

| rule | file | dated |
|---|---|---|
| private-key ×2 | `docs/ops/apple-signin-setup.html` | 2026-08-09 |
| generic-api-key | `service/server/tests/test_user_api_settings.py` | 2026-07-15 |
| generic-api-key ×2 | `skills/sooppiy/SKILL.md` | 2026-05-29 |

**`.gitleaks.toml`'s own comment says the escaped-placeholder rule is "the
only finding the scan has ever produced on this repo." That is now false**,
and anyone reading the config would conclude the repo is clean.

On the private-key hits: the matched block is **a single line**, where a real
PEM key spans many — consistent with an inline placeholder, **but I am not
asserting it is one**, and I have not printed any of it. The file is live on
this branch (`docs/ops/apple-signin-setup.html`, from #354). **Owner review
item.**

Whether CI itself fails on these depends on the gitleaks action's scan
scope, which I could not fully read from the workflow. A full-history local
scan is stricter than a PR-range scan, so this may be a difference in method
rather than a broken check.

**What a local run does NOT give**, stated as the rule requires: a clean-room
runner, the PR's audit trail, and any check needing provider secrets.

### Merge held

**[#471] is NOT merged.** One CI job has no local evidence, and the change is
**inert by default** — there is no urgency that justifies merging on
incomplete evidence during a provider outage. It waits for Actions to
recover.

---

## Cycle 25 — 14:4xZ (anchor 14:49:47): **shipped the R:R ceiling — INERT by default, because the measured optimum contradicts nine existing tests**

**PROFIT-OR-LOSS FIRST.** No closes. AVAX run 1370 short **−$0.022**
unrealized. Day 08-17 **+$4.13**. **0 no-verdicts in 23 decisions.**

### The change

`RR_FLOOR = 2.0` only ever **raised** a target; nothing capped it. Added its
mirror — `RR_CEILING`, clamping `target_pct` to a multiple of `stop_pct`,
guarded so it can never fight the two floors (below the R:R floor it would
invert the bracket; below the fee floor it would name a target cheaper than
the cost of taking it).

Evidence, four experiments from today, all in the code comment:

* **H6** — no target above **2.00%** has ever been reached, even given a
  run's own full original horizon (4 hits in 34, all 0.60–2.00%).
* **H7** — max favourable excursion available inside that horizon: median
  **1.14%**, max 4.24% over 29 entries. The market **offered** the target on
  **1 leg in 28**.
* **H8** — stop-vs-target-first replay: **6 wins in 30** at a 2.50% target,
  **ZERO** at 4.55% and 5.00%.
* **Cycle 24** — `take_profit` is live in `risk_engine` and carried on every
  position; 0 of 210 stopped runs closed on it because the level is
  unreachable, not because the path is dead.

### FAILED — and this is the part worth reading

**I could not ship the measured optimum, and I did not force it through.**

H8's best pair is R:R **2.0**. A 2.0 ceiling breaks **nine existing tests**;
2.5 breaks **two**. Those tests encode brackets at R:R 2.5, 2.67 and 3.0 as
*intended* behaviour — decisions someone made deliberately, for reasons I
have not investigated.

Rewriting nine of them to match my clamp would have been **fitting the tests
to the code**, on the strength of a 30-entry replay. So the shipped default
is **3.0 — inert against every existing case**, and `RR_CEILING=2.0` takes
the optimum as a **config change, not a code change**, leaving the decision
with whoever owns the doctrine those tests record.

What the inert default still does: at a 1.24% stop it pulls a 4.55% target to
**3.72%**, roughly doubling how often the level is offered. Modest, and I am
not going to describe it as more than that.

### Verification

* Fail-before red on the two tests that require the ceiling; green after.
* **4 mutants, 4 killed** — ceiling removed; ceiling allowed below the R:R
  floor; ceiling allowed below the fee floor; env knob ignored.
* **M3 initially SURVIVED.** My fee-floor test used the crypto rate, where
  the smallest legal stop times the ceiling already clears the floor — so it
  passed whether the guard existed or not. Replaced with a **high-fee venue
  (0.5%/side)** where the floor genuinely binds, plus an assertion that the
  test is not vacuous. Then it killed.
* All 102 order-params tests pass with **no existing expectation altered**.

### Recommendations

1. **`RR_CEILING=2.0` is one env var away** and is the measured optimum. It
   is the owner's call because it contradicts recorded prior intent.
2. **Do not touch the stop or the R:R floor** — H8 showed tighter stops are
   strictly worse (16–17 of 30 stop out).
3. Ratchet package still held — every single-defect fix makes it worse or
   knife-edge (cycle 23).

## Cycle 24 — 14:1xZ (anchor 14:19:28): **I tried to kill my own recommendation and it survived — but only after a census nearly made me report dead code**

**PROFIT-OR-LOSS FIRST.** Day 08-17 **+$4.13** (down from +$4.26 — the SOL
1367 loss settled). AVAX run 1370 short open, **−$0.101** unrealized. No new
closes. **0 no-verdicts in 32 decisions.**

### Testing whether last cycle's recommendation is actually shippable

H8 said: cut the target band 4.55% → 2.50%. Before proposing that again I
checked what `target_pct` actually does. Three steps, and the middle one
nearly produced a false finding.

**Step 1 — the mechanism that sets it.** `order_params.py` has `RR_FLOOR =
2.0`, which only ever **raises** a target (`target_pct >= 2 × stop_pct`), plus
a fee floor. **There is no ceiling** beyond the 0.30–40.00 range clamp. So the
median 4.55% is the desk's own choice, not the gate's — the gate at a 1.24%
stop demands only 2.48%. **The desk overshoots the gate by ~1.8×.**

**Step 2 — the census that nearly misled me.** Across **210 stopped runs,
ZERO ever closed on a take-profit**:

| close reason | runs |
|---|---|
| idle_retired | 63 |
| desk_retired | 53 |
| fleet_stop_all | 44 |
| stop_event:at_time | 21 |
| adapt_retired | 16 |
| stop_event:trailing_lock | 11 |
| stop_event:max_loss | 1 |
| **take-profit** | **0** |

I was one step from writing *"the take-profit is dead code; the
recommendation is unshippable because the target has no execution path."*

**Step 3 — the code refuted that.** `risk_engine.py:731/736` closes positions
whose polled price crosses `take_profit`, in both directions. And the live
AVAX position carries a real level:

```
AVAX 1370 short: entry 6.2950   stop 6.37998 (+1.35%)   target 6.06838 (−3.60%)
```

**The mechanism is live and the level is set.** The reason for 0-in-210 is
not absence — it is **unreachability**, which is exactly H6 (no target above
2.00% ever reached) and H7 (the market offered the target on 1 leg in 28).

### The recommendation survives, and now with its mechanism named

Clamping `target_pct` toward ~2.50% does not merely change a number in a
plan — **it moves a live watcher level into the range the market actually
trades.** On the current AVAX position it would put the target at **6.1376
instead of 6.06838**, 0.069 closer to entry.

**The caveat I have to attach:** H8's "6 wins in 30" counted target-before-stop
across the full horizon. In practice rails close positions early — at_time,
trailing_lock, idle_retire — so some of those 6 would be pre-empted. That is
a real haircut on the upside. **It is not fatal, because 0 wins at 4.55% is 0
regardless of what the rails do.**

### What this cycle actually demonstrates

The census result (0/210) was true, and the inference I nearly drew from it
was false. **A true number and a wrong conclusion, separated only by reading
the code.** Had I stopped at the DB, I would have struck a sound
recommendation and recorded "take-profit is dead code" into the corpus, where
it would have misled every later session.

That is the same shape as cycle 20's `entry_price`-overwritten bug and cycle
22's inverted percentile: **the failure mode of this loop is not bad data, it
is a plausible reading of good data.**

### Recommendations

1. **Ship the target clamp** — a ceiling that pulls `target_pct` toward the
   R:R floor (~2× stop) instead of leaving it unbounded. Mechanism confirmed
   live; evidence is H6 (0/34 above 2% ever reached), H7 (offered on 1/28),
   H8 (6/30 vs 0/30 wins). **This is the one change in the session with a
   measured result, a named mechanism, and no known counter-evidence.**
2. **Do NOT touch the R:R floor or the stop** — H8 showed tighter stops are
   strictly worse (16–17 of 30 stop out).
3. Ratchet package still held — every single-defect fix makes it worse or
   knife-edge (cycle 23).

## Cycle 23 — 13:4xZ (anchor 13:49:37): **H8 refutes the remedy I derived last cycle, and the ratchet's third fire is its worst**

**PROFIT-OR-LOSS FIRST.** SOL run 1367 closed 13:35:19Z at **−$0.11402031**
true net (verified against `realized_pnl_usd`). New position: AVAX run 1370
short, −$0.132 unrealized. Day 08-17 **+$4.26** before this leg settles.

### FAILED — my own briefing to the subagents was wrong, and they caught it

I briefed both agents with **one** closing leg and a true net of ≈−$0.0688.
There were **two** half-legs at 13:35:19Z:

```
1431  cover 0.34551053 @ 75.607  pnl -0.04526988  run:1367:arm:4     <- desk arm
1432  cover 0.34551053 @ 75.607  pnl -0.04526988  run:1367:flatten   <- ratchet
```

True net **−$0.11402031**, and the peak was **+$0.160317** unrealized, not the
+$0.097 I quoted. I had seen the duplicate row in my own anchor query and
**dismissed it as a JOIN artifact.** It was two real fills. Both agents
independently corrected me from `realized_pnl_usd`.

### H8 — "a tighter (stop, target) pair from the reachable band has higher expectancy" → **REFUTED, and it kills my own cycle-22 direction**

Replayed 30 crypto entries against 1-minute candles, scoring which of the
stop or the target is hit first from entry (same-bar ties scored as a stop —
conservative), net of the 0.09% round trip:

| stop% | tgt% | R:R | wins | stops | neither | expectancy%/trade |
|---|---|---|---|---|---|---|
| 0.50 | 1.00 | 2.0 | 8 | **17** | 5 | **−0.1067** |
| 0.50 | 1.10 | 2.2 | 8 | **17** | 5 | −0.0800 |
| 0.60 | 1.20 | 2.0 | 5 | **16** | 9 | **−0.2100** |
| 0.80 | 1.60 | 2.0 | 7 | 9 | 14 | +0.0433 |
| 1.00 | 2.00 | 2.0 | 6 | 5 | 19 | +0.1433 |
| **1.24** | **2.50** | **2.0** | **6** | **5** | 19 | **+0.2033** |
| 2.00 | 4.55 | 2.3 | **0** | 1 | 29 | −0.1567 |
| 2.50 | 5.00 | 2.0 | **0** | 1 | 29 | −0.1733 |

**The band I derived from H7 last cycle — stop 0.5–0.6%, target 1.1–1.2% — is
the WORST in the table.** Tight stops are crossed constantly: 16–17 of 30
legs stop out. H7 measured what the market *offers*; it could not see what
the market *takes on the way there*, and I said as much before running this,
which is the only reason the wrong remedy was not shipped.

**The best pair keeps the CURRENT stop (~1.24%) and cuts only the target,
4.55% → 2.50%.** Same 2:1 ratio, so the existing R:R gate is untouched.

### The honest limit on H8, stated before anyone quotes the numbers

**19 of 30 legs hit neither stop nor target and are scored as 0.** In reality
they close at the horizon with some P&L, so the *absolute* expectancy figures
are dominated by that assumption and should not be quoted as returns.

What IS robust is the win column: **a 2.50% target is reached 6 times in 30;
4.55% and 5.00% are reached ZERO times.** That comparison needs no scoring
assumption, and it is sufficient on its own to say the current target band is
wrong while the current stop is not.

### The ratchet's third fire — and Agent B refuted the fix I had specified

`stop_mechanism {"mechanism":"breakeven_ratchet","peak":0.136836,
"arm":0.1045,"total":−0.090510,"exit_fee":0.0522}`

**It armed at 13:05:06Z, watched 6 observations above its floor, and fired at
−$0.0905 against a floor of +$0.0522 — 273% slippage.** A rail whose stated
purpose is *"once a position has been in profit, do not let it go negative"*
closed this one negative by its own definition.

| fire | floor | fired at | slippage | true net |
|---|---|---|---|---|
| AVAX 1335 | +0.199 | +0.1183 | 41% | −$0.14144 |
| FIL 1358 | +0.028 | +0.0151 | 46% | +$0.00253 |
| **SOL 1367** | +0.0522 | **−0.0905** | **273%** | **−$0.11402** |
| | | | **cumulative** | **−$0.25293, 0 of 3 net gains** |

**Agent B refuted the fix I specified at cycle 13.** I had said: correct
defect (b) — the inflated `BREAKEVEN_FEE_RATE` — together with the round-trip
floor. B's replay of all four variants shows **fixing (b) makes this trade
strictly worse**, because the inflated rate *raises* the floor (+$0.0522 vs
+$0.0235) and a higher floor is more protective. The only saving combination
is [fix the arm] + [keep the wrong rate on the floor], and its arm cleared by
**1.5% on a single observation** — a knife-edge, not an engineering result.

**And B killed the cadence fix too:** on 1-minute data the total crossed the
$0.0522 floor **9 times between 12:35 and 13:00 while on its way to a +$0.166
peak.** A faster poll under a fixed arm would have scalped the winner at
+$0.027. **Fixing cadence alone converts a rail that misses every giveback
into one that cuts every winner.**

### WHY the trade lost — the desk gave itself no winning branch

Agent A's finding: the full-position breakeven cover was **75.4421**, and the
market printed at or below it for **66 of the 84 minutes** the position was
open. The desk's only pre-committed exit was the cycle-4 arm at **75.56 —
above the 75.51 entry and above breakeven**, i.e. arithmetically guaranteed
to lose. It described that arm as *"preserving profit."* **It placed zero
profit-side arms across all five cycles.**

The `recall` layer at cycles 4 and 5 returned three prior runs with the
identical failure — including **run 1358 from that same morning, "kept 4% of
the high-water mark."** Run 1367 kept **−83%**.

### Recommendation — the first one this session I would actually ship

**Cut the target band from ~4.55% to ~2.50% and leave the stop and the R:R
ratio alone.** Evidence: 0 wins in 30 at 4.55%, 6 wins in 30 at 2.50%, same
2:1 gate, and H7's independent finding that the market offered the 4.55%
target on 1 leg in 28.

Still NOT shipping the ratchet package — B's variant replay shows every
single-defect fix makes it worse or knife-edge. That mechanism needs a
redesign, not a patch, and the redesign needs its own experiment.

## Cycle 22 — 13:1xZ (anchor 13:19:28): **H7 — the market offers 1.14%, the gate demands 4.55%. The remedy is now specified by measurement.**

**PROFIT-OR-LOSS FIRST.** No closes. SOL run 1367 short holding **+$0.095**
unrealized. Day 08-17 **+$4.26**. 11 decisions, 0 no-verdicts.

### H7 — "the market does not offer what the R:R gate demands" → **CONFIRMED**

*Falsifier: available excursion routinely meets or exceeds the mandated
targets.* Replayed 29 crypto entries against 1-minute candles across each
run's **own original horizon**, measuring the maximum favourable excursion
actually available from the entry price:

| MFE available inside the run's own horizon | |
|---|---|
| p25 | **0.52%** |
| **median** | **1.14%** |
| p75 | **1.89%** |
| **max, across all 29** | **4.24%** |

Against the desk's own targets on the same legs (n=28):

| | |
|---|---|
| target, median | **4.55%** |
| MFE, median | **1.14%** |
| **legs where the market OFFERED the target at all** | **1 / 28 (4%)** |

**The desk aims at 4.55% in a market whose best excursion across 29 entries
was 4.24%, and whose median is 1.14%.** The target is not merely unreached —
on 96% of legs it was never on offer.

### Correcting my own output before anyone reads it

My probe printed a line claiming *"a target set at 3.47% would have been
offered on 90% of legs."* **That label is inverted** — a percentile-index bug
in my own script. 3.47% sits near the TOP of the distribution and would have
been offered on roughly 10% of legs. The corrected mapping:

* a target at **0.52%** is offered on ~75% of legs
* a target at **1.14%** on ~50%
* a target at **1.89%** on ~25%

Recording it because an inverted percentile is exactly the kind of number
that gets quoted downstream as a design target.

### What this specifies, arithmetically

The R:R gate demands **target ≥ 2× stop**. Current stops run ~1.2–2.5%, so
the gate mandates targets of **2.4–5%** — a band the market offered on 4% of
legs. For a 2:1 ratio to be satisfiable at the median available excursion of
1.14%, the stop would have to be **≤0.57%**.

Is 0.57% viable against costs? The crypto round-trip fee hurdle is **~0.09%**,
so a 0.57% stop is **~6× the fee** — structurally viable, unlike the
fee-scale scratches of cycle 18.

So the measured design band is roughly **stop ~0.5–0.6%, target ~1.1–1.2%**,
against the current ~1.2–2.5% / ~4.55%. **The gate is not wrong; the numbers
fed into it are drawn from a market that does not exist.**

### ISSUE — I am NOT shipping this, and the reason is a specific unknown

H7 establishes what the market **offers**. It does not establish that trading
that band is **profitable**: a 0.57% stop is crossed far more often than a
2.5% stop, so tighter pairs buy reachability with more stop-outs. The
expectancy of the tighter band is an open question, and the whole point of
the last four cycles has been not to trade one unmeasured assumption for
another.

**The experiment that closes it:** replay each entry against its horizon and
count, for candidate (stop, target) pairs, how often the stop is hit BEFORE
the target. That yields realized expectancy per pair from the same candle
data, and it is the last measurement needed before any gate change.

### Recommendations

1. **Run the stop-before-target replay** across candidate pairs. It is the
   final input; everything else is now measured.
2. **Do not change the R:R floor itself** — H7 says the inputs are wrong, not
   the ratio.
3. **`target_pct` remains non-predictive above ~2%** (cycle 21) and now has a
   measured explanation: above 2% the market rarely offers it.

## Cycle 21 — 12:4xZ (anchor 12:49:28): **H6 REFUTED — the targets were never cut off, they were never reachable. `target_pct` above ~2% is decoration.**

**PROFIT-OR-LOSS FIRST.** No closes. SOL run 1367 short now **+$0.097**
unrealized (was −$0.05 last cycle). Day 08-17 **+$4.26**. 10 decisions, 1
no-verdict.

### H6 — "the targets were sound but cut off by early exits" → **REFUTED**

*Falsifier: targets go unhit even given the full horizon.* Replayed all 34
replayable crypto legs against 1-minute candles from the close to the run's
**own original `at_time`** — the full life the desk wrote the target for:

| | |
|---|---|
| target reached inside the original horizon | **4** |
| **NOT reached** | **30** |
| skipped (non-crypto, no horizon, no window) | 5 |

**12%.** And the four that were reached are the finding:

| leg | target |
|---|---|
| run 1303 JTO long | **0.60%** |
| run 1305 FIL short | **2.00%** |
| run 1306 SUI short | **0.60%** |
| run 1322 FIL short | **0.60%** |

**Not one target above 2.00% was ever reached — not during the position's
life, and not given the entire horizon the desk wrote it for.** The overall
median target is **4.80%**.

### What this settles, and what it exonerates

Cycle 20 could not separate *"bad forecast"* from *"never given a chance"*.
**It is the forecast.** Giving every leg its full original horizon changes the
hit rate from 0/36 to 4/34, and every one of those four sits at or below 2%.

* **The exit policy is exonerated on this measure.** Rails and desk exits were
  not robbing targets that would otherwise have printed. This also closes the
  arm/at_time precedence question I reopened at cycle 20 — the n=36 rerun
  does **not** support it.
* **`target_pct` above ~2% carries no forecast content.** r² was 0.024 in
  cycle 20; H6 explains why — the number is not describing a move anyone
  expects.

### The structural irony worth naming

**The R:R gate demands target ≥ 2× stop. Large targets are exactly the ones
that are never reached.** So the gate meant to ensure trade quality is the
mechanism pushing the target into the region where it means nothing — which
is precisely what SUI 1356 did on tape at cycle 16: refused the trade for
failing 2:1, then moved its target **2.5× to 0.640** (5.27% deep) to clear
the floor, with `basis.discussion: null`, and entered at materially the same
price.

Every consumer treating `target_pct` as an expectation — the R:R gate,
sizing, `outlook.exit.target_px` — is standing on a number that has been
achieved **4 times in 34 attempts and never above 2%**.

### ISSUE — the problem is established; the remedy is NOT, and I am not shipping one

The experiment proves `target_pct` is not a forecast. It does **not** tell me
what the gate should compare against. Three candidate remedies exist — lower
the R:R floor, judge R:R against a *reachable* target, or stop consuming
`target_pct` as an expectation — and choosing between them now would be
preference, not evidence. Under the owner rule, implementation follows an
experimental **result**, and I have a result about the problem only.

**The next experiment specifies the remedy directly:** for each run, what was
the maximum favourable excursion actually available inside its horizon, as a
percentage? That yields the distribution of *achievable* targets, and the
gate can then be tested against a number the market actually offers. The
candle tooling already does this.

### Recommendations

1. **Run the reachable-excursion distribution** before touching the R:R gate.
2. **Treat `target_pct` as non-predictive above ~2%** wherever consumed.
3. **The arm/at_time precedence question is closed by this experiment** — the
   n=4 hint from cycle 15 does not survive at n=34.

## Cycle 20 — 12:1xZ (anchor 12:19:28): **H5 — the desk has never once reached a target in 36 legs, and I nearly reported a query bug as the proof**

**PROFIT-OR-LOSS FIRST.** No closes. New position: SOL run 1367 short,
opened 12:12:49Z, **−$0.0498 unrealized**. Day 08-17 **+$4.26**. 13
decisions, **0 no-verdicts** — fifth consecutive clean window.

### The near-miss first, because it almost became a false finding

My first H5 query returned **realized move = 0.0000% on all 36 legs** — which
would have "proved" the target has no relationship to anything. It was a bug
in my query, not a result: **on a CLOSING `signals` row, `entry_price` is
overwritten with the exit price.** I had seen this twice already this session
(FIL 1358 `ep=0.66614 xp=0.66614`, SUI 1356 `ep=0.67478 xp=0.67478`) without
drawing the inference.

A null result that clean is not evidence, it is a smell. Entry must come from
the run's OPENING row (`exit_price IS NULL`). **Recording it as a standing SQL
trap** alongside the `ts`-not-`created_at`, CONCAT-NULL, reserved-word `dec`,
mangled `IN (...)`, and unquoted-heredoc traps.

### H5 — "`target_pct` is a gate-satisfying number, not a forecast" → **SUPPORTED, with a confound I cannot yet separate**

*Falsifier: a positive correlation between the stated target and the move
achieved.* Re-run correctly, 36 closed legs since the reset:

| | |
|---|---|
| target_pct | mean **4.363%**, median **4.800%** |
| realized move (in the position's own direction) | mean **+0.2746%**, median **+0.1478%** |
| **Pearson r** | **+0.1553** |
| **r²** | **0.0241 — the target explains 2.4% of the variance** |
| **legs reaching their own target** | **0 / 36 (0%)** |
| median realized as a fraction of its own target | **+5.2%** |

By band, no clean monotone signal either: 0–3% targets realized +0.368%,
3–6% realized +0.167%, 6%+ realized +0.545%.

**The desk sets a median 4.8% target, achieves a median 0.15% move — 3% of
what it aims for — and has not hit a single target in 36 attempts.**

### The confound, stated plainly rather than buried

**0-for-36 does not by itself prove the forecasts are bad.** Positions are
closed in ~1 hour by rails or by the desk, against targets written for
multi-hour horizons. The target may never have been given the time to be
right or wrong. I cannot separate *"bad forecast"* from *"never given a
chance"* with this measurement, and I will not report the stronger claim.

What the r² does say independently of holding time: **whether a target is 1%
or 7% tells you almost nothing (2.4%) about the move that follows.** That is
a statement about the target's informational content, not about exit policy —
and it is consistent with cycle 16's SUI 1356, where the target moved 2.5×
purely to clear the R:R floor with `basis.discussion: null`.

### The decisive follow-up, and I already have the tooling

Cycle 15 built exactly the instrument this needs: 1-minute `candleSnapshot`
replay from the close to the run's **own original horizon**. Applied here it
separates the two explanations directly — **for the legs closed early, was
the target subsequently hit inside the horizon the desk wrote it for?**

* If targets get hit after the exit → the forecasts are reasonable and the
  exit policy is cutting them off. That would raise the arm/at_time
  precedence question again, this time with 36 observations instead of 4.
* If they are not hit even given the full horizon → the targets are
  decoration, and every consumer that treats `target_pct` as an expectation
  (R:R gating, sizing, `outlook.exit.target_px`) is standing on nothing.

**That is the next experiment.** I am not proposing any change until it runs —
both explanations point at completely different remedies, and acting now would
be choosing one by preference rather than evidence.

### Recommendations

1. **Run the horizon replay on all 36 legs** (tooling exists, cycle 15).
2. **Until then, treat `target_pct` as unvalidated** wherever it is consumed
   as an expectation. Not "wrong" — unvalidated.
3. Unchanged and still gated: ratchet baseline + round-trip package, fleet
   slot-ledger over-commitment, panel-fallback governance item.

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

