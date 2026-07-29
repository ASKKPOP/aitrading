# Sooppiy — Research & Plans

This folder is the durable thinking for Sooppiy: where we are, who we're competing with, what to build, and the order to build it in. Three documents below — read them in this order.

## What's here

| # | Document | What it answers | Words |
|---|---|---|---|
| 1 | [research/01-competitive-landscape.md](research/01-competitive-landscape.md) | Who exists in the agent-trading / copy-trading space, what's unique about Sooppiy, how new users get stuck, and 12 ranked accessibility wins. | ~3,300 |
| 2 | [research/02-marketing-site.md](research/02-marketing-site.md) | A standalone marketing site design brief — references, audience segments, IA, page-by-page, tech stack, SEO, rollout. | ~2,400 |
| 3 | [research/03-signal-expansion-gap-analysis.md](research/03-signal-expansion-gap-analysis.md) | Signal cards 07–16 vs the platform: what existed, what was built (macro calendar, OI/long-short, kimchi premium/DXY), what needs paid keys, and the priority queue. | ~1,200 |
| 3 | [plan/01-technical-roadmap.md](plan/01-technical-roadmap.md) | The codebase as it actually is, what hurts to extend, and a 4-phase roadmap (foundations → broker execution → backtesting → scale). | ~3,800 |
| 4 | [plan/02-deployment-readiness.md](plan/02-deployment-readiness.md) | What stands between local Docker dev and a real deploy. | ~700 |
| 5 | **[plan/09-session-handoff-2026-07-17.md](plan/09-session-handoff-2026-07-17.md)** | **START HERE if resuming/continuing (newest).** Current state, deploy runbook, prod flags/models/keys, what this session did, next work (actionable vs blocked-on-Henry), and the P-1 safety invariants. Supersedes plan/03. | ~2,000 |
| 5b | [plan/03-session-handoff.md](plan/03-session-handoff.md) | Earlier (2026-07-16) handoff — dual-auth architecture, test accounts, deploy runbook. Superseded by plan/09 but still useful background. | ~2,000 |
| 5c | [plan/07-overnight-audit-2026-07-17.md](plan/07-overnight-audit-2026-07-17.md) · [plan/08-api-keys-reference.md](plan/08-api-keys-reference.md) | The 5-agent audit record, and the API-keys reference (status + how to get each). | — |
| 6 | [plan/04-ai-model-parameter-upgrade.md](plan/04-ai-model-parameter-upgrade.md) | Deep analysis of `research/parameters/*` vs the decision engine, and the 5-phase modification plan (confluence engine, regime filter, vol sizing, validated flip). v2 — adversarially verified by a 6-agent panel (2026-07-16). | ~3,500 |
| 7 | [plan/10-ai-auto-trading-runs.md](plan/10-ai-auto-trading-runs.md) | **AI Auto-Trading Runs** — per-run settings (max bet, symbol, spot/futures, start/stop events), server-side background execution, SMS/email P&L reporting, WebGL2 live monitoring. v2, verified by a 16-agent pipeline (5 scan / 3 plan / 3 verify / 5 QA, 67 findings folded in, 2026-07-18). Visual companion: [plan/10-ai-auto-trading-runs.html](plan/10-ai-auto-trading-runs.html). | ~4,500 |
| 8 | [plan/15-run-ai-reading-algorithm-fix.html](plan/15-run-ai-reading-algorithm-fix.html) | **RUN AI Reading Algorithm Fix** — 5 targets (confidence-signal redesign, us-stock data feed, fleet thesis/gate coherence, inventory awareness, adapt-loop rescale) in a 4-phase flagged rollout, each file-anchored with exit criteria. Derived from the 2026-07-22 monitoring window; evidence: [reports/2026-07-22-automation-run-monitoring.html](reports/2026-07-22-automation-run-monitoring.html). | HTML |

| 9 | [i18n-review-status.md](i18n-review-status.md) | The six-language localization ledger: what is machine-authored and pending native review, the enforced trading-term glossary, deliberate bilingual conventions, and how to re-run the translation pipeline. | ~600 |

### Design documents (HTML)

All HTML documents live under [design/](design/) — this is the standing convention; new documents always go somewhere under `docs/`.

| Document | What it is |
|---|---|
| [12-system-architecture-report.html](12-system-architecture-report.html) | **System Architecture & Technical Flow** — the full-stack technical reference: process topology (API vs worker), 292-endpoint API surface, the 3-principal auth model, all 28 background daemons with intervals, the AI auto-trading gate chain, order-execution routing, the 87-table data layer, both frontends, deployment topology, and 12 ranked findings. 8 hand-authored SVG diagrams. Written for service managers and engineers. Generated 2026-07-19 from a full source scan. |
| [design/ai-trading-guide.html](design/ai-trading-guide.html) | **Full AI-trading pipeline guide** — 10 steps, 5 SVG diagrams, trader/CEO/QA views. Live at sooppiy.com/guide.html. |
| [design/implementation-plan.html](design/implementation-plan.html) | Signal-collection implementation plan (5 phases, verified sources, per-phase acceptance). Live at sooppiy.com/plan.html. |
| [design/signal-framework.html](design/signal-framework.html) | The AI trading-signal collection framework the plan implements. Live at sooppiy.com/framework.html. |
| [design/theme-preview.html](design/theme-preview.html) | Signal design-system reference (tokens, type scale, components). |
| [design/parameter-upgrade-result.html](design/parameter-upgrade-result.html) | **Parameter-upgrade implementation result** — full visual report: session pipeline, 4-layer architecture diagram, automation-tick flow, verification-panel charts, Phase-4 backtest evidence (PF per fold, capital preservation, exit mix, agreement heatmap), deployed-state table. |
| [design/api-keys-reference-en.html](design/api-keys-reference-en.html) | **API Keys Reference (owner-only)** — source for the `api-keys-en` guide doc (served only to `DOCS_OWNER_EMAILS`). Companion to [plan/08-api-keys-reference.md](plan/08-api-keys-reference.md). Rebuild with `service/server/build_guide_content.py` after editing. |

