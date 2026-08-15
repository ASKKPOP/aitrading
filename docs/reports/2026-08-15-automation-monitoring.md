# Automation monitoring — 2026-08-15 (UTC day), newest-first

Loop RESUMED by owner 01:34Z after the 2026-08-14 23:3xZ stop. Crons re-armed:
30-min cycle `4ade12c3` (`13,43 * * * *`), 24-h sweep `71d7c9ce` (`7 8 * * *`).
Live fleet is **34** (forevery1969@gmail.com, user 25 / agent 60) — the Plan 25
Phase D v2 cohort, created 00:12:28Z. See `2026-08-15-plan25-phase-d-baseline.md`
for the v1 bar this fleet must beat.

---

## Cycle 3 — 02:27Z (anchored 02:27:49Z) — FIRST REAL LOSS, two-agent analysis

**P&L FIRST: fleet 34 realized −$2.06** (1271 −0.074, 1272 −0.446, **1274 −1.544**),
open +$0.13 → **≈ −$1.93 mark-to-market**. `pnl_audit` 08-15 remains `ok`.

Run 1274 SOLUSDT: shorted 6.5755 @ 75.28 (01:11:03Z), covered in two halves —
3.2877 @ 75.38 (02:10:19Z, `run:1274:cyc:5`) and 3.2877 @ 75.514 (02:24:52Z,
**`client_order_id: null`**). Both agents dispatched per the owner rule.

### Loss decomposition (Agent B, reconciled to equity seq 165 to the cent)

| component | USD | share |
|---|---|---|
| fees (0.22275 + 0.11152 + 0.11172) | **−0.44599** | **28.9%** |
| leg 1 price (75.28→75.38) | −0.32877 | 21.3% |
| leg 2 price (75.28→75.514) | −0.76933 | 49.8% |

**29% of the loss was fee, on a $495 notional held 74 minutes.**

### 🔴 THE AGENTS DISAGREED — and the disagreement is the finding

**Agent A:** honouring the desk's own cycle-5 stop (0.7% → 75.807) means leg 2
never fires; realized would be **−0.663 instead of −1.544 — "$0.881 less loss."**

**Agent B:** refuted it on the actual tape — SOL's post-hit lows were 75.506 /
75.535 / 75.536 and the wider stops (75.807, 76.454) were **never reached**
(max 75.576).

**Main-session adjudication — B is right, A is wrong.** Priced against the live
mark **SOL 75.55** (OKX, 02:37Z): the surviving 3.2877 short at entry 75.28
marks at **−0.888**, plus the −0.663 already realized = **−1.551**, and it would
still owe ~0.111 of exit fee → **−1.662 versus the actual −1.544.**
**The counterfactual is ~$0.12 WORSE, not $0.88 better.**

Agent A compared a *realized* loss against an *unrealized* snapshot of the
alternative and booked the gap as a saving. That is precisely the flawed logic
the owner law forbids, and it is rejected. **No rail cost money in this window;
the fail-safe close at 75.514 was at or better than every subsequent print.**

### ✅ CONFIRMED BY BOTH, and re-verified in the main session

1. **The stop that killed it was never the desk's.** Verbatim from
   `order_params` cycle 3: `"stop_pct 0.016 raised to floor 0.3"` (SOL) and
   `"stop_pct 0.007 raised to floor 0.3"` (BTC). The desk emits sub-basis-point
   stops while writing the rationale *"stop sits just above recent
   resistance"* — its words and its number are disconnected.
2. **Stop revisions after the opening cycle are journaled and discarded.**
   BTC 1271 asked for `stop_pct 1.23` at cycle 5 (→ 63,749); the stored
   `positions.stop_loss` is still **63,163.5**, the cycle-3 0.3% value. Agent B
   audited all four writers of `positions.stop_loss` — `automation.py:247/271`
   (monotone), `orphan_reclaim.py:183` (`WHERE stop_loss IS NULL`),
   `risk_engine.py:656` (tighten-only), `routes_trading.py:845` (manual user
   API) — **no path exists for the desk to widen a stop mid-life**, while
   `_stop_hit_line` (run_engine.py:3196) explicitly instructs it to *"hold ONLY
   with a re-authored stop_pct"*. An instruction the code cannot execute.
