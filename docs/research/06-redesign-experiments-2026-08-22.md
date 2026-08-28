# Redesign Experiments — Panel-Demotion Replay and Horizon Reconciliation (2026-08-22)

Follow-up to [05-full-logic-audit-2026-08-22.md](05-full-logic-audit-2026-08-22.md).
The audit's §7 named two fork-deciding experiments; both are now run, with the
decision rules pre-registered before any data was touched. This document records
the designs, the results, the verdicts, and the Phase 1 changes they justify.

## Experiment 1 — were the panel's demoted buys right? (three agents, all markets)

**Pre-registered:** replay each demoted buy proposal from decision time to the
first of {its own stop, its own target, horizon end → mark-to-market}, net of
per-market fees. Primary unit = EPISODE (consecutive same-run proposals collapse
to one idea; streak broken by >2h gaps or an intervening non-buy). PANEL-WRONG
requires net > 0 that survives stripping the single largest winner; a sign flip
under any single removal = INCONCLUSIVE.

**Data limits stated:** demoted proposals never journal their own stop
(stop_ref_px null in all 310 crypto/futures rows; the panel replaces the
proposal wholesale before order-params are authored), so plans were recovered
from the same-cycle standing plan / run thesis; losses ride to horizon where no
stop exists. Futures prices are Yahoo continuous front-month proxies (median
offset vs platform 0.039%); us-stock gaps fill AT the gap open.

**Results (episodes, net of fees):**

| Market | n | Net | Strip largest winner | Win rate | Targets hit | Verdict |
|---|---|---|---|---|---|---|
| crypto | 74 | **+$145.10** (+50.1pp) | **+$84.54 — still positive** | 55.4% | 6/53 with targets | **PANEL WRONG** |
| futures | 40 | −$13.63 | (strip largest LOSER: −$7.22, still −) | 32.5% | **0/32** | **PANEL RIGHT** |
| forex | 41 | −$0.94 | −$7.82 | 36.6% | **0/41** (21/41 hit own stop first) | **PANEL RIGHT** |
| us-stock | 24 (strict) | +$7.21 | **−$0.60 — sign FLIP** (all profit = INTU) | 50% | 5/25 | **INCONCLUSIVE** |

Notable single datum: CBRS (annex) made +$49 to its 10% target while its own
invalidation condition was already breached at proposal time — a self-invalidated
thesis that paid anyway. Selection carries no information even when it wins.

**Verification:** episode collapse hand-audited; sums independently recomputed
(awk vs python, exact); candle-level audits (FIL/GC/ZEC + 6 stock/fx spot checks
against a second price vendor); per-proposal secondary unit (2.7× n) agrees in
sign for every market; the synthesizing session independently re-measured the
611→11 panel matrix and the #413/#414 merge timestamps.

## Experiment 2 — are the desk's targets real or decoration? (all opened positions)

**Pre-registered:** for every opened position (30d), walk price from entry to the
first of {registered stop, registered target, the desk's own stated horizon end}.
H-LEAK (exits cut winners short) requires the counterfactual P&L to beat the
realized P&L; H-DECORATION if targets are hit <20% even given full horizon.

**Result: H-DECORATION, decisively; H-LEAK REFUTED in every market.**

- Targets hit within the desk's own stated horizon: **7/104 (6.7%)**.
  Stop hit first: 31/104. Neither: 63.5%.
- Counterfactual net **−$337.65 vs realized −$179.58** — holding to the desk's
  own plan would have lost **$158.07 MORE**. Robust to stripping the largest
  contributor either way.
- Median time-to-stop 5.4h vs time-to-target 32.9h: extending holds harvests
  stops, not targets.
- The early-exit machinery (desk exits, at_time, retires) is net
  value-PROTECTING — consistent with the audit's rail replays (7/7 in the
  rails' favor).
- Exclusions: 8/112 accounted; realized total reconciles the audit's
  triple-verified −$175.30; conservative same-candle rule invoked 0 times.

## Synthesis — the fork, decided

1. **Crypto: entry suppression is the defect.** The panel/doctrine wall demoted
   entries that would have paid (+$145/8d, robust). The suppression channels
   (reachability line, panel prompt) must stop firing for crypto.
   > **2026-08-23 note (24h after deploy):** the reachability line was removed and is verifiably uncited (crypto decision reports citing it 21% → 0.9%), yet panel-kept buys stayed 0/68. The line was NOT the binding channel. The binding channels measured are the panel's technical read (68/68), the outcome-less `agent_memory` echo (24/223 decisions cite "desk memory", rising), and `desk_memory` recall ranking `reachable-exits#1` first in 222/222 flat cycles while the new `measured-entry-record` skill ranks #11 under the pooled (outcome+lesson) BM25 IDF — pool is 5, so it is never shown. See [reports/2026-08-23-deep-analysis-24h.md](../reports/2026-08-23-deep-analysis-24h.md).

2. **Futures + forex: the generator is the defect.** No authored target has
   ever been reached inside its horizon (0/73 demoted + 0/44 opened). Blocking
   these trades protected money; un-gating changes nothing until targets are
   derived from measured per-hold movement.
3. **Everywhere: LLM targets are decoration** (6.7% hit rate at full horizon).
   The replacement is volatility-derived (ATR-of-hold) brackets — Phase 2, to
   be proven by replay before wiring (audit §7.2–7.3).
4. **The exit rails stay.** Both experiments independently re-confirmed they
   protect value.

## Phase 1 changes shipped with this document (each justified above)

- **desk_record R30 denominator fix**: the reachability record now scales by
  peak concurrent notional, not the sum of every opening leg (was understating
  the ceiling ~47% us-stock / ~57% forex — the doctrine's pessimism was partly
  a bug).
- **Crypto excluded from the reachability line** (both prompts, centrally in
  `desk_record.record_line`) — implementing Experiment 1's crypto verdict.
  Futures/forex/us-stock keep the line with corrected numbers.
- **`DESK_REACHABILITY_AB` retired**: the A/B was proven unreadable (the panel
  prompt rendered the line in both arms; the doctrine reached control runs
  through other channels; 0 entries in both arms). Its question was answered by
  Experiment 1 instead.
- **New skill `measured-entry-record`** (owner rule: decisions become skills):
  three measured lessons — targets must be sized to measured per-hold movement;
  crypto declines have a measured opportunity cost; futures/forex plans whose
  targets exceed measured movement are unexpressible.

## Phase 2 (next, in order — each with its proving experiment)

1. ATR-of-hold bracket generator, proven by paper-replay on the 30d entries
   against the desk's own brackets before any wiring.
2. Win-side exit machinery rebuild (trailing activation scaled to position, not
   max_loss; position-scaled profit target; split the two `trailing_lock`
   labels).
3. Sizing ladder $52 → $520 → $5,200, sign measured at each rung.
4. Futures/forex: re-horizon or descope, decided by the ATR-bracket replay.
5. positions DB invariant (UNIQUE index or SUM-based reads) — run-1099 class.
6. Retire→cooldown→rebuild treadmill fix.

Datasets: `exp1-crypto/episode_replay.tsv`, `exp1-stockfx/episodes.tsv`,
`exp2-horizon/episodes_counterfactual.tsv` (session scratchpad; headline numbers
reproduced in full above).
