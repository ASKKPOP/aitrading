# Deep analysis — last 24 hours (2026-08-22T10:24Z → 2026-08-23T10:24Z)

Owner request 2026-08-23: "deep analysis for last 24 hours". Method per the
two-subagent rule (Agent A = AI-authored outcomes, Agent B = algorithm-authored
outcomes, main session cross-check) and the experimental-mindset rule. Solution
documents this note is measured against: [research/05](../research/05-full-logic-audit-2026-08-22.md),
[research/06](../research/06-redesign-experiments-2026-08-22.md) (Phase 1 justification),
[HANDOFF-SESSION-2026-08-22 §5](HANDOFF-SESSION-2026-08-22.md) (accountability metric).
Prod image all window: `sooppiy-backend:20260822-redesign-phase1` (deployed 10:36Z), 0 tracebacks.

## 1. Profit or loss

**Realized $0.00 · fills 0 · open positions 0.** Last fill on the platform:
2026-08-20T07:10Z (3 days 3 h ago). Four consecutive 24h windows, panel-kept
buys: 11→0, 16→0, 82→0, 68→0 proposals→kept. Fills: 6, 0, 0, 0.

Counterfactual (Agent A, Hyperliquid 5m, rail stop 4% / algo target / run horizon):
top-5 demoted proposals by confidence −$11.06, flips to +$17.1 with the largest
loser stripped → **inconclusive** (rule 6). All 7 distinct proposals −$33.6;
strip largest loser −$5.4 → sign holds: **no forgone profit proven**. 3/7 stopped
(UNI, SUI, DASH via its own invalidation), 0/7 reached target; the two runners
(TRB +7.3%, CRV +8.2%) stalled 0.1–1.1% short of target. The three desk
retirements (TAO, BTC, ZEC) each avoided a loss on replay.

## 2. Phase 1 accountability at 24h — the metric did not move, and we know why

Phase 1 removed the reachability record line for crypto (research/06 Synthesis §1).
Measured: crypto `decision` reports citing a reachability/stop-first statistic fell
**52/247 (21%) → 2/223 (0.9%)** pre→post (both post cites are at 10:25Z, before the
deploy). The exclusion reached the prompt. Panel-kept buys: **0 → 0**. Therefore
the record line was **not the binding suppression channel** (H1, Agent A, n=68:
1/68 demotion reports cite it, pre-deploy). Do not re-run H1.

What *is* binding (three channels, all measured):

| channel | evidence | Phase 1 touched it? |
|---|---|---|
| **Panel technical read** — RSI 74–87 + long/short >2 + volume 0.02–0.5× → "pullback" | 68/68 demotion reports; primary in 67/68 | no |
| **`agent_memory` echo** — panel writes 2 outcome-less lessons per panel, recalls 5 newest | 174 writes/24h; of last 200 lessons 131 say pullback/reversal, 114 overbought, **0 carry an outcome**; "desk memory" cited in 24/223 post-deploy decisions (10.8%) vs 19/404 (4.7%) the day before | no |
| **`desk_memory` recall** — `skill:reachable-exits#1` injected as the "past lesson" | 222/222 flat crypto cycles post-deploy; the new skill `measured-entry-record` recalled **0/222** | no (see §3) |

Agent A's H5 (supported, n=68 + 924-row corpus): the panel's self-written memory is
unfalsifiable by construction — no lesson carries an outcome, each hold writes two
more copies of the reason for the next hold.

## 3. The new skill is buried by the recall ranker (reproduced, read-only)

`measured-entry-record` (the Phase 1 skill that says a flat crypto book has a
measured opportunity cost) IS in the corpus (4 chunks, ingested 10:37:02Z) and IS
rendered in the static skills block (`trader` 43 KB / `light` 25 KB prompts, found).
But `run_engine._recall_line` searches kinds `("outcome","lesson")` with the fixed
query `"crypto flat considering entry fee hurdle expected move"` and a pool of 5.
Run inside the worker container:

```
kinds=(outcome,lesson): #1 reachable-exits#1 8.33 … #11 measured-entry-record#2 6.28  (pool=5 → never shown)
kinds=(lesson,):        #1 measured-entry-record#1 8.43, #2 measured-entry-record#2 7.81
```

