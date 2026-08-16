# Automation monitoring — 2026-08-16 (UTC day), newest-first

Continued from [2026-08-15](2026-08-15-automation-monitoring.md) (fleet 35
day one: 9 closed trades ≈ +$0.01 realized; 11 PRs #439–#449 shipped from
live tape). Target: **info@askkpop.com — user 5 / agent 6 / FLEET 35**.
Open watches: arm-reachability rail + side-coherence check
(next-session implementations), fee-accounting + scratch-band owner
package, empty-why arms (n=6), #446 unit-slip converter first live
fire, #439 BYPASSED first exercise, AUDCHF 1147 flatten at Sunday
21:00Z FX open, fleet 33 `stopping`.

**OWNER ORDER (2026-08-16 ~00:5xZ): monitor Plan 26 (Slot Strategy
Outlook / Forward Book)** per
`docs/reports/plan26-outlook-monitoring-guide.md`. That guide file
DOES NOT EXIST YET (checked 00:55Z; the plan itself,
docs/plan/26-slot-strategy-outlook.html, is marked PROPOSAL — nothing
shipped). Standing per-cycle check added: the moment the guide appears
its instructions bind this loop; until then, watch for Plan 26
implementation artifacts (outlook objects in decision JSON, per-slot
standing plans, plan-following cycles) and judge them per §3.7 —
realized-P&L terms, plan-following cycles must ADD expectancy or the
flag comes off.

---

## VERDICT (cross-checked) — the run-level trail is GEOMETRICALLY DEFECTIVE: banked cash arms a lock the live position never earned

**P&L first:** run 1305 banked **+$2.356** against a peak of **+$3.037**
— the rail surrendered **$0.681 (22.4% of peak)** and landed **$0.073
BELOW the 2.4294 line it fired to defend**. It was the **only
meaningfully profitable run in all 36 runs of fleet 35**, and it is now
dead. Position-level the flatten is immaterial (±$0.07; the sign flips
between two marks 5 minutes apart). **The loss is the terminated
compounding of the fleet's only winner.**

**The mechanism (Agent B, arithmetic exact to 8 dp, two bracketing
equity samples):** `_trailing_lock_hit` compares `activate_usd`
(POSITION-scaled: 2.089 = 2.0% × $104 notional) against
`peak_pnl_usd` (RUN-scoped, **including banked realized cash**).
So the arming test was passed by **banked cash**, not by the new
position — whose own maximum unrealized profit was **$0.019, i.e.
0.89% of the arming floor**. A profit lock armed with no profit of its
own to lock. Consequences, quantified:
- Adverse room: **0.5365%** of entry vs its own authored stop 2.00% —
  **the rail was 3.73× tighter than the desk's own stop**; flattened
  at 4% of its $15.67 max-loss budget, 4h48m into a 36h horizon. The
  desk's plan was never executable.
- **The rail punishes success within a run:** replacement run 1322
  started 30s later with `peak_pnl_usd = 0` → its trail is inert until
  it earns $2.09 of its own. **Banking a winner makes a run strictly
  more fragile than never having traded.**
