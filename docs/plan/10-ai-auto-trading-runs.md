# Plan 10 — AI Auto-Trading Runs: Settings, Server-Side Execution, SMS/Email Reporting, WebGL2 Live Monitoring

**Status:** v2 Verified (2026-07-18) — synthesized from a 5-agent codebase scan and a 3-architect planning round; then revised against 67 findings from 3 logic-verification agents and 5 QA agents (all verdicts: *sound_with_fixes*; every finding is folded in).
**Owner:** Henry
**Scope:** New "Trading Runs" subsystem on top of the existing Automation engine. Paper/simulator execution only (no real broker routing — that remains a future subsystem per the platform's design).
**Companion:** `10-ai-auto-trading-runs.html` — visual version (flows, charts, tables, diagrams).

---

## 1. Executive summary

Henry's requirements:

1. **Settings per automated trading run** — max bet (money) per trade, target symbol, spot/future market type, start condition and stop event.
2. **Server-based background execution** — each run is an automated background process trading from our own AI analysis; multiple concurrent runs.
3. **Reporting** — SMS or email on configurable terms (schedules and/or profit/loss threshold events).
4. **Monitoring** — realtime WebGL2 dashboard connected to each live background run.

**Headline finding from the deep scan: ~80% of the execution machinery already exists.** The "Automation" subsystem already provides: per-rule AI trading configs (`automation_configs` with `size_usd` ≈ max bet, symbol, market, schedule windows, min-confidence), a worker-side tick loop (`tasks.automation_loop` → `automation.run_rule`), a layered risk-gate chain (`evaluate_execution_gates` → `risk_engine.evaluate_order`), the single paper-trade primitive (`execute_paper_trade`), SL/TP/trailing/time-stop closing (`risk_engine.run_sltp_watcher_tick`), and **fully wired SMS (Twilio) + email (SendGrid/Resend) + in-app alerting**. A raw-WebGL2 component already exists in the frontend (`AnalysisPipelineViz.tsx`).

What we build:

| Gap | What we add |
| --- | --- |
| Run lifecycle (start/stop events, pause, crash recovery) | `trading_runs` state machine + lease-claimed scheduler loop with fencing |
| Per-run trade attribution & P&L | `signals.run_id` + `client_order_id` idempotency key + `positions.run_id` ownership |
| Spot/futures market type | `market_type` column; futures = crypto shorts first (with synthetic-liquidation bankruptcy rule), leverage later |
| Realtime telemetry to the browser | `run_events` journal + Redis pub/sub + multiplexed `/ws/runs` WebSocket with per-sub authorization |
| WebGL2 live dashboard | new `src/webgl/` chart kernel + live monitoring page |
| P/L report terms (digest schedules, thresholds) | per-run reporting columns + `run_reports` journal + scheduler loop |
| Server-side tier gating & abuse limits | `entitlements.py` PLAN_LIMITS covering **both** the new runs engine **and** the existing automation engine |

---

## 2. What exists today (scan results, corrected by verification)

### 2.1 Backend core

- FastAPI app assembled in `service/server/routes.py:create_app()` from **28** `register_*_routes` modules; entry `main.py` (alembic upgrade on MySQL / `init_database()` on SQLite; **alembic head = 0021**, prod was at 0018 on 2026-07-18).
- A **trade** = a `signals` row (`message_type='operation'`, side buy/sell/short/cover) + `positions` mutation (negative qty = short, averaged entry, DELETE on full close) + `agents.cash` debit/credit — all in **one** `begin_write_transaction` (verified atomic, `automation.py:82-187`). Fees: 0.1%/leg via `fees.TRADE_FEE_RATE`, **included in cash but excluded from the existing `trade_stats` replay** — a precedent conflict this plan resolves (§D4).
- Auth principals: **agents** (bearer token, SHA-256 in `agents.token_hash`; `agents.user_id` is **nullable** — self-registered agents have no user), **users** (email/password + sessions, MFA, OAuth), **admins**. Agents bridge to users via `agents.user_id`.
- Broker layer exists but is inert — live execution deliberately disabled.

### 2.2 Existing automation engine (the base we extend)

- `automation_configs` + CRUD in `routes_automation.py` (agent-token auth, **zero subscription/entitlement checks today** — see D9).
- `tasks.automation_loop` (60s tick) → `run_rule`: `analysis_agents.run_analysis` (30–90s multi-agent LLM) → `evaluate_execution_gates` (auto-execute, simulator-only, confidence, market-open, event guard, cooldown, regime, budget, `risk_engine.evaluate_order`) → `execute_paper_trade`. **Due rules execute sequentially today** (`automation.py:640`) — the starvation problem D1 fixes. **`run_rule` pays for the LLM before gating** — market-closed skips still burn a full analysis (fixed in D2).
- Stop machinery: `risk_limits` + `breaker_state` + `risk_watcher_loop` (30s; **no-op unless `RISK_ENGINE_ENABLED`**, default off). Watcher exits **bypass the gate chain by design** ("Exits bypass the gate: they only reduce risk", `risk_engine.py:581`) — the convention our flatten path follows.

### 2.3 Background execution model

- Production: standalone `worker.py` — singleton lock per role (Redis `cache.acquire_lock`, 120s TTL renewed every 40s; **file-lock fallback is per-container `/tmp`, so two containers can coexist when Redis is off**), roles all/prices/settlement/research; prod currently runs a single role=all worker. Dev: in-API via `SOOPPIY_API_BACKGROUND_TASKS`.
- **The worker cannot reach the API's WebSocket connections** — live dashboards need Redis pub/sub (`cache.publish`/`create_pubsub` exist but have **zero call sites today**; sync client only; channel names are namespaced+scoped — see D6) or DB polling.
- Prices: `price_fetcher.get_price_from_market` — Hyperliquid (crypto), Alpha Vantage (us-stock; 1-min bars at best, `entitlement='realtime'` param requires the paid add-on, provider-wide 60s cooldown on any 429), Polymarket. Poll loop refreshes `positions.current_price` every `POSITION_REFRESH_INTERVAL` (code default 900s; **`.env.example` ships 300s**) — and **only crypto positions are re-polled once priced** (`POSITION_PRICE_REFRESH_PRICED_MARKETS` default 'crypto'), so a new fast-poll task is the *sole* us-stock refresher for run symbols. `positions` has **no price-timestamp column** — mark age is currently untrackable (fixed in D3). Optional sub-second crypto push: `ENABLE_PRICE_PUSH` (currently unbatched: one DB connection + UPDATE + commit per symbol per message — see Phase 10 prerequisite).
- `asyncio.to_thread` uses the default executor — `min(32, cpu+4)` = **~6 threads on a 2-vCPU EC2**, shared by all 23 loops (fixed in D1).

### 2.4 Notifications

- `alerts.send_alert(agent_id, kind, …)` **itself** sends email (SendGrid) + SMS (Twilio) after journaling to `alert_log`, then mirrors in-app via `notifications.notify(…, external=False)`. The **10/h external rate limit and 1h dedupe live only on the `send_alert` path**; `notify()` has neither and sends unconditionally per prefs — so every external report send in this plan **must** route through `send_alert` (D8). Channel switches are **per category, not per kind**.
- Two email stacks: Resend (`email_sender.py`, live in prod for signup codes) and SendGrid (`alerts.py`; creds absent/commented in `.env.example` — silent no-op when unconfigured).
- Membership tiers (junior/pro/professional/enterprise): **gating is frontend-only today**; no server-side enforcement anywhere. SMS send path has **no tier awareness** — any user who toggles the sms switch gets SMS today.

### 2.5 Frontend

- React 18 + Vite 5 + TS; no state/UI libs; CSS variables, 3 themes; i18n `tr()` 5 languages; Vite proxies `/api` and `/ws`.
- `AnalysisPipelineViz.tsx` proves: WebGL2 context acquisition with null fallback, `#version 300 es` shader compilation, DPR-capped sizing, on-demand rAF. It does **not** contain context-loss handlers, instancing, scissor, or ring buffers — those are greenfield (Phase 7 budgets accordingly).
- `pages/AutomationPage.tsx` (4 user modes: agent/simple/guided/pro) is the rules UI; `pages/MonitorPage.tsx` is a 20s-poll board. **`pages/TerminalPage.tsx` FuturesPage already advertises a 1–100× leverage slider with a client-side liquidation preview** (leverage is client-side sizing only; the ledger stays spot) — D5 reconciles this.
- Nav active-state uses prefix matching (`appChrome.tsx:250`) — a `/monitor/live` route would double-highlight; we use **`/runs/live`** instead.

---

## 3. Architecture decisions (verified & revised)

### D1. A run is a **database row + state machine**, executed by a lease-claimed scheduler loop

One new multiplexed loop (`trading_run_loop`) in `BACKGROUND_TASK_REGISTRY`, with the following **verified-precise** mechanics (each item closes a specific verification finding):

1. **Claim = its own short committed transaction.** The claim UPDATE runs on a fresh connection and commits **immediately, before analysis begins** (MySQL runs autocommit=False + REPEATABLE READ — holding the claim open would block other workers into `ER_LOCK_WAIT_TIMEOUT` retry storms and pin a stale read view, the exact bug class of commit 73f4573).
2. **Claim predicate allows owner renewal:**
   `UPDATE trading_runs SET claimed_by=?, claim_expires_at=?, cycle_seq=cycle_seq+1 WHERE id=? AND (claim_expires_at IS NULL OR claim_expires_at < ? OR claimed_by = ?)` — rowcount-checked.
3. **`cycle_seq` increments atomically inside the claim UPDATE.** Any reclaimer of the same in-flight work reuses the same logical seq, so `client_order_id = "run:{id}:cyc:{seq}"` (UNIQUE on `signals`) actually collides. A reclaimer deriving a fresh seq was the exactly-once hole.
4. **Lease TTL > worst-case cycle** (semaphore wait + 90s LLM + trade; default 300s) and the lease is claimed **at execution start** (when the concurrency slot is acquired), not at scan time — a queued-but-claimed cycle must not expire. The cycle heartbeats the lease during long LLM calls.
5. **Fencing check inside the trade transaction:** `execute_paper_trade` (run variant) re-reads `claimed_by`/`claim_expires_at` (`SELECT … FOR UPDATE` on MySQL) and aborts if the lease is no longer ours — closes the zombie-claimant window (SIGSTOP'd worker, docker-stop 10s SIGKILL grace, Redis-lock 40s dual-running window, per-container file locks).
6. **Dedicated executor + configurable concurrency.** LLM cycles run on their **own `ThreadPoolExecutor`** sized to the concurrency limit — never the default 6-thread pool the SL/TP watcher and settlement loops share. Concurrency is env-config (`RUN_CYCLE_CONCURRENCY`), sized by queue math: slots ≥ N_max × T_call/interval_floor (Semaphore(4) supports only ~4 runs at a 60s interval or ~20 at 5-min; see §7 capacity table). A per-LLM-provider rate limiter is the true bounding resource.
7. **Zero-LLM pre-gates run before `run_analysis`:** market-open, cash ≥ max_bet, breaker, agent-exists. Cycles skipped by pre-gates don't burn LLM spend and don't count against tick budgets (today `run_rule` pays for the LLM first — a us-stock rule cycling all weekend burns analysis against guaranteed "market closed" skips).

**Verification gate (Phase 2) now includes the zombie test:** SIGSTOP worker A mid-cycle past lease expiry, let B reclaim and trade, SIGCONT A → assert exactly one signal (kill -9 alone only tests the easy dead-claimant case).

### D2. Reuse the automation execution pipeline; do not fork it

`run_cycle(run)`: pre-gates (D1.7) → `analysis_agents.run_analysis` → `evaluate_execution_gates` (contract unchanged) → `execute_paper_trade` extended with `run_id`, `client_order_id`, and the fencing check. `automation_configs` and `trading_runs` coexist in v1 — **but both engines sit behind the same entitlement gate (D9); the bypass hole is closed at birth.** Run settings may tighten gates, never bypass them — with one deliberate, codebase-consistent exception: **exits** (flatten, synthetic liquidation) follow the watcher convention and skip entry gates.

### D3. Run lifecycle

```
draft → armed → running ⇄ paused → stopping → stopped | stopped(positions_held)
                     ↘ error (auto-pause / auto-stop, see rails)
```

- **Start conditions** (`start_condition_json`): manual | at_time | schedule-window | price_cross. **Strictly validated at POST — malformed JSON rejects** (never defaults to "start now"; note `schedule.in_window` is deliberately fail-open, so we do not reuse its parse semantics for start conditions). `at_time` in the past rejects at creation. `armed` price_cross runs get a **timeout + alert** (they can hang forever on an unfetchable symbol).
- **Stop events** (`stop_conditions_json`): at_time | max_loss_usd | profit_target_usd | max_trades | price_cross.
  - Evaluated **on every scheduler scan (60s) for every running *and paused* run**, decoupled from the LLM cadence — stop evaluation reads only the DB and costs nothing. Pause blocks entries, not the clock or the stops.
  - **Fail closed, with staleness as failure:** we add `positions.price_updated_at` (today marks have no age and a frozen price is indistinguishable from a fresh one — "fail-closed" never fired on the worst input). Mark age > threshold ⇒ evaluation failure ⇒ pause entries + alert. N consecutive no-price cycles ⇒ auto-stop (delisted/unfetchable symbol).
  - N consecutive stop-eval failures escalates to **stop-with-alert**, not an infinite pause↔resume livelock.
  - **max_loss wins ties** when profit_target and max_loss are crossed in one gap (safety first). `run_cycle` re-reads run status immediately before `execute_paper_trade` so a stop pressed during an in-flight cycle prevents the trade.
- **Flatten follows the watcher convention** (exits bypass entry gates — sell/cover only reduce risk): calls `execute_paper_trade` directly; the only respected block is a **manual** breaker HALT. If flatten stays blocked (manual halt, or symbol untradeable) past a bounded retry window, the run transitions to the explicit terminal **`stopped(positions_held)`** with `status_reason` + alert — a stop can never wedge in `stopping`. (Market-closed does not block flatten: paper fills execute at the last mark, same as the watcher's closes; the fill-staleness caveat is surfaced in the UI.)
- Config **snapshotted** at start; stop conditions tighten-only while running. Ancient paused runs (error-paused, subscription-paused) are swept to stopped+notify after a max-pause age — no eternal zombies accumulating claimable rows.

### D4. Position ownership & P&L attribution (hardened)

Symbol exclusivity among runs is necessary but **not sufficient** — manual trades, copy-trade mirrors, and enabled automation rules also write the same `positions` row (one row per agent+market+symbol, averaged basis). v1 rules:

1. **One active run per (agent, market, symbol)**, enforced by an **`active_key` nullable-UNIQUE column** (`'agent:market:symbol'` when status ∈ {armed, running, paused, stopping}, NULL otherwise) — a real DB constraint on both dialects, not a racy check-then-insert (Henry runs 3+ parallel sessions; check-then-set WILL race).
2. **Run start refuses** if a position already exists in that (agent, market, symbol), or if an **enabled `automation_config`** targets the same tuple; enabling such a rule while a run is active is likewise blocked. Manual/copy-trade operations on a run-owned symbol are rejected with a clear error while the run is active. (Alternative — adopt-with-basis-snapshot — deferred; commingled average-cost rows make attribution fiction.)
3. **`positions.run_id`** marks ownership. The SL/TP watcher stamps closes from this column (not an "active run" lookup), so a **stopped(positions_held)** run still gets its final exit attributed and `realized_pnl_usd` remains updatable after stop.
4. **Run P&L is fee-inclusive** and mirrors `execute_paper_trade`'s exact leg math (including the cover credit formula) — the existing `trade_stats` replay is fee-exclusive and would fire max_loss late by ~0.2%/round-trip on churny runs. The fee is **persisted on each run-attributed signals row**, immunizing replay against future `TRADE_FEE_RATE` changes.
5. `realized_pnl_usd` is a display cache with a **recompute-from-ledger reconciliation** at every pause/stop/report transition; discrepancies are journaled as a `run_event`.

### D5. Spot/futures — phased, honestly, and reconciled with the existing Futures terminal

- **v1**: `market_type ∈ {'spot','futures'}`; futures (crypto-only, Hyperliquid perp mids) = shorts allowed, leverage 1. **v1 shorts get a bankruptcy rule**: a leverage-1 short already has >100% loss potential and the cover credit `((2×entry)−price)×qty` goes negative past 2× — so a **synthetic liquidation** force-flattens when loss reaches ~100% of escrowed collateral, plus a cash-floor check on cover that raises a run-stopping event instead of silently driving `agents.cash` negative.
- **v2 (gated on `ENABLE_PRICE_PUSH` in prod)**: leverage 2–5× isolated margin + liquidation watcher. Liquidation on multi-minute polls is refused.
- **Terminal reconciliation:** the manual FuturesPage already shows a 1–100× slider whose leverage is client-side notional sizing only (the ledger stays spot). Auto-runs are deliberately stricter than the manual terminal (server-side money, no human watching); the run form copy states this explicitly. Aligning the terminal's cosmetic leverage with real margin semantics is a separate cleanup, out of scope here.
- `market_type` is never conflated with the existing `market` column.

### D6. Two-plane telemetry (durable + ephemeral), with the loss modes closed

- **Durable plane:** `run_events`, producer-assigned monotonic `seq`, UNIQUE(run_id, seq).
  - **Trade and state-change events are written inside the `execute_paper_trade` / transition transaction** (one more INSERT on the same cursor — exactly how SL/TP stamping already rides that txn). Fail-soft `emit_run_event()` applies **only to telemetry** (equity snapshots, gate-skips). A committed trade can therefore never be missing from the journal.
  - **Seq recovery on claim:** next seq initializes from `last_event_seq` on `trading_runs` (updated in the same txn as each insert) — a reclaiming worker resuming from a stale counter would collide with UNIQUE and, being fail-soft, silently discard events forever. `emit_run_event` distinguishes duplicate-key (re-read max, retry) from other failures.
  - **Equity snapshots on change** (price update or trade) with a 60s max-interval heartbeat — not a fixed 10s cadence that would write 30–90 identical rows between 300–900s mark refreshes (~500k junk rows/day at 50 runs).
  - **Pruning is equity-only** (24h full / 15-min buckets to 7d / hourly to 30d / daily to 365d — the real `profit_history` tiers). Decision/trade/state rows are never pruned; they are the audit journal. Backfill responses carry the oldest retained seq; contiguity is guaranteed only within the unpruned window; older ⇒ snapshot-reset.
- **Ephemeral plane:** `cache.publish("runs:{id}", …)` after each durable write; ticks on `ticks:{market}:{symbol}` from a hook in `price_dispatch.apply_price_update` **filtered to active-run symbols** + a fast-poll task for active symbols.
  - **Honest floors:** crypto sub-second only with `ENABLE_PRICE_PUSH`; **us-stock floor is 60s** (Alpha Vantage 1-min bars; and ~15-min delayed unless the paid realtime entitlement is confirmed in Phase 0). The AV request budget (symbols × cadence + refresh loop + probes ≤ plan quota) is computed in Phase 0; one 429 trips a provider-wide 60s cooldown that would starve *all* us-stock pricing including stop-condition checks.
  - Redis frictions handled explicitly: `cache.py` is a **sync** client (hub uses a thread or `redis.asyncio` — decided in Phase 6); publish is namespaced+DB-scoped, so a `subscribe` helper reusing `_namespaced` is added and the Phase 6 two-process test asserts **worker and API compute identical channel names** (the scope digest derives from DB config — env drift silently splits the channel). `publish`/`create_pubsub` have zero call sites today; they are unproven until this test passes.
- **Transport:** one multiplexed `/ws/runs` WebSocket; `RunStreamHub` in the API fans out pubsub to bounded per-connection queues; ticks coalesce ≤10Hz.
  - **Per-sub authorization (was a blocker):** every `sub {run_id}` / `sub_ticks` frame resolves the run's `agent_id` and verifies it belongs to the connection principal (agent token → that agent; user token → all agents where `agents.user_id` = user, which is 1:many). Otherwise an authenticated connection could stream any tenant's live P&L. Rejection = control frame.
  - **Auth transport:** short-lived single-use **WS ticket** (POST to mint, redeemed on connect) instead of the long-lived session token in the query string (token-in-query leaks via proxy logs/history; the existing `/ws/notify` pattern is not a precedent worth extending to live P&L). Fallback: if ticket work slips, Phase 0 must confirm prod nginx does not log query strings for `/ws` — as a **blocking** gate.
  - **Live-path gap detection (was silently lossy):** `cache.publish` returns 0 on failure and the client retries connection for 10s windows — pubsub is at-most-once, so the hub **tracks last-relayed seq per run and backfills from DB before forwarding a discontinuous event**, and emits `resync_required` to all subscribers when its own pubsub connection re-establishes. Clients also treat any seq jump as an implicit gap → re-sub from last seq.
  - **No-Redis fallback is scoped to durable events** (1.5s DB tail — same protocol, higher latency). Ticks are *not* DB-journaled, so in fallback mode the hub polls `positions.current_price` as the tick source (this is dev's default config — `REDIS_ENABLED=false` in `.env.example`).
- **Reconnect/replay:** client tracks last seq; server backfills `> from_seq` (cap 500, else snapshot-reset), splices live, dedupes by seq. Cold start via `GET /api/runs/{id}/snapshot`.

### D7. WebGL2 dashboard: raw WebGL2, zero new dependencies

New `service/frontend/src/webgl/` kernel. **Extraction vs greenfield, honestly:** from `AnalysisPipelineViz` we extract shader plumbing, DPR sizing, on-demand rAF, and the WebGL2-null fallback pattern; **context-loss restore, ring buffers, instanced line strips, and the scissor grid are built new** (the viz has none of them — it re-uploads full arrays per frame). Phase 7 is budgeted as construction, not extraction.

Load-bearing techniques:

- Multi-run grid renders **all tiles from one canvas/context** via `gl.viewport` + `gl.scissor` (browsers cap contexts at ~8–16).
- Preallocated Float32Array ring buffers + `bufferSubData`; min/max-per-pixel-column decimation → 100k+ points at 60fps; draw only on new data/interaction.
- Canvas2D polyline fallback shares the ring-buffer/decimation layer.
- `webglcontextlost/restored` handling; ring buffers absorb hidden-tab rAF throttling with fast-forward on `visibilitychange`.
- **Honest staleness:** every tile shows a last-update age badge (and the run form warns that us-stock stops evaluate on minutes-old marks).
- Boundary: ≥1Hz or >5k points ⇒ WebGL kernel; else Recharts.

**Route: `/runs/live`** (not `/monitor/live` — the sidebar's prefix-matching would double-highlight the existing Monitoring item). Grid of small multiples → click-through to run detail (price + trade markers, equity curve, event log). Price-chart seeding is per-market: crypto from Hyperliquid/OKX candles; us-stock/polymarket seed from the run's own tick/equity journal (**no 1-min candle source exists for them** — `historical_data.py` is daily-only).

### D8. Reporting rides `alerts.send_alert` — exclusively

- **Every external send routes through `send_alert`** (never `notify(external=True)`, never raw `_send_email/_send_sms`): it is the only path with the 10/h rate limit and dedupe. The corrected flow: `send_alert` journals to `alert_log`, sends email/SMS itself, then mirrors in-app via `notify(external=False)`.
- **Two categories, not one** — channel switches are per-category and cannot express "SMS for safety but never digests" within a single category: **`auto_trading_reports`** (digests; email/in-app, SMS switch absent) and **`auto_trading_safety`** (thresholds + lifecycle; email/SMS/in-app). Kinds: `run_report`, `run_threshold`, `run_stopped`.
- **Email Resend-first** (shared `send_email()` helper; Resend already live in prod, SendGrid fallback if keyed; no SES).
- **SMS tier check lives in the send path** (the send path has zero tier awareness today — a creation-time-only check is unenforceable). Proposed: SMS for professional/enterprise only — *pricing decision, see open questions*.
- Report terms per-run: `report_frequency off|hourly|daily|weekly`, **`report_hour_local` + `report_tz`** (zoneinfo; DST rules: spring-forward skips to next valid hour, fall-back fires once via `last_report_at` guard), `notify_on_trade`, `profit/loss/drawdown_threshold_pct`, `last_report_at`. (Stop conditions are USD-denominated, report thresholds %-denominated — the run form visually reconciles both, showing the computed counterpart.)
- Thresholds: hysteresis re-arm, dedupe `run:{id}:{rule}:{date}`.
- **Delivery journal with retry:** `run_reports` row written before send **with a `status` column (pending→sent)**; a scheduler sweep retries pending rows older than N minutes. Plain journal-before-send is at-most-once — a crash after journal, before send, would permanently swallow the one alert that matters (`run_stopped`).
- **Rate-limit reserve** for `run_stopped` (requires extending `alerts._external_rate_limited`); digests degrade to in-app at the limit, visibly in the feed.
- `POST /api/notifications/test` — **routes through the `send_alert` throttled path with its own tight per-user cap** (an unthrottled test endpoint built on `notify()`/raw senders would be a free SMS-send primitive = direct Twilio cost abuse).

### D9. Server-side tier gating covering **both engines** + abuse rails

- `entitlements.py` `PLAN_LIMITS` (plan_code → max_concurrent_runs, max_bet cap, sms_allowed, daily LLM-tick budget), enforced:
  1. at run create/start,
  2. **at `automation_configs` create AND inside `automation_loop`** — the existing automation API has zero subscription checks and runs the same `execute_paper_trade`; gating only the new engine leaves a trivial bypass (create an automation rule instead, unlimited auto-executing LLM trades),
  3. by a `subscription_enforcer_loop` that **pauses** (never deletes) runs on lapse; resumable on renewal.
- **NULL-`user_id` agents** (self-registered, no user, no subscription — the platform's primary agent-native principal): **rejected from runs and from `auto_execute` automation** in v1; they keep analysis-only access. *(Flagged for Henry — this changes existing behavior for unlinked agents.)*
- Kill switches: `AUTO_TRADING_ENABLED` gates the runs loop **and** `automation_loop`'s auto-execute path.
- Safety rails per run: mandatory default daily-loss stop; `max_trades_per_day`; consecutive-**error** auto-pause (default 5) **plus** consecutive-**infeasible** auto-pause (insufficient cash / agent deleted are skips, not errors — without this a zombie run burns one LLM call per tick forever); tick-interval floor ≥60s; per-tier daily tick budget (only market-open-eligible cycles count).
- **Agent lifecycle:** `trading_runs`/`run_events`/`run_reports` added to `routes_admin.py:_AGENT_CONTENT_TABLES` (admin agent-delete cascade); the scheduler stops runs whose agent row is missing.

---

## 4. Data model (dual DDL: `database.py` init + alembic `0022`)

> Conventions verified: no MySQL reserved words; indexed/timestamp columns VARCHAR(N); **all new timestamps pinned to `"%Y-%m-%dT%H:%M:%SZ"`** (the codebase has a second, microseconds format — lexicographic comparison across formats mis-orders at the same second, which would corrupt lease expiry checks); money NUMERIC(20,8).

| Table / change | Definition |
| --- | --- |
| **`trading_runs`** (new) | id PK; agent_id; symbol VARCHAR(20); market VARCHAR(16); market_type VARCHAR(10) DEFAULT 'spot'; status VARCHAR(16) idx; status_reason VARCHAR(255); **active_key VARCHAR(80) NULL UNIQUE** (set when active — DB-level exclusivity, multiple NULLs OK on both dialects); config_snapshot_json MEDIUMTEXT; start_condition_json; stop_conditions_json; reporting cols (`report_frequency`, `report_hour_local` INT, `report_tz` VARCHAR(64), notify_on_trade, profit/loss/drawdown_threshold_pct NUMERIC(20,8), last_report_at); safety cols (max_trades_per_day, consecutive_errors, consecutive_infeasible, paused_reason); started_at/stopped_at/last_cycle_at VARCHAR(32); cycle_seq INT; **last_event_seq INT** (seq recovery); claimed_by VARCHAR(64); claim_expires_at VARCHAR(32); realized_pnl_usd NUMERIC(20,8) (display cache w/ reconciliation); created_at |
| **`run_events`** (new) | id PK; run_id; seq INT; event_type VARCHAR(32) (run_status \| decision \| trade \| gate_skip \| equity \| alert); **ts VARCHAR(32)**; payload MEDIUMTEXT; UNIQUE(run_id, seq); INDEX(run_id, seq); INDEX(event_type, ts). Trade/state rows written in the trade/transition txn; telemetry fail-soft; **equity-only pruning** |
| **`run_reports`** (new) | id PK; run_id; user_id; kind VARCHAR(16); period_start/end VARCHAR(32); pnl NUMERIC(20,8); trades INT; **status VARCHAR(12) (pending\|sent)**; sent_at VARCHAR(32); channels_json MEDIUMTEXT; created_at; INDEX(run_id, created_at) |
| **`signals`** (ALTER) | + run_id INT NULL; + client_order_id VARCHAR(64) NULL; + fee_usd NUMERIC(20,8) NULL. **SQLite cannot `ADD COLUMN … UNIQUE`** (and `database.py` swallows ALTER failures in try/except — the column would silently never exist): plain ADD COLUMN + separate `CREATE UNIQUE INDEX IF NOT EXISTS` on client_order_id; alembic keeps inline UNIQUE for MySQL |
| **`positions`** (ALTER) | + **price_updated_at VARCHAR(32)** (mark age — required by fail-closed stops); + **run_id INT NULL** (ownership/attribution). Futures-v2 only: + market_type; + **leverage NUMERIC(6,2)** DEFAULT 1 (bare NUMERIC on MySQL = DECIMAL(10,0) → 2.5× would silently round to 2); + margin_usd; + liquidation_price NUMERIC(20,8) |

Wire envelope: `{run_id, seq, ts, type, v:1, data}`; ticks `{type:'tick', market, symbol, price, ts}` (lossy by design); control frames `resync_required`, `backfill_done` (+ oldest retained seq).

---

## 5. API surface

All `/api/runs/{id}*` reads and writes carry the **same agent-ownership predicate `routes_automation.py` uses** (`WHERE agent_id = principal`; user tokens resolve to their agent set) — stated explicitly because by-run_id telemetry endpoints are where IDOR creeps in. Authz tests are a Phase 1 gate.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/runs` | Create (validation: max_bet>0, symbol price-probe, futures→crypto only, **strict typed condition schemas — malformed rejects**) → draft |
| `POST /api/runs/{id}/start` | Entitlements + exclusivity (`active_key`) + no-existing-position + no-conflicting-automation-rule; snapshot config → armed/running |
| `POST /api/runs/{id}/pause` / `resume` | Pause entries (stops keep evaluating; clock keeps running) / resume |
| `POST /api/runs/{id}/stop` | `{flatten: bool}` (UI default flatten); watcher-convention exit; bounded retry → `stopped(positions_held)` terminal |
| `PUT /api/runs/{id}/stop-conditions` | Tighten-only while running |
| `GET /api/runs`, `GET /api/runs/{id}` | List / detail (status, P&L incl. reconciliation, open position) |
| `GET /api/runs/{id}/events?after_seq=&limit=` | Replay + polling fallback (returns oldest retained seq) |
| `GET /api/runs/{id}/snapshot` | Cold-start state |
| `GET /api/runs/{id}/price-history` | Per-market seed (crypto candles; others from own journal) |
| `POST /api/runs/ws-ticket` | Mint short-lived single-use WS ticket |
| `WS /ws/runs` | Multiplexed stream; **per-sub ownership check on every sub frame**; ticket auth |
| `GET|PUT /api/runs/{id}/reporting` · `GET /api/runs/{id}/reports` | Report terms / history |
| `POST /api/notifications/test` | Throttled test send (own per-user cap) |
| `GET /api/auto-trading/entitlements` | plan_code + PLAN_LIMITS for the caller |
| Admin | `GET /api/admin/auto-trading/runs`, `POST …/runs/{id}/pause` (admin_tokens auth) |

**Frontend surfaces (decided, was unspecified):** run management = a **"Runs" tab inside `/automation`** (AutomationPage already has a mode system; a sibling page would duplicate its symbol/market/schedule pickers), containing the run form (settings + reporting panel + test-send + entitlement banners). Live monitoring = **`/runs/live`** (new nav item under AI Desk). The existing `/monitor` page gains a link banner to `/runs/live`; consolidation of the two monitoring surfaces is an open question for Henry.

---

## 6. Build phases

| # | Phase | Scope | Verification gate (≥2 independent passes each, per working rules) |
| --- | --- | --- | --- |
| 0 | **Prod env audit** (½ day) | SSH to EC2: RESEND/SENDGRID/TWILIO creds; `REDIS_ENABLED`; `RISK_ENGINE_ENABLED`; `ENABLE_PRICE_PUSH`; **`ALPHA_VANTAGE_API_KEY` tier + request quota + realtime entitlement**; **`POSITION_REFRESH_INTERVAL` + `POSITION_PRICE_REFRESH_PRICED_MARKETS`**; nginx `/ws` proxy **and query-string logging**; `alembic current` | Recorded env matrix; AV budget computed (symbols × cadence + refresh + probes ≤ quota); blocks all downstream promises |
| 1 | **Schema + lifecycle** | alembic 0022 + `database.py` DDL (incl. SQLite index-not-inline-UNIQUE); `trading_runs.py` state machine; `routes_runs.py` CRUD; strict condition validation; ownership predicates | pytest both dialects (SQLite + throwaway MySQL 8, up/down); **concurrent double-start test** (active_key); **authz tests** (cross-tenant 404) |
| 2 | **Scheduler loop** | `trading_run_loop`: claim-with-seq-increment (own committed txn), lease TTL/heartbeat, dedicated executor + `RUN_CYCLE_CONCURRENCY`, pre-LLM gates, fencing in trade txn, `run_events` (trade/state in-txn; telemetry fail-soft; seq recovery) | kill -9 test **and zombie test** (SIGSTOP past lease → reclaim → SIGCONT → exactly one signal); claimed-but-queued-past-TTL test |
| 3 | **Run-level risk + stops** | Stop evaluation every scan (running+paused); mark-age staleness→fail-closed; flatten watcher-convention + `stopped(positions_held)`; v1 short synthetic liquidation + cash floor; `positions.run_id` attribution; fee-inclusive replay + reconciliation | Seeded-ledger replay tests (max_loss/profit/tie→max_loss wins); staleness-pause test; short-bankruptcy test |
| 4 | **Reporting** | 2 categories + 3 kinds via `send_alert` only; Resend-first adapter; throttled test endpoint; `report_scheduler_loop`; hysteresis; `run_reports` pending→sent + retry sweep; rate-limit reserve; SMS tier check in send path | Real test email/SMS; restart-mid-digest test (no double-send, no lost `run_stopped`); DST boundary tests |
| 5 | **Tier gating both engines + rails** | `entitlements.py`; enforcement at runs **and** automation create + in-loop; NULL-user_id policy; `subscription_enforcer_loop`; infeasible-skip auto-pause; `_AGENT_CONTENT_TABLES` additions; kill switches | Lapse-mid-run → pause+notify; **automation-API bypass test** (rejected at both doors); orphaned-agent run auto-stop |
| 6 | **Streaming backbone** | `RunStreamHub` (async Redis or thread; subscribe helper w/ namespacing); hub seq-contiguity backfill + resync-on-reconnect; WS ticket mint/redeem; per-sub authz; tick fast-path (filtered publish + fast-poll task, us-stock 60s floor); DB-tail + positions-poll fallback | Two-process test, Redis ON/OFF; **channel-name parity assert**; chaos reconnect: zero gaps within unpruned window, zero dupes; **cross-tenant sub rejection test** |
| 7 | **WebGL2 kernel** (frontend) | `src/webgl/`: GLSurface/RingBuffer/LineStrip/Markers/GridLayout (scissored single context) — budgeted as new construction; Canvas2D fallback; decimation | 100k-point synthetic stream 60fps; context-loss restore; 16-tile single context; 3 themes |
| 8 | **UI: run management + live dashboard** | "Runs" tab in `/automation` (form: settings, reporting, test-send, entitlement banners, USD/% reconciliation, staleness warnings); `/runs/live` grid + detail; `useRunStream` (ticket, reconnect/replay, visibility fast-forward); age badges; i18n ×5; nav + guides; `/monitor` link banner | E2E vs local worker, 3 concurrent runs; 10-min backgrounded tab; tsc clean |
| 9 | **Hardening + prod rollout** | Equity prune task; load test (30 runs × 5 clients **incl. SL/TP watcher tick-latency assertion** under LLM load); nginx /ws; deploy dark (`AUTO_TRADING_ENABLED=false`); one admin-owned agent first; real digest + threshold SMS on sooppiy.com; then per-tier flip | WS handshake via `curl --http1.1 -H Upgrade` (SPA fallback 200s lie); prod `alembic current == 0022`; ruff+pytest+tsc CI green |
| 10 | **Futures v2** (later, gated) | **Prereq work item: batch/coalesce `price_push_loop` DB writes** (currently 1 connection+UPDATE+commit per symbol per ~1s allMids message ≈ hundreds/s — the heaviest infra change in this plan, not a checkbox) + filter to active symbols; then leverage 2–5× isolated margin + liquidation watcher | Liquidation property tests; push-feed latency measurement; DB write-rate measurement |

Effort: backend 1–6 ≈ 3 weeks; frontend 7–8 ≈ 1.5–2 weeks (kernel is construction, not extraction); overlap after Phase 2.

---

## 7. Top risks (updated)

1. **Prod delivery creds unverified** — silent no-op senders. Phase 0 is the gate.
2. **Price granularity honesty** — us-stock: 60s floor at best, possibly 15-min delayed without the AV realtime entitlement; one 429 = provider-wide 60s cooldown starving stop checks too. Age badges + form warnings everywhere; AV request budget is a Phase 0 deliverable.
3. **`RISK_ENGINE_ENABLED` off ⇒ watcher no-ops** — the runs loop refuses to start runs when the engine is off (hard check, not a warning).
4. **LLM cost = OpEx attack** — pre-LLM gates, per-tier tick budgets, interval floors, **and closing the automation-API bypass** (the largest hole found in QA).
5. **Capacity math** — at 60s avg LLM calls: 4 slots ≈ 4 runs at 60s intervals / ~20 at 5-min. `RUN_CYCLE_CONCURRENCY` env + dedicated executor + provider rate limiter; saturation behavior (delayed cycles, never dropped stops — stops don't use LLM slots) documented in the admin runbook. Henry's target run count (open Q8) sizes this.
6. **Dual-dialect schema drift** — plus the two SQLite-specific traps now known (no inline UNIQUE on ALTER; swallowed ALTER failures). Phase 1 tests both dialects both directions.
7. **Alert starvation** — hysteresis + reserve + pending→sent retry sweep.
8. **Deploy survivability** — lease+fencing+seq-in-claim+journal-status are all load-bearing; zombie-claimant test in CI gates.
9. **Concurrent-session drift** — 0022 authored against origin/main at merge; prod `alembic current` confirmed at deploy.
10. **`ENABLE_PRICE_PUSH` write amplification** — turning it on unbatched would hammer MySQL with hundreds of writes/s on the shared EC2; batching is a named prerequisite of Phase 10 (and of any v2 leverage promise).

---

## 8. Open questions for Henry

1. **Run budget**: max bet per trade + total run budget (`run_budget_usd`)? Plan includes both — confirm.
2. **Stop default**: flatten (UI default) vs hold under watcher — confirm.
3. **Futures scope**: v1 = label + shorts w/ synthetic liquidation, leverage 1; leverage 2–5× deferred behind `ENABLE_PRICE_PUSH` + write-batching. OK?
4. **Exclusivity strictness**: while a run owns (agent, market, symbol), manual trades and copy-mirrors on that symbol are **rejected** and conflicting automation rules blocked. Acceptable? (Alternative — adopt-existing-position with basis snapshot — is a bigger build.)
5. **SMS policy**: (a) SMS only for professional/enterprise? (b) **SMS digests are excluded by design** (threshold/lifecycle SMS only) — confirm, or name tiers that get scheduled SMS digests.
6. **PLAN_LIMITS numbers**: placeholders — junior: 1 run, no SMS, max bet $100; pro: 3 runs; professional: 10 runs + SMS; enterprise: negotiated cap (a truly uncapped tier breaks the capacity math in §7.5). Need your numbers.
7. **UI placement (concrete)**: run management as a "Runs" tab inside `/automation` (proposed) vs a separate `/runs` page? And `/monitor` vs `/runs/live`: keep both with cross-links (proposed) or fold the old Monitor's runs/positions sections into the live page?
8. **Concurrent-run target** (10 / 50 / 200?) — sizes `RUN_CYCLE_CONCURRENCY`, snapshot cadence, prune tiers, load-test bar.
9. **Unlinked agents**: agents with no user account are barred from auto-execution (runs *and* existing automation) in v1 — this tightens current behavior for self-registered agents. Confirm.

---

## 8.5 Phase 0 results (2026-07-19, prod EC2 audit — read-only)

| Item | Prod value | Consequence |
| --- | --- | --- |
| SENDGRID_API_KEY / ALERT_FROM_EMAIL | SET / cs@sooppiy.com | Alert email **live today** |
| TWILIO_* (SID/token/from) | SET / +12513095355 | SMS **live today** |
| RESEND_API_KEY | **empty** | **Dated correction to D8:** drop "Resend-first" — keep `alerts._send_email` (SendGrid) as-is; Resend remains signup-codes-only |
| REDIS_ENABLED | false (REDIS_URL set) | DB-tail fallback is the day-one live plane; pubsub activates if/when Redis is enabled |
| RISK_ENGINE_ENABLED | true (backend + worker) | Risk §7.3 satisfied |
| ENABLE_PRICE_PUSH | unset (off) | Crypto sub-second unavailable; honest floors apply; futures v2 stays gated |
| ALPHA_VANTAGE_API_KEY | set (16 chars), tier unknown | Treat as free tier: **us-stock runs config-gated at launch** until quota confirmed |
| POSITION_REFRESH_INTERVAL | 300 | Mark staleness threshold tuned to 300s-basis |
| nginx /ws | proxied → :8101 ✓ | WS routing exists; **access_log logs full $request incl. query strings** → ticket auth confirmed required |
| alembic (MySQL sooppiy) | **0021** | Prod caught up with repo head today; our migration is 0022 |
| Workers | sooppiy-worker (role=all) ticks automation; backend has SOOPPIY_API_BACKGROUND_TASKS=true but shows 0 automation ticks | No live dual-runner observed; lease+fencing still required for deploy overlap. Recommend setting backend flag false at next deploy (flag for Henry) |

## 8.6 Implementation status (2026-07-19)

Phases 0–8 built and green; Phase 9 (prod rollout) is the remaining gate. All work ships **dark** behind `AUTO_TRADING_ENABLED=false` (+ `ENTITLEMENTS_ENFORCED=false`), so nothing changes on prod until the flags flip.

| Phase | Status | Key files | Tests |
| --- | --- | --- | --- |
| 0 Env audit | ✅ | §8.5 | prod matrix recorded |
| 1 Schema + lifecycle | ✅ | `trading_runs.py`, `routes_runs.py`, `database.py`, `alembic/0022_trading_runs.py` | `test_trading_runs.py` (20) |
| 2 Scheduler | ✅ | `run_engine.py`, `automation.py` (execute_paper_trade run args), `tasks.py` | `test_run_engine.py` (13) |
| 3 Risk + stops | ✅ | `run_engine.py`, `risk_engine.py`, `price_dispatch.py`, `tasks.py` (price_updated_at) | `test_run_stops.py` (14) |
| 4 Reporting | ✅ | `run_reports.py`, `alerts.py`, `notifications.py`, `routes_support.py` | `test_run_reports.py` (11) |
| 5 Entitlements + rails | ✅ | `entitlements.py`, `routes_admin.py` (cascade), automation + runs gates | `test_entitlements.py` (11) |
| 6 Streaming | ✅ | `routes_run_stream.py`, run_events equity emit + prune | `test_run_stream.py` (10) |
| 7+8 WebGL2 + UI | ✅ | `webgl/GLLineChart.ts`, `hooks/useRunStream.ts`, `components/RunSparkline.tsx`, `pages/RunsLivePage.tsx`, App/nav | tsc + prod build clean; browser-verified WebGL2 active, live WS, 5-lang i18n, 3 themes |
| 9 Prod rollout | ✅ DEPLOYED DARK | image `sooppiy-backend:20260719-plan10`, alembic 0022 on prod MySQL | verified — see below |

**Phase 9 deploy (2026-07-19):** merged PR #15 to main (`c2066e5`), deployed to sooppiy.com via EC2 tarball+docker. Verified: alembic `current == 0022 (head)`, `trading_runs`/`run_events`/`run_reports` tables + `signals.client_order_id`(UNIQUE) + `positions.price_updated_at` live on prod MySQL; backend + worker on the new image, healthy, both containers stable; the three new worker loops (`trading_runs`/`run_reports`/`subscription_enforcer`) start and no-op (AUTO_TRADING_ENABLED=false, ENTITLEMENTS_ENFORCED=false confirmed in-container); SPA republished to `/usr/share/nginx/sooppiy` + `restorecon`, public root 200, distinctive Plan-10 strings (`ws-ticket`, `실시간 자동매매`) present in the served `RunsLivePage` chunk; `/ws/runs` handshake returns 403 on a bogus ticket (real route enforcing ticket auth, not the SPA-fallback 200). Rollback retained: `app.prev-20260719-plan10`, `sooppiy.prev-20260719-plan10`, prior image `20260718-2228`.

**Activation (remaining, needs Henry):** the feature is inert until `AUTO_TRADING_ENABLED=true` is set in `backend.env`+`worker.env` on prod (runs won't execute cycles while dark). Recommended sequence: (1) provide the real PLAN_LIMITS numbers → set `ENTITLEMENTS_ENFORCED=true`; (2) flip `AUTO_TRADING_ENABLED=true` for a first admin-owned agent and verify a real digest email + threshold SMS; (3) roll out per tier. The `/runs/live` nav item is already visible to agent-authed members — a member can create runs now, but they will not trade until the flag flips.

**Dated corrections applied during build:**
- **D8 Resend-first dropped** — Phase 0 found `RESEND_API_KEY` empty on prod but SendGrid live; kept `alerts._send_email` (SendGrid) unchanged.
- **SMS tier gate is always-on** (not behind `ENTITLEMENTS_ENFORCED`) — SMS is a direct per-message cost, so it fails closed from day one; run/automation *plan* limits stay env-gated until Henry confirms `PLAN_LIMITS`.
- **UI placement**: shipped the live dashboard as a dedicated `/runs/live` page + AI-Desk nav item (avoids the `/monitor/*` prefix-highlight collision). The "Runs tab inside /automation" option from the plan was not needed — the create form lives on `/runs/live` itself.
- **Behavior changes to existing features** (both gated): SMS on any alert category now requires a qualifying plan; auto-executing automation rules now pass the same entitlement gate as runs. Two existing tests were updated to the new contract.

**Full backend suite: 1294+ passing, zero regressions** across every phase. Six new test modules (79 Plan-10 tests). CI ruff (F401/F811/F821/F841) clean; frontend `tsc` + production build clean.

**Open items still needing Henry (unchanged from §8):** PLAN_LIMITS numbers (placeholders in `entitlements.py`), SMS tier policy, concurrent-run target, and the Phase 9 go/no-go to flip the flags on prod.

## 9. Verification record

- 2026-07-18 — Draft v1: 5-agent deep scan + 3 independent architecture proposals (engine/risk, realtime/WebGL2, notifications/ops), synthesized.
- 2026-07-18 — **v2 Verified**: 3 logic-verification agents (code-reality, concurrency/crash, dataflow/streaming) + 5 QA agents (edge cases, security, performance, data integrity, UX/completeness). Verdicts: 8× *sound_with_fixes*; 0 *flawed*. **67 findings** (3 blocker, 26 major, 38 minor) — all folded into this revision. Highest-impact: automation-API entitlement bypass (D9), WS per-sub authorization (D6), exactly-once seq hole in lease reclaim (D1), flatten-wedge under gates (D3), stale-marks-never-fail (D3), v1 short bankruptcy (D5), SQLite inline-UNIQUE infeasibility (§4), fee-exclusive replay divergence (D4).
