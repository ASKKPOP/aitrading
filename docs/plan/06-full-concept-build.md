# Plan 06 — Full Concept Build: Math × Psychology × 3 Modes × AI-Native Signals

**Date:** 2026-07-16 · **Owner directives (Henry):**
1. 수학적 요소 — make FULL: no skipping, no mocks, no hardcoding
2. 심리학적 요소 — add 고래 추적(whale tracking); remove the preset→SL/TP propagation gap
3. Full build of ① 완전 위임(Agent Mode) ② 리스크 파라미터(middle level) ③ Personalized (지침 + schedule + configuration + monitoring + alert + SMS + EMAIL + personal functions)
4. ALL signals aggregated · calculated · **verified by AI** — no fixed programming for signal judgment (Claude API key to be provided)

This plan supersedes/absorbs Plan 05 (its four phases become Workstream D items D1–D3). Grounded in the 2026-07-16 five-agent audit; every gap referenced below was code-verified.

---

## 0. Two engineering positions (stated firmly, per house rules)

**P-1. Safety enforcement stays deterministic code. The AI decides *signals*; code enforces *limits*.**
"No fixed programming" is implemented for judgment (scoring, fusion, verdicts, verification — all AI). But circuit breakers, daily-loss caps, position caps, SL/TP execution, and the simulator-only invariant remain deterministic. An LLM must never be able to talk its way past a stop-loss. This is the industry-standard split and it is not negotiable from an engineering-integrity standpoint.

**P-2. Profitability-flip flags stay governed by the pre-registered Phase-4 rule.**
`CONFLUENCE_GATE / REGIME_FILTER(enforce) / VOL_SIZING` stay opt-in until live-forward evidence meets the pre-registered criteria (≥400 gated decisions etc.). "Make full" here means the *machinery* is complete, telemetered, and user-visible — not that unproven gates silently become defaults. Safety-class flags (risk engine, psych feed, scanner, quant, cross-market, event-guard advisory) are turned ON in production as part of this plan.

---

## Workstream A — Mathematics: complete to FULL

| # | Item | Detail | Est |
|---|---|---|---|
| A1 | **Portfolio-level capital caps** (audit gap) | `evaluate_order` gains two new limits: `max_portfolio_exposure_pct` (Σ all position notionals ≤ X% of equity, default 60%) and `max_concurrent_positions` (default 8). Per-user/agent overrides via `risk_limits`. | 0.5d |
| A2 | **Live calibration** (audit gap) | Nightly job builds confluence→hit-rate table from `automation_runs` telemetry (+backtest priors); exposed at `/api/risk/calibration`; feeds decision confidence as a prior (advisory field first, sizing input after P-2 criteria). | 1d |
| A3 | **Short-side exits (cover)** | Complete SL/TP symmetry for short positions (documented deferral in risk_engine.py:458). Paper-ledger `cover` action + watcher support. | 1d |
| A4 | **Prod flag audit → enable safety class** | Verify prod `.env`; ensure `RISK_ENGINE / PSYCH_FEED / SCANNER / QUANT_CRYPTO / CROSS_MARKET` = on, `EVENT_GUARD` = advisory. Document final state in the guide. | 0.25d |
| A5 | **Factor history persistence** | Extend factor snapshots so OI/funding/basis/L-S accumulate deep history → future backtests include them (current backtest can't; that's a data gap, not a code mock). | 0.5d |

No mocks exist in this layer today (audit-confirmed); A1–A3 are the "make full" items.

## Workstream B — Psychology: whale tracking + preset propagation

