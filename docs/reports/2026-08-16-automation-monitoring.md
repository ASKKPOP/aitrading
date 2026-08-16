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

## Cycle 32 — 14:4xZ (anchor 14:49:28): **escalation n=5 REPRODUCES the exact defect B predicted** — the line was in front of the desk and it missed by 2.8 points

**P&L: SUI 1306 forced-closed −$0.133** (day ledger +$2.47 → **+$2.32**;
run 1306 still net +$0.072 overall). Mechanism identical to DOT an hour
ago: desk authored `reduce 0.5`, rail escalated
`{"from": 0.5, "to": 1.0, "why": "dust_remainder_closed"}`.

**This is the reproduction B's analysis called for, and it is sharper
than the DOT case.** The arithmetic:
- book at the decision: 69.693 × 0.679 = **$47.32** — inside the
  $25–50 band, so **`reduce_geometry` DID render** (confirmed in the
  decision's own brief array).
- the line's stated bound: `1 − 25/47.32` = **47.2%**.
- **the desk authored 50.0%** — over the line by **2.8 percentage
  points**, and its `why` reads *"Partial reduction preserves the short
  thesis"*, i.e. it intended to keep a position the rail then took.

**So the desk had the number, in that cycle's brief, and authored just
past it.** DOT was "the line spoke too late"; SUI is **"the line spoke
and was not used."** Both fixes in the backlog are now justified by
reproduced evidence rather than one instance:
1. **prospective warning** (B): warn at the cycle that *creates* the
   trap, not after — DOT's case.
2. **round the ask to the bound** rather than escalating past it: when
   an authored reduce exceeds the max non-escalating fraction by a
   small margin, the honest rail action is to **clamp to the bound**
   (47.2%) — preserving the desk's stated intent to keep a position —
   instead of inverting it into a full close. Escalation n=5, and in
   2 of 5 the desk explicitly said it wanted to KEEP the remainder.

Escalation running tally now **n=5**: UNI −$0.032, FIL +$0.031,
ETH +$0.0018, DOT −$0.0103, SUI (this one, its own delta to be priced
next cycle at a live mark). Still not a P&L lever — but it is now
**twice** an authorship inversion, which is the part worth fixing.

Also this window: DOT 1308 re-shorted 53.09 @ 0.7624; new run 1329
built and deliberating; adherence 7/7; `side_contradiction` 0;
Plan 26 §2 green. 0 tracebacks.

---

## Cycle 31 — 14:1xZ (anchor 14:19:25): quiet — 4 holds, replacement run 1328 built, no closes

New run 1328 started 14:15:12Z (LTC slot replaced after its TTL
flatten) and deliberated immediately — `deviated`, i.e. it declined the
standing plan on its first look. Adherence 4/4, `side_contradiction` 0,
Plan 26 §2 green (crypto 14:16:10Z / us-stock 14:09:11Z, no
`algo_fallback`). Book: SUI −$0.06, FIL −$0.18 (both inside stops;
FIL is 2.0% from its 0.695164). Day ledger +$2.47. 0 tracebacks.

---

## Cycle 30 — 13:4xZ (anchor 13:49:27): LTC TTL-flattened −$0.077 — but **#448 LANDED**: the desk saw the deadline and said so

**P&L: run 1297 flattened by `stop_event:at_time` at 13:46:22Z**, cover
0.4536 @ 44.24 = **−$0.077** (run total −$0.151). Day ledger
+$2.55 → **+$2.47**.

**This is the same class as the 08-15 SUI at_time flatten** — the case
#448 (`run_expiry`) was built for — so instead of re-dispatching two
agents on a solved class, I tested the one NEW question directly: **did
the desk USE the deadline it can now see?**

**It did.** Its 12:49 report reads *"We hold the short as planned,
awaiting a drop toward the 42.78 target **before timeout**"* — the desk
reasoning explicitly against run life. Its final brief carried
`run_expiry` alongside `standing_plan`. On 08-15 the desk authored a
24 h thesis on an 8 h vehicle because nothing told it; today it planned
around the clock it was given. **#448 is landing.**

**What it did NOT do is act on it.** Knowing the deadline, it held to
the end rather than closing ahead of a flatten it could see coming
(`horizon_until` 11:51 had already passed; `at_time` 13:46 was
rendered). Seeing the deadline changed the NARRATIVE, not the ACTION —
which is the same gross/net-blindness shape A found: information
reaches the report but not the order. Logged, n=1 on this specific
"saw-it-held-anyway" pattern; not shipping on one instance.

Otherwise: adherence 4/4 (`followed` ×4), `side_contradiction` 0,
Plan 26 §2 green (crypto 13:45:06Z / us-stock 13:35:46Z, no
`algo_fallback`). Book: SUI −$0.03, FIL +$0.08. 0 tracebacks.

---

## CROSS-CHECK (A × B) — one root cause from two axes: **fee blindness**, desk-side and rail-side

**P&L: −$0.1764 fee-complete.** B's attribution: adverse price move
−$0.1157 (66%), **fees $0.0608 (34%)**. Third independent confirmation
that `signals.pnl` omits the open fee (realized before the final leg was
+$0.0199, not the +$0.039 I first reported).

**They converge without collusion:**
- **A (desk):** the desk **reasons in GROSS and books in NET** — every
  staging decision taken on a number 3–7× the ledger figure. Staging
  cost 2.7× everything three runs earned today (3/3).
- **B (rails):** `BREAKEVEN_FEE_RATE` is a hardcoded **0.001** while the
  platform's real crypto fee is **0.00045** (verified exactly from the
  tape). So the ratchet's arm sits **2.22× too high on every crypto
  run** — DOT's peak cleared its TRUE round trip by 1.63× and the rail
  still declined to protect it. **Not a near-miss: a defect against the
  rail's own docstring** ("its own round-trip cost").
  B's replay at the correct rate: exit at −$0.0456 vs actual −$0.1764 =
  **+$0.131 on this run alone, 12× the escalation question.**

