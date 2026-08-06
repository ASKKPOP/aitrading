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
