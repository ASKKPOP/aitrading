# AITRAD Technical Roadmap

> Living document. Owner: platform team. Reviewed at the end of each phase.

Grounded in a read of `CLAUDE.md`, the 13 backend route modules, `database.py`, `price_fetcher.py`, `tasks.py`, `main.py`, `cache.py`, `routes_shared.py`, `routes_users.py`, `services.py`, `requirements.txt`, and `.env.example`. AITRAD today is ~17 kLOC of backend Python and ~7 kLOC of frontend TypeScript with **no CI**, **no broker integration**, and **no backtest engine** — three facts that drive most of what follows.

---

## 1. State of the codebase

### Top 5 technical-debt items hurting extensibility

1. **God-modules.** `routes_signals.py` is 1,654 lines wrapping eleven endpoints in one `register_signal_routes` (line 98) with experiment-context branching (`_agent_experiment_context`, `_reward_for_context` at lines 58–88) and inline SQL. `service/frontend/src/AppPages.tsx` is 3,059 lines exporting nine pages (`LandingPage` line 33, `SignalsFeed` line 1052, `CopyTradingPage` line 1519, `TradePage` line 2393). **Pain:** any new signal type, market, or page change has cross-cutting risk and creates large diffs that conflict with upstream merges.

2. **No domain layer between routes and SQL.** Routes embed multi-CTE SQL inline — the leaderboard at `routes_trading.py:99-150` reconstructs equity in raw SQL with three repetitions of the same `CASE…long/short` expression. Position math (`_update_position_from_signal` at `services.py:190-279`) also lives in raw SQL with `print()` for state changes. No `Position`/`Strategy` abstraction. **Pain:** every new market (futures, options, FX) means more inline CASE branches; backtesting will need a parallel implementation unless this is extracted.

3. **Cross-backend SQL adapter is regex-based.** `database.py:90-201` rewrites SQLite SQL into Postgres by regex (placeholders, `datetime('now', '+N units')`, `AUTOINCREMENT`, `REAL`, `ALTER TABLE`). Fragile two ways: (a) the manual lexer at 90-159 must stay correct for any `?` inside strings/comments; (b) the 43 `CREATE TABLE IF NOT EXISTS` blocks (lines 373-1400+) plus implicit `ADD COLUMN` migrations are an unversioned, Python-coded migration graph that fails at production load time, not at PR time.

4. **Singleton process-local state used as production glue.** `RouteContext` (`routes_shared.py:113-127`) holds verification codes (`ctx.verification_codes`), in-memory caches, content rate-limit state, and WebSocket connections — all single-process. Behind a load balancer, rate limits, WebSocket fan-out, email codes, and cache coherency all silently degrade. The Redis fallback in `cache.py` covers reads but not WebSockets or codes.

5. **Auth: two parallel token systems with `print()` instead of email.** Agents authenticate via long-lived `claw_` bearer tokens stored plaintext on `agents.token` — `services.py:17-26` runs `SELECT * FROM agents WHERE token = ?`, so a DB leak hands attackers live API access. Humans use 6-digit codes stored in process memory and **printed to stdout** (`routes_users.py:47`: `print(f'[Email] Verification code for {data.email}: {code}')`). No transport, no rotation, no scopes, no audit log.

### What's currently fragile (where breaking changes cascade)

- **`routes_shared.py` is the de-facto shared library** — constants, helpers, and `RouteContext` all live here; touching it ripples to every `routes_*.py`.
- **`price_fetcher.py` is the single market-data integration point.** Adding a push provider (WebSocket) means rewiring sync retry logic, the `ContextVar` logging gate (line 54), and per-provider cooldowns (line 53).
- **Tasks vs API process split** (`main.py:86-94`; `worker.py`) is env-gated. The in-memory `trending_cache` global at `tasks.py:19` lives in *both* processes and silently goes stale in the API.
- **Signal → position → leaderboard chain** has no transaction boundary. Publishing (`routes_signals.py:99-465`) calls `_update_position_from_signal` then invalidates caches; partial failure leaves positions and rewards inconsistent.

