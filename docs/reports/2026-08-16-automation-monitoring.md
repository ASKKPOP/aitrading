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