3. **The null `client_order_id` is `risk_engine.sl_tp_watch`'s fail-safe.**
   Worker log names it: 6 × "SL/TP hit routed to desk" at 30 s ticks from
   02:21:48, then `02:24:51,977 WARNING SL/TP desk routing TIMED OUT —
   fail-safe close`. Desk orders stamp `run:{id}:cyc:{n}`; the watcher has no
   cycle to name.
4. **The desk was structurally barred from ruling on its own stop.**
   `stop_router` timeout 180 s vs an adapt loss-cooldown of **3600 s**, and the
   cooldown gate (`run_engine.py:5047`) `return`s 186 lines *before*
   `stop_router.clear()` (line 5233). **A 20× asymmetry: any stop hit during
   adapt cooldown deterministically ends in a watcher close.** Self-inflicted —
   the desk's own risk-reducing half-cover armed the cooldown 23 seconds after
   the stop hit was noted. `adapt` simultaneously recorded
   `thesis_status: "intact"` and locked the desk out for an hour.
5. **`young_dump_flag` is telemetry only** — `run_engine.py:5462`, comment says
   *"NO behavior change"*. P&L effect exactly $0.00.
6. **recall never returns lessons or outcomes.** Agent A measured **163 recall
   events since 2026-08-14: `monitoring` 163, `lesson` 0, `outcome` 0** — an
   independent, wider-window confirmation of the cycle-2 finding that PR #432
   fixes. Bitter detail: recall delivered *"stops tighter than a day's noise"*
   to this very run at 01:38 and 02:10. **The desk acted on it** — it asked for
   0.7%. The platform discarded the request and stopped it out on 0.3%.

### 🔴 THE PROFIT FINDING — the thesis was fabricated, and the gate cannot see it

Agent B found this and Agent A missed it entirely. Verified verbatim in the
main session from `research_theses` / `config_snapshot_json`:

| field | value |
|---|---|
| `expected_move_pct` | **4.0** |
| `vol_daily_pct` (SOL's own measured daily range) | **1.2421** |
| `mom_2d_pct` | −0.3175 |
| `volume_ratio` | **0.2573** (26% of normal) |
| `technical` subscore | **−0.0597** (≈ zero) |
| `psych` / `social` / `news` subscores | **all null** |
| `final_score` | 0.8655 → **selected** |

**A 4.0% expected move was claimed on an asset whose ordinary day is 1.24%** —
3.2× a day's range, over 48 h, on quarter-normal volume, with a technical
subscore of approximately zero and no psych/social/news support at all.

The resulting geometry could essentially only lose:

- stop 0.3% = **one quarter of an ordinary day**
- target 0.6%, claimed move 4.0% = **3.2 ordinary days**
- round-trip fee ≈ 9 bp = **30% of the stop distance**

**And the fee/edge gate consumes `expected_move_pct` as an INPUT** — so it
verified the arithmetic against a number the planner invented. The gate cannot
detect that the claim is unsupported by the momentum and volume fields sitting
beside it in the same row.

**This chains directly to cycle 1.** The ranker had 5 crypto candidates for 5
open slots and took 100% of them — so a thesis claiming 3.2× a day's range on
26% volume could not be rejected, because there was nothing to reject it in
favour of.

### Falsifiable prediction, stated BEFORE the outcome

**BTC 1271 is 0.110% from the same death**: mark 63,094, stop 63,163.5, thesis
invalidation ~63,785, and its cycle-5 request for `stop_pct 1.23` was discarded.
If it stops out on an unfalsified thesis, the mechanism is proven at n=2 and a
fix is designed. If it does not, this analysis is revised. Recorded now so it
cannot be confirmed after the fact.

### Watch items (new)

7. **Run 1274 is still `status='running'` with a flat book**, cooldown to
   03:22:11Z, on the same fabricated thesis. Watch whether it re-shorts SOL.
8. Liquidation daemon liveness **inside** the window is not provable from logs —
   there is no heartbeat line, only registration + a successful run 36 min
   prior + no crash trace. Stated as a limit, not asserted as healthy.

---

## Cycle 2 — 01:47Z (anchored `SELECT NOW()` = 2026-08-15 01:47:34Z)

**Tape: silent.** Zero trades, zero closes since cycle 1 → no two-agent
dispatch (nothing to attribute). `pnl_audit` 08-15 **−$0.30**, `ok`, 0 flattens
— unchanged. Two decisions, both `hold` (SOL 1274 conf 0.53, ZEC 1275 conf
0.48). Fleet 34 still **5/25**. Queued flattens still correctly parked. Worker
clean; one new benign feed 404 (`Yahoo daily candles failed for BK`).

**Book drifted against us, small:** SOL 1274 short −$0.53 → **−$0.74**,
BTC 1271 short −$0.09 → **−$0.12**. Fleet 34 total −$1.16 (−$0.30 realized fees
+ −$0.86 open). Both shorts are losing because crypto ticked up; neither has
reached any rail. Not a defect — but it is a loss, and it is the reason the next
finding matters.

### 🔴 FINDING — the desk's memory recall reads the wrong 15% of its own corpus

First live sighting of the Plan 22 RAG `recall` event this session, on run 1274
cycle 4 — the SOL short, while losing, asking *"cut or hold?"*.

**The corpus (`desk_memory`, prod):**

| kind | chunks | retrieved in production? |
|---|---|---|
| `decision` | 3,231 | ❌ never |
| **`monitoring`** | **636** | ✅ **the only kind ever read** |
| `outcome` | 278 | ❌ never |
| `lesson` | 147 | ❌ never |

There is exactly **one** production call site — `run_engine.py:3937`, inside
`_recall_line`, with **`kind="monitoring"` hardcoded**. Every other
`desk_memory.search` in the tree is in `tests/`. The result is injected straight
into the decision prompt at `run_engine.py:4385` under the heading
*"What this desk has already learned about cycles like this."*

So the desk's memory of **actual trade outcomes (278 chunks)** and its
**curated Plan 22 trading lessons (147 chunks)** are dead weight — written,
stored, and never read by anything that trades.

**What it actually injected into run 1274's prompt** (`scheme:
deterministic-top2`, both hits from `2026-08-03-automation-monitoring.md`):

1. `#The ladder that never ends — quantified, and NOT shipped` (score 12.29).
   Body: scaling out of a position cost **0.53 of drag** versus holding whole,
   concluding *"the cause is not mechanical greed, and that is why nothing
   ships."*
2. `#NEW WATCH — stops tighter than a day's noise` (score 10.88). Body:
   *"Two instances, **no outcome yet** — neither has been stopped out. Logged,
   not shipped."*

A desk deciding whether to cut a losing short was handed (a) an argument that
trimming is drag, and (b) an explicitly unresolved hypothesis — both labelled
as things it had *learned*. Neither chunk carries an outcome. Both are
engineering commentary about whether to ship a platform change.

**Base rate of deliberately-inconclusive chunks** ("NOT shipped" / "no outcome
yet" / "logged, not"): **16 / 636 monitoring — and 0 in every other kind.** The
one corpus the desk reads is the only one carrying text we wrote precisely
*because we had not concluded anything.* And retrieval is biased toward them:
those sections are written while analysing a losing shape, so they are
term-dense for exactly the query a losing run generates. The observed hit
ranked **#1**.

**Honesty about strength of claim** (owner law — do not assume the analysis is
right):
- **CERTAIN** (code + payload + body all read): the single prod recall path
  reads only `monitoring`; `outcome` and `lesson` are never retrieved.
- **CERTAIN**: the two chunks quoted above were injected into a live decision.
- **NOT PROVEN**: that this changed the decision. SOL held at conf 0.53 and is
  −$0.74. **n=1.** This is not yet grounds to claim a measured P&L cost.

**Fix designed (AI-first):** rank `outcome` + `lesson` first — what actually
happened last time in this shape, and the curated lessons — with `monitoring`
as fallback, and exclude chunks carrying unresolved markers. One call site.

### Watch items (carried + new)

5. Recall corpus kind selection — fix in build.
6. `horizon_shadow` fired twice (runs 1274, 1271) with triggers
   `["psych_shock","hot_issue"]`, "desk horizon holds until ~13:1xZ". Shadow
   mode, not acting. First sighting; watching for its first live promotion.

---

## Cycle 1 — 01:34Z (anchored `SELECT NOW()` = 2026-08-15 01:34:35Z)

**P&L (pnl_audit ledger replay, authoritative):** 08-15 **−$0.30**, 0 flattens,
verdict `ok` (fee_asym −0.30, resid 0.00). 08-14 −$17.99 `ok`, 08-13 −$147.49
`ok`. The whole of today's −$0.30 is the **entry fee on two open shorts** —
there are **zero closed trades today**, so no two-agent outcome dispatch this
cycle (nothing to attribute).

**Book (fleet 34):** 5 runs of 25 slots. Two positions open, both shorts, both
marginally underwater: SOLUSDT 1274 −6.5755 @ 75.28 (mark 75.36, uPNL −$0.53),
BTCUSDT 1271 −0.00262 @ 62,974.6 (mark 63,009, uPNL −$0.09). Deployed notional
≈ **$660 against a $100,000 budget**.

**Legacy book (fleets 31/33, both `stopping` since 22:2xZ yesterday):** 4
positions awaiting queued flattens — AUDCHF 1147 (Sunday 21:00Z FX open),
MSFT 1113 / JPM 1116 / IBM 1119 (Monday 13:30Z NYSE open). All four emit
`gate_skip {"stage":"flatten","reason":"market closed — flatten queued to the
next open"}`, 3× each since 00:00Z (R12 dedupe holding — no spam). **Correct
behaviour, not a stall.** Execution must be verified at those two opens.

**Daemons:** worker restarted 00:36:07Z with all 40 tasks. Zero tracebacks in
45 min. `[Liquidation] escalations=1 worst=T1 measured=4/4` — alive. Feeds
healthy (Social 150 fetched, Psych fng=34, Scanner candidates=2, Market Intel
inserted=10, errors=0 on all).

### 🔴 FINDING — the crypto research universe is structurally starved (ROOT CAUSE, measured)

Fleet 34 has sat at **5 of 25 slots for 68 minutes**, and it is Saturday: crypto
is the **only** market tradeable until the FX open Sunday 21:00Z. The fleet is
not stalled by a bug in the fleet planner — it ran out of ideas.

`[FleetPlanner] tick: {'claimed': 3, 'researched': 0, 'built': 0, 'supervised': 3}`
on every tick, and the last build-related fleet event is
`slot_waiting {"slot": 5, "reason": "no_candidates"}` at 00:27:42Z.

**Where the candidates die — measured live in the prod worker:**

| stage | count |
|---|---|
| OKX USDT perpetuals available | **431** |
| Hyperliquid-listed (priceable) bases | **232** |
| `top_symbols._VOLUME_CANDIDATES` pre-filter cut | **20** |
| …of those 20, Hyperliquid-priceable | **8** |
| + scanner discovery candidates | 2 → universe **10** |
| survive the research screen → theses | **5** |

`build_universe()` in prod returns `{'crypto': 10, 'us-stock': 126,
'futures': 21, 'forex': 30}`. Crypto — the only 24/7 market — is **5.3% of a
187-symbol universe.**

**Reproduced, not n=1:** the last **12 consecutive research batches** over 24h
each produced **exactly 5** crypto theses (us-stock 40, forex 24, futures 14).
This is a hard structural ceiling, not a quiet-tape artifact.

**Counterfactual, measured against the live OKX/Hyperliquid response:**

| `_VOLUME_CANDIDATES` | priceable crypto symbols |
|---|---|
| 20 (today) | **8** |
| 40 | 12 |
| 60 | **21** |
| 80 | 33 |
| 120 | 51 |

At 60 the pool is BTC, ETH, SOL, XRP, ZEC, HYPE, DOGE, PUMP, LINK, WLD, UNI,
SUI, 2Z, BNB, KAITO, ADA, WLFI, FIL, TRUMP, BCH, AVNT — all top-60 by 24h OKX
volume, so all genuinely liquid. The ranking step costs **no extra network
call** (`_okx_get("tickers")` already returns all 431 rows); only the research
screen's daily-candle reads grow.

**Why `_VOLUME_CANDIDATES = 20` is wrong here:** its docstring says "Top-5
symbol universe (Plan 11 F1)" — it was sized for a **UI widget**
(`TOP_SYMBOLS_LIMIT = 5`), then reused as the discovery channel for a 25-slot
fleet. `symbol_research.build_universe` even documents the ceiling
("The effective ceiling is top_symbols._VOLUME_CANDIDATES (20)") — the
2026-08-07 widening fix raised its own `[:50]` slice but stopped at the
constant that actually binds.

### ⚠️ The honest profit reading — widening is NOT "more trades = more profit"

Per the Phase D v1 baseline, **crypto is the worst v1 cohort: −$1.50 per closed
run over 68 runs.** Filling 20 more slots into a negative-expectancy book would
*increase* losses. Saying "$99k is idle, deploy it" would be exactly the flawed
logic the owner's law forbids.

The defensible profit argument is **selection, not exposure**:

> With 5 candidates and 5 open slots, the ranker **made no choice at all** —
> it took 100% of what existed.

Evidence: fleet 34 accepted HYPEUSDT at `final_score` **0.30** / confidence
**0.45** (the weakest of the five; BTC scored 1.08). Run 1273 has since decided
`hold` on every one of its 4 cycles (confidence 0.42–0.46) and has **never
traded** — $5,000 parked in a slot that only exists because nothing better was
offered. A ranker given 21 candidates rejects that tail; a ranker given exactly
as many candidates as slots is a pass-through.

**So the fix is scoped as: widen the candidate pool, keep exposure governed by
the existing quality gates.** More to choose from, not more taken.

### Other observations

- **Auto-tune raised fleet 34 from 10 → 25 slots at 00:36:27Z**
  (`auto_tune_slots {"from":10,"to":25}`), 24 minutes after the user created it
  at 10. This is by design (`fleet_auto_tune.recommended_max_slots(budget)`,
  clamped to the plan entitlement cap), but it means the platform silently
  overrode the user's own sizing choice, and it **cut per-slot allocation from
  $10,000 to $4,000** — then created 15 slots that could never fill. Worth an
  owner decision: should auto-tune raise a fleet above the size the user chose?
- `"llm": {"provider":"local","model":"gpt-oss:120b","source":"rule"}` on every
  decision. **`source: "rule"` is NOT "a rule decided this"** — it is the
  `LlmContext` spend-attribution tag set in `run_cycle` (run_engine.py ~5008).
  The desk is live. Checked so a future cycle does not re-raise it.
- Both trades today fired at confidence **exactly 0.62** — the known
  quantization shape (memory `run-ai-confidence-quantization`). n=2, watching.
- One `gate_skip {"stage":"execute","reason":"fence: lease expired"}` on run
  1271 cycle 1. Single occurrence; watching for recurrence.

### Watch items opened

1. Fleet 34 crypto universe — fix in build (above).
2. Queued flatten execution: AUDCHF 1147 @ Sun 21:00Z; MSFT/JPM/IBM @ Mon 13:30Z.
3. R15 (`bracket_infeasible`) and R16 (predecessor line) — first live exercise
   on fleet 34, not yet observed.
4. Fleet 34 is the Plan 25 **v2** cohort: the us-stock v2 members needed for the
   Phase D A/B do not exist yet and cannot until the Monday open.
