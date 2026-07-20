# Plan 11 — AI auto-trading: enablement handoff (any account)

**Status:** QA complete, two blocking bugs fixed and deployed. Ready to enable on a new account.
**Owner:** Henry
**Date:** 2026-07-20
**Predecessor:** [10-ai-auto-trading-runs.md](10-ai-auto-trading-runs.md) — the build plan. This document covers *turning it on* and the two defects that prevented any trade from executing.

---

## 1. What was wrong, and what changed

Auto-trading had never produced a successful trade. Two defects, both fixed and live on prod:

| # | Defect | Fix | Verified by |
| --- | --- | --- | --- |
| 1 | **Local dev loaded no feature flags.** `config.py` read `.env` via pydantic-settings, which populates only declared `Settings` fields and never exports to `os.environ`. Every gate read with `os.getenv()` (`SOOPPIY_API_BACKGROUND_TASKS`, `AUTO_TRADING_ENABLED`, `RISK_ENGINE_ENABLED`, LLM keys) was therefore unset locally — the automation and runs loops never started. Prod was unaffected because docker `--env-file` injects real process env. | `52e4d03` — `config.py` mirrors `.env` into `os.environ` with `setdefault`, so real process env still wins and prod behaviour is byte-identical. | Backend now starts all 28 loops with no manual `set -a; source .env`. |
| 2 | **Futures runs could never trade.** The desk emits only `buy \| sell \| hold` (both the trader prompt and `_rule_based_decision`), so a futures run's bearish `sell` with no long position skipped every cycle with `no long position to sell`. The entire short ledger, inverted SL/TP, and synthetic-liquidation machinery from Plan 10 was unreachable. | `f8e7f86` — `run_engine.run_cycle` maps, for `market_type='futures'` only: `sell` with no long → `short`; `buy` while short → `cover`. Spot is untouched. | `service/server/tests/test_run_futures_short.py` (3 tests). Full backend suite 1399 passed. |

Both fixes confirmed present **inside the running prod containers** (image contents, not tag) as of image `20260719-archdoc`.

## 2. The non-bug that looks like a bug

Most "it isn't trading" reports are the system working correctly. In order of likelihood:

1. **The run was never started.** `DRAFT` and `ARMED` runs do not cycle. Only `RUNNING` does.
2. **The AI decided HOLD.** On a rangebound symbol the desk legitimately declines. Observed on BTC for four consecutive hourly cycles with full Opus reasoning, each correctly gated as `decision is 'hold'`.
3. **A spot run in a downtrend cannot open anything.** Spot `sell` only reduces an existing long. With no position and no buy signal, nothing can ever execute. **This is the single most common cause of an apparently dead run.**
4. **Interval and confidence hide activity.** A 60-minute interval with `min_confidence 0.65`, while the desk returns 0.55–0.60, yields one gated decision per hour.

## 3. Enabling on a new account — task list

Prerequisites (already true on prod, re-verify if the environment differs):

- [ ] `AUTO_TRADING_ENABLED=true` in `~/sooppiy/.env`
- [ ] `RISK_ENGINE_ENABLED=true` (the runs engine refuses to start runs when the risk engine is off)
- [ ] `ANTHROPIC_API_KEY` set (empty key silently degrades every decision to the technical-score fallback)
- [ ] Worker container running with the runs loop: `docker logs sooppiy-worker | grep "background task: trading_runs"`

Per-account setup:

