# Automation monitoring — 2026-08-06 (UTC day)

**Loop RESUMED by the owner 2026-08-06 ~05:47Z** — new cadence: **30-minute
cycles** (cron `6f554382`, `13,43 * * * *`) + the unchanged **24-hour
verification sweep** (cron `947fea0d`, 08:07 local = 15:07Z, KST day
boundary). Both session-only; re-arm per HANDOFF §1. Predecessor:
`2026-08-05-automation-monitoring.md` (cycles 49–74 — note: cycles 62–74,
which fell on UTC 08-06, were appended there before the roll; this file
starts at cycle 75).

Owner's standing questions each cycle: working per plan? losses and WHY
(RUN AI reading)? what we missed? how-it-works + plan-16 docs healthy?
Suggestions + shipped solutions.

---

## Inter-cycle ship — 2026-08-06 12:10Z — owner asked to cover the FILL side; PRs #260 + #261

Owner: *"can we cover?"* on cycle 83's finding that trades are executing at
frozen marks. Two parts, AI-first order, image `20260806-fillorder`.

### Part 1 — the lesson I owed

**#259 shipped an observable with no lesson.** `_mark_freshness_line` gave
the desk the FACT of a motionless tape and **no skill attached any
judgment to it.** Data Honesty already teaches *"if a needed input is
missing or stale, treat it as a reason for caution"* — a frozen price is
precisely the case it missed, because it does not look stale at all. It
looks like a healthy quote, **and it still fills.**

The clause now refuses OPEN/ADD and level-setting on a motionless price,
and carves out reduce/close as the one act that still makes sense.

### Part 2 — the record the desk cannot keep

`fill_audit` splits realized P&L into earned vs booked-against-a-stalled
tape. Signature: two fills on the SAME symbol at the SAME price to full
float precision, separated by real time. **Live prod, first run:**

| run | symbol | price | gap | notional |
|---|---|---|---|---|
| 977 | GC | 4320.700195 | 181m | 712.21 |
| 979 | SI | 62.099998 | 172m | 2,572.69 |
| 968 | USDKRW | 1428.310059 | 136m | 32.60 |
| 960 | SI | 62.320000 | 45m | 2,444.25 |
| 979 | SI | 62.099998 | 36m | 5,145.39 |
| 960 | SI | 62.099998 | 35m | 1,217.81 |

**$12,124.96 of notional transacted at a stalled price**, across 3
symbols — and correctly silent on BTCUSDT and ETHUSDT, which move.

### The budget was measured, not bumped

