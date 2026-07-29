# Phase-4 strategy backtest — go/no-go result

**Date:** 2026-07-16 · **Verdict: INSUFFICIENT_EVIDENCE → the flip package does NOT ship. All execution gates stay default-off.**
**Runner:** `service/server/run_phase4_backtest.py` · raw numbers: [phase4-backtest-result.json](phase4-backtest-result.json) · engine: `backtest_strategy.py` (unit-tested; two independent runs byte-identical).
**Plan:** [docs/plan/04-ai-model-parameter-upgrade.md](../../plan/04-ai-model-parameter-upgrade.md) §Phase 4 — criteria were pre-registered before the OOS windows were opened.

## 0. Summary

<!-- This section was written in Korean and left untranslated in the ENGLISH
     document until 2026-07-29, so English readers were served ~309 Korean
     characters here. The Korean text lives where it belongs, in
     3-phase4-backtest-report-ko.md; this is its English counterpart. -->

Judged against the pre-registered criteria the result is **INSUFFICIENT_EVIDENCE** — the flip package (execution gates on by default) does **not** ship. The deployment-faithful configuration (≥4/6) produced only **38** OOS trades across the six-year walk-forward against a 400-trade bar, and both the Wilson 90% lower bound on the 36.8% win rate (0.28) and the bootstrapped profit-factor lower bound (0.64) fall short. Relaxing to the sensitivity row (≥3) raises the count to 237, but the PF lower bound is still 0.88 — under 1.0, so profitability is not statistically established.

**What did hold up:** the risk stack behaved exactly as the research promised — worst-asset maximum drawdown **2.6%** against −38% to −47% for buy-and-hold over the same window, 53% of exits taken by the trailing stop (letting winners run), and capital preserved by cutting losses rather than by predicting. The verification panel's statistical lens called this outcome in advance: too few trades.

**Next:** every feature is already shippable as display / advisory / opt-in. Re-evaluate the six-condition system including B4 live-forward once live telemetry (confluence vectors, factor snapshots) has accumulated. The thresholds go back to research — not to production.

## 1. Pre-registered setup (unchanged after seeing results)

- **Primary row:** deployment-faithful defaults (`confluence_min=4`, `volume_confirm_min=1.5`), never tuned — zero snooping by construction.
- **Walk-forward row:** anchored, 4 folds, 14-day purge, 6-config grid (reported), tuned on train by pooled profit factor (≥30 trades), frozen on test.
- **Sensitivity row:** `confluence_min=3` fixed (B4 is null historically → only 5 of 6 conditions achievable; the live gate is therefore *stricter* in backtest than in deployment).
- **Criteria:** ≥400 pooled OOS trades, else INSUFFICIENT_EVIDENCE · Wilson 90% lower bound of win rate > 0.50 · bootstrap 90% lower bound of profit factor > 1.0 · worst-asset max DD ≤ 30%.
- **Scope honesty:** B4 null throughout; B3 degraded to MA/RSI/volume; B5 = F&G leg only (full 2018+ archive, one-day extra lag); S5 null; events = the doubly-source-verified 2019–2025 calendar. Assets: BTC/ETH bars from 2019-01 (signals ≈2020-02 after 400-bar warmup), SOL from 2020-04 (signals ≈2021-05). Fees 0.1%/leg + 0.05% slippage; close-t signals fill at open t+1.

## 2. Results

### Primary (deployment-faithful ≥4/6) — pooled over 4 OOS folds × 3 assets

| Metric | Value | Criterion | Met? |
|---|---|---|---|
| OOS trades | **38** | ≥ 400 | ❌ (evidence floor) |
| Win rate | 36.8% (14/38) | Wilson90 LB > 0.50 → LB = **0.276** | ❌ |
| Profit factor | 1.13 | bootstrap90 LB > 1.0 → LB = **0.644** | ❌ |
| Worst-asset max DD | **2.63%** | ≤ 30% | ✅ |

Per fold: F1 (2021-07→2022-12, bear): 19 trades, PF 1.82 · F2: 6 trades, PF 0.69 · F3: 7 trades, PF 6.53 · F4 (2025-07→2026-07, bear): 6 trades, PF 0.0.
Exit mix: trail_stop 20 (53%) · stop_loss 15 · time_stop 3 — the trend-following profile the research prescribes (win small share of trades, let winners run: mean winner ≫ mean loser is what pushes PF above 1 at a 37% win rate).

### Sensitivity (≥3 of 5 available)

237 trades · win 37.1% (Wilson LB 0.332) · PF 1.15 (bootstrap LB **0.884**) · worst DD 8.97%. More evidence, same conclusion: point-estimate profitability, not statistically distinguishable from break-even.

### Walk-forward (tuned per fold, 6 configs — snooping accounted)

Every fold tuned to `confluence_min=3`; test PF: F1 1.46, F2 1.82, F3 0.69, F4 0.79. Edge is regime-dependent and does not persist across folds — consistent with the research's "published edges decay" warning.

### Condition correlation (the statistics lens predicted this)

B1↔B2 daily agreement **0.709** (both trend measures), B1↔B3 0.52, B2↔B3 0.40. The six conditions are not independent; the "stack independent 53% edges" arithmetic does not apply at face value.

### What DID work

In the F4 bear window the strategy lost ≈1.1–1.7% per asset while buy-and-hold lost **−21% (ETH), −38% (BTC), −47% (SOL)**. Max drawdowns of 2–9% vs B&H's 60%+ historical drawdowns. Exposure 3–6% of days. **The system's verified value is capital preservation through regime filtering and the exit stack — exactly the research's claim that "the edge comes from risk management, not prediction." What is NOT verified is stand-alone profitability.**

## 3. Decision (per the pre-registered rule)

1. **No flip.** `CONFLUENCE_GATE_ENABLED`, `REGIME_FILTER_ENABLED`, `VOL_SIZING_ENABLED` stay **default-off**. No preset/`min_confidence` migration ships. The plan's own sentence governs: *"If below [criteria], the confluence thresholds go back to research, not production."*
2. **What ships anyway (already merged, zero execution-behavior change):** confluence display + agent API, regime advisory + tile, telemetry (confluence vector per decision, factor snapshots), the safety fixes (breaker tripped_by/expires_at, never-loosen SL/TP, first_opened_at, risk-direction gating, put_risk_limits repair), the repaired backtester metrics, and the opt-in per-agent exit toolkit (trailing/time stops — individual agents may enable them; they are positional risk tools, not profitability claims).
3. **Re-evaluation path:** live-forward. The Phase-1 telemetry accumulates the full 6-condition vector (including B4) with every decision; factor snapshots record funding/OI/L-S/StockTwits. When ≥400 gated-quality live decisions exist (or a future backtest can include the missing conditions), re-run the criteria. The calibration table (hit rate per confluence count, Wilson CIs) builds itself from telemetry.
4. **Threshold work returns to research:** the interesting open question from the data is whether the *exit stack alone* (trail + time stop + regime veto) on a simpler entry signal carries the value — the confluence entry gate at ≥4/5 was so strict it traded 6×/year across 3 assets.

*Not investment advice. Simulator platform. Historical edges decay; these numbers describe one backtest under the documented scope limits.*