## The five decisions to anchor on

These cut across all three documents. If any of these is wrong, half the work below changes.

1. **The wedge is the publish-side API, not the UI.** Every closed competitor (eToro, Bitget, Hyperliquid copy) requires a human-in-the-loop to publish a signal. The `claw_` token + curl-based agent registration is structurally unmatchable — that's where we double down. (Competitive §2.)
2. **Defer auth until value is shown.** 70% of fintech onboarding drop happens above 3 minutes; the leaderboard should be the landing page, with anonymous paper-follow before any login. (Competitive §3 and §6.)
3. **Polymarket is the lowest-friction first-value lane.** CFTC-cleared for US since Sept 2025, no broker linking, no KYC for the prediction-market path. Use it as the on-ramp before equities/crypto. (Competitive §6.)
4. **Marketing site is its own thing.** Astro static, deployed to Cloudflare Pages, on `sooppiy.com`. The trading app lives at `app.sooppiy.com`. Docs at `docs.sooppiy.com`. SEO + LLM-citation is the growth lever — Astro and a separate site protect both. (Marketing §3, §5.)
5. **The codebase is a signal/copy-trading platform, not an execution engine.** Today's "broker compatibility" is aspirational. Real order routing (Alpaca first) is Phase 2, behind production foundations. (Roadmap §1, §3.)

## Suggested first sprint (1-2 weeks)

> **2026-07-16 note:** two Foundations rows below have since landed in code (GitHub Actions CI; pydantic-settings config). Token hashing has NOT landed. The four Product/accessibility rows and the Marketing row remain open. See the roadmap's dated corrections for details.

A single coherent slice that touches all three docs. Each item maps to a research finding or roadmap line item — chosen because they're independent enough to parallelize.

| Workstream | Item | Source |
|---|---|---|
| **Product / accessibility** | Public leaderboard landing page (no login to view top agents) | Competitive §6 — item 1 |
| **Product / accessibility** | One-click anonymous *paper* follow with ephemeral session token | Competitive §6 — item 2 |
| **Product / accessibility** | Curl-based agent registration page with copy-paste example + sample signal | Competitive §6 — item 5 |
| **Product / accessibility** | Risk-normalized leaderboard scoring (Sharpe + drawdown + sample size by default) | Competitive §6 — item 8 |
| **Marketing** | Stand up `marketing/` Astro project with English landing page only — hero + dual on-ramp + leaderboard embed + footer | Marketing §7 — Phase A |
| **Foundations** | GitHub Actions CI (tests + lint + type-check + npm build) — unblocks everything else | Roadmap §2 — item 1.1 |
| **Foundations** | Pydantic-settings + secret extraction from `os.getenv` | Roadmap §2 — item 1.2 |
| **Foundations** | Hash stored agent tokens; add audit log | Roadmap §2 — item 1.8 |

This sprint deliberately avoids the L-effort items (Alembic + NUMERIC migration, broker abstraction, backtest engine). Those wait until CI and observability are landed so we can catch regressions when they happen.

## What's not in scope yet

- Real broker execution (Alpaca/Binance/IBKR) — Phase 2, after foundations.
- Backtesting engine — Phase 3, depends on broker abstraction shape.
- Localized landing pages for ja / th / vi — Phase B of marketing, after English MVP validates layout.
- Multi-agent tournaments and slashing — Phase 4 of the technical roadmap.
- Mobile-native app — not on the roadmap; trading audiences are mobile-web-first in 2026 (Competitive §3).

## How the documents were produced

All three were generated by parallel Opus 4.7 sub-agents using web search, structured to be opinionated rather than survey-style. Each agent grounded its claims in cited sources (or, for the technical roadmap, in actual file:line references inside the codebase). The synthesis above (decisions, sprint) was assembled after all three returned.

The intent is for these documents to be **revised, not rewritten** as the project moves. If a research finding turns out wrong in practice, edit the relevant section with a dated note rather than starting fresh.

## Frameworks used (Claude Code skills)

- **Superpowers** — `/brainstorm`, `/execute-plan` (TDD + verification).
- **GSD** — anti-drift state/spec anchoring across sessions.
- **gstack** — `/office-hours`, `/plan-ceo-review`, `/plan-eng-review` for decision-making perspectives.

See the root `CLAUDE.md` for install / workflow notes once the frameworks are wired into the project loop.
