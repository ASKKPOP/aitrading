# Automation monitoring — 2026-08-21 (UTC day), newest-first

Continued from [2026-08-20](2026-08-20-automation-monitoring.md) (day closed
**−$1.46** ledger, check ok — the FIL 1531 floor-carry churn leg was the
whole day; R25 + R27 shipped and verified; fence PASS day 3; docs batch
PR #499 merged to main).
Targets: **info@askkpop.com — user 5 / agent 6 / fleet 38** (7 slots,
$10,012, crypto); **forevery1969@gmail.com — user 25 / agent 60 /
fleet 37** (us-stock+forex, EXTREME; us-stock watched 13:30–20:00Z).

## RAG-CADENCE PASS — 08:0x–08:5xZ (anchor `SELECT NOW()` = 2026-08-21 08:05:31Z): the entry engine did not slow down, it was SWITCHED OFF at a deploy boundary — and two numbers in the authority docs are artifacts

**PROFIT-OR-LOSS FIRST.** 08-21 has **no realized row at all** — zero
closes, zero opens, 25h+ since the last executed entry (08-20T06:40:29Z).
Ledger 08-15→08-20: −0.12 / +5.65 / +3.63 / −0.94 / −1.14 / −1.46 =
**+5.62**, of which +5.65 is 08-16 alone; strip the largest contributor
and it is **−0.03**. n = 42 opens. Nothing here establishes that the desk
trading more makes money — but the shutdown is now traced to a mechanism.

### 1. CORRECTION — "`short` zero" is a STRUCTURAL ARTIFACT, not a behaviour

`HANDOFF-rag-phase3.md` §6 and plan 22 §7 both state: *"On flat cycles the
desk says `buy` 7 times in 3,444 (0.20%), `short` zero."* The `short` zero
is not a finding. It cannot be anything else:

- The decision prompt fixes the schema at
  `{"action": "buy"|"sell"|"hold"}` (`run_engine.py:5919`).
- The `decision` telemetry event is emitted at **line 6572**; the futures
  `sell`→`short` remap runs at **line 6775**. The event is written BEFORE
  the remap, always.
- All-time `decision` actions, 5,103 rows: `hold` 4668, `sell` 239,
  `buy` 128, `retire` 68. **`short`: 0 — and 0 is the only value it can
  ever take.** Meanwhile `signals` carries **48 `short` opens all-time**.

**Corrected flat-cycle entry rate, 08-15 → 08-21 08:0xZ (n = 3,588):**

| | decisions | executed |
|---|---|---|
| `sell` (→ `short` on a futures book) | 55 | **36** |
| `buy` | 7 | **6** |
| **entry intents** | **62 = 1.73%** | **42 = 1.17%** |
| `hold` | 3,498 | — |
| `retire` | 28 | — |

The published 0.20% understates entry intent by **8.7×**, and **86% of
executed entries are SHORTS.** The desk is a short-side crypto desk; the
document says it never shorts.

### 2. CORRECTION — §4a's harm test cannot answer its own question

The pre-committed test compares post-flip `buy` count against a 7/3,444
baseline. On the corrected population the baseline is 62/3,445 = 1.80%,
so 0 intents in 144 post-flip flat cycles gives P(0) = 0.98²⁰¹⁴⁴ ≈
**0.073**, not the ~0.27-expected framing. But the baseline is **not
stationary** — see §3 — and against 08-20's own rate (0.44%) the same
zero gives P(0) ≈ 0.53. **The test as designed cannot separate the flag's
effect from the pre-existing collapse. It is INCONCLUSIVE for a second,
worse reason than the one recorded.**

`DESK_RECALL_FLAT` itself is healthy: 143/143 flat decisions carry a
`recall` row (crypto 101 + forex 42, matching decisions per market
exactly), 0 rows with empty `chunks`, **0 tracebacks in 8h**. The abort
rule is not triggered.

### 3. THE FINDING — a level shift at the #484 deploy, z = 4.43

Crypto flat-cycle entry-intent rate, 6h buckets, split at the
`20260818-ai-first-batch` image build (**2026-08-18T11:49:34Z**, the
deploy that carried #484):

| arm | cycles | intents | rate |
|---|---|---|---|
| PRE (08-16T00 → 08-18T11:49:34) | 566 | 33 | **5.83%** |
| POST (08-18T11:49:34 → now) | 649 | 8 | **1.23%** |

Two-proportion **z = 4.427, two-sided p = 9.5e-6**; the exact binomial is
stronger still — P(≤8 intents in 649 cycles at the PRE rate) = **2.3e-9**. The ten PRE buckets oscillate
around 5.8% with **no downward trend** (4.5 / 4.3 / 11.6 / 2.4 / 12.1 /
7.8 / 6.8 / 4.9 / 4.5 / 4.9 %); POST decays to zero. This is a **level
shift at the boundary, not a trend crossing it.**

Independent confirmation from a different table and a different
definition — executed opens from `signals`, crypto:

| arm | hours | opens | opens/hour |
|---|---|---|---|
| PRE | 59.8 | 22 | **0.368** |
| POST | 68.5 | 7 | **0.102** |

3.6× on execution against 4.7× on intent. Last executed open:
**08-20T06:40:29Z**.

**The batch delta is narrow.** Between image `20260818-recall-contest`
(08:46:30Z) and `20260818-ai-first-batch` (11:49:34Z) only four commits
landed: #483 and #486 are docs; **#485 is an EXIT rail** (breakeven
ratchet peak-epoch); **#484 is the only entry-side behavioural change** —
`desk_record.record_line()` wired into both bracket prompts.

### 4. The desk says so itself — 11 of 12 high-confidence holds, one reason

Every crypto flat cycle on 08-21 scoring confidence ≥ 0.65 said `hold`
(15 of them). Their own `report` text, 11/12 identical in substance:

> *"the required stop is too wide relative to the expected move, yielding
> negative expectancy"* · *"oversized stop, insufficient target distance,
> and **historical reachability limits**"* · *"the expected 4% move
> exceeds **observed historic upside**"* · *"no positive-expectancy entry
> exists"*

That vocabulary is `record_line()`'s, verbatim in substance. The live
crypto line the desk reads every cycle:

> REACHABILITY (this desk's own closed crypto book, n=33 …): the best
> moment a run ever reached was **1.44%** of entry; the median run's best
> moment was **0.17%**, p75 **0.33%**, and **39%** of runs never had a
> positive moment at all. … **Judge whether this trade is worth taking at
> all.**

### 5. Confidence went UP while entries went to zero — the two decoupled

| day | crypto flat n | avg conf | conf ≥0.65 | entry intents |
|---|---|---|---|---|
| 08-15 | 206 | 0.4989 | 12 (5.8%) | **16** |
| 08-17 | 197 | 0.5129 | 16 (8.1%) | 15 |
| 08-19 | 256 | 0.5320 | 27 (10.5%) | 4 |
| 08-20 | 232 | 0.5504 | 23 (9.9%) | 2 |
| 08-21 | 104 | 0.5625 | 15 (14.4%) | **0** |

Confidence rose 0.499 → 0.563 and the ≥0.65 share rose 5.8% → 14.4%
while entries fell 16 → 0. **The confidence score is no longer connected
to the entry decision.** This re-refutes the confidence-gate hypothesis
from the other direction.

### 6. HYPOTHESES REFUTED TODAY — do not re-run them

| hypothesis | verdict |
|---|---|
| the tape went quiet — the desk is correctly declining a dead market | **REFUTED, and inverted.** Per-cycle absolute crypto move, same 17 symbols present in both arms, deploy day excluded: PRE mean **0.210%** / median **0.140%** / p90 **0.444%** (n=489) → POST mean **0.499%** / median **0.291%** / p90 **1.044%** (n=479). **Volatility roughly DOUBLED** (2.4× mean, 2.1× median) as entries went to zero. The POST median per-cycle move (0.291%) now EXCEEDS the p75 (0.33%) ceiling the desk is being shown — the disclosure is stale against its own live tape |
| the reachability record ratcheted more pessimistic over time | **REFUTED.** It IMPROVED: crypto n 26→33, best 0.969%→**1.438%**, never-positive 42%→**39%**, median unchanged at 0.169% — while entries fell 6→0 |
| population mix — more flat-heavy markets diluted the rate | **REFUTED for crypto**, which is the entire entry engine (forex 3 intents/1,152 cycles, futures 1/324, us-stock 1/695). Crypto's OWN rate fell 7.77% → 0.86% → 0.00% on stable run counts (22 → 28 → 14) and stable cycle counts (206 → 232 → 104) |
| a confidence gate blocks entries | **re-refuted, inverted** — §5 |

### 7. What this does NOT establish — stated because it matters

- **It is observational, not an experiment.** A level shift at a deploy
  boundary with one candidate cause, a refuted rival, and the desk
  quoting the change's own text is as strong as observation gets — and
  it is still not a randomised A/B. Per the owner's experimental-mindset
  rule the next increment is the EXPERIMENT, not the fix.
- **#484 was itself shipped on a real measurement**: authored `target_pct`
  median was 4.80% against a book that had never peaked above ~1%. A naive
  revert reinstates that defect. #484's own text pre-registered the risk —
  *"truthful disclosure may push the desk toward tighter stops, and the
  expectancy of the tighter band is UNMEASURED"* — and pre-registered the
  wrong failure: it predicted tighter brackets and got **no brackets**.
- **The profitable record is thin and outlier-driven.** +9.16 over the
  three high-activity days is 2 days; strip each day's largest
  contributor and it is ≈ +0.10. n = 42 opens. "Trading more makes money"
  is NOT established by this tape and must not be reported as if it were.

### 8. The (b) gate — MET, but the recorded evidence is partly confounded

Re-measured independently at 08:0xZ on all 833 `recall` rows. The gate
(≥2 ε-scheme classes, each ≥30 events and ≥3 distinct chunk pairs) is
**MET more widely than recorded — six ε classes, not three**: crypto/
giveback+winning 104/14, crypto/FLAT 101/5, futures/giveback+winning
90/4, forex/giveback+winning 82/6, forex/winning 49/3, forex/FLAT 42/4.

**But the pair count is not all exogenous, and (b) must not treat it as
if it were.** The deterministic (greedy) arm's distinct pairs occupy
**perfectly non-overlapping time blocks** — e.g. crypto/giveback+winning:
`9d8b125b+c8559767` 08-12→08-14, `0e7a7833+9b9cd916` 08-15→08-17,
`9b9cd916+c72e011b` 08-17→08-18, `818d9f91+c72e011b` 08-19. Zero overlap
in every class. That variation is **corpus drift, perfectly confounded
with calendar time and market regime.** Only ε-exploration-induced sets
are attributable. Exogenous-only counts:

| class | events | explore rows | ε-induced novel sets |
|---|---|---|---|
| crypto / giveback+winning | 104 | 22 | 10 |
| crypto / FLAT-entry | 101 | 28 | 4 |
| futures / giveback+winning | 90 | 29 | 3 |
| forex / giveback+winning | 82 | 20 | 4 |
| forex / FLAT-entry | 42 | 11 | 3 |

Five classes still clear on exogenous variance alone, so **(b) remains
unblocked** — but the effective sample is the *explore arm* (11–29 rows
per class, ~2–3 observations per novel set), and (b) must record the
deterministic block in force at each row's timestamp and never compare an
explore row in block 3 against a deterministic row in block 1.

`chunks: []` control rows: still **0 of 833, all time.**

### 9. Owner-rule compliance note

The two-subagent trade-outcome split (CLAUDE.md, 2026-08-13) was not run
this pass: there is **no tape to split** — zero AI-authored and zero
algorithm-authored closes in the window. The analysis is of the
non-trades instead, with a stated reason per non-trade (§4).

## 24H SWEEP — 03:5xZ (anchor 03:59:32, displaced cron): risk hygiene perfect, throughput ZERO — R26's trades/day metric has not moved

**PROFIT-OR-LOSS FIRST.** 24h realized: **$0.00 — zero trades** since
the FIL cyc33 cover (08-20 07:10Z). Ledger 08-18/19/20: −0.94 / −1.14 /
−1.46; 08-21 has no realized row yet. The platform's risk stack is
faultless and its engine is idle.

**Adversarial re-proofs (all by direct count, window 08-20 15:37 → now):**
- **#475 fence: 0 — PASS, day 4.** Caps 0 (ledger unchanged: 5 fires,
  net-positive insurance). Ratchet 0 (R21 stays validated at n=2).
  R:R floor/ceiling actionable fires 0. Loss floor #460: still zero
  enforcement fires ever.
- **R23: 0 sweeper writes to dead runs — holds.** **R25: 0 events, but
  also 0 fills — unexercised this window** (metric valid only on tape).
  **R27: 0 `floor_carry` renders — correct: no run currently carries a
  past-floor total while flat** (1531 retired; successors start clean).
- **Shape:** 420 decisions, 99.3% hold, **no_verdict 0/420** (the
  collapse is complete this window; salvaged 4 — the rail absorbing
  every truncation), empty-why 0/8 (watch-11 rate stays zero).
- **Churn tally: unchanged** (a=4 ≈−$5.4 · b=5 · c=4 · d=2) — no legs.

**The honest verdict:** R26's binding metric — trades/day against the
8.2/day baseline — has NOT moved; it fell (5 on 08-20, 0 since). The
gate no longer strips candidates (proven), the slots fill (proven), the
desks see the candidates and decline ~100% on conviction. The binding
constraint is now fully DESK CONVICTION on the current candidate
quality, exactly where the funnel diagnosis said the falsification
sample pointed (declined entries were ≈ fee-negative). Nothing to fix
by rail; the lever, if the owner wants throughput, is candidate quality
(research depth/coverage), not gates. Recording, not acting (n is
tape-thin and the discipline is not wrong at these setups).

Docs→main batch: PR follows (cycles 150–174 + this sweep).

## Cycle 174 — 03:5xZ (anchor 03:56:52): quiet

No money events, no positions. NFLX 1591 expired at_time, never traded
($0, flat book). Fence 0; 0 tracebacks.

## Cycle 173 — 03:2xZ (anchor 03:26:55): quiet

No money events, no positions. TMO 1621 built (fleet 37, dormant till
NYSE). Fence 0; 0 tracebacks.

## Cycle 172 — 02:5xZ (anchor 02:56:51): quiet

No money events, no positions. CHFJPY 1611 fused ($0); KAITO 1620
built. Fence 0; 0 tracebacks.

## Cycle 171 — 02:2xZ (anchor 02:26:51): quiet

No money events, no positions. ETH 1619 built. Fence 0; 0 tracebacks.

## Cycle 170 — 01:5xZ (anchor 01:56:54): quiet

No money events, no positions. AUDUSD 1617 + AVAX 1618 built. Fence 0;
0 tracebacks.

## Cycle 169 — 01:3xZ (anchor 01:31:38): micro-window (30s — displaced cron), nothing new

No events, no positions, 0 tracebacks.

## Cycle 168 — 01:3xZ (anchor 01:31:08): quiet

No money events, no positions. Three $0 fuses (EURCHF 1608, EURUSD
1609, GBPAUD 1610); one build (1616). Fence 0; 0 tracebacks.

## Cycle 167 — 00:2xZ (anchor 2026-08-21T00:26:52): quiet; day rolled

No money events, no positions. 08-20 final: **−$1.46** (check ok).
Two builds (1614, 1615). Fence 0; 0 tracebacks.

<!-- newest-first -->
