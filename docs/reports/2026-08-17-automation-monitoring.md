# Automation monitoring — 2026-08-17 (UTC day), newest-first

Continued from [2026-08-16](2026-08-16-automation-monitoring.md) (day
closed **+$5.65 realized, resid 0.00**; 15 code/skill PRs + 4 docs
merges shipped). Target: **info@askkpop.com — user 5 / agent 6 /
FLEET 35**. Open items: `BREAKEVEN_FEE_RATE` (needs fleet-wide replay),
prospective #443 warning, outlook intent-vs-execution defect,
arm-reachability rail.

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

