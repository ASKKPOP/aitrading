# Plan 21 — Hermes Trading Research Work Package: Analysis & Selective Integration

Date: 2026-08-03. Source repos analyzed (both MIT, © 2026 TraderMonty):

- `tradermonty/hermes-trading-research-agent-work-package` (v0.1.6) — a **Hermes Profile Distribution** (NousResearch `hermes-agent` CLI) that packages the upstream skills repo into an always-on *human-in-the-loop* research assistant.
- `tradermonty/claude-trading-skills` — the upstream canonical repo: **~75 skills** across 8 categories (market-regime, core-portfolio, swing-opportunity, trade-planning, trade-memory, strategy-research, advanced-satellite, meta), 12 workflow manifests, `skills-index.yaml`.

Visual companion: [21-hermes-research-workpackage-integration.html](21-hermes-research-workpackage-integration.html).

## 1. What the work package actually is

Four layers, none of which contain new *decision methods* — the methods all live upstream:

| Layer | Contents | Nature |
|---|---|---|
| **Orchestration** | 10 slash-command bundles (`/pre-market-routine`, `/after-close-review`, …), 4 cron presets, `SOUL.md` persona, 3 Hermes-native adapter skills (orchestrator, brief-writer, risk-gate) | Hermes-runtime specific |
| **Process contracts** | Required output sections (thesis / invalidation / risk / next-human-action / **data freshness** / **source provenance**), degraded-mode rules, session-state vs posture-basis preamble (TICKET-013), guardrails.yaml (no execution, no imperative trade language) | **Portable ideas** |
| **Trade-ticket primitive** | JSON-Schema-validated ticket, 5 states (DRAFT / REVIEW_READY / APPROVED / REJECTED / EXPIRED), approval requires the reviewer to **re-type** ticker/direction/entry/stop/risk (mismatch demotes), journal bridge to memory | **Portable idea** |
| **Upstream governance** | external-linked vs vendored modes, `x-generated` ownership markers, drift tests, `make upstream-status` pre-pull risk report | Sooppiy already has the equivalent (`catalog_hash` auto-upgrade, admin-edit wins) |

**Explicit non-execution stance:** "This is not an automated trading system… The human reviewer makes all entry and exit decisions." That is the *opposite* of Sooppiy's autonomous desk. We adopt methods and contracts, never the runtime or the philosophy.

## 2. Where Sooppiy already stands

- `service/server/trading_skills.py` (main) already carries a **6-skill port distilled from this exact upstream repo** (2026-08-02): `market-topping-evidence`, `news-reaction-evidence`, `drawdown-circuit-breaker`, `exposure-discipline`, `contrarian-crowding-gate`, `scenario-precommit`. The registry holds 23 skills total, zero-LLM selection, per-prompt budget `MAX_BLOCK_LEN = 20000` (busiest site: trader/us-stock ≈ 17,859 chars at defaults → ~2.1k headroom).
- Existing analogs for whole upstream categories: `regime.py`/`psych_feed.py` (data-engine daemons), `run_feedback.py` (trade-memory-loop), `backtest_gate.py` (backtest-expert), `hot_issue_daemon.py` (event-driven triage), `run_reports.py` + localized alert emails (briefs), Plan 17 order intents + Plan 19 gateway consent (execution boundary).

**Conclusion: do not install the package. Port the remaining value in phases.**

## 3. Skill triage (75 upstream skills → 4 buckets)

| Bucket | Examples | Destination |
|---|---|---|
| Judgment methods, unported, high value | `crypto-regime-analyzer` (6-component crypto posture), `ftd-detector` (bottom confirmation / re-entry — offensive complement to our topping skill) | → `BASE_SKILLS` rows (Phase 1) |
| Judgment methods, already covered | exposure-coach, market-top-detector, scenario-analyzer, drawdown-circuit-breaker, pre-trade-discipline-gate, position-sizer/futures-position-sizer (deterministic sizing is code, not prompt) | none |
| Data engines (need FMP/FINVIZ keys, emit report files) | vcp/canslim/pead screeners, ibd-distribution-day-monitor, earnings-calendar, institutional-flow-tracker, sector/theme analysts, stockbee suite | → backend daemons only if wanted (Phase 3 crypto-regime composite now; FMP-backed us-stock enrichment deferred, Phase 6) |
| Process / memory / meta | trader-memory-core, signal-postmortem, dual-axis-skill-reviewer, edge-* pipeline, skill-designer | run_feedback / backtest gate already own this; monthly process-review report is the one gap (Phase 4) |