**B refuses to oversell, and I'm adopting the caution:** the corrected
ratchet also forfeits the 06:38 dip where a full close was +$0.153. It
is *a floor, not alpha*, and B says plainly **do not ship it on one
run — replay fleet-wide first**, because a rail that turns losers into
smaller losers while turning winners into scratches is not a profit fix.

**Dust escalation, n=4, settled: NOISE.** UNI −$0.032, FIL +$0.031,
ETH +$0.0018, DOT −$0.0103 → cumulative **−$0.0115, sign 2:2**. It cost
5.9% of this loss. It remains an authorship defect (a rail issuing a
close the desk declined) — worth fixing on principle, **never to be
sold as a P&L lever.**

**#443 is DESCRIPTIVE, not PROSPECTIVE — and that is why it failed
here.** B's table: the trap was set at **cover 1** ($67.45 → $33.70),
and at that cycle the line **said nothing** (it only speaks below
2×floor = $50). It first spoke at cover 2, *after* the book was already
binary. Cover 2 survived only because the desk picked 0.25 against a
0.258 ceiling — **a $0.21 margin, luck not design.**

**idle_retire on 1319/1320: CORRECT** (12 worked cycles, flat, zero
trades, both theses' entry zones never triggered). If anything the rail
is **late** — 1320's entry zone was stale from cycle 1.

**SHIPPING NOW (the AI-first half of A's fix):** feed the exit prompt
**net-of-round-trip** P&L instead of gross. Pure information, no rail —
the pattern that has worked all session (#443, #448). The
forced-close-compilation half and the fee-rate constant both wait for
the fleet-wide replay B requires.

---

## VERDICT (Agent A) — staging cost 2.7× everything these runs made; the desk reasons in GROSS and books in NET

**P&L first, fee-complete (A, verified 3 ways to 8 dp): DOT run 1308
−$0.1764.** And **three corrections to my cycle-29 note**:
1. The two banks netted **+$0.0199, not +$0.039**. Bank #1 netted
   **+$0.0008** — it paid a $0.0303 round trip to capture $0.0311 of
   gross. It banked the fee.
2. **My "sell winners, hold losers" hypothesis is REFUTED as stated** —
   only DOT kept a residual; SUI and FIL both staged and fully closed
   within ~30 min, both tranches profitable.
3. **conf-0.0 no-LLM-verdict holds today = 9, not 5** (1305×3, 1308×2,
   1306×2, 1293×1, 1297×1). My watch undercounted by nearly half.

**What survives instead is stronger and 3/3:** a single full close at
the FIRST reduce decision beats the actual staging in every case today.

| run | staged actual | full close at first reduce | forgone |
|---|---|---|---|
| DOT 1308 | −$0.1764 | +$0.0016 | **$0.178** |
| SUI 1306 | +$0.0385 | +$0.0552 | $0.017 |
| FIL 1322 | +$0.0901 | +$0.1514 | $0.061 |

**Forgone $0.256 against $0.0954 actually earned — staging cost 2.7× everything these three runs made.** Across the six profitable
tranches, **fees ate 54% of gross** (DOT's first tranche 97%, FIL's
second 77%).

**The mechanism, and it is not psychology:** the desk **reasons in
GROSS and books in NET**. FIL cyc9 wrote *"Lock the $0.10 profit"* —
net was **+$0.0143**. SUI cyc11 wrote *"captures the $0.12 gain"* —
net **+$0.0164**. Every staging decision is taken on a number 3–7×
larger than the one that reaches the ledger.

**DOT specifics:** both banks were taken at **1.2%** and **4.1%** of
the desk's own 7.7% target — and it logged that fact in its own words
before doing it. **No `outlook` existed at either bank** (first one came
5 h after the open). Its only arm in 6.5 h was `price_below 0.75` on a
SHORT at 0.7581 — **1.35% further INTO profit, dead on arrival.**
All 7 outlooks carried byte-identical target/entry values: the plan was
a frozen constant re-narrated, not re-planned.

**⚠️ PLAN 26 FINDING — `plan_adherence` reported healthy while the book
bled 5×.** It read **`followed` ×6** across uPNL −$0.037 → −$0.176, and
**never once read `deviated`**. The flag measures compliance with a
STALE plan, not whether the plan still deserves compliance. Also a
data-integrity flag: cyc19 stamped **`revised` on a cycle with NO LLM
verdict** — a revision nobody authored.

**ACTION (A's fix, quantified on today's tape):** make exit decisions
fee-aware — feed the reduce/close prompt **net-of-round-trip** P&L, and
compile any `reduce` whose tranche gross is under ~2× the round trip
into `close 1.0`. On these three trades that turns
−$0.176/+$0.038/+$0.090 into +$0.002/+$0.055/+$0.151:
**+$0.0954 → +$0.208, a 2.2× swing with no change to the AI's market
view.** Holding for Agent B's rail axis before shipping.

---

## Cycle 29 — 13:1xZ (anchor 13:19:25): **DOT closed at a LOSS via a dust ESCALATION** — the "sell winners, hold losers" shape; agents dispatched

**P&L: run 1308 realized −$0.1764** (day ledger slips +$2.74 → **+$2.55**).
The shape is the concern, not the size:

| leg | ts | qty | price | signals.pnl |
|---|---|---|---|---|
| open short | 05:10:56 | 88.98 | 0.7581 | — |
| bank #1 | 06:08:45 | 44.49 | 0.7574 | +$0.016 |
| bank #2 | 06:38:45 | 11.12 | 0.7557 | +$0.023 |
| **forced full close** | **13:09:12** | **33.37** | **0.7633** | **−$0.185** |

The desk banked **two-thirds of the book for +$0.039**, then left the
last third exposed for **6.5 hours** to lose **5× that**. And the final
exit was not the desk's: it authored `reduce 0.5` and the rail
escalated to 1.0 (`dust_remainder_closed` — the ~$12.7 remainder is
under the $25 floor). **Escalation n=4+ on this fleet.**

Both agents dispatched with the central question stated plainly: **is
staged exiting making this fleet sell its winners and hold its losers?**
— tested against today's other staged exits (SUI 1306, FIL 1322) — and
whether the reduce-geometry line warns the desk *before* it stages down
to a book too small to reduce again, or only once it is already trapped.

Also: runs 1319 and 1320 `idle_retired` (12:57, 13:01) — sent to Agent B
to confirm correct vs premature. Adherence 7/7 (seventh window),
`side_contradiction` 0 flags, Plan 26 §2 green. 0 tracebacks. Book:
LTC −$0.09, SUI −$0.06, FIL +$0.09.

---

## Cycle 28 — 12:4xZ (anchor 12:49:27): quiet — 7 holds, no trades, all four shorts inside their stops

Adherence 7/7 (sixth consecutive 100% window), `side_contradiction`
**0 flags**, Plan 26 §2 green (crypto 12:46:59Z / us-stock 12:29:15Z;
adjusted 7 · adopted 4 · overridden 2; no `algo_fallback`). Book:
LTC −$0.09 (0.57% from stop), DOT −$0.16, SUI +$0.03, FIL −$0.07.
0 tracebacks.

---

## Cycle 27 — 12:1xZ (anchor 12:19:26): quiet — FIL 1322 re-entered (4th short open); no closes

Short 17-min window. FIL 1322 re-shorted 76.78 @ 0.6802 (12:16:33Z,
`revised`) — its second entry after this morning's +$0.0901 round trip;
stop 0.695164. **No closed-trade tape**, so no agent dispatch. Plan 26
§2 green: freshness crypto 12:16:32Z / us-stock 12:17:16Z ✓, verdicts
adopted 2 · adjusted 1, **no `algo_fallback`** ✓, adherence 2/2,
`side_contradiction` **0 flags**. Book: 4 shorts (LTC −$0.10,
DOT −$0.09, SUI +$0.09, FIL +$0.01). 0 tracebacks.

**Note for the next re-entry watch:** this is exactly the shape #450
was built for — a run that banked a winner and re-entered. Its realized
is +$0.0901 and the trail arm is $2.09, so the trail stays inert
(excursion 23× short of the arm); #450 remains **untested** rather than
exercised.

---

## Cycle 26 — 12:0xZ (anchor 12:02:21): quiet — 11 holds; side-coherence live with **0 flags**

No trades. Adherence **11/11** (fifth consecutive 100% window).
`side_contradiction` present on the decision path since #454 and
**0 flagged** — the clean state, not a silent failure (the detector was
proven against the real failing text at deploy). Plan 26 §2: freshness
crypto 12:00:55Z / us-stock 11:54:06Z ✓, verdict mix adjusted 11 ·
adopted 7 · overridden 5, **no `algo_fallback`** ✓. Book: LTC −$0.13
(0.36% from its stop — closest of the three), DOT −$0.12, SUI +$0.07.
0 tracebacks.

---

## Cycle 25 — 11:2xZ: first Plan-26 round trip, cross-checked — **+$0.0901 net**, and #450 was NOT exercised

**P&L first (both agents, independently, matching `peak_pnl_usd` to
8 dp): +$0.0901 net.** Gross $0.184, **fees 51.1% of gross**, +0.17%
on $52 margin. My reported +$0.137 was the DB figure — corrected.

**Agent A (desk):** the plan never constrained the trade. Published
target 0.65; exits at **5.11%** and **2.56%** of that distance with
43.5 of 48 horizon hours unused, both immediately after a
`horizon_shadow` saying HOLD. Cycle 9 carried **three falsehoods**:
"the current long trade", "opening a long… closing corrects the
mis-direction", and "lock profit before a likely further drop" — a drop
PAYS a short. It closed a winning, correctly-directed short to fix a
violation that never happened. Confidence was manufactured: proposed
0.55 → final 0.68, **identical +0.13 on cycles 7, 8 AND 9**, landing
just above the 0.65 gate.

**Agent B (rails):** every rail per design — leverage cap fired (3→2,
cost $0.045 of this winner, its job); #440 silent (ask was 5× the
floor); #446 silent (desk authored PERCENT form — correct
discrimination, and it also abstained on `stop_pct 0`, which is "no
bracket", not a unit slip); dust-remainder silent (remainder 2.09×
the floor). **The intent compiler SAVED the trade**: cycle 9 emitted
`legacy_action: short` to CLOSE a short — on the legacy path it would
have opened a SECOND short. Independent confirmation of A.

**⚠️ CORRECTION TO MY CYCLE-24 FRAMING: #450 was NOT exercised.**
I called this "the first live opportunity to test #450". B's
arithmetic: peak run total 0.2029 vs arm 2.09 — **neither the old nor
the new geometry arms** (10.3× and 13.9× short). The old code would
NOT have flattened this leg. **Report #450 as untested, not verified.**

**NEW DEFECT — in code I shipped (B):** `_breakeven_arm_usd` and the
exit-fee terms I added in #449/#450 read the flat
`BREAKEVEN_FEE_RATE=0.001` while `fees.fee_rate(market)` is live and
returns **0.00045** for crypto. Same class already fixed once in
`fleet_planner.trail_config`. Effect: the ratchet's arm bar is
**2.22× too high** (protection arms far later than designed — precisely
why it missed here by $0.0055) while the exit-fee term fires **2.22×
too early**. On us-stock/forex the multiple is ~10×/12.5×.
**One wrong constant, two opposite-direction errors, on the rail whose
whole purpose is to work without the desk.** Next ship.

**Sweeper waste quantified (B, code-verified):** `_cold_reason` returns
`run_idle` for any `status != running`, so `stopped` (terminal) is
treated like `dormant` (will resume). **15 of 25 sweeper outlooks (60%)
went to runs that can never trade again**, each an LLM call recurring
~every 33 min. Intended path, real waste; fix is one condition.

**#454 DEPLOYED — 11:4xZ addendum.** PR MERGED (`4bec711`), image
`sooppiy-backend:20260816-side-coherence` live. Verified by REPLAYING
THE REAL FAILING TEXT in the running container:
- FIL 1322 cyc9 *"limited upside for the current long trade"* on a −76.66
  book → **caught**: "a long claim on a SHORT position".
- FIL 1305 cyc9 *"Given we are long"* on a −304 book → **caught**.
- coherent short text → **None** (no false positive).
- flat book → **None** (exemption holds).
Plan 26 survived the rebuild (66 `outlook` hits, `OUTLOOK_ENABLED=1`) —
the deploy-rebuilds-from-main rule applied. 0 tracebacks.
Rollback: `SOOPPIY_IMAGE=sooppiy-backend:20260816-plan26-guide`.
Session ship count: 13 PRs (#439–#454).

**SHIPPED THIS CYCLE:** side-coherence detection — the desk's prose is
checked against the sign of its own book, journaled on the decision,
and quoted back next cycle (#441 pattern). Detection only, never blocks
(#119). 11 tests, mutants killed (one survived because MY flat-book
test used a claim silent either way — test fixed, re-killed).

---

## Cycle 24 — 11:1xZ (anchor 11:19:26): first FULL round trip under Plan 26 (+$0.137); no double-writing; sweeper spends on STOPPED runs

**Plan 26 §2 — the double-write check, run by run.** Crypto showed both
`cycle` (7) and `sweeper` (2) rows this window, which is the guide's
known-gap signature — so I checked per run rather than in aggregate:
every **`running`** crypto run got **only cycle rows**; both sweeper
rows belong to runs **1315 and 1321, which are `stopped`**.
**No double-writing** ✓.
**But:** the sweeper is authoring outlooks for runs that are STOPPED —
a stopped run has no slot left to plan for, and each row costs an LLM
call. That is guide known-gap #1 ("non-running runs treated as cold");
logging it as instructed, **n=2**, dispatched to Agent B for a code
verdict (waste vs defect vs intended).

Other checks: freshness crypto 11:19:26Z / us-stock 11:14:08Z ✓;
verdict mix adopted 5 · adjusted 4 · overridden 3 — **no
`algo_fallback`** ✓; adherence **7/7** (fourth consecutive 100%
window — the guide's §3b "minority of cycles" claim is now
comprehensively refuted).

**FIL 1322 completed the first FULL trade lifecycle under Plan 26:**
open 153.32 @ 0.6813 (deviated) → reduce 0.5 @ 0.6797 (revised) →
close @ 0.6805 (deviated). **P&L CORRECTED (Agent A): true net
+$0.0901, NOT the +$0.137 I reported** — `signals.pnl` nets only the
CLOSING fee on each leg and never subtracts the $0.047 open fee, so the
DB figure overstates net by 52%. Gross $0.184, **fees 51.1% of gross**,
return +0.086% on $104 notional. Run stays `running`. Both covers `railed: {}`. Two-agent
review dispatched — this is the first trade judgeable **against its own
published plan** (guide §3), and the first live opportunity to test
whether **#450**'s position-scoped trail changed anything for a run
holding a second leg after banking.

SUI 1306 opened a fresh short 69.69 @ 0.6774. Book: LTC, DOT, SUI.
0 tracebacks. Day ledger +$2.74 → to be re-read after these closes.

---

## Cycle 23 — 10:4xZ (anchor 10:49:31): **STOP-ECHO INVARIANT PASSES**; us-stock sweeper coverage arrives; FIL halved for +$0.099

**Plan 26 — the armed test resolved ✓.** Run 1322's next outlook
(10:47:04Z) carries `stop_ref_px` **0.688999**, byte-equal to the live
stop 0.688999 — the previous null was correctly a flat-book artifact
(authored 1 s before the fill). The guide's load-bearing invariant
("the model's stop is discarded in code — write-once stop rule") holds
on a position opened AFTER the flag flip.

**us-stock coverage appeared** (runs 1323–1327, 5 outlooks, newest
10:47:44Z) — **all `sweeper`-sourced**, which is exactly right: the
session is closed on a Sunday, and the guide reserves sweeper rows for
closed sessions / dormant slots. No cycle-sourced us-stock rows =
**no double-writing** ✓.

Other §2 checks: freshness crypto 10:47:15Z / us-stock 10:47:44Z, both
minutes old ✓; verdict mix sweeper adopted 5 · adjusted 3, cycle
adopted 3 · adjusted 3 · overridden 1 — **no `algo_fallback`** ✓;
adherence **7/7** (third consecutive 100% window).

**Trade:** FIL 1322 reduced exactly half (153.32 → 76.66) at 0.6797,
realizing **+$0.0757 true net** (I reported +$0.099 — that was the DB
figure, which omits the open fee; see cycle 25); `railed: {}` —
remainder ~$52 is double the $25 floor, so no escalation, correct
silence. The cycle was labelled
`revised` and the reduce came through the intent path (`reduce 0.5`).
Day ledger **+$2.74**.

Book: LTC −$0.11, DOT −$0.02, FIL +$0.11 (half-size). 0 tracebacks.

---

## Cycle 22 — 10:1xZ (anchor 10:19:27): Plan 26 §2 all green; new FIL short opened on a `deviated` cycle

**Plan 26 (guide §2):** outlook freshness **6 seconds** (newest
10:19:21Z) ✓; verdict mix cycle overridden 3 / adjusted 2 / adopted 1 +
sweeper adjusted 2 / adopted 1 — **no `algo_fallback`** ✓; adherence
**7/7 = 100%** — second independent confirmation that the guide's
§3b "minority of cycles" claim is wrong.
Adherence mix: followed 3 · **deviated 3** · revised 1.

**Per-trade check on all three deviations (guide: a deviation without a
stated reason is a finding).** All three DO state reasons — verified
individually:
- 1293: *"holding flat preserves capital as the short thesis lacks a
  clear positive expectancy within the remaining ~11 hours"* — note it
  is reasoning against **run life**, i.e. #448 still steering.
- 1306: 600-char report (fear/greed contrarian read, crowded longs,
  desk memory) ✓.
- 1322: full technical + sentiment + news rationale, and it **acted** —
  short 153.32 FIL @ 0.6813, stop 0.688999.

**⚠️ My own false alarm, corrected before reporting:** 1306's report
first read as EMPTY and looked like the first Plan-26 defect. It was a
display artifact — a binary byte in the payload made `grep` swallow the
row. Re-fetched with `-N | tr -d '\000'`: 600 chars present. **No
defect.** Query hygiene noted for the loop.

**Stop-echo invariant — not yet testable on 1322, watch armed:** all
three of its outlooks carry `stop_ref_px: null`, but the newest
(10:16:24Z) was authored **1 second before** the position opened
(10:16:25Z) — null is correct while flat. The real test is its NEXT
outlook (~10:46Z), which must echo **0.688999**.

Book: 3 shorts (LTC −$0.12, DOT −$0.02, FIL +$0.13). 0 tracebacks.

---

## Cycle 21 — 09:4xZ (anchor 09:49:21): quiet — Plan 26 healthy; guide now in main and pulled into the tree

Short 6-min window. Plan 26 per guide §2: crypto outlook newest
09:44:57Z (**4 min old vs 30-min floor** ✓); source/verdict split
sweeper·adjusted 1 + cycle·overridden 1 — **no `algo_fallback`** ✓;
adherence 1/1 (`followed`) ✓. No trades. Both shorts inside stops
(LTC −$0.12, DOT −$0.04). 0 tracebacks. The guide is now merged to
main (#452 chain) and pulled into the working tree, so the
existence check is closed — future cycles read it locally.

---

## Cycle 20 — 09:4xZ (anchor 09:43:18): docs deploy verified NOT to have reverted Plan 26 — and a process risk I took

The docs PR #452 chain rebuilds the image **from main** and replaced
`20260816-plan26-outlook` with `20260816-notes-0816`. **I did not check
before deploying whether Plan 26 was merged to main.** It was —
`2b058b03 feat(outlook) … (#451)` sits one commit below my docs merge,
and the running image carries 66 `outlook` hits with
`OUTLOOK_ENABLED=1`; outlooks kept writing straight through the restart
(2 more by 09:42:29Z, adherence 1/1). No harm done.

**But the risk was real and is structural:** every docs deploy I run
rebuilds prod from main, so ANY feature deployed from an unmerged
branch would be **silently reverted by my next routine docs deploy**.
Standing rule added for this loop: before any deploy, diff the running
image's feature surface against main, or confirm the feature's PR is
merged. Cheap check, silent failure mode.

---

## Cycle 19 — 09:3xZ (anchor 09:35:48): **PLAN 26 IS LIVE** — guide found, checks run, and its baseline table is WRONG

**The guide exists** — on branch `fix/plan26-monitoring-guide`
(commit ebaee986), not in this working tree, which is why every prior
cycle's existence check failed honestly. Read and now binding.
**Plan 26 shipped**: image `sooppiy-backend:20260816-plan26-outlook`,
`OUTLOOK_ENABLED=1` in both .env and the container, flag flipped
09:10Z.

### §1 deploy verification — ALL GREEN
| check | result |
|---|---|
| outlook rows by market | crypto 8, newest 09:30:49Z — **4 min old vs a 30-min floor** ✓ |
| source split | cycle 5 / sweeper 3 — no double-writing on open+cycling runs ✓ |
| `basis.verdict` mix | adopted 2 · adjusted 2 · overridden 4 — **no `algo_fallback`**, LLM path alive ✓ |
| **stop-echo invariant** | run 1297: `stop_ref_px` **44.5309** = live stop **44.5309**, byte-equal ✓ (the other 7 are flat runs → null, correct) |
| adherence mix | followed 4 · revised 1 · deviated 1 |
| deviated-with-reason | 1322 states it: *"weak momentum, low volume, sub-coin-flip confidence, the short entry lacks positive expectancy; we stay flat"* — compliant ✓ |
| errors | 0 outlook errors, 0 tracebacks ✓ |

### ⚠️ MATERIAL CORRECTION TO THE GUIDE'S §3b BASELINE
The guide's table says *"decisions | 395 | 181"* and *"3 adherence
stamps"* in the first 30 min, and tells sessions to chase
**"compliance trending to zero."** Measured here, twice, independently:

- decisions in 09:10–09:40 = **6** (not 181). **181/208 is the count of
  ALL `run_events`** in that window, not decisions.
- The guide's own numbers are internally inconsistent: 395 decisions/24 h
  is ~8 per 30 min, so 181 decisions in 30 min would be a 55× rate jump.
  My 6-in-25-min matches 397/24 h exactly.
- **`plan_adherence` coverage is 6/6 = 100%**, not 3/181 ≈ 1.7%.

Consequence if followed blindly: a session would report "outlook
coverage is thin / compliance failing" when compliance is **complete**.
The §3b conclusion *"the model emits the block on a minority of
cycles"* is **not supported** by this measurement. Not editing another
session's branch (parallel-session rule); flagged here and to the owner.

**Verdict per §3.7:** too early for the profit test (day-7 ledger split
by adherence and verdict). Nothing to judge on P&L yet; the feature is
healthy on every process check the guide defines.

---

## Cycle 18 — 09:1xZ (anchor 09:19:27): quiet — 3 holds; conf-0.0 on a HELD book again (n=5)

DOT 1308 (held short, −$0.08) took another `conf 0.0` no-LLM-verdict
hold at 09:07 — **n=5 on the repeat watch, and the third on a HELD
book**. Fail-safe holding is safe (bracket guards it) but it is a
management look lost on a live position; FIL's flatten was preceded by
exactly this pattern. LTC drifting to 0.39% from its stop. 0 trades,
0 tracebacks. Plan 26 guide absent at 09:19Z.

---

## Cycle 17 — 08:5xZ (anchor 08:57:05): quiet — 13 holds, no trades; Plan 26 guide still absent

Both shorts underwater but well inside their stops (LTC −$0.11, entry
44.09 / mark 44.332 / stop 44.531; DOT −$0.08, 0.7581 / 0.76048 /
0.775536) — this is exactly the regime #450 now protects: neither run
has banked cash that could arm a lock against them. One idle_retire
(1315). 0 tracebacks. Plan 26: guide file absent at 08:57Z, no
implementation artifacts.

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