| # | Item | Detail | Est |
|---|---|---|---|
| B1 | **Whale tracking (고래 추적) — real data, free sources** | Implement `fetch_whale_signals` (currently `[]` stub): **BTC** — blockchain.info/Blockchair public large-tx polling; **ETH** — Etherscan free API, large ETH/ERC-20 transfers with public exchange-wallet tagging (inflow=sell-pressure, outflow=accumulation); threshold `WHALE_MIN_USD` default $5M. Feeds: scanner candidate reasons, psych feed (fear/anticipation), signals-board tile, AI decision snapshot. Fail-soft; `estimated:false` + `source` labels. **Needs: `ETHERSCAN_API_KEY` (free) from Henry.** SOL deferred until a free source is verified. | 2d |
| B2 | **Preset → SL/TP propagation** (audit gap) | Risk presets (안정/균형/공격) also write matching `risk_limits`: stable = SL3%/TP6%/trailing on/time-stop 5d · balanced = SL5%/TP10%/trailing on · aggressive = SL8%/TP15%. Server-side (ties into C2), shown in UI before confirm. | 0.5d |

## Workstream C — Three modes: full build

### C1 — ① Agent Mode (완전 위임) — *new*
User sets ONLY: total budget cap ($), account (simulator), and a kill switch. The AI decides everything else — symbol (scanner + LLM pick), position size (vol/Kelly within cap), cadence (event-aware scheduling), risk level, when to exit early. Implementation: new rule `mode:'agent'`; a planning LLM call (strong tier) emits the rule's current parameters each cycle within hard bounds; every AI parameter change journaled (`agent_mode_decisions`); UI: one-card setup + live "what the AI decided and why" feed. Deterministic guards (P-1) still gate every order. **Est 3d.**

### C2 — ② Risk parameters, middle level — *first-class*
`risk_level (stable|balanced|aggressive)` becomes a backend field on rules AND a per-user default; server-side preset expansion (params + risk_limits per B2); AI reads risk_level as context ("user tolerance: medium"); admin visibility. Middle(균형) = default. **Est 1d.**

### C3 — ③ Personalized Mode — *suite*
| Piece | Detail | Est |
|---|---|---|
| 지침 Guidelines | Per-user freeform guidelines (≤2,000 chars, 5-lang UI) stored and injected into every analyst/trader/verifier prompt. Guardrail: guidelines may tighten but never loosen deterministic limits. | 1d |
| Schedule | Per-rule trading windows (days-of-week + hour ranges, timezone-aware) + quiet hours; automation tick respects them; event-calendar integration. | 1d |
| Configuration | Named config profiles (params+limits+guidelines bundle), switchable; export/import JSON. | 0.5d |
| Monitoring | Personalized dashboard: my rules, runs, verdicts (incl. AI-verify results), positions, P&L, alert history. Mostly composition of existing data. | 1d |
| Alerts + EMAIL + SMS | Alert engine: triggers on fill, SL/TP hit, breaker trip, verify-rejected, whale event, custom watch conditions (price/psych thresholds). Channels: in-app (exists) → **email** (SMTP env: `SMTP_HOST/PORT/USER/PASS/FROM`) → **SMS** behind provider key (recommend **Twilio** `TWILIO_SID/TOKEN/FROM`; Korean alternative: Naver SENS — Henry picks). Per-user channel preferences + rate limiting. | 2d |
| Personal functions | Custom watch conditions builder (metric + comparator + threshold → alert or "propose trade" draft), per-user saved analyst prompts. | 1d |
| Consultation chat | Stateful `/api/analysis/chat` (per agent+symbol session, history-aware, guidelines-aware) with final "make this a rule" handoff that pre-fills an automation rule for one-click confirm. | 2.5d |

## Workstream D — AI-native signal layer (Claude API)

| # | Item | Detail | Est |
|---|---|---|---|
| D1 | **User LLM settings bridge** (P0 bug from Plan 05) | `user_api_settings` → `llm_client` per-request context (provider/model/key), fallback labeled. | 1d |
| D2 | **Model tiering + defaults** | Briefs = cheap tier (claude-haiku-4-5), decision/verify/agent-planner = strong tier (claude-sonnet-5); registry defaults refreshed; `LLM_MODEL_BRIEF/DECISION` env. | 0.5d |
| D3 | **Verification pass** | Adversarial verifier call on every automated decision (`upheld/weakened/rejected` → deterministic application; rejected→hold). Advisory-first (`VERIFY_ENABLED=advisory`), enforce after ≥200 reviewed verdicts. Optional cross-provider `VERIFY_PROVIDER`. | 1.5d |
| D4 | **AI aggregation & scoring** ("no fixed programming") | New `ai_fusion` path: Claude (structured output) receives the complete factor snapshot — quant indicators, sentiment, psych, cross-market, events, whale, ETF — and emits component scores, fused verdict, confidence, rationale. Replaces fixed 0.5/0.3/0.2 weights as the **primary** path; the deterministic fusion remains ONLY as fail-soft fallback, always labeled (`fusion_source: ai|rule-fallback`). Board/fusion APIs expose the source. Every AI fusion result telemetered for calibration (A2). | 2.5d |
| D5 | **AI data verification** | Verifier also sanity-checks inputs (staleness, cross-source contradiction, anomaly) and can mark a snapshot "suspect" → decisions during suspect windows are held. Fulfills "verified" for the data itself, not just the verdict. | 1d |