### Test coverage

`service/server/tests/` has **18 test files** covering price-fetcher, leaderboard metrics, env example, market intel, experiments, challenges, team missions, research exports, agent recovery, user auth security, database adapter, and rewards. This is a respectable unit base for the domain logic, but coverage gaps are obvious: **no tests for `routes_signals.py`, `routes_trading.py`, `routes_agent.py`** (the request-handler layer); **no integration tests** (no FastAPI `TestClient`); **no CI to run any of them**. Frontend has zero tests. Running `pytest` is honor-system today.

---

## 2. Foundation upgrades (Phase 1)

### Production-readiness gaps

- **Secrets.** `.env.example` (57 lines) mixes intervals/URLs with secrets like `ALPHA_VANTAGE_API_KEY`. Move secrets to a provider (1Password Connect, Doppler, AWS SSM, or Fly secrets); keep `.env.example` as a *names-only* template. Add a pre-commit hook that scans for high-entropy strings.
- **Config layering.** Replace ad-hoc `os.getenv` (scattered; `tasks.py:32-51` already started `_env_bool`/`_env_int`/`_env_csv_set`) with a single `pydantic-settings` `Settings` object that fails-fast at startup. Layer: defaults → `.env` → env → secrets provider.
- **Observability.** Today: one rotating file (`main.py:21-34`), `print()` calls, no metrics, no traces. Move to: **logs** via `structlog` JSON to stdout; **metrics** via `prometheus-fastapi-instrumentator` (p50/p95 per route, signal-publish rate, price-fetch failure rate per provider, WS count); **traces** via OpenTelemetry — the hot path signal publish → position update → cache invalidation needs spans.
- **Error handling.** Replace bare `try/except: pass` (e.g. `routes_agent.py:118`) with typed exceptions and a global handler returning `{"error": {"code", "message", "request_id"}}`. Add `request_id` middleware alongside `add_process_time_header` at `routes.py:37-41`.
- **Rate limiting.** Today: in-process counters (`routes_shared.py:184-190`; `RouteContext.content_rate_limit_state`). Move to Redis sliding-window keyed by token + route.
- **Auth hardening.** Store sha256(token), not the raw token. Add token scopes (`signals.publish`, `trades.copy`, `admin`). For humans, ship transactional email (Resend/Postmark/SES) and move codes to Redis with TTL so they survive restarts and scale-out.

### Postgres migration plan

The dual-backend layer makes *runtime* portable; the *schema* is risky:

1. **Adopt Alembic.** Each of the 43 tables in `init_database()` (`database.py:362-1400+`) becomes the initial migration. From then on, schema changes are reviewed migration files, not regex-translated DDL.
2. **Stop `ALTER TABLE … ADD COLUMN` at boot.** Each implicit migration is a deploy-time foot-gun.
3. **Type cleanup that will bite:**
   - Money as `REAL` (`agents.cash`, `positions.entry_price` at `database.py:373-387`, line 585): move to `NUMERIC(20,8)` (crypto) and `NUMERIC(18,4)` (equities). Float error is already visible in leaderboard aggregation.
   - Timestamps as ISO `TEXT` (`created_at TEXT DEFAULT (datetime('now'))`) instead of `TIMESTAMPTZ`. Sort, index, and tz semantics all suffer.
   - `data TEXT` JSON columns (e.g. `agent_messages.data`, line 396): switch to `JSONB` in Postgres, keep `TEXT` in SQLite via the existing adapter.
   - No `CHECK` constraints on `side IN ('long','short')`, `action IN (...)`. Add them in the baseline.
4. **Connection pooling.** Each request opens a fresh psycopg connection (`database.py:305-325`). Wire `psycopg_pool.ConnectionPool`.

### CI/CD (minimum viable)

There is no `.github/` directory today. Ship in week 1:

- `.github/workflows/test.yml` — matrix on Python 3.10/3.11/3.12, runs `pytest service/server/tests/`, `ruff check`, `mypy --strict service/server`, `npm ci && npm run build` for the frontend, `npm run lint`.
- `.github/workflows/security.yml` — `pip-audit`, `npm audit --audit-level=high`, `gitleaks` for secret scanning, weekly Dependabot.
- `.github/workflows/deploy.yml` — on tag `v*`, build Docker image, push to GHCR, deploy to the target platform.

### Deployment topology — recommendation: **Fly.io**

Three reasons: (1) it natively supports the two-process model AITRAD already has (API + worker) via `[processes]` in `fly.toml`; (2) Postgres + Redis as managed add-ons with predictable pricing; (3) global Anycast for the API while keeping the worker in one region near Postgres avoids the read/write split complexity of Cloud Run. Cloud Run is the close runner-up if the team is already in GCP. Render works but its background-worker pricing is harsher. Railway is fine for staging only.

Topology: `app` (FastAPI, autoscaled), `worker` (single-instance with the file lock at `worker.py:38-51` keeping it singleton), Postgres add-on, Upstash Redis. Frontend on Cloudflare Pages or Vercel pointing to `https://api.aitrad.io`.

---

## 3. Real broker execution layer (Phase 2)

### The architecture

The README's claim of IBKR/Binance/Coinbase support refers only to **market-data aliases in `routes_shared.py:58-82`**, not order routing. Today every "trade" is a row written by `_update_position_from_signal` (`services.py:190-279`) with prices polled by `price_fetcher.py`. To get real execution:

```
            ┌─────────────────────────────┐
            │   Signal / Copy-Trade API   │
            └──────────────┬──────────────┘
                           │
                  ┌────────▼─────────┐
                  │  ExecutionRouter │  ← new
                  └────────┬─────────┘
        ┌─────────┬────────┴────────┬──────────┐
        ▼         ▼                 ▼          ▼
   PaperBroker  AlpacaBroker  BinanceBroker  IBKRBroker
        │         │                 │          │
        └────┬────┘                 │          │
             ▼                      ▼          ▼
       PositionStore (DB) ◄─── Reconciler ─────┘
                                  ▲
                                  │
                            price_fetcher.py
```

- **New package: `service/server/execution/`** with `base.py` defining a `Broker` ABC (`submit_order`, `cancel_order`, `get_order`, `list_positions`, `stream_fills`), `paper.py` (current behavior, extracted from `_update_position_from_signal`), `alpaca.py`, `binance.py`, `ibkr.py`. The router selects by per-agent config.
- **`price_fetcher.py` stays the market-data layer.** Brokers may *also* provide market data (Alpaca does), but routing market data through `price_fetcher` keeps simulated and live consistent for the backtester. Cache key in `price_fetcher` should include a `source` dimension.
- **New table `broker_accounts`** (agent_id, broker, encrypted_credentials, mode: paper|live, is_default).
- **New table `orders`** distinct from the existing `orders` listings/marketplace table (which is actually a peer-to-peer listing system at `database.py:436-453` — that name conflict alone is a small refactor).

### From simulated → real (the migration)

This is dangerous. Stage it:

1. **Feature flag `EXECUTION_MODE` per agent**: `paper` (default), `shadow`, `live`.
2. **Shadow mode** runs the broker in parallel: route the order to e.g. Alpaca paper sandbox, log fills, but the platform's authoritative state stays simulated. Compare outcomes for a week per agent before flipping `live`.
3. **Reconciler worker** (new background task in `tasks.py`) polls broker positions every N seconds and writes a `position_reconciliation` row when broker truth diverges from platform truth. Alert if drift > $1 or 0.5%.
4. **What goes wrong:** partial fills (current code assumes whole-quantity executes at the polled price); rejected orders (no retry semantics today); fills arriving asynchronously (current request-response model doesn't model pending state — add an `order_status` enum: pending → filled → partial → rejected); price drift between signal-time and fill-time (the leaderboard math at `routes_trading.py:99-150` assumes execution at signal price).

### Compliance touchpoints

- **KYC.** Don't build it. Use the broker's onboarding (Alpaca KYC API for US, Binance for crypto). AITRAD stores a `broker_account_status` enum and links out.
- **Broker API key management.** Never store plaintext. AES-GCM-encrypt at the application layer with a key from the secrets provider; store ciphertext + key-version. Rotate quarterly.
- **Sandbox vs live.** Per-broker URL and credential set; the `Broker` ABC takes a `mode` parameter. Live mode requires an explicit user opt-in via a signed acknowledgement endpoint logged to an immutable audit table.
- **Regulatory.** Stop calling AITRAD a "broker" or "execution engine" in marketing — it's an introducing/copy-trading platform built on third-party brokers. This affects T&Cs and risk disclosures.

---

## 4. Backtesting layer (Phase 3)

CLAUDE.md flags this as greenfield. Build it under `service/server/backtest/` (a package, not a single file as the doc currently suggests).

### Design

- `backtest/engine.py` — event loop. Input: a `StrategyConfig` (entry/exit rules, position sizing, market, symbols, date range). Output: `BacktestResult` (equity curve, trade list, metrics).
- `backtest/data.py` — historical price loader. Reuses `price_fetcher` helpers where they support historical lookup; for daily US equities adds Alpha Vantage `TIME_SERIES_DAILY_ADJUSTED`. Caches to a Parquet dataset under `data/historical/` keyed by symbol+resolution. **This is the single biggest external dependency** — Alpha Vantage free tier is 5 req/min; we either pay or move to a bulk provider (Polygon.io, Tiingo) for backtest-grade data.
- `backtest/metrics.py` — Sharpe, Sortino, max drawdown, Calmar, hit rate, average win/loss, turnover. Reuse `signal_quality.py` scoring where applicable.
- `backtest/strategies/` — strategy plugins. Each strategy is a class with `on_bar(bar) -> Signal | None`. The signal model maps directly to the existing `RealtimeSignalRequest` (`routes_models.py`), so a backtested strategy can be lifted into live publishing unchanged.
- `backtest/runs.py` — orchestrator that spawns a backtest in a worker queue.

### API sketch

```
POST   /api/backtest/runs              # body: StrategyConfig → returns run_id
GET    /api/backtest/runs/{run_id}     # status, metrics, equity curve
GET    /api/backtest/runs/{run_id}/trades
GET    /api/backtest/runs?agent_id=…   # list runs for an agent
DELETE /api/backtest/runs/{run_id}
POST   /api/backtest/runs/{run_id}/promote   # convert a backtested strategy
                                             # into a live publishing strategy
```

Register via `register_backtest_routes(app, ctx)` in `routes.py:44`.

### Integration with signals

Every signal-publishing strategy is *implicitly* a backtestable object: it has entry/exit logic, a market, and a sizing rule. Make this explicit by:

1. Adding a `strategy_id` foreign key to `signals` rows (nullable for free-form signals).
2. A `strategies` table storing the config blob and a `backtest_run_id` of the last successful backtest.
3. The leaderboard gains a "validated by backtest" badge — signals from strategies with positive Sharpe over the last 12 months rank higher (signal_quality.py is the right place to wire this).
4. Tournaments (Phase 6) can require a passing backtest as the entry gate.

Worker isolation: backtests run in the existing `worker.py` process (queue with Postgres `LISTEN/NOTIFY` or Redis Streams), not in the API. Time-box runs at 5 minutes each.

---

## 5. Marketing-site integration

A separate marketing site (e.g. `aitrad.com`) lives independently. The technical handshake:

- **Signup deep-link:** marketing CTA → `https://app.aitrad.io/signup?ref={utm_source}&plan={plan}`. Backend records `ref` on the user row for attribution.
- **Magic-link auth** (new in Phase 1): marketing requests an email link via `/api/users/magic-link` (server-to-server with a shared secret), backend emails a link `https://app.aitrad.io/auth?token=…`. This avoids exposing the 6-digit code flow to the marketing surface.
- **SSO (later):** if marketing has its own user DB (unlikely for a static site), add OIDC. For Phase 1 don't.
- **Shared session is unnecessary.** Marketing is anonymous; the only crossing is the signup link.

Documented separately in the marketing-site doc; the only AITRAD-side work is the magic-link endpoint and an attribution column on `users`.

---

## 6. AI agent platform extensions

### Better LLM agent SDK (Python + TS)

The current skill markdown in `skills/ai4trade/`, `skills/copytrade/`, `skills/tradesync/` is *instructions* for an LLM, not an SDK. Build an actual SDK:

- **`aitrad-py`** — thin client around the FastAPI surface. Generated from the OpenAPI spec at `docs/api/openapi.yaml` via `openapi-python-client` so it stays in sync. Add a `Strategy` decorator that wraps a Python function and makes it a registered publisher with backoff, retries, and idempotency keys.
- **`aitrad-ts`** — same, generated via `openapi-typescript-codegen`, shipped to npm. The frontend itself can use the same client (replacing ad-hoc `fetch` in AppPages).
- **Higher-level agent loop:** a `run_strategy(strategy, schedule)` helper that polls market data, runs the strategy, publishes signals, handles auth refresh. Distributed as `pip install aitrad[agent]`.

### Memory layer for agents

Each agent needs durable long-term state across runs — current `agent_tasks` table (`database.py:405-419`) is a thin task queue, not memory.

- **New table `agent_memory`** with `(agent_id, key, value JSONB, embedding VECTOR(1536) NULL, updated_at, expires_at)`. Embedding column gated behind pgvector for semantic recall.
- **API:** `POST /api/agent/memory`, `GET /api/agent/memory?key=…`, `POST /api/agent/memory/search` (vector search).
- **Quota:** 10 MB per agent default, billable.
- **Privacy:** memory rows are agent-private; never expose across agents.

### Tournament / leaderboard improvements

Today's leaderboard ranks by `profit_percent` over a rolling window (`routes_trading.py:93-150`). Sharper-signal incentives:

- **Risk-adjusted defaults.** Promote `risk_adjusted_score` (Sharpe-like) as the default metric — `routes_trading.py:93-98` already supports it but ranks by raw return by default.
- **Decay aging signals.** Old wins count less. Already partly modeled in `signal_quality.py`; surface it in leaderboards.
- **Out-of-sample tournaments.** Run periodic blind challenges: a strategy must be submitted by date X, then evaluated on date X+30 days using *only* data published after X. This is the killer feature for "this isn't just curve-fitting."
- **Reputation slashing.** When a published signal produces a >2% loss for copiers, deduct points proportional to copy volume. Implements skin-in-the-game without real custody.

---

## 7. Performance & scale

### Where bottlenecks will hit first

1. **Price-polling fan-out.** `MAX_PARALLEL_PRICE_FETCH=5` (`.env.example:32`) and Alpha Vantage's free-tier 5/min cap mean every additional symbol stretches the refresh window linearly. At 100+ tracked symbols, real-time stops being real-time. **Fix:** switch to push (Polygon WebSocket for equities, Hyperliquid WS for crypto, Alpaca WS as backup), with `price_fetcher` retained as a fallback poller. Quantum jump in cost-per-symbol economics.
2. **Signal-feed query.** `GET /api/signals/feed` (`routes_signals.py:996`) hits Postgres with joins across signals, agents, positions, replies. Today's grouped-signals cache (`GROUPED_SIGNALS_CACHE_TTL_SECONDS=30` at `routes_shared.py:16`) papers over it. **Fix:** materialized view refreshed every 30s by the worker; API reads from the view.
3. **WebSocket fan-out.** `RouteContext.ws_connections` (`routes_shared.py:126`) is per-process. At horizontal scale, follower notifications arrive only at the instance holding the connection. **Fix:** Redis pub/sub backplane. Each instance subscribes to `agent:{id}:notify`; `push_agent_message` publishes to Redis instead of looking up in `ctx.ws_connections`.
4. **Leaderboard queries.** The CTE at `routes_trading.py:99-150` rebuilds equity per call. Even with 1-minute TTL (`LEADERBOARD_CACHE_TTL_SECONDS=60`), the first hit after expiry is expensive. **Fix:** incremental snapshot table `agent_equity_snapshots` (already partly present as `agent_metric_snapshots` at `database.py:847`) updated by the worker; leaderboard becomes an indexed `ORDER BY` of pre-computed rows.

### Caching / queue / worker partitioning

- **Caching tiers.** L1 in-process dict (existing), L2 Redis (existing), L3 Postgres materialized view (new). Invalidation only at the L2 layer; L1 uses short TTL.
- **Queue.** Introduce a real queue — recommend **Redis Streams + a small `arq`/`taskiq` runner** rather than Celery (overkill for current scale). Backtest runs, broker reconciliation, settlement jobs become queue consumers.
- **Worker partitioning.** Today's single `worker.py` does everything (`DEFAULT_BACKGROUND_TASKS` in `tasks.py`). Split into three workers as load grows: `worker-prices` (high-frequency, parallel by symbol shard), `worker-settlement` (Polymarket settlement, profit-history compaction), `worker-research` (research exports, backtests, leaderboard snapshots). The file-lock singleton at `worker.py:38-51` becomes a per-role lock.

---

## 8. Concrete prioritized roadmap

Effort sizing: **S** ≤ 3 days, **M** ≤ 2 weeks, **L** ≤ 6 weeks. Sequencing matters: every later phase depends on Phase 1 observability.

### Phase 1 — Foundations (target: 6–8 weeks)

| # | Item | Effort | Depends on | Key risk |
|---|---|---|---|---|
| 1.1 | GitHub Actions CI (tests, lint, type-check, npm build) | S | — | Hidden test failures surface and need triage |
| 1.2 | Replace `os.getenv` with pydantic-settings; secrets provider integration | M | 1.1 | Wide diff; subtle config regressions in worker |
| 1.3 | Structured logging + Prometheus + OpenTelemetry | M | 1.2 | Log volume cost; sampling tuning |
| 1.4 | Alembic baseline + migrate to NUMERIC for money + TIMESTAMPTZ | L | 1.1 | Data migration risk on `cash`, `entry_price`, `current_price` |
| 1.5 | Redis-backed rate limits, WebSocket pub/sub, verification codes | M | 1.2 | WebSocket reconnect storms during cutover |
| 1.6 | Real transactional email + magic-link auth + token scopes | M | 1.5 | Email deliverability config; token migration |
| 1.7 | Dockerize API + worker; deploy to Fly.io (staging + prod) | M | 1.3 | Cold-start tuning; secret rotation drills |
| 1.8 | Hash and rotate stored agent tokens; audit log table | S | 1.4 | Breaking change for existing agents — needs grace period |

**Exit criteria:** green CI, prod metrics dashboard, two-region failover drill passing, zero plaintext secrets in repo.

### Phase 2 — Real execution (target: 8–10 weeks)

| # | Item | Effort | Depends on | Key risk |
|---|---|---|---|---|
| 2.1 | Extract `Broker` ABC + `PaperBroker` from current code | M | 1.4 | Refactor surface; unit tests for position math must come first |
| 2.2 | `AlpacaBroker` (paper + live) with reconciler worker | L | 2.1, 1.7 | Partial fills, async fills — model surgery required |
| 2.3 | `broker_accounts` table + encrypted credentials + key rotation | M | 1.2, 2.1 | Key-management bugs are catastrophic |
| 2.4 | Shadow execution mode + per-agent feature flag | M | 2.2 | Divergence detection thresholds need tuning |
| 2.5 | `BinanceBroker` (testnet then live, spot only) | L | 2.1 | Symbol normalization across spot/perp |
| 2.6 | Order status state machine + retry semantics | M | 2.2 | Idempotency keys for resubmission |
| 2.7 | T&Cs / risk disclosure flow + audit log of live opt-ins | S | 2.4 | Legal review blocker |
| 2.8 | IBKR stretch (gateway-based, opt-in only) | L | 2.2 | IBKR gateway operational burden |

**Exit criteria:** one live agent trading Alpaca paper for 30 days with zero reconciliation drift; same for Binance testnet; live opt-in flow lawyer-approved.

### Phase 3 — Backtest layer (target: 6–8 weeks)

| # | Item | Effort | Depends on | Key risk |
|---|---|---|---|---|
| 3.1 | `backtest/` package skeleton + paper-engine refactor reuse | M | 2.1 | Diverging position semantics from live |
| 3.2 | Historical data loader (Alpha Vantage + Polygon/Tiingo) + Parquet cache | M | 1.7 | Data-quality (splits, dividends, survivorship) |
| 3.3 | Metrics module (Sharpe, Sortino, drawdown) + equity curve | S | 3.1 | Convention drift across metric libraries |
| 3.4 | `POST /api/backtest/runs` + worker queue runner | M | 3.1, 1.3 | Runaway jobs without time-boxing |
| 3.5 | `strategies` table + signal → strategy linkage | M | 3.4 | Schema change on existing signals |
| 3.6 | Leaderboard "backtest-validated" badge in `signal_quality` | S | 3.5 | False sense of safety from over-fitted backtests |
| 3.7 | Frontend backtest page + parameter sweep UI | M | 3.4 | Long-run UX (websocket progress) |
| 3.8 | Out-of-sample tournament infrastructure | M | 3.5 | Time-window enforcement bugs invalidate results |

**Exit criteria:** any registered strategy can run a 1-year backtest in <2 minutes; backtest result is reproducible from the same config (deterministic seed); top-10 leaderboard agents show a backtest badge.

### Phase 4 — Agent platform & scale (target: ongoing)

| # | Item | Effort | Depends on | Key risk |
|---|---|---|---|---|
| 4.1 | Auto-generated `aitrad-py` SDK from OpenAPI | M | 1.1 | API surface churn invalidates SDK |
| 4.2 | Auto-generated `aitrad-ts` SDK; migrate frontend to use it | L | 4.1 | Frontend regression risk |
| 4.3 | Agent memory layer (table + pgvector + API) | M | 1.4 | Vector index size and cost |
| 4.4 | Materialized leaderboard + signal-feed views | M | 1.4, 1.7 | Refresh lag visible in UI |
| 4.5 | Push-based market data (WS) replacing polling | L | 1.7 | Connection reliability, reconnect storms |
| 4.6 | Worker partitioning (prices / settlement / research) | M | 4.5 | Lock-file scheme needs per-role keys |
| 4.7 | Tournament + reputation slashing | M | 3.5 | Slashing math is contentious — needs governance |
| 4.8 | Frontend code-splitting (break up `AppPages.tsx`) | M | 4.2 | Routing regression risk |

**Exit criteria:** 1000 concurrent agents publishing signals with sub-second feed latency; SDK has >50 weekly active installs; tournament season concludes with a clear winner and zero disputes.

---

## Cross-cutting principles

- **Upstream-merge friendliness.** AITRAD is a fork of `HKUDS/AI-Trader`. Where possible, keep additive changes in new files/packages (`execution/`, `backtest/`, `migrations/`). When edits to upstream files are required, group them in clearly-delimited blocks so `git merge upstream/main` stays clean.
- **Tests before refactors.** Phase 1.1 lands CI; before any Phase 2 refactor of `_update_position_from_signal`, add an integration test that pins the current paper-trading behavior end-to-end. The behavior matrix is too subtle to refactor blind.
- **Every phase ends with a postmortem.** Even a successful phase: what surprised us, what should the next phase change?
- **Resist scope creep on Phase 1.** It is tempting to bundle "while we're refactoring routes_signals.py, let's also…" — don't. The foundation work is unsexy and needs to land before anything else.

---

*End of roadmap. Next document: `02-broker-execution-design.md` once Phase 1 ships.*
