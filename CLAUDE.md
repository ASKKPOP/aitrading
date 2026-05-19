# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## Project: AITRAD

A fork of [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) — an agent-native trading platform. We are extending it for our own use.

**Repo:** `origin` → `https://github.com/ASKKPOP/aitrading.git` (ours), `upstream` → `HKUDS/AI-Trader` (sync source).

### What this project actually is

A **signal and copy-trading platform**, not a broker execution engine. Agents register, publish signals (strategies, operations, discussions), and followers mirror trades. Positions are tracked by polling prices via `price_fetcher.py`, not by routing orders to real brokers. Read this twice — feature work that assumes real execution will be wrong by default.

### Stack

- **Backend:** FastAPI + Python 3.12 (3.10+ required — codebase uses `X | None` syntax).
- **Frontend:** React 18 + Vite 5 + TypeScript.
- **DB:** SQLite by default (`service/server/data/clawtrader.db`), PostgreSQL in production (set `DATABASE_URL`).
- **Cache:** Redis (optional).
- **Market data:** Alpha Vantage (stocks), Hyperliquid (crypto), Polymarket (prediction).

### Directory map

```
service/server/      # FastAPI backend (routes_*.py = 13 route modules)
service/frontend/    # React app (AppPages.tsx is the big one)
skills/              # Agent skill markdown — integration docs for external agents
research/            # Analysis scripts, notebooks, paper artifacts
docs/api/            # OpenAPI specs
```

### Local run

```bash
# One-time setup
python3.12 -m venv .venv
.venv/bin/pip install -r service/requirements.txt   # remove openrouter line first; it pins an unresolvable version
cd service/frontend && npm install && cd ../..
cp .env.example .env

# Run (from project root — important for correct DB path)
.venv/bin/python -m uvicorn --app-dir service/server main:app --host 0.0.0.0 --port 8001
cd service/frontend && npm run dev                    # frontend on :3000 (proxies /api → :8001)
```

### Known gotchas

- `requirements.txt` has `openrouter>=1.0.0` — that version doesn't exist on PyPI. It's optional (wrapped in try/except in `market_intel.py`); strip the line before installing.
- Frontend uses `API_BASE = '/api'`. Vite dev server must proxy `/api` → backend. Already configured in `vite.config.mts` (targets `:8001`).
- Backend default port in `main.py` is `8000`, but `:8000` is occupied locally by the Loom MLX server. We run on `:8001` via `uvicorn main:app --port 8001`.
- Pydantic's `EmailStr` needs `email-validator` (install with `pip install 'pydantic[email]'`).
- Run the backend from **project root** with `--app-dir service/server`. The flat imports in `main.py` (`from cache import ...`) need `service/server` on `sys.path`, but `DB_PATH=service/server/data/clawtrader.db` in `.env` must be resolved relative to project root. Running `cd service/server && python main.py` will create a junk nested `service/server/service/server/data/` directory.
- `service/README.md` claims main.py is the whole backend. It isn't — there are 13 `routes_*.py` modules plus workers, services, schema.

### Extension areas (current direction)

1. **Custom AI agents / strategies** — `routes_agent.py`, `routes_signals.py`, `services.py`. Agents auth with `claw_` bearer tokens.
2. **Brokers / markets** — `price_fetcher.py` is the single integration point for market data. Real order-routing to IBKR/Alpaca/etc. would be a new subsystem; none exists today.
3. **Frontend** — most pages live in `service/frontend/src/AppPages.tsx` and `appCommunityPages.tsx`. Recharts for charts.
4. **Backtesting** — does not exist. Greenfield. Build under `service/server/backtest.py`, expose via `routes_research.py`, use `price_fetcher` for historical data.

### Working with upstream

```bash
git fetch upstream
git merge upstream/main      # or rebase, depending on local state
```

Keep our changes additive where possible so upstream merges stay clean. When modifying existing files, prefer a clearly-scoped section over scattered edits.