**Cost model (Claude API, to size Henry's key budget):** per automated run ≈ 4 haiku briefs + 1 sonnet decision + 1 sonnet verify (+1 sonnet fusion when D4 lands). At balanced preset (hourly) ≈ 24 runs/day/rule. Rough order: cents/day/rule on haiku+sonnet tiering. Agent Mode adds 1 sonnet planning call per cycle. Rate limits respected via existing fail-soft.

---

## Keys Henry provides (env, never in code)
`ANTHROPIC_API_KEY` (Claude — confirmed incoming) · `ETHERSCAN_API_KEY` (free, whale ETH) · `SMTP_HOST/PORT/USER/PASS/FROM` (email) · SMS provider choice + key (`TWILIO_*` or SENS) · optional: none else — BTC whale source is keyless.

## Phasing (each phase: tests + tsc + full suite + deploy + ≥2 live verification passes)

| Phase | Contents | Est |
|---|---|---|
| **I — Foundations & bug** | D1, D2, D3(advisory), A1, A4, B2, C2 | ~4d |
| **II — Real data completion** | B1 whale, A2, A3, A5 | ~4d |
| **III — Agent Mode** | C1 (uses D2/D3) | ~3d |
| **IV — Personalized suite** | C3 (guidelines→schedule→monitoring→alerts/email→SMS→personal functions→chat) | ~8d |
| **V — AI-native fusion** | D4, D5, then D3→enforce after review | ~3.5d |

> **2026-07-17 status.** Phases I–V are implemented and deployed; suite at 1039 passing. Everything above is shipped **except**: C3 *Configuration* (named profiles), and `D3 → enforce`, which is still gated on ≥200 reviewed advisory verdicts — that telemetry cannot accumulate until `AI_FUSION_ENABLED=true`, which is an open cost decision (~$34/day worst case), so the flip is *blocked, not skipped*.
>
> Two additions made during Phase V, not in the original table:
> - **D5b — per-feed age.** D5 shipped unable to verify staleness (the feeds' `as_of` stamps existed but were dropped in transit). Now measured per feed and judged against each feed's own cadence, read from the config that governs it. Verified live: an injected 3h-stale quant feed → `suspect`/high, 2/2; clean → `ok`, 2/2.
> - **P-3 — measure deterministically, judge with AI.** Code computes the facts (ages, presence, ranges); the AI judges what they mean. An LLM asked to do timestamp arithmetic returns confident guesses, and false assurance is worse than no check.
>
> **Model tiering (2026-07-17):** brief = `claude-sonnet-5`, decision = `claude-opus-4-8`. Haiku was measured returning high-severity *false* faults 4/4 on real snapshots (read MA20 against MA200 as a contradiction); Opus was clean 4/4. Briefs feed the trader, so a cheap tier that misreads inputs is not a saving.

Total ≈ 22 working days of sessions; phases ship independently and are each default-safe. Order rationale: Phase I unblocks everything AI (key bridge + tiering + verify) and closes the quick audit gaps; whale/data next so later AI layers see full inputs; Agent Mode before Personalized because C3 reuses its scheduling/alert plumbing; AI-native fusion last so its telemetry lands on a complete factor set.

*All trading remains paper/simulator. Nothing in this plan enables real-money execution.*
