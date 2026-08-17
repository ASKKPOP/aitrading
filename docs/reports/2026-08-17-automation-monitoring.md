# Automation monitoring — 2026-08-17 (UTC day), newest-first

Continued from [2026-08-16](2026-08-16-automation-monitoring.md) (day
closed **+$5.65 realized, resid 0.00**; 15 code/skill PRs + 4 docs
merges shipped). Target: **info@askkpop.com — user 5 / agent 6 /
FLEET 35**. Open items: `BREAKEVEN_FEE_RATE` (needs fleet-wide replay),
prospective #443 warning, outlook intent-vs-execution defect,
arm-reachability rail.

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

