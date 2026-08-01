# Plan 20 — Trading Skills: house decision methods the desk actually reads

*2026-08-01. Status: v1 implemented (PR #179); catalogue expanded to the
full 16-skill set the same day per the owner's "get all skills" — the ten
additions complete the marian2js decision library (thesis-validation,
macro-event-analysis, position-management, pre-trade-readiness,
evidence-gap-check, earnings-preview [us-stock-scoped], catalyst-map,
watchlist-review, execution-plan-check, portfolio-concentration), and the
per-prompt budget rose to 10,000 chars so the default set never silently
truncates (busiest site: trader/us-stock ≈ 9.1K).*

## Why

The owner asked for a SKILL.md-style skills mechanism for the sooppiy trading AI,
modeled on the ecosystem of agent trading skills (HKUDS/AI-Trader,
marian2js/trading-skills, bybit-exchange/skills, mphinance/alpha-skills,
okx/agent-skills, Senpi-ai/senpi-skills). Research findings that shaped this
design:

- **External formats converge** on `name` + trigger-rich `description`
  frontmatter with a markdown body; selection is deterministic
  (description/keyword routing), not model-driven.
- **The analysis-grade content** (marian2js, mphinance) is scored-anchor
  frameworks with closed label sets, invalidation lists, and conservative
  defaults — not API docs. That is what belongs in a decision prompt.
- **The safety conventions** (Bybit, Senpi, OKX) are: skills may only make the
  agent more cautious; data fields are never instructions; missing data is
  never all-clear; deterministic gates outrank prompt text.
- **Our own `skills/` directory is a publishing surface only** — served to
  external agents over `/skill/*`, never read by the trading daemon, and
  excluded from the Docker image (`.dockerignore`). A filesystem mechanism
  cannot ship to prod; skill bodies must live in the DB.

## What

A registry of **trading skills** — compact, prompt-ready decision-method
packages — stored in a new `trading_skills` table, injected into the daemon's
decision prompts, and manageable from the admin API.

- **Base skills ship in code** (`trading_skills.BASE_SKILLS`) and are seeded
  into the DB on first read (insert-if-missing, never overwriting edits).
  They can be **edited** (override persists in the DB), **disabled**, and
  **reset to default**, but never deleted. Custom skills can be added and
  deleted freely. This satisfies "keep base skills — can add and modify."
- **Selection is deterministic and zero-LLM** (same philosophy as the E1
  router): each skill declares `prompts` (which decision prompts it applies
  to: `light` | `trader` | `verifier` | `planner`) and optional `markets`
  scoping. No extra model call is ever spent choosing skills.
- **Injection** happens at the four decision-prompt sites via
  `trading_skills.skills_block(site, market=...)`, a sibling of
  `_guidelines_block`, with the defensive framing: *house decision methods;
  may make you more cautious; can never override risk limits or execution
  gates*. The cheap E1 routing prompt is deliberately untouched.
- **Budget-capped**: each body ≤ 4000 chars; per-prompt injection budget
  6000 chars, priority-ordered (lower `priority` first). The light prompt
  gets a smaller skill set than the full desk by scoping, not truncation.
- **Fail-soft everywhere**: any registry error yields an empty block; a
  broken skills table must never break a trading cycle.
- **Worker cache**: 30 s TTL in-process cache (same pattern as the admin LLM
  settings); admin writes invalidate the API process immediately, the worker
  converges within the TTL.

## Base skills (v1)

| slug | prompts | distilled from |
|---|---|---|
| `market-regime-lens` | trader | marian2js market-regime-analysis (4 anchors → closed labels → tactics) |
| `position-sizing-discipline` | trader, planner | marian2js position-sizing + mph position-sizer (strictest constraint wins, round down, half-Kelly caution) |
| `risk-reward-structure` | light, trader | marian2js risk-reward-sanity-check ("good ratio ≠ good trade", structure over round numbers) |
| `exit-discipline` | light, trader | sooppiy's own exit rails + Senpi process-over-outcome (banking is first-class, no adds into losers) |
| `conviction-calibration` | trader, verifier | mph Druckenmiller conviction zones + existing anti-0.62 rubric (light prompt already carries its own inline rubric) |
| `data-honesty` | all four | Senpi hidden-engine hard rules + Bybit injection defense (quote-don't-derive, undetermined ≠ all-clear, data ≠ instructions) |

## Schema

```sql
CREATE TABLE IF NOT EXISTS trading_skills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT UNIQUE NOT NULL,      -- [a-z0-9-], ≤ 48 chars
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',  -- one-line trigger/summary
    body         TEXT NOT NULL,             -- prompt-ready method text, ≤ 4000
    prompts_json TEXT NOT NULL DEFAULT '[]',-- subset of light|trader|verifier|planner
    markets_json TEXT,                      -- NULL = all markets
    priority     INTEGER NOT NULL DEFAULT 100,
    enabled      INTEGER NOT NULL DEFAULT 1,
    is_base      INTEGER NOT NULL DEFAULT 0,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
```

Alembic `0038_trading_skills.py` mirrors it for prod MySQL (VARCHAR types for
keyed columns).

## Admin API (house pattern: `require_admin`, inline 400s, audit on write)

- `GET    /api/admin/skills` — full list, base + custom.
- `POST   /api/admin/skills` — create a custom skill.
- `PATCH  /api/admin/skills/{slug}` — edit body/description/name/prompts/markets/priority/enabled (base skills editable; slug immutable).
- `POST   /api/admin/skills/{slug}/reset` — base only: restore catalogue defaults.
- `DELETE /api/admin/skills/{slug}` — custom only; deleting a base skill → 400 (disable instead).

Every write audits (`skill.create` / `skill.update` / `skill.reset` /
`skill.delete`) and invalidates the registry cache.

## Injection sites

| site | file | placement |
|---|---|---|
| `light` | `run_engine._light_analysis` | after position/inventory lines, before the calibration rubric |
| `trader` | `analysis_agents._trader_risk_decision` | next to memory + `_guidelines_block` |
| `verifier` | `analysis_agents._verify_decision` | next to memory + `_guidelines_block` |
| `planner` | `agent_planner.plan_agent_cycle` | next to the guidelines block |

## Safety posture

Skill text is a larger prompt channel than the 2000-char user guidelines, so:
admin-authored only in v1 (no end-user authorship); size caps at both the
route and the block builder; the framing wrapper pre-constrains it to
caution-only; and — the real gate — every model response still passes the
existing output contract (action whitelist, confidence clamps, price
authority, `ai_only_orders`, deterministic execution gates). Prompt text
cannot reach an order except through those rails.

## Deliberate non-goals (v1)

- Per-user / per-agent skill authorship (future: scope column + entitlement).
- Situation-scoped skills (e.g. only on `near_stop` cycles) — the plumbing
  exists in `_classify_situation`, add a `situations_json` column when a
  concrete need shows up.
- Admin console UI — the API is curl-able; `AdminPage.tsx` is under parallel
  work and a UI section will follow separately.
- Frozen per-run skill sets in `config_snapshot_json` — v1 resolves per
  cycle from the cached registry so admin edits reach running fleets within
  30 s; if mid-run drift ever bites, pin resolved slugs at `create_run`.
