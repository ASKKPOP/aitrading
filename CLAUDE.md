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

## Project: Sooppiy

An independent agent-native trading platform. Sooppiy is a standalone product.

**Repo:** `origin` → `https://github.com/ASKKPOP/aitrading.git`. Single remote.

### What this project actually is

A **signal and copy-trading platform** first. Agents register, publish signals (strategies, operations, discussions), and followers mirror trades. Positions are tracked by polling prices via `price_fetcher.py`; the internal simulated ledger is the default for everything. Since 2026-07-19 a real execution layer exists (`service/server/execution/` — see extension area 2), but it is opt-in per automation rule (`account_type: live`) and gated behind gateway credentials + consent. Feature work should still assume the simulated ledger unless it is explicitly about live routing.

### Stack

- **Backend:** FastAPI + Python 3.12 (3.12+ required — the dependency lock `service/constraints.txt` pins packages that need it, e.g. numpy 2.5.3).
- **Frontend:** React 18 + Vite 5 + TypeScript.
- **DB:** SQLite by default (`service/server/data/sooppiy.db`), **MySQL 8 in production** (set `DATABASE_URL`, e.g. `mysql+pymysql://…`). There is no Postgres driver in `requirements.txt`.
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
- Run the backend from **project root** with `--app-dir service/server`. The flat imports in `main.py` (`from cache import ...`) need `service/server` on `sys.path`, but `DB_PATH=service/server/data/sooppiy.db` in `.env` must be resolved relative to project root. Running `cd service/server && python main.py` will create a junk nested `service/server/service/server/data/` directory.
- `service/README.md` claims main.py is the whole backend. It isn't — there are 13 `routes_*.py` modules plus workers, services, schema.

### Extension areas (current direction)

1. **Custom AI agents / strategies** — `routes_agent.py`, `routes_signals.py`, `services.py`. Agents auth with `claw_` bearer tokens.
2. **Brokers / markets** — `price_fetcher.py` is the single integration point for market data. Real order-routing EXISTS: `service/server/execution/` (router + Alpaca, Binance, IBKR-CPAPI adapters, AES-GCM credential storage). Automation rules route by `account_type` (simulator | shadow | live) via `execution/gateway.py`; live requires a connected gateway + per-broker T&Cs consent and needs `EXECUTION_ENCRYPTION_KEY` set.
3. **Frontend** — most pages live in `service/frontend/src/AppPages.tsx` and `appCommunityPages.tsx`. Recharts for charts.
4. **Backtesting** — does not exist. Greenfield. Build under `service/server/backtest.py`, expose via `routes_research.py`, use `price_fetcher` for historical data.

### Research and plans

Durable strategic thinking lives under [docs/](docs/README.md) — read the index first. Three documents today:

- [docs/research/01-competitive-landscape.md](docs/research/01-competitive-landscape.md) — competitors, differentiation, accessibility wins.
- [docs/research/02-marketing-site.md](docs/research/02-marketing-site.md) — separate Astro marketing site design brief.
- [docs/plan/01-technical-roadmap.md](docs/plan/01-technical-roadmap.md) — codebase state and 4-phase technical roadmap.

When a finding turns out wrong, **edit the relevant section with a dated note** rather than starting a new document. The "Suggested first sprint" in [docs/README.md](docs/README.md) is the current execution focus.

### Automation monitoring sessions (operating model)

For recurring "monitor sooppiy.com/automation" work (owner-set, 2026-07-31):

