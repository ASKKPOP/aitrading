# Automation monitoring — 2026-08-15 (UTC day), newest-first

Loop RESUMED by owner 01:34Z after the 2026-08-14 23:3xZ stop. Crons re-armed:
30-min cycle `4ade12c3` (`13,43 * * * *`), 24-h sweep `71d7c9ce` (`7 8 * * *`).
Live fleet is **34** (forevery1969@gmail.com, user 25 / agent 60) — the Plan 25
Phase D v2 cohort, created 00:12:28Z. See `2026-08-15-plan25-phase-d-baseline.md`
for the v1 bar this fleet must beat.

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