- [ ] **T1 — Pick the account.** Note its `agents.id`; every run is keyed to an agent, not a user. A user reaches their agent via `agents.user_id`.
- [ ] **T2 — Choose `market_type` deliberately.** Use **futures** in a bearish or unclear tape so a `sell` can open a short. Use **spot** only when the account already holds a position the run should manage, or in a confirmed uptrend.
- [ ] **T3 — Set a cadence you can afford.** Each cycle is ~6 LLM calls (4 analyst briefs on Sonnet, decision + verification on Opus). Three runs at 5-minute intervals is ~200 calls/hour. **Recommended steady state: 15–30 minutes.** Use 5 minutes only for short verification bursts.
- [ ] **T4 — Set `min_confidence` at or below where the desk actually lands** (observed 0.55–0.70 on crypto). 0.65 gates out most real signals; 0.30–0.50 is a working range for testing.
- [ ] **T5 — Confirm no symbol conflict.** One active run per `(agent, market, symbol)`, enforced by the `active_key` unique column. Run start is also refused if a position already exists on that tuple or an enabled auto-executing automation rule targets it.
- [ ] **T6 — Start the run and confirm dispatch:** `docker logs sooppiy-worker | grep TradingRuns` should show `due: N, dispatched: N`.
- [ ] **T7 — Verify a real trade end to end**, not just a green card: a `signals` row with `run_id` and `client_order_id`, the `positions` row stamped with `run_id`, `agents.cash` moved by exactly notional + fee, and a `trade` event in `run_events`.
- [ ] **T8 — Watch for pyramiding.** A run adds a fresh position each conviction cycle rather than holding one. The risk engine caps this at `max_symbol_exposure_usd` (default $10,000), but at 5-minute intervals that cap is reached in ~100 minutes. Size `max_bet_usd` and interval against the cap you want.
- [ ] **T9 — Decide reporting terms** (`report_frequency`, thresholds, `notify_on_trade`). SMS is tier-gated in the send path and always on, independent of `ENTITLEMENTS_ENFORCED`.

## 4. Safety properties worth knowing

- **Trading runs are simulator-only by construction.** `run_engine.py:911` pins `account_type: "simulator"` for every cycle. A run cannot reach a real broker regardless of configuration. Real-account routing exists only on automation *rules* with `account_type: live`, which additionally require a connected gateway and per-broker consent.
- **Exits bypass entry gates by design**, following the SL/TP watcher convention — a stop can never be wedged shut by a gate.
- **Entitlements are env-gated.** With `ENTITLEMENTS_ENFORCED=false` there are no per-plan run limits, so any account can create unlimited auto-executing runs. Set `PLAN_LIMITS` before opening this to real customers.

## 5. Evidence from the 2026-07-20 verification

Local (5 QA agents, both engines): 47 automated trades. Spot rules sold held longs then correctly idled at flat; futures runs opened shorts and stopped adding at exactly the $10,000 exposure cap.

Prod (`info@askkpop.com`, agent 6, simulator): 3 futures runs at 5-minute intervals and `min_confidence 0.30`, run to a complete lifecycle — entry, pyramid, exit, reconciliation.

| Cycle | Event | Detail |
| --- | --- | --- |
| 1 | SHORT | 456.37 XRP @ $1.0956 — `run:6:cyc:1` |
| 2 | SHORT | 455.91 XRP @ $1.0967 — `run:6:cyc:2` |
| 3 | SHORT | 452.78 XRP @ $1.1043 — `run:6:cyc:3` |
| stop | COVER | 1,365.06 XRP @ $1.1043, fee $1.51 — `run:6:flatten` |

Nine decision cycles, four executed trades. DOGE and AVAX held every cycle on reasoned bearish-but-no-edge analysis — correct, not failure. Price rose against the short, so the run closed at **−$10.44 realized**, and the ledger reconciles exactly: cash 100,704.35 → 100,693.91, a $10.44 delta matching `realized_pnl_usd` to the cent, with open exposure returned to $0.00.

This exercises every stage: futures `sell → short` mapping, `client_order_id` idempotency, `run_id` attribution on positions and signals, fee-inclusive P&L, and flatten-on-stop. Run 3 (BTC, Henry's own) was left untouched and is still running.

## 6. Open items

- `PLAN_LIMITS` numbers in `entitlements.py` are still placeholders; `ENTITLEMENTS_ENFORCED` stays `false` until they are set.
- Run tiles on `/runs/live` are not clickable — the Plan 10 click-through to run detail was not built.
- Pyramiding (§T8) has no per-run position cap independent of the account-wide `max_symbol_exposure_usd`. Worth considering if runs go to customers.