The pooled BM25 IDF across `outcome` chunks re-weights the query terms so the old
doctrine outranks the new lesson every cycle. **H-RECALL-FLAT is explained**: it is
a ranking artefact, not a content choice. This is a Phase 2 item (Plan 22 ledger),
not a hot-fix — changing recall touches every desk prompt and needs its own
experiment (replay the 222 queries with lesson-only kinds or a query that names
opportunity cost, and show the panel's demotion rate moves).

## 4. Algorithm-authored costs (Agent B, all verified two ways) — $0, slot-hours not

1. **Fleet 38 self-starvation — 64% occupancy** (41.3 of 115.6 slot-hours empty):
   idle-retire (12 worked cycles ≈ 5h10m, `RUN_IDLE_RETIRE_CYCLES=12`, 100% of runs)
   × 12h `IDLE_SYMBOL_COOLDOWN_HOURS` × ~15-name crypto pool → `select_targets`
   returned 0–1 candidates (33 cooldown rows in window; `no_candidates` 07:14,
   10:05, 19:00). Largest algorithm-side cost of the day.
2. **ENAUSDT loop**: 28 deterministic `bracket_infeasible` retries every 5 min
   (`FLEET_EMPTY_SLOT_RETRY_SECONDS=300`); sigma is frozen on the thesis row
   (12.84/12.71/12.53%); only the "outside any run" reason writes a cooldown;
   ~5.5 slot-hours. H-ENA-FLAPPING-SIGMA refuted.
3. **H-GATE-SPLIT — proven.** `_bucket_expectancy_block` is called only on the
   build path (`fleet_planner.py:1807`); `fleet_supervisor._build_replacement`
   never references it (its docstring's "parity" claim refers to the per-symbol
   `backtest_gate`, a different gate). 04:57Z build refused crypto/long ×4
   (−1.31 over 109 closed runs); 04:59Z replacement started the same four
   (1704–1707); recurred 10:26Z (1711 ASTER). Cost: 48 desk cycles + 23 panels,
   $0 — and the alternative candidates were Sunday-closed forex.
4. **H-AUTOTUNE-UNFUNDABLE — verified.** Fleet 39 slots sum $10,005.32 of a
   $10,005.35 budget → headroom $0.03; `auto_tune_slots 7→25` (05:14Z) lowers
   `floor_usd` 714→200 and the backfill loop breaks at `alloc=0.03 < 200`; zero
   `slot_created`; "replenishing:7/25" is a phantom label. Replacement funding of
   the 7 real slots unaffected (funding = retiring run's own budget, observed).
   `recommended_max_slots` ignores budget already committed.
5. **Weekend-closed rotations by owner rule** (explicit `market_scope_json` is
   used verbatim, 2026-08-12 decision): AUDUSD/EURUSD dead until 21:00Z, ZC/SI/HG
   until 22:00Z → ~17 slot-hours in window, ~74 by reopen.
6. **Idle-retire is not culling ripening setups** (H-IDLE-PREMATURE refuted):
   16 retired runs × 12 cycles = 192 decisions, 0 final buys, no confidence trend.
7. `fleet_stop_all` on 38 at 01:10Z: user `/api/fleets/38/stop`, 10 flat members,
   nothing flattened, 37 s.

## 5. Where the two agents disagreed — and the resolution

B: "the panel's demotion reasons quote platform rails (TRB '$2.63 loss rail');
the composer sized `max_loss_usd` so small that `bracket_infeasible` should have
refused these crypto runs at build, as it refused ENA." A: bracket/rail language
is secondary in 32/68 and primary in 0/68; the primary reason is the technical
read. Resolution from the tape: both are true and neither is the lever —
removing the rail clause would leave 68/68 overbought demotions standing. The
rail sizing is a real build-parity gap (ENA refused, TRB admitted then
unexpressible) and goes to the backlog; it did not decide a single entry today.

## 6. Observability gaps that block the next experiment

- The desk's proposal is destroyed on demotion: no bracket, scores or rationale
  persisted (`order_params` = `deferred`); only 8 truncated `verdict_salvaged`
  tails survive. Panel-vs-desk replay needs the proposal persisted in the
  `order_discussion` payload.
- 1 null verdict + 8 truncations: the JSON+outlook+report contract still overruns
  the light tier's output budget.

## 7. Hypotheses closed by name

REFUTED: H1 (reachability line binding), H2 (0.65 gate mechanical: 13/68 finals
*raised* confidence yet held), H-IDLE-PREMATURE, H-ENA-FLAPPING-SIGMA,
H-AUTOTUNE-STARVES-REPLACEMENT. SUPPORTED: H5 (memory echo), H-GATE-SPLIT,
H-AUTOTUNE-UNFUNDABLE, H-RECALL-FLAT (now explained as pooled-IDF ranking).
INCONCLUSIVE: H3 (desk proposals weak — n=0, not persisted), top-5 counterfactual.
PARTIAL: H4 (quantization: 41% of finals on 0.58/0.62).

## 8. What changes, and what does not

Nothing was changed on prod in this session. Per the experimental rule, each
item above that touches the desk's prompt (recall kinds/query, agent_memory
outcome attachment, proposal persistence) needs a pre-registered replay before
wiring; the two algorithm items with no money path (H-GATE-SPLIT parity,
auto-tune committed-budget check, bracket_infeasible cooldown) are backlog
candidates with their measured cost stated above. Phase 1's 48h clock (fleet 39
crypto, ends ~2026-08-25T05:03Z) stays; at 24h the honest reading is **0 entries
and the cause identified** — the record line was a sentence the panel was not
leaning on.