The clause overflowed `trader/us-stock` by **166 chars** and **silently
dropped `execution-plan-check`**, a 667-char safety skill. That
combination sits at **~33,890 of 34,000** while every other site/market
pair has 3,700–30,800 spare. Room came from compressing this catalogue's
own arm lesson (mine, #253/#259) — **not** a fifth `MAX_BLOCK_LEN` raise
— and the ceiling is now documented at the constant.

### Three defects in my own work, all caught before or at verification

1. **The skill test was appended AFTER `if __name__ == "__main__"`** and
   was never collected. Fail-before caught it.
2. **Its guard would have passed vacuously** if Data Honesty ever left a
   site. Now asserts the skill's presence unconditionally.
3. **`fill_audit` paired fills in `seq` order** — and `run_events.seq` is
   **per-run**, so a cross-run scan interleaved them out of time order.
   The first live run printed run 960's 08:18:07 fill as the "repeat" of
   run 979's 08:54:26 one — **a repeat predating its first**. Fixed in
   **#261** (`ORDER BY ts, seq`) with a regression test that seeds two
   runs whose seq order reverses their time order. The corrected total
   rose from $6,979.57 to $12,124.96.

**That is the THIRD time live data has caught a defect in one of these
tools that its own unit tests passed** (#253's flatten-timestamp and
duplicate-status-row traps were the first two). Fixtures are tidy; prod
is not.

**Verified:** fail-before real on both PRs, mutation 6/6, 3534 pass, ruff
clean; in-image 14/14 fill_audit + 47 skills OK; frozen judgment renders
on all four sites and `execution-plan-check` is back on trader; DB rows
`data-honesty` and `position-management` both `seed-upgrade` at 12:07:00
(durable); 0 tracebacks; docs 200/200. Verified twice.

⚠️ **Still the owner's call:** the CAUSE. Alpha Vantage rate-limited at 25
req/day; the feed answers "Successfully fetched" with a stale quote. And
whether a frozen mark should ever BLOCK a fill — deliberately not built,
because that halts trading.

---

## Cycle 83 — 2026-08-06 10:58Z (prod DB clock)

**1. Working per plan?** Yes. Fresh `20260806-deskeyes` stable — **0
tracebacks** in either container since deploy, 8 runs live, docs 200/200,
`ratchet_audit` EXIT=0, events current to the second.

**2. Losses and WHY — the biggest single-beat drop today, and it came
from a CORRECTLY-shaped decision.** Ledger **−20.18 → −30.05**.

**975 BTCUSDT took −11.51 on one reduce**, the whole of the move:

| | |
|---|---|
| 05:37:34 | buy 0.0730544 BTC @ **64870**, fee 2.1326 |
| 10:54:43 | sell 0.0365272 @ **64584**, fee 1.0616 |

`(64584 − 64870) × 0.0365272 − 1.0616 = −11.51` ✓, and with the entry fee
the run stands at −13.64 on a $4,739 notional.

**This is not a #245-shaped loss.** The desk used the **partial verb**
(`reduce` 0.5, conviction 0.63), on a losing position, after 5h17m — the
exact discipline the skills teach. The price simply went **−0.44%**
against it. This is the "we can not fix 100%" case: right shape, losing
outcome.

Worth noting rather than acting on: **fees are 3.194 of the 13.64 = 23%
of the loss.** Round trip is ~0.09% against a BTCUSDT ordinary day of
0.915%, so the hurdle is ~10% of a normal day — not dominant here, but it
compounds with every reduce.

Also 977 GC banked +1.65 and 968 +0.14. DRIFT widened to −20.53 purely
because 975's and 977's closes had not yet emitted their next-cycle
adapts — the documented lag, not a new hole.

**3. What we missed — a consequence of the freeze I had not stated.**

**Trades are EXECUTING at frozen marks.** 977 exited GC at
**4320.700195** — the identical price it has printed for 70+ minutes. The
freeze is therefore not only a decision-quality problem, it is a **fill-
price** problem: the book is being marked, and now transacted, at a
number that is not moving. The +1.65 it booked is measured against that
stale price.

*First post-#259 decision:* 977 cycle 8 at 10:58:41 (deploy was 10:56:42)
chose `reduce` 0.5 at conviction 0.80 and did **not** re-arm — while
holding a standing arm the new line now shows it (price_below 4285,
reduce 0.5, set 43 min earlier). That is exactly the intended response to
`_standing_arm_line`, but it is **n=1 and I cannot see the prompt**, so
it is recorded as data, not as proof the line worked.

*Watch (vii):* `conviction_missing` **6 of 64** decisions today (9.4%, up
from 7.7%). *Watch (ii):* `armed_exit` still **0** fleet-wide.

**4. Docs.** Both 200.

**5. Shipped.** Nothing this beat — #259 landed two minutes before it and
needs live cycles to judge, not another change on top.

---

## Inter-cycle ship — 2026-08-06 10:56Z — owner asked for solutions to cycle 82's items 3 and 5; PR #259

Owner: *"try to make solution for 3,5."* Both shipped in one PR
(`a6f752f`, image `20260806-deskeyes`). Both are the same shape as
#241/#244/#245 — **the desk judged against something it cannot perceive**
— so both are AI-first: facts into the brief, judgment left to the desk.
**Neither halts trading.**

### Item 3 — a fresh timestamp is not a fresh price

`_mark_freshness_line` counts trailing `equity` events whose `unrealized`
is unchanged and states it. Deliberately **not** a gate: I raised in
cycle 82 that a value-staleness rail *halts trading*, and quiet markets
are real — so the desk gets the observable and stays the actor.

Conservative by construction: `unrealized = (mark − avg) × qty`, so an
add or reduce moves it even under a frozen mark and **resets** the count.
It can under-report a freeze, never invent one.

**Live render immediately found more than I had measured** — SLV, a
us-stock, is frozen too, so this is not a futures/forex problem:

| run | line rendered |
|---|---|
| 968 USDKRW | SAME price for **38** straight reads (~44 min) |
| 972 **SLV** | SAME price for **60** straight reads (~69 min) |
| 977 GC | SAME price for **60** straight reads (~69 min) |
| 979 SI | SAME price for **60** straight reads (~69 min) |
| 975 BTCUSDT | *(silent — it moves)* ✅ |

The detector fires exactly where a freeze was measured and stays silent
on the one symbol that is trading. That discrimination is the evidence
it works.

### Item 5 — 64 arms, zero fires, and the yardstick was the wrong clock

I verified the executor first, so the fix would land on the real cause:
`arm_fires()` 5/5 correct tested live in the image, `_fire_armed_order`
provably reached, and **no level ever crossed**. So the levels, not the
code.

**The skill contradicted itself.** It told the desk *"your cycles are
roughly 45 minutes apart"* and, in the same breath, to place the level
*"inside roughly one ordinary day's move"* — **two horizons ~30× apart**.
The desk followed the yardstick it was given. Re-anchored to the clock
the arm actually runs on, with the 64/0 evidence stated in the lesson.

**And one claim in it was simply false.** *"Each cycle's arm replaces the
last"* — `_store_armed_order` runs only on `intent == "arm"`, so a reduce
or hold cycle leaves the arm standing. Corrected to what the code does,
and `_standing_arm_line` now shows the desk the arm it already has. Live
proof of why that was needed: **975's arm had been standing 137 minutes
unrestated**, and 968's `close 1.0` 89 minutes.

Skill text was **tightened to fit the existing budget** rather than raise
`MAX_BLOCK_LEN` a fifth time — the same call as #253.

**Verified:** fail-before 16/16, mutation 6/6 (incl. both unwirings and a
revert to the day-yardstick), 3519 pass, ruff clean; in-image 13/13 then
the full 46-test skills suite OK; both lines wired on **both** prompt
paths; skill text live on both sites with the old yardstick gone; DB row
`position-management` shows `seed-upgrade` at 10:56:42 (durable, not just
in the image); 0 tracebacks; docs 200/200. Verified twice.

⚠️ **Still open for the owner:** the *cause* of the freeze. Alpha Vantage
is rate-limited at 25 req/day and the feed answers "Successfully fetched"
with a stale quote. That is a provider/tier decision, not a code one.

---

## Cycle 82 — 2026-08-06 10:19Z (prod DB clock) — 🚨 FROZEN MARKS

**1. Working per plan?** Containers healthy on `20260806-prunebackups`
(tag compared per the new trap — unchanged since 09:45), docs 200/200,
**0 tracebacks**, `ratchet_audit` EXIT=0. But see below: healthy
processes are running against a **frozen tape**.

**2. Losses and WHY.** 08-06 ledger **−20.18** (was −19.21). The −0.97
decomposes exactly: 978 ETHUSDT's entry fee **−1.1059** plus 968's reduce
**+0.14**. That is component (a) — entry-side fees — the by-design term,
not a trading loss.

**3. 🚨 THE FINDING: futures and forex marks have not moved in over two
hours, and the staleness guard cannot see it.**

| symbol | last change | frozen for | value |
|---|---|---|---|
| GC | 07:57:40 | **2h26m** | 4320.700195 |
| SI | 08:18:07 | **2h05m** | 62.099998 |
| USDKRW | — | ~40m+ | 1428.310059 |
| BTCUSDT | continuous | — | moves 64564–64936 ✅ |

Evidence chain, each step checked rather than assumed:

1. **Marks are FRESH by timestamp** — `price_updated_at` = 91s old on all
   four. So `mark_age_ok` passes.
2. **`_maybe_emit_equity` only emits on a CHANGED total or a heartbeat.**
   979 produced 36 consecutive samples with identical unrealized, 977
   produced 8. The value genuinely did not move.
3. **Three SI trades printed at exactly 62.099998** across 08:18→08:54,
   and SI had been stepping normally before that (62.55 → 62.47 → 62.32
   → 62.10).
4. **Calling `get_price_from_market` directly returns the same frozen
   numbers** — GC 4320.7, SI 62.1 — and logs *"Successfully fetched"*.
5. **Alpha Vantage is fully rate-limited**: *"our standard API rate limit
   is 25 requests per day"*, hitting equities, macro, crypto and
   commodities refreshes.

**The guard measures the wrong thing.** `mark_age_ok` checks the
*timestamp* of the last fetch, not whether the *value* changed. A feed
that keeps answering with a stale quote refreshes the timestamp every
90s and is therefore invisible to every staleness check in the engine.

**4. Docs.** Both 200.

**5. What this explains — watch (ii), answered.**

**64 arms authored, ever. `armed_exit` events: 0. Not one has ever
fired.** I verified this is *not* a dead executor:

- `order_intent.arm_fires()` returns True on all should-fire cases and
  False on all should-not (5/5 correct, tested live in the image).
- `_fire_armed_order` is provably reached — `_maybe_emit_equity` sits
  after it in `_control_active`, and equity events are flowing.
- **No arm level has ever been crossed.** Reconstructing price from
  equity events, all four standing arms remain 0.48–0.88% short:
  968 0.877%, 975 0.533%, 977 0.826%, 979 0.483%.

So the executor is sound and the levels were never reached — and on GC,
SI and USDKRW they *could not* be reached, because the price is not
moving at all.

Standing arms, all reachable-by-the-skill except 968:

| run | verb | ordinary days |
|---|---|---|
| 979 SI | reduce 0.5 | 0.24 ✅ |
| 977 GC | reduce 0.5 | 0.61 ✅ |
| 975 BTCUSDT | reduce 0.5 | 0.62 ✅ |
| 968 USDKRW | **close 1.0** | **2.65** ❌ |

*Also noted:* `_store_armed_order` is called **only when
`intent == "arm"`**, so a cycle that reduces or holds leaves the previous
arm standing. 968 executed a reduce at 10:12:40 and its 09:27 `close 1.0`
arm still stands. The code comment says "each cycle's arm replaces the
last" — that is true only of arming cycles.

**Shipped: nothing, deliberately.** Stated plainly because the owner is
asleep: the natural fix — a *value*-staleness guard — would **halt
trading** when it fires, and shipping a trading-halting rail unattended
is not a call I should make alone. The root cause may also be an API
tier/key decision (Alpha Vantage exhausted; memory already carries a
"watch FMP tier thinness" item) which is the owner's, not mine.

**→ TOP OPEN ITEM FOR THE OWNER.** Two separable decisions: (a) the data
provider/tier, (b) whether a frozen-value guard should pause runs, warn,
or only be reported by a read-only detector like `ratchet_audit`.

---

## Cycle 81 — 2026-08-06 09:49Z (prod DB clock)

Owner is asleep from this beat; the loop continues on cron `688d79c1`
(`13,43 * * * *`) plus the 24h sweep `d869c56a` — both confirmed armed.

**1. Working per plan?** Yes. 8 runs live, `20260806-pendflush`, docs
200/200, **0 tracebacks** over 22m, `ratchet_audit` EXIT=0.

**2. Losses and WHY.** 08-06 ledger **−19.21**, unchanged for a third
consecutive beat — no closes since 08:54. DRIFT −9.56, unchanged and
already explained (#257 is forward-only; both affected runs are
`stopped`). **#257 has not yet been exercised live** — no run has entered
`stopping` since it deployed. That remains the open verification.

**3. What we missed.** Nothing new. **The named watch from cycle 80 is
NOT tripped.** One new arm this beat, and it is a clean one:

| run | verb | distance |
|---|---|---|
| 979 SI | `reduce` 0.5 @ 62.4 | 0.483% = **0.24** ordinary days |

That is well inside the skill's ≤~1 ask. Post-#253 tally is now **5 arms
— 4 `reduce`, 1 `close` = 20% full-book** (down from 25% by dilution, not
by evidence) against the 45% pre-fix base rate. n=5.

Reachability across every post-#253 arm keeps 968 as the *sole* outlier:

| run | ordinary days |
|---|---|
| 979 SI | **0.24** |
| 975 BTCUSDT | **0.75** |
| 975 BTCUSDT | 1.28 |
| 968 USDKRW | 2.03 |
| 968 USDKRW | 2.65 (the `close 1.0`) |

Four of five arms are at or near the ask. 968 is the only run drifting on
both verb and distance — still **n=1**, so the #253 clause stays closed.

**4. Docs.** Both 200.

**5. Shipped.** Nothing. No reproduced evidence; the watch is holding.

**⚠️ A PARALLEL SESSION DEPLOYED MID-CYCLE.** The verification pass found
the containers on `20260806-prunebackups`, not the `20260806-pendflush` I
deployed at 09:26 — another session shipped **#258** (backup pruning) on
top of #257 at ~09:45. Checked rather than assumed, and it is clean:

- `_flush_pending_close_adapts` still wired, still before the flatten
- `ratchet_audit.RATCHET_TS` and `audit_exposures` both present
- `run_engine.py` and `ratchet_audit.py` sha256 **match `origin/main`
  exactly** — nothing of #255/#257 was clobbered

The other session built from fresh main, which is exactly what the
parallel-worktree rule asks for. **Never infer this from a green health
check — an image tag changing under you is invisible unless you compare
it.** `pending_close` adapt events fleet-wide: **0**, confirming #257 is
still unexercised live.

---

## Cycle 80 — 2026-08-06 09:30Z (prod DB clock)

**1. Working per plan?** Yes. 8 runs live, both containers on
`20260806-pendflush`, docs 200/200, **0 tracebacks** since the deploy,
`ratchet_audit` EXIT=0, events current to the second.

**A false alarm I checked before raising it.** `[TradingRuns] tick` was
**absent from the entire worker log** after the 09:27:38 restart, which
reads like a stalled control loop. It is not. `tasks.py:795` prints that
line **only when `dispatched` or `armed_started` or `stopping_finished`
is truthy** — silence means nothing was due. Positive proof the loop is
alive: `_maybe_emit_equity` is called from `_control_active`, on the same
tick as `_control_stopping`, and equity events are landing at 09:31:10.
So the path #257's flush sits on is confirmed running. Recorded as a trap
— a future session could easily mis-call this a dead worker.

**2. Losses and WHY.** 08-06 ledger **−19.21**, unchanged; no realized
movement this beat. `pnl_audit` DRIFT persists at −9.56 exactly as
predicted — #257 is forward-only and both affected runs are already
`stopped`.

**3. What we missed — the first post-#253 counter-example.**

Cycle 79 reported 3 post-#253 arms, all `reduce`, and called it *not yet
significant*. That caution was right: **968 armed `close 1.0` at 09:27:18.**
Post-#253 tally is now **4 arms — 3 `reduce`, 1 `close` = 25% full-book**
against a 45% pre-fix base rate. n=4. **The clause has not eliminated
full-book arms**, and nothing here is significant either way.

**The instance is worse than the verb alone.** 968 *replaced its own
better arm*:

| time | verb | level | distance |
|---|---|---|---|
| 08:42:25 | `reduce` 0.5 | 1442.6 | 1.000% = **2.03** ordinary days |
| 09:27:18 | `close` 1.0 | 1447.0 | 1.309% = **2.65** ordinary days |

It moved the level **further away** *and* **escalated the verb** in one
cycle — on a run that has never been in profit (realized −3.59, peak
−2.08). Watch (ii) asks ≤~1 ordinary day; both are beyond it.

**But this is 968-specific, not systemic** — the split matters:

| run | arm | ordinary days |
|---|---|---|
| 975 BTCUSDT | reduce | 1.28 |
| 975 BTCUSDT | reduce | **0.75** (moved CLOSER) |
| 968 USDKRW | reduce | 2.03 |
| 968 USDKRW | close | 2.65 |

975 is doing exactly what the skills ask — partial verb, and it tightened
its own level on the second pass. Only 968 drifts.

*Watch (vii):* `conviction_missing` = **4 of 52** decisions today (7.7%).

**4. Docs.** Both 200.

**5. Shipped.** **Nothing, deliberately.** One counter-example on one run
is not reproduced evidence, and the standing daily-solution duty never
licenses a thinly-evidenced ship. Logged as a named watch: **a second
run authoring an unreachable full-book arm re-opens the #253 clause.**

---

## Inter-cycle ship — 2026-08-06 09:28Z — owner asked for a solution to the pnl_audit DRIFT; PR #257

Owner: *"make solution for pnl_audit는 여전히 08-06 DRIFT … 알려진 미수정
adapt-flatten 누락 문제입니다."*

**First finding: it is NOT mostly the known flatten gap.** Decomposing the
day's −9.56 delta to the cent:

| component | USD |
|---|---:|
| (a) entry-side fees, by design | −3.2027 |
| **(b) adapt NEVER emitted** | **−6.6894** |
| (c) 973's pre-#249 flatten | +0.3967 |
| (d) 08-05 close landing on 08-06 | −0.0644 |
| **sum** | **−9.5598** = observed |

#249's emission fix **is working**: 3 of today's 4 flattens emitted
`flatten_close` adapts (969, 976, 960); only 973 predates the deploy.

**(b) is a different, unfixed defect — and #249's own comment states its
mechanism while fixing only one instance of it:**

> "run_feedback derives its own adapt events from closed SIGNALS on a later
> cycle, and a flattened run is stopping/stopped, so no later cycle ever
> processes this leg"

True of the flatten leg — and equally true of **every other close still
pending when the run stops**. Run 960 reduced at 08:18:07 (−4.3752) and
stopped at 08:53; run 976 reduced at 05:40:01 (−2.3142) and was flattened
at 05:40:02. Neither ever reached the adapt stream. **The same failure shape
twice: a number journalled only "next cycle" is lost precisely when there is
no next cycle — which is precisely when the run died.**

**Fix (PR #257, image `20260806-pendflush`, main `4041812`).**
`_flush_pending_close_adapts` at the **top** of `_control_stopping`, before
all three terminal branches and before the flatten leg exists as a signal.
Emits, never adapts — a terminal run's `size_mult` ladder is moot, so it
deliberately skips the claim fence `save_state` needs (a stopping run is
unclaimed; the write would be discarded). Idempotent by construction: the
watermark is read back out of the run's *own* adapt events, so the bounded
flatten retry cannot double-journal.

**NOT an AI-first fix, deliberately.** The desk cannot emit the platform's
record of what the desk already did — the "code only where the desk cannot
be the actor" case, stated rather than skipped.

**Verified:** fail-before 7/7, mutation 4/4 (incl. unwiring, and moving the
call after the flatten), 3504 pass, ruff clean; in-image 7/7 then the full
82-test `test_run_engine` OK; wiring confirmed live from the image twice;
0 tracebacks; docs 200/200. **Read-only replay proves it would have caught
exactly the two lost legs: run 960 signal 475 = −4.3752, run 976 signal 469
= −2.3142** — the decomposition's (b) to four decimal places.

⚠️ **The fix is forward-looking.** Today's −6.69 is already lost (both runs
are `stopped`, and `_control_stopping` only visits `stopping`), so the
08-06 DRIFT line will not change retroactively.

⚠️ **Open, not shipped:** even after this, component (a) — entry-side fees,
which the ledger charges on the opening leg and the adapt stream never sees
— will keep the delta non-zero, ~−3.20 on a 4-newborn day against a $5.00
tolerance. On busy days the alarm will still fire benignly. Deciding whether
to model (a) in the tolerance is a separate call; **do not chase it as a bug**.

---

## Cycle 79 — 2026-08-06 08:53Z (prod DB clock)

Fired 59 seconds after cycle 78's final verification, so this is a short
beat with one genuine observable and **nothing to ship**.

**1. Working per plan?** Yes. 8 runs live (979 SI newborn 08:53), both
containers on `20260806-band2`, docs 200/200, **0 tracebacks** in both
containers over 60m. `ratchet_audit` EXIT=0.

**2. Losses and WHY.** 08-06 ledger **−14.58**, unchanged since 08:49 —
no new realized loss this beat.

**960 SI closed +28.47** (peak 42.84), the day's best run, on
`stop_event:at_time` — its 24h horizon expiring exactly one day after
birth (08-05 08:53 → 08-06 08:53). **Not** a rail fire. It did reduce
0.5 at 08:18:07 and is worth checking against the band: book 39.22 →
19.61 at mark 62.10 gives arm-full **4.87** and arm-after **2.44**
against a peak of **42.84**. The peak cleared *both* arms by ~9×, so the
floor was armed under old and new code alike and simply never reached —
correct behaviour, and **non-discriminating**, exactly as the auditor
reports (0 in-band rows for 960).

**3. What we missed.** Nothing new. The post-#251 discriminating sample
is still **n=0** and the in-band table still reads one row (976,
pre-fix, FLATTENED).

*The one observable:* since #253 deployed at 07:51:01 the desk has taken
**7 decisions — 3 arms, all `reduce` 0.5; 3 executed reduces; 1 hold.
Zero `close 1.0`, zero full exits.** Against the measured pre-fix base
rate of **45% full-book arms**, three consecutive partials carries
p ≈ 0.55³ ≈ **0.17** under the null. Suggestive, **not significant** —
the base rate would predict ~1.4 full-book arms in three. Keep counting;
do not call it working yet.

*Noted, not alarming:* 968 USDKRW carries `peak_pnl_usd` = **−2.08**. A
negative peak can never satisfy `peak >= arm > 0`, so the breakeven floor
is simply inert on that run — which is the intended shape for a position
that has never been in profit.

**4. Docs.** how-it-works 200, liquidation-defense 200.

**5. Shipped.** Nothing. No reproduced evidence called for a change, and
a quiet beat is the correct outcome one hour after two ships.

⚠️ `pnl_audit` still reports 08-06 DRIFT (ledger −14.58 vs adapt −5.28,
3 flattens) — the known unfixed adapt-omits-flattens gap.

---

## Cycle 78 — 2026-08-06 07:55Z (prod DB clock)

**1. Working per plan?** Yes. 8 runs live, both containers on
`20260806-gap77`, docs 200/200, zero tracebacks (the six log "error"
lines are feed counters: `Market Intel inserted=0 errors=4`, not
exceptions). Events current to the second.

**2. Losses and WHY.** 08-06 ledger **−13.77** (tool, ledger
authoritative). Closed today: 949 −15.51, 976 −5.24, 973 −0.70, 969
**+10.57**. 949 HYPEUSDT ended on `stop_event:at_time` — a 2-day run
timing out, not a rail failure.

**976 is the cycle's real finding, and it is a confirmation, not a new
defect.** Its 47-minute life:

| time | event |
|---|---|
| 04:54:31 | buy 1.3166 GC @ 4317.40 |
| 05:40:00 | desk decides `reduce` 0.5 — a deliberate partial exit |
| 05:40:01 | sell 0.6583 @ 4314.10 |
| **05:40:02** | **`stop_event:trailing_lock` flattens the remainder** |

Loss −5.24 on a **0.088%** adverse move; fees were 0.568 of it (11%).
This is unambiguously the **breakeven ratchet**, not the legacy trail:
`trail.activate_usd` = **85.26** against a lifetime peak of **7.22**, so
the legacy lock could never have armed. It is the textbook instance of
the defect #251 was built to kill — and it happened **one hour before
#251 reached prod (06:40)**. `run_engine` already cites 976 by name.

**3. What we missed — and the correction owed.**

*Correction.* Cycle 77 reported the full-book arm as **n=1**. That was
wrong. Over 08-04 → 08-06 the desk armed **42 times, 19 of them
`close 1.0` — 45%**, not one. The clause shipped in #253 was therefore
addressing a base rate, not an anomaly. Post-#253 arms so far: **2, both
`reduce` 0.5** (975 at 07:53, and 977's third partial at 07:57:40).
n=2 is not yet a trend.

*The gap.* `ratchet_audit` can alarm on a bad fire but is **structurally
blind to the fix working**. A post-fix sample of zero fires reads
identically to "the rail never got a chance" — and it printed exactly
that while 976 sat one hour the wrong side of the boundary. Shipped as
**PR #254**: count the *reduces*, not just the fires. The anchor only
decides anything inside one band — the lifetime peak clears the arm on
the **shrunken** book but not the arm on the **largest book ever held**.

*A near-overclaim, caught.* 977 (same symbol, same trail config,
`reduce` 0.5 at 07:12, survived, still running) looks like the positive
control for #251. **It is not.** Its peak of 21.08 cleared *both* arms
(5.69 and 11.37), so both code versions behave identically — it proves
nothing either way. 976 landed inside the band (5.68 ≤ 7.22 < 11.36).
A test now pins that distinction so no future reader can fudge it into
evidence. **The discriminating post-#251 sample is still n=0**, and the
band is narrow (a 2× window plus a retrace to the floor), so an empty
sample is expected for a while rather than suspicious.

**4. Docs.** how-it-works 200, liquidation-defense 200.

**5. Shipped — TWO PRs, because the first was wrong.**

**PR #254** added the in-band reduce table. **Running it live got 976 —
the single case whose answer is known — BACKWARDS**, reporting the
textbook retro-arm as `survived`. **PR #255** fixes three live-only
defects:

1. **Fire matching was exact-second.** 976 reduced at 05:40:01 and was
   flattened at 05:40:02. Now a 90s window, lower-bounded so a fire
   *before* a reduce never counts.
2. **It judged reduces that predate the rail.** The ratchet merged
   2026-08-06 01:45Z; the table scored eight 08-01/08-02 reduces against
   it and called them all "survived" — eight counts of evidence for
   nothing.
3. **A sliver arm printed as `0.00`** — a fractional book's arm is
   $0.004, and at 2dp the band read as trivially satisfied on 9 of 11
   rows. Now 4dp.

**Correction to an inherited claim.** The snapshot recorded **973 as the
second retro-arm instance**. It cannot be: its fire (00:21:23) predates
the ratchet's own merge by **84 minutes**, and its reduce was 2h02m
earlier — not the same-second escalation signature. **Confirmed
retro-arm count is n=1 (976), not 2.** What actually fired 973 is
unexplained by either emitter under its stored config (legacy
`activate_usd` 82.42 vs peak 1.72) — logged as an open question, not
guessed at.

Live table now reads exactly one row — 976, pre-fix, **FLATTENED**.

Deployed `20260806-band2` (main `4ea2a00`). Verified: containers on the
new image; auditor runs from the image twice with identical output;
38/38 in-image tests twice; events current to the second (08:49:53 vs
NOW 08:49:54); 8 runs live; **0 tracebacks** both containers.

⚠️ `pnl_audit` reports 08-06 **DRIFT** (ledger −14.58 vs adapt −5.28, 3
flattens) — the *known unfixed* gap where the adapt query omits forced
flattens. Not caused by this change (read-only, `ratchet_audit` only).


---

## Inter-cycle ship — 2026-08-06 ~08:1xZ — owner asked for solutions to cycle 77's two gaps; PR #253

Owner: *"make solution for [the two honest gaps]."* Both shipped in one
PR (#253, branch `20260806-gap77`).

### Gap 1 — #251 was unproven live, and proving it was a manual chore

The problem was never that the fix was wrong; it was that **the only
evidence path was a human remembering to hand-audit every future
`trailing_lock`** — the same arrangement that let the retro-arm defect
run undetected in the first place. So the watch became a tool.

`ratchet_audit.py` replays each fire's own trade events and asks: was
the book at the fire smaller than the largest book that run ever held?
Post-fix that must never happen — such a fire is flagged and the module
**exits non-zero**, like `pnl_audit` on ledger drift. An empty post-fix
sample prints *"post-fix sample is EMPTY — the anchor is untested
live"* rather than implying success.

**Running it against live prod caught two defects in my own tool that
the unit tests did not**, and both are now pinned by regression tests:

1. **The fire's own flatten leg carries the SAME timestamp as the fire.**
   A naive `ts <= fire_ts` snapshot counted the liquidation as part of
   the preceding book, so **15 of 16 fires read as a flat → "shrunken"
   book**. Post-fix, the first genuine full-book fire would have raised
   a false alarm. (A desk *reduce* in the same second must still count —
   that is the actual signature — so the filter keys on the flatten's
   `client_order_id`, not on time.)
2. **A stop emits TWO `run_status` rows** (`running→stopping`,
   `stopping→stopped`) and both contain "stopping" — every fire was
   double-counted. Now matched on the transition INTO stopping.

**And I corrected an overclaim before shipping.** The first draft
declared a shrunken-book post-fix fire a `*** REGRESSION ***`. But
`stop_event:trailing_lock` is **shared with the legacy trailing lock**,
whose `trail.activate_usd` is a **fixed dollar figure written at build**
— so the legacy trail *cannot* retro-arm, and a shrunken-book legacy
fire is perfectly normal (the desk banked some, the trail caught the
rest). The tool now flags for **REVIEW** and names the disambiguator:
the worker log line `breakeven ratchet fired`.

**Live result (deduped, corrected), 8 fires since 07-01:**

| run | max book | at fire | verdict | era |
|---|---|---|---|---|
| 119 | 760.04 | 760.04 | full-book | pre-fix |
| 125 | 1.32 | 1.32 | full-book | pre-fix |
| **854** | 57.28 | 37.32 | **shrunken** | pre-fix (legacy trail) |
| 897 | 41.58 | 41.58 | full-book | pre-fix |
| 919 | 84.64 | 84.64 | full-book | pre-fix |
| **921** | 44.43 | 1.37 | **shrunken** | pre-fix (legacy trail) |
| **973** | 22.24 | 11.12 | **shrunken** | pre-fix (ratchet — the defect) |
| **976** | 1.32 | 0.66 | **shrunken** | pre-fix (ratchet — the defect) |

`0 post-fix; 0 to review` — the honest state. 854/921 carry the shape
but predate the ratchet entirely, so they are NOT extra instances of the
defect; noting them as such would have been the overclaim.

### Gap 2 — the arm vocabulary never got the exit-verb lesson

968 armed a **full-book close**. #245 taught the partial verb for
*discretionary* exits only; the skill text contained **no arm-sizing
guidance at all** — structural, not an n=1 behavioural read, which is
why it did not need a second occurrence. An armed level fires
unattended: the size armed is the size taken, with no cycle in between
to reconsider, and whole-book exits carry **91% of all measured loss**.
`position-management` now teaches the partial verb as an arm's default
and names why an arm repeating the stop with a full close buys nothing.

**Sized to fit the EXISTING budget** rather than raising `MAX_BLOCK_LEN`
a fifth time — the first draft overflowed (pushing `Execution Plan
Check` out of the block) and was tightened instead.

Verification: fail-before on the skill clause and on both live-data
defects; mutation ×3 on the auditor, each killed by its pinned test;
ruff green; **3381 backend tests green**.

---

## Cycle 77 — 2026-08-06 07:00Z — the arm-reachability skill LANDED: an arm inside 0.60 ordinary days (was ~25)

DB clock 07:00:12. Session handover cycle (new account); **both crons
re-armed** — 30-min `688d79c1` (`13,43 * * * *`) and the 24h sweep
`d869c56a` (08:07 local = 15:07Z). Prior session's `3e0160dc` cancelled.
Prod `20260806-armanchor`, 0 tracebacks, docs 200/200.

### 1. Working per plan — yes, and the arm watch produced its best result yet

**#247's open question was whether the desk would arm REACHABLE levels.**
Measured against each symbol's own ordinary daily move:

| when | run | arm | distance | ordinary days |
|---|---|---|---|---|
| 08-05 (pre-skill) | various | — | 11–13% | **~25** |
| 08-06 00:22 | 968 | `price_above 1440 → reduce 0.5` | 1.21% | 2.5 |
| **08-06 06:26** | **977 GC** | **`price_above 4350 → reduce 0.5`** | **0.80%** | **0.60** ✅ |
| 08-06 06:25 | 968 | `price_below 1414 → close 1.0` | 0.87% | 1.76 |

977's arm is **inside one ordinary day** — the skill's actual ask, met for
the first time. Progression 25 → 2.5 → 0.60 days across two days. It is a
BANKING arm (`reduce 0.5` above), not merely protective.

**Still zero `armed_exit` events fleet-wide.** Reachable ≠ fired; the
executor remains unproven end-to-end. That is the next thing to catch.

**New observation (n=1, not a finding):** 968 armed **`close 1.0`** — a
full-book arm. The measured killer is the whole-book dump (full closes =
91% of all loss), and #245's exit-verb lesson targets *discretionary*
exits; the ARM vocabulary was never given the same `reduce`-over-`close`
teaching. Watch whether armed full-closes recur; if a second appears,
the AI-first fix is a clause in `position-management` extending the exit
verb discipline to armed levels.

### 2. Losses and WHY — 08-06 ledger −15.48 (pnl_audit `ok`, delta −4.93)

| run | realized | cause |
|---|---|---|
| 969 HG | **−8.41** (−2.08, −3.10, flatten −3.24) | `retire_consecutive_losses` after 3 losses; review honest: "returned −0.5% vs the anticipated +4%". The rail cutting a bleeding thesis — working as designed |
| 976 GC | −2.64 | the **pre-fix retro-arm death** (#251 shipped 06:40Z, after this) |
| 968 USDKRW | −1.29 net | three small legs, size laddered 0.5→0.25 by adapt |
| 960 SI | +1.80 net | banking |

No new pathology. The day's largest single loss is **−3.24** — the
971-class tail (−58) remains absent, and the whole-book-dump shape did
not appear.

### 3. What we missed — nothing new; two honest gaps

- **Post-#251 sample is n=0.** Both 08-06 `trailing_lock` fires (973
  00:21, 976 05:40) predate the 06:40Z deploy. The retro-arm trap is
  fixed in code and verified 3× at ship, but **no live fire has yet
  exercised the new anchor.** Do not call it proven.
- `armed_exit` still 0 (above).

### 4. Docs — `how-it-works` 200, `plan-16` 200.

### 5. Suggestions / shipped

Nothing shipped this cycle — no reproduced evidence supported a change,
and per §1 the daily obligation never licenses a thin ship. Two triggers
now armed: a second armed full-close, and the first post-#251 ratchet
fire (audit peak/now/arm against the max-book anchor).

Book at read: 977 GC +6.3, 968 +0.4, 972 +0.3, 975 −4.6, 960 −15.5
→ net ≈ **−13.2** unrealized across 8 runs.

---

## Cycle 76 — 2026-08-06 06:54Z — first post-#251 beat: all quiet, and the fix's intended shape is visible on 960

DB clock 06:54:04. Image `armanchor` up 10 min, 0 tracebacks, **0 ratchet
fires, 0 daily-move blindness logs**, pnl_audit `ok` (−15.48, unchanged —
no closes since the ship), docs 200, events fresh.

**Fleet grew to 8:** 978 ETHUSDT born 06:48 (969's retired slot, HG on
24h cooldown → different symbol). Cycle-1 `hold` at conf 0.45 — a patient
newborn, no forced entry (newborn-guard count n=6).

**960 SI is the fix working as intended:** unrealized slid −6.9 → −16.47
(total +20.75, down from +30.36; adapt loss-cooldown active). Its peak
+42.84 ≥ its max-book arm (~9.8), so the breakeven floor is GENUINELY
armed — if total ever touches 0 the run flattens with its +37 realized
intact. That is the floor protecting a real winner's breakeven, exactly
what it is for; under the old sizing nothing changes here either (book
grew, not shrank). The residual-shape watch (big paper gain
round-tripping to the BRAKE on an unarmed floor) does not apply — 960's
floor is armed.

Books: 960 +20.75, 977 +2.88 (GC gave back most of the pop; arm at 4350
stands), 968 −3.47 but open book turned POSITIVE (+0.39, short finally
paying; banking arm `price_below 1414 → close` stands), 975 −6.22 (BTC
long drifting against — no brake proximity, desk's next read due), 972
+3.24, 961/974/978 flat. 974 still sell-gated at sub-0.5 conf; idle-retire
will eventually collect it if SOL stays refused — correct behaviour.

Nothing shipped; nothing warranted. Next beat :13.

---

## Cycle 75-FIX — 2026-08-06 06:44Z — owner said "fix 2,3": #251 SHIPPED to prod, retro-arm removed, pnl_audit in-image

Owner directive on the cycle-75 report: *"fix 2,3."* The retro-arm defect
is deterministic (source + live-log arithmetic, not a statistical claim),
so the n=1 bar did not apply; shipped as **PR #251**, prod image
**`sooppiy-backend:20260806-armanchor`** (containers up 06:40Z).

**The fix:** `_run_max_abs_qty(run)` replays the run's own trade events
(pnl_audit's signed convention) and the breakeven floor's arm is now
sized off **the largest book the run ever held** — a reduce can no longer
lower the bar under an already-earned peak. Strictly conservative vs the
old sizing (constant books and adds byte-identical); fail-soft to the
current book. Plus: `_typical_daily_move_pct` now logs when a symbol has
no usable daily history (976's silent GC blindness).

**Pipeline:** fail-before 9/9 red → pass-after 17/17; 4 verified
mutations killed (`__pycache__` cleared); ruff clean; local suite 3369 +
1312 subtests green; CI green (2nd full pass, backend 12m12s); squash
merge `77c628a`; drift guard held (prod ≡ parent `29018da` pre-copy);
in-image `Ran 17 — OK` + anchor-wiring assert + `import pnl_audit` OK.

**Verified 3× live:** (1) worker replays 976 → max book **1.316579**,
arm 11.36, floor on the exact death inputs now **False** (old sizing:
True); `docker exec … -m pnl_audit` works — **08-06 reads `ok`, delta
−4.93, EXIT=0** (runbook item closed, §4 caveat lifted). (2) 6 min on new
image: 0 tracebacks, 0 spurious ratchet fires. (3) fleet cycling — 7 runs
intact, 34 skills, events fresh (06:44:29Z), margin bookkeeping flowing,
and TWO new banking arms since 05:53: 977 `price_above 4350 → reduce`
(~+0.9% ≈ inside one GC ordinary day — the #247 skill's ask), 968 rotated
to `price_below 1414 → close`.

**CORRECTION to the 05:53 note:** 973 was NOT a clean small-book fire.
Live replay shows its max book was **22.24 vs 11.12 at fire** — its
morning fire was ALSO retro-arm-class (a reduce had halved the book
earlier). **Both of today's ratchet fires were the same defect (n=2)**;
the "n=1, watch first" caution was over-conservative and the ship is
better evidenced than first stated. Under the new anchor neither would
have fired (973: arm 3.29 > peak 1.72; 976: arm 11.36 > peak 7.22).

**Post-ship watch (next cycles + 15:07Z sweep):** ratchet fire rate
should drop; every `trailing_lock` fire must now audit as same-size-book
genuine (log carries peak/now/arm); the tail rail (max_loss/drawdown
brake) still backstops runs whose peak never covered their biggest book.

---

## Cycle 75 — 2026-08-06 05:53Z — resumption cycle; the ratchet cut a recovering winner, and the desk's `reduce` armed the rail that flattened it

DB clock `05:52:59` (= UTC). Prod image `20260806-flatpnl` on both
containers, host app tree ≡ `origin/main` (sha256 ×5 files). 0 tracebacks
90 min. Events fresh (MAX ts 05:52:57Z). how-it-works 200 (SPA shell; full
DOM check due at the sweep). liq-defense: `liquidation_watch` task running
since the 00:35:45Z worker start. `[TradingRuns] tick` healthy —
eval_failures 0.

**Fleet (7):** 960 SI, 961 UBER, 968 USDKRW, 972 SLV, 974 SOLUSDT,
975 BTCUSDT, **977 GC (new — replaced 976)**.

**P&L (pnl_audit, mounted — the RUNNING IMAGE LACKS the module, see
below):** UTC 08-05 ledger **+7.09** (2 flattens). UTC 08-06 so far ledger
**−15.48**, adapt −10.43, delta −5.05, 3 flattens, verdict `*** DRIFT ***`
— **explained, NOT a #249 regression** (decomposition below). Open books
right now: 960 −6.86 unreal (realized +37.22), 968 −0.48 (r −3.86),
972 +0.27 (r +2.96), 975 −2.78 (r −2.13), 977 **+16.88** (r −0.28),
961/974 flat. Net open unrealized ≈ +7.1.

### The main finding — run 976 GC, born 04:53Z, dead 05:40Z, −5.24

Timeline (all confirmed from `run_events` + worker log):

1. **04:53:44Z** — GC daily-bars fetch FAILED at build ("possibly
   delisted; no price data found (1d …)"). One-shot; 977's build at
   05:40 did not log it. Consequence: `_typical_daily_move_pct` had no
   candles, so 976's Exit-scale line would render WITHOUT the
   ordinary-day sentence (the line itself still renders — fail-soft only
   drops that sentence).
2. **04:54:30** — cycle 1: buy 1.3166 GC @ 4317.40, conviction 0.8725,
   authored stop 0.76% / target 2.0%. (Newborn-guard count → n=5 incl.
   977; no cycle-1 retire pathology.)
3. Position ran to **peak +7.22** (05:13Z), then faded to −0.68 by
   05:32, −4.50 by 05:34:53 (GC dropped 4317→4313 fast).
4. **The breakeven floor was NOT armed this whole time**: arm_usd on the
   full book = qty·mark·0.001·2 ≈ **11.36 > peak 7.22**. The configured
   trail (activate 85.26) was never in play either.
5. **05:40:00** — cycle 2: decision `sell` conf 0.68 → **order_intent
   `reduce 0.5`** — the desk chose the cheap verb on adverse drift
   (−0.076%). **Exit-verb #245 evidence n=2** (line rendered; caveat:
   day-sentence likely absent per (1), and the move was tiny).
6. **05:40:01** — the reduce **halved the book → arm_usd fell to 5.68 <
   peak 7.22 → the floor retro-armed against a peak earned by the FULL
   book**, saw total −5.10 ≤ 0, and fired the same second (worker log:
   `breakeven ratchet fired (run 976): peak=7.22 now=-5.10 arm=5.6792`).
   Remaining half flattened −2.64. Run total **−5.24**.
7. **05:40:38** — fleet planner rebuilt the slot as **977 GC**, cycle-1
   buy 1.3187 @ 4310.50 (conviction 0.7675, stop 0.58%). 977 is now
   **+16.88 unrealized** — GC rallied to ~4323.

**Counterfactual:** had the floor not fired, 976's remaining half at the
current mark ≈ +3.75 → run ≈ +1.2 and rising. The ratchet's promise is
"exit ≈ breakeven"; it delivered −5.24 because the floor ARMED only at
the instant of the reduce, with the book already at −5.10 — breakeven
protection engaged five dollars below breakeven by construction (the
retro-arm defect; no evaluation lag was involved — control scans were
evaluating it all along, correctly unarmed). The position it cut
recovered within 15 minutes. **First cut-winner instance (n=1).** The replacement catching the rebound was
planner luck, not design (949's slot shows replacements don't always
re-enter the same symbol).

**The mechanism worth recording:** `_breakeven_arm_usd` is computed from
the **current** position size while `peak_pnl_usd` is a run-lifetime
high-water mark. **Any reduce on a red book lowers the arm and can
retro-arm the floor → instant full flatten.** The desk's deliberate
`reduce` (exactly what #245 teaches) gets escalated by the rail into the
expensive verb it deliberately avoided. This couples two shipped fixes
against each other. n=1 — NOT shipping; per §2.3 this needs a second
instance. Candidate fixes if it reproduces (platform, not skill — the
desk cannot see the floor): snapshot arm_usd at arming time; or scale
peak down proportionally on reduces; or suppress the floor for the cycle
in which a desk-authored reduce just executed.

### Second ratchet fire today — 973 SOLUSDT, 00:21Z (clean)

peak +1.72 ≥ arm ~1.65 (small book) → armed on the full book → total ≤ 0
→ flatten −0.70. No reduce involved, no verb-escalation. Working as
designed. **Ratchet fires now n=2 (973, 976); churn cost today −5.94 =
38% of the day's realized red.** SOL after 973's cut: replacement 974 has
sat flat 5 cycles (sell 0.48 < gate 0.5) — can't call 973 a cut winner.

### The rest of the day's −15.48 (attribution)

969 HG: 3 consecutive losing closes → **adapt retire** (+10.57 lifetime,
24h HG cooldown, flatten −3.24 journaled correctly). The adapt system
retiring a former winner on schedule — working as designed. 949 HYPEUSDT
died on its scheduled `at_time` (−15.51 lifetime; no flatten — was
already flat). 968 net −1.29 today (three small closes). 975 fresh BTC
long carrying −2.13 realized (entry fee) — watch. 960 realized +1.92
today but note its 04:31 buy 78.44 @ 62.32 → 05:16 sell 39.22 @ **62.32**
— a same-price half-unwind 45 min later, pure fee burn (~0.37); shape
logged, not actionable.

### DRIFT decomposition (why −5.05 is explained)

(a) 976's dying reduce leg −2.31: a close on a run's FINAL cycle never
gets its next-cycle `losing_close` adapt — structural, ledger catches it;
(b) 975's entry fee −2.13 sits in ledger-realized but adapt only speaks
at closes — structural; (c) 960's 05:16 close adapts next cycle; (d) the
pre-restart 973 flatten (00:21, old image) predates the #249 journal.
Post-restart flattens (969, 976) both journaled. **#249 works; the tool's
$5 tolerance is simply tighter than the structural deltas on a day with a
mid-day image restart + fresh entries.**

### Fix-verification ledger (what this cycle proves)

- **#245 exit-verb: n=2** (969 c20, 976 c2 — both with the line
  rendered). `why` still empty fleet-wide.
- **#249 ratchet: n=2 fires**, but tonight bought −5.94 of churn against
  a tail it didn't need to cut; **watch triggers**: (i) a second
  cut-winner (position recovers past breakeven within ~2 cycles of a
  floor fire), (ii) a second reduce-triggered retro-arm, (iii) slippage
  > $5 through the floor again. Any of these → design the fix above.
- **#249 flatten journal: verified again** (2/2 post-restart).
- **#244 newborn guard: n=5**, zero wrongful retires.
- **#247 arm executor: alive** (ticks clean); 968's arm standing
  (price_above 1440 → reduce 0.5, ~1.55% away); no `armed_exit` fires
  yet; no NEW arms this window — the fleet's arming habit is still thin.
- **#250 pnl_audit: the RUNNING IMAGE does not contain it** — it landed
  on the host tree at 04:58, after the 00:32 image build. Use the
  HANDOFF §4 mount fallback; fold the file into the NEXT image build (do
  not rebuild prod for this alone). Its drift alarm is working (it
  correctly flagged today, and the flag decomposed to structural causes).

### Owner-facing summary

Working: newborn guard, exit-verb (n=2), arm executor plumbing, adapt
retire, flatten journal, liq-defense, docs up, 0 tracebacks. Lost today
(UTC): −15.48 realized, no catastrophic dump (largest single loss −5.24 —
the 971-class tail remains absent). New issue found: the breakeven ratchet
can (a) cut recovering winners and (b) be retro-armed by the desk's own
reduce — both n=1, evidence bar set, nothing shipped. Watching, not
tuning: `BREAKEVEN_ARM_FEES` stays untouched until the triggers above
fire.