1. **Purpose is analysis, not trading.** The session monitors the live auto-trading fleet to *improve, extend, and find solutions* for sooppiy.com — it never places trades itself (trading is always the daemon's job).
2. **Default mode is monitoring.** Observe every ~30 min via prod MySQL (`run_events` — query by the `ts` column, NOT `created_at`; there is no `created_at` and filtering on it errors silently — plus `trading_runs`, `positions`) and `sooppiy-worker` logs over SSH. Make no premature changes.
3. **Change only when monitoring proves it required** — reproduced evidence, not a single data point.
4. **When required, the fix is applied to sooppiy.com itself (prod):** code → test (fail-before/pass-after) → local ruff+pytest+tsc green → build → deploy to prod. Never a local/session-only edit that stops short of prod.
5. **Then keep monitoring** to confirm the deployed change works on prod (or roll it back).

Cycle notes live in `docs/reports/` (`*-automation-monitoring.md`, `automation-snapshot.json`, `recommendations-backlog.md`) — these are monitoring artifacts, never the deliverable. See also memory `automation-monitoring-operating-model`.

### Claude Code frameworks installed

This project uses three Claude Code frameworks. Use them in sequence (not parallel) — they cover different phases.

- **gstack** (`~/.claude/skills/gstack`) — decision-making perspectives. Use `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/plan-devex-review` *before* coding to align on what to build.
- **GSD** (`gsd` CLI, npm `gsd-pi`) — anti-drift execution. Use `/gsd:new-project` to lock specs and prevent context drift across long sessions or session handoffs.
- **Superpowers** (`/plugin install superpowers@claude-plugins-official`) — TDD-enforced implementation. Use `/brainstorm` to surface requirements, then `/execute-plan` to ship with verification.

Don't layer them simultaneously — GSD's interactive input prompts will block Superpowers' build phase if used in parallel.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore


## Basic Working Rules (Non-Negotiable — from the user)

1. **Never flatter me or simply give the answers I want to hear.**
2. **If you believe something is correct, state your position firmly, regardless of my own opinion.**
3. **Never gloss over errors or let them slide simply to save effort.**
4. **Verify everything thoroughly — run a verification loop at least ten times when needed. Even after it verifies successfully, repeat the check a MINIMUM of 2 times to make it 100% before reporting results.**

These override any tendency to agree, hedge, or cut verification short. Disagree openly with evidence; report failures plainly; do not claim something works until it is actually verified. A single passing check is never enough — re-run it (≥2×, up to 10) before you report "it works".

## Behavioral Guidelines

1. **Think before coding** — state assumptions explicitly; surface tradeoffs; ask when uncertain
2. **Simplicity first** — minimum code that solves the problem; no speculative features or abstractions
3. **Surgical changes** — touch only what the task requires; match existing style; don't refactor adjacent code
4. **Goal-driven execution** — define success criteria before implementing; verify after each step


# 1. Think Before Coding

Don't assume.  
Don't hide confusion.  
Surface tradeoffs.

Before implementing:

- State your assumptions explicitly.
- If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so.
- Push back when warranted.
- If something is unclear, stop.
- Name what's confusing then Ask.

---

# 2. Simplicity First

Minimum code that solves the problem.  
Nothing speculative.

Rules:

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.

If you write 200 lines and it could be 50, rewrite it.

Ask yourself:

> "Would a senior engineer say this is overcomplicated?"

If yes, simplify.

---

# 3. Surgical Changes

Touch only what you must.  
Clean up only your own mess.

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that **YOUR** changes made unused.
- Don't remove pre-existing dead code unless asked.

The test:

> Every changed line should trace directly to the user's request.

---

# 4. Goal-Driven Execution

Define success criteria.  
Loop until verified.

Transform tasks into verifiable goals:

- `"Add validation"`  
  → `"Write tests for invalid inputs, then make them pass"`

- `"Fix the bug"`  
  → `"Write a test that reproduces it, then make it pass"`

- `"Refactor X"`  
  → `"Ensure tests pass before and after"`

For multi-step tasks, state a brief plan:

```txt
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently.

Weak criteria like:

> "make it work"

require constant clarification.

---

# Success Indicators

These guidelines are working if you see:

- Fewer unnecessary changes in diffs
- Fewer rewrites caused by overcomplication
- Clarifying questions appearing before implementation instead of after mistakes


## Ship Process — LOCAL ONLY (OWNER, 2026-08-31 — non-negotiable)

Owner rule, verbatim: "do not use github CI, PR , all process use local
Claude CI,PR".

**No GitHub Actions CI. No GitHub PRs. The entire merge gate runs locally.**

1. Work on a feature branch as usual.
2. Run every job from `.github/workflows/*.yml` locally, exact commands and
   working directories, in a **fresh clean checkout** of the branch — a
   temporary scratch CLONE, never a git worktree (owner 2026-08-31: "do not
   use github worktree"; results and deliverables live in the main checkout):
   ruff (`--select F401,F811,F821,F841`, cwd `service`), backend pytest
   (cwd `service/server`), frontend `npm ci && npm run build`,
   `npm audit --audit-level=high --omit=dev`, gitleaks scoped to
   `origin/main..HEAD`, and pip-audit (on this machine: freeze the resolved
   env with `uv pip freeze`, then `pip-audit -r frozen.txt --no-deps
   --disable-pip` — `-r requirements.txt` cannot bootstrap here).
3. Merge locally (squash into main), putting the local-CI evidence table in
   the merge commit message, and push `origin main` directly. Do NOT
   `gh pr create` / `gh pr merge` and do not wait on GitHub checks. When no
   clean main checkout exists (the owner's checkout may sit dirty on a
   feature branch — never switch/stash it unasked), the worktree-free merge
   is a fast-forward push of the reviewed head: `git push origin <sha>:main`.
4. Deploy to prod per the deploy rule (`scripts/deploy.sh <tag>`), then
   verify on prod.

Always state what a local run does not give: a clean-room runner, the hosted
audit trail, and any check needing provider secrets.

## Monitoring Rules (OWNER, 2026-08-13 — non-negotiable)

For every sooppiy monitoring session (verbatim owner law):

> "Do not make excuses, do not delude yourself into thinking your analysis
> is always correct, and do not justify losses with flawed logic; instead,
> always analyze the reasons behind the outcome of every trade.
> The ultimate goal of all analysis is profit or loss; conduct your
> analysis with that in mind."

Binding procedure — TWO-SUBAGENT MONITORING:

1. Every monitoring cycle/sweep with tape to analyze dispatches **two
   subagents in parallel**: Agent A analyzes every **AI-authored** trade
   outcome (desk cycles, panel finals, armed exits); Agent B analyzes
   every **algorithm-authored** outcome (SL/TP watcher, trailing locks,
   max_loss, at_time, adapt-retire, flattens, sizing/selection). Each
   must state the REASON behind every trade's outcome — a description
   without a reason is not analysis; an excuse is not a reason.
2. The main session then **fully cross-checks** both reports against the
   law above: reject any finding that excuses a loss, assumes its own
   correctness, or lacks a per-trade reason. Where the two agents
   disagree, the disagreement is the finding — chase it.
3. Verdicts are stated in **profit-or-loss terms first**; process health
   second. A small favorable delta on a large loss is NOT improvement
   and must never be reported as one.

Authority chain: docs/reports/HANDOFF-n-slot-monitoring.md §7e (this rule),
§7b (the AI is the final author of every order), §7c (two-axis attribution).

## Rule of Analysis & Monitoring — EXPERIMENTAL MINDSET (OWNER, 2026-08-17 — non-negotiable)

Owner rule, verbatim:

> "all Analysis thinking about experiment ( Must be thinking Experimental
> mindset ) — also Implement by Experimental result"

**Every analysis is an experiment. Every implementation follows an
experimental result.** This binds monitoring, investigation, and shipping.

1. **State the hypothesis before the data.** Write down what you believe and
   what would falsify it. An observation with no prior hypothesis is a
   description, not an experiment.
2. **Design the measurement so it CAN refute you.** If no possible result
   would change your mind, you are not running an experiment. Prefer a
   probe, an A/B, or a replay over reasoning from the code.
3. **Run it, and report the refutations.** Hypotheses killed by measurement
   are the primary output, not an embarrassment. Record them by name so no
   future session re-runs a dead theory.
4. **Implement ONLY on an experimental result.** A fix justified by "the code
   plainly says so" or "it is obviously wrong-ordered" is a guess. If the
   change alters money paths, the experiment must include the counterfactual
   P&L at the live mark.
5. **After shipping, measure the same quantity again.** A fix that does not
   move its own metric FAILED, and must be reported as failed in the same
   terms it was justified in — no re-framing.
6. **Name the n, and never let one outlier stand as a result.** Report the
   figure with and without the largest contributor; if stripping it flips
   the sign, the experiment is inconclusive and must be stated as such.

**Worked precedent, 2026-08-17 (why this rule exists):** the no-verdict
regression produced four hypotheses — model too slow, concurrency queueing,
Plan 26 outlook schema, cap set too tight. Probes refuted all four
(4.9-7.4s idle; 4 concurrent = same wall as 1; without-outlook was SLOWER;
raising the cap moved the rate 18.5% -> 23.1%). Only `llm_usage` arithmetic
(~178 calls/h x ~100s vs 3600s available = ~5x oversubscribed) survived
measurement. A fix (#468) shipped on sound REASONING rather than an
experiment did not work.