## 4. Phases

**P1 — Two new base skills (+ budget bump).** My authority under the owner's skill exception; ship without asking.
- `crypto-regime-lens` — distilled from `crypto-regime-analyzer`: judge crypto posture on six anchors (BTC trend structure, alt participation breadth, dominance rotation *jointly with* BTC trend, perp funding crowding as a contrarian tell at extremes, drawdown/vol cycle position, short-horizon thrust); conflicting anchors → lower exposure. `markets: ["crypto"]`, `prompts: ["trader"]`.
- `bottom-confirmation` — distilled from `ftd-detector` (O'Neil): after a correction, a rally attempt only counts from day 4–7 when a major index gains ~1.5%+ on rising volume; before confirmation, re-entry is scouting size at most; a failed FTD (undercut of rally low) resets the count. Offensive complement to `market-topping-evidence`. `markets: ["us-stock"]`, `prompts: ["trader"]`.
- Bump `MAX_BLOCK_LEN` 20000 → 24000 and update `test_defaults_never_hit_the_budget` (the additions fit under 20k, but would shrink custom-skill headroom below the point of the invariant).
- Verify: catalog-sync inserts on prod read; per-site block totals recomputed in tests; mutation check (break a body, watch the test fail).

**P2 — Brief integrity contract in `symbol_research.py`.** Adopt the package's data-freshness + provenance + carry-forward discipline at the *source* (the level-integrity incident class :496026-:496035 was exactly a stale-brief failure): every thesis carries `as_of` price/timestamp, source labels, and a staleness flag the desk prompt renders; a brief older than its market's session bridge is labeled carried-forward, not fresh.

**P3 — Crypto regime composite daemon.** Upgrade `regime.py` toward the 6-component 0–100 composite (keyless: CoinGecko + Binance funding; we already hold Hyperliquid + F&G feeds). Feeds the decision prompts and an admin console card. This is the "data engines become daemons, not registry rows" path the registry docstring already prescribes.

**P4 — Desk briefs + monthly process review.** Pre-market (us-stock) / daily (crypto) desk brief and a monthly process-review report assembled from existing feeds (regime, psych, hot issues, fleet P&L, run_feedback deltas), localized ×6, delivered through the existing notifications/email stack. The monthly review's output format ends with "candidate skill drafts" — closing the owner's decisions-become-skills loop.

**P5 — Live escalation ticket (owner-gated, optional).** Port the ticket primitive's *approval shape* (schema-validated object; APPROVED requires re-typed symbol/direction/caps; mismatch demotes) as the shadow→live promotion step in the admin console, layered on the existing consent + `LIVE_BROKER_ALLOWLIST` + $1k cap design. Decision-making stays the daemon's; the ticket gates *enablement*, not trades.

**P6 — US-stock data enrichment via FMP (deferred).** The screeners/earnings engines would address the known us-stock data starvation, but need a paid FMP key and a cost decision. Revisit after P1–P4.

## 5. Risks

- Prompt-budget growth → skills skipped silently (mitigated by the bump + invariant test).
- Adding skills ≠ adding compliance — every prior skill landed with monitoring evidence; the two P1 skills are method-ports, so watch 1–2 weeks of run_events for uptake before tuning.
- P4 briefs add LLM cost per day per language — reuse the market_i18n cache-only + background-warm pattern.
- P5 touches the live boundary — owner decision, grep-verified simulator/shadow/live split per the standing rule.

## 6. Attribution

Both source repos are MIT (© 2026 TraderMonty). Keep the in-code attribution comments in `BASE_SKILLS` (the 2026-08-02 port already models this).