- The lock cannot defend its own line: 22.42% actual giveback vs 20%
  designed, because `_trailing_lock_hit` models no exit fee — while
  `_breakeven_floor_hit` beside it DOES (#449 added it).

**Cross-check A×B: no contradiction, complementary axes.** A: the desk
authored the re-entry churn (believing itself long) — −$0.68 destroyed,
$0.22 of it pure adverse re-entry pricing. B: the rail then killed the
run for it. Both independently priced the position-level flatten as
noise. Both accepted.

**Rails scorecard:** dust-remainder — correct, silent, `railed:{}` on
all four partial covers (DOT c13 left $25.22, $0.22 above the floor —
razor's edge, flagged). **#449 discriminator — working as shipped: its
ABSENCE is what proved this was the configured trail**, and B manually
confirmed JTO 1304 was the ratchet. Configured trail — fired per spec,
**and the spec is wrong**.

**#450 DEPLOYED — 08:5xZ addendum.** PR MERGED (`cd4c320`), image
`sooppiy-backend:20260816-trail-position-scoped` live. Verified in the
running container by REPLAYING THE EXACT PROD NUMBERS:
- FIL 1305 (peak 3.036759, total 2.403265, baseline 2.989755) → **False**
  — the flatten that killed the fleet's only winner no longer fires.
- single-position run (baseline 0) → **True** — unchanged, no regression.
- genuine second-position excursion (peak 8.0, baseline 3.0) → **True**
  — a position that truly earns is still locked.
0 tracebacks. Rollback:
`SOOPPIY_IMAGE=sooppiy-backend:20260815-ratchet-fee-floor`.
Session ship count: #439–#450 (12 PRs).

**SHIPPING NOW (B's #1 + #2):** position-scope the trail —
`baseline = run total at position open`, `armed ⟺ (peak − baseline) ≥
activate_usd`, `lock = peak − giveback × (peak − baseline)` (textbook
trailing stop: giveback of the EXCURSION, not of the LEVEL). On this
tape: peak − baseline = 0.047 ≪ 2.089 → inert, no flatten, run alive
at ~+2.42 with 30h left. Zero regression on single-position runs
(baseline 0 → identical; verified against 1303 and 1305's own first
trade). Plus the exit-fee term, at parity with the ratchet.

**BACKLOG (strengthens the OWNER fee package):** `adapt` telemetry
omits the ENTRY fee — `winning_close` reported 3.1308 vs ledger-true
3.03676; `flatten_close` −0.6338 vs −0.68076. Systematic optimism of
one entry fee per trade **in the number that feeds the tightening loop
and the RAG outcome chunks.**

---

## Cycles 4-16 CONSOLIDATED — 00:40–08:1xZ (anchor 08:11:09): day **+$2.69**; staged partial exits arrive; a run-level trail flattens a fresh position

Queued cycle prompts stacked while the FIL verdict ran; this note covers
the whole 7.5 h gap in one sweep. Agents dispatched on the batch.

**P&L first (pnl_audit, flatten-reconciled, resid 0.01, 1 flatten):
UTC 08-16 ledger = +$2.69 — BUT the overnight desk authorship was
NET NEGATIVE −$0.494** (Agent A, fee-complete). The +$2.69 exists
because of the 00:17 FIL bank (+$3.04) on a position opened 08-15
22:17Z. Strip that and this batch is a loss. Headline honesty: the
day is green on yesterday's trade, not on tonight's decisions.

**WORKED — #443 PROVEN CAUSAL (Agent A, and it refuted MY framing).**
My "first surviving partial exits this fleet has ever produced" was
**FALSE** — ETH 1302's half-reduce already survived the floor on
08-15 (my own cycle-31 note, commit 392d5d86). What is genuinely new
is the **non-canonical fraction chosen under the stated bound**:
- SUI 1306 cyc10: notional $47.11, line renders bound 47%, desk chose
  **0.40**, and its `why` quotes the number verbatim — *"cutting 40%
  keeps a meaningful position (>$25)"*. $25 exists nowhere in the
  desk's world except `_reduce_geometry_line`.
- DOT 1308 cyc13: notional $33.62, bound 26%, desk chose **0.25**.
- Both cycles where the line is SUPPRESSED ($67.39, $104.45): the desk
  reverted to canonical 0.5 / no reduce.
- Prior: **150 reduce intents before 08-16, 123× 0.5 and 27× 1.0 —
  zero non-canonical fractions in four days.**
4/4 correlation with render/suppress. This is the #443 signature.
**But #443 gives true information, not edge**: the identical mechanism
produced SUI +$0.0385 and DOT **−$0.119 so far** (its 25% stage left a
book that then rallied). Stated plainly, not laundered.

**FAILED — FIL 1305 re-entry flattened for −$0.634 by the CONFIGURED
TRAIL** (no `stop_mechanism` event → #449's discriminator correctly
silent; not the ratchet). Sequence: banked +$3.131 at 00:17, re-shorted
154.7 @ 0.675 at 02:47, and at 07:35 the run-level trail
(activate 2.09, giveback 0.2) flattened the NEW position while the run
total sat ≈2.62 — i.e. **the previous trade's banked profit set the
peak, and the fresh position was killed for giving back 20% of a peak
it never earned.** Its own stop (0.7104) and max_loss ($15.67) were
never near. Agent B is judging whether that is intended
"protect banked gains" semantics or a structural bar on re-entry.

**Run churn:** 7 desk_retires + 1 idle_retire; new runs 1308–1322
built continuously — replenishment healthy.
**Fail-safe watch (repeat CONFIRMED):** three conf-0.0 no-LLM-verdict
holds on the HELD losing FIL book (03:16, 06:17, 07:15) — management
looks lost on the position that then got flattened; n=4 total.

**PLAN 26 (owner order):** guide file
`docs/reports/plan26-outlook-monitoring-guide.md` **still does not
exist** (checked 08:11Z). Zero implementation artifacts: `outlook`
appears 0× in the deployed run_engine.py, and the 4 tape hits are the
word inside free-text reports, not outlook objects. Nothing to judge
per §3.7 yet; check re-armed every cycle.

---

## Cycle 3 — 00:5xZ: FIL +$3.04 verdict cross-checked — the win is the DESK'S; both agents independently demand the same fix

**P&L first: +$3.04 net, verified to the cent against the ledger (2×).**
Counterfactual at both marks: the close cost ~$0.03 vs holding — a wash.

**Where the money came from (A, accepted):** entry timing (3.5 h of
patient refusal, then short at the local range top when momentum
jumped 0.45→0.80) × size ($209 notional — the same 1.54% move at
floor-scale is a scratch) × one hour of correct patience (96% of gross
earned in hour one). The 3.4% stop bought permission to hold, never
tested.

**Rails (B, accepted):** ALL per design — leverage cap 3×→2× (cost
$1.52 on this winner; its job), ratchet armed at $0.42 and correctly
silent (floor never approached; #449 live for the final 45 min,
out of range), trail/arm/stop/target untouched, TTL visible (44 h
left) and rightly unreferenced. The profit-retention band between
ratchet arm ($0.42) and trail arm ($10.45) remains 100% desk
discretion — this time the desk gave back only $0.50 from peak.

**The defect BOTH agents found independently: side confusion.** The
exit report reasoned "Given we are LONG…" against a −304 SHORT book
(position_state rendered in its own brief); the panel proposed `buy`;
params why said "close the existing long"; the intent compiler alone
produced the correct `cover`. Truthful-exit and direction-coherence
both FAILED in prose (my cycle-2 credit to the exit was too generous —
corrected). Side confusion is n=2 today (LTC, FIL). On an ADD intent
the same slip flips exposure instead of closing it.

**Actions (next-session implementation queue, specs in backlog):**
1. Side-coherence check on exit/add cycles: stated side vs
   position_qty sign — telemetry flag + quote the contradiction back
   (#441 pattern). Both agents' #1.
2. Arm-reachability rail (queued from JTO).
3. Journal hygiene: params sizing non-authoritative on intent-close
   cycles (attribution keeps tripping on it).

Fleet 35 totals: 10 closes, **+$3.05 realized**; open LTC + SUI shorts.

---

## Cycle 2 — 00:4xZ (anchor 00:40:49): FIL CLOSED **+$3.04 NET** — the fleet's first material win; agents dispatched

Desk-authored at both ends: short 304.09 @ 0.687 (22:17Z) → full cover
@ 0.6764 (00:17Z). Gross +$3.22, fees $0.19. Banked at 15.7% of path,
conf 0.68 — and the exit's cited risk (short squeeze, price UP) is
genuinely AGAINST a short: direction-coherence satisfied on first live
contact. SUI 1306's new entry authored its target to "fit within
remaining run life" — **run_expiry shaping bracket authoring already**.
Two-agent review dispatched (win scrutinized like a loss; noted for
them: prose label slip "the existing long", intent-1.0 vs params-0.05
contradiction at exit, empty-why arm n=6). Book: LTC + SUI shorts.
Fleet-35 running total: 10 closes, ≈ +$3.05 realized.

---

## Cycle 1 — 00:1xZ (anchor 00:10:44): quiet — LTC re-entered; FIL short +$3.32

LTC 1297 re-entered short 0.454 @ 44.09 (floor raise fired again; sane
1.0/2.5 bracket, trail_arm 1.5). FIL 1305's $209 short extended to
**+$3.32** (0.67609), desk holding; one `conf 0.0` no-LLM-verdict
fail-safe hold on the HELD FIL book (23:45 — safe, bracket+arm guard,
but a skipped management look on the day's best position; watch if it
repeats). Book: 2 shorts. 0 tracebacks, no closed trades.
