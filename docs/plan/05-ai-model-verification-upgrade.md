# Plan 05 — AI Model & Verification Upgrade

**Date:** 2026-07-16 · **Trigger:** 5-agent concept audit ("AI trading = mathematics × psychology; aggregated, calculated and *verified* by a high-intelligence AI; three delegation modes").
**Audit verdict:** the math and psychology layers are implemented (mostly flag-gated); the AI layer is the weak leg. Four confirmed defects below, ordered by severity. All claims were adversarially re-verified against code by an independent 5th agent before this plan was written.

---

## 0. Confirmed problems (all code-verified)

| # | Problem | Evidence | Severity |
|---|---|---|---|
| P0 | **Per-user LLM settings are dead UX.** Settings-page provider/model/API key are stored in `user_api_settings` and read back for display only; `llm_client.py` resolves provider/key exclusively from server env vars. A user "choosing their AI" changes nothing. | `routes_users.py:376-448` write/read; `llm_client.py:100-108, 119-150` env-only | **Bug — ship first** |
| P1 | **No AI verification step.** The "trader debate" is one synthesis LLM call; no critic, no second pass, no cross-model check, no confidence calibration beyond clamping. The concept's "verified by AI" is unmet. | `analysis_agents.py:290-322, 371` | **Concept gap** |
| P2 | **Weak / stale default models.** Auto-detect picks the first provider with a key in registry order — OpenAI first → `gpt-4o-mini`; the Anthropic default is `claude-3-5-sonnet-latest` (two generations old). Nothing enforces a "high-intelligence" model for the decision step. | `llm_client.py:67-89, 143-149` | **Quality gap** |
| P3 | **Mode 3 (Personalized/consultation) missing.** No user-guidelines storage (no schema, no API), no conversational trade loop; AnalystPage is one-shot and disconnected from order placement. Mode 1 (full delegation) is ~40% (SCANNER + auto_execute, but size/cadence/risk always user-fixed). Mode 2 exists as frontend-only presets. | `analysis_agents.py:162-168`; `AnalystPage.tsx`; modes audit | **Concept gap** |

Non-problems confirmed en route: fallback runs are honestly labeled `llm_provider: null`; the `_DEV_NEWS` seed is production-disabled and never served to users.

---

## Phase 1 — Wire user model settings into the engine (P0, bug fix)

**Goal:** the Settings page's provider/model/key actually control which model analyzes for that user's agents.

1. `llm_client.py`: extend the resolution chain to accept a per-request `LlmContext {provider, model, api_key}`; precedence = explicit context → automation-rule `provider` → `LLM_PROVIDER` env → registry auto-detect.
2. New bridge in `services.py` (or `analysis_agents.py`): `llm_context_for_agent(agent_id)` — resolve owning user → `user_api_settings['llm']` → decrypt key → context. Cache 60 s.
3. `automation.py` + `routes_analysis.py`: pass the context into `run_analysis`.
4. Key handling: keys stay server-side only, never echoed (existing masking stands); user key failures fall back to the server-env provider **with the fallback recorded in the run payload** (`llm_provider_source: user|server|fallback-rule`).
5. Tests: user-key path, bad-user-key fallback, no-settings path unchanged. UI: Settings page shows "적용됨/active" state instead of silently persisting.

**Effort:** ~1 day. No flag needed — it's a bug fix; behavior only changes for users who already entered keys expecting exactly this.

## Phase 2 — Default model upgrade + task tiering (P2)

**Goal:** "high-intelligence AI" is true by default where it matters, without 5× cost.

1. Tier the 5 calls per run: the four **analyst briefs** are summarization → cheap tier; the **trader decision** (and Phase-3 verifier) → strong tier.
2. New defaults (per provider): `anthropic: briefs=claude-haiku-4-5, decision=claude-sonnet-5` · `openai: briefs=gpt-4o-mini, decision=gpt-4o` · others keep single default. Registry defaults updated: `anthropic → claude-sonnet-5` (replaces `claude-3-5-sonnet-latest`).
3. Server env gains `LLM_MODEL_BRIEF` / `LLM_MODEL_DECISION` (both optional; `LLM_MODEL` still overrides both). Frontend `MODEL_OPTIONS` already lists current models — add the tier hint text.
4. Production `.env` (Henry action): set `LLM_PROVIDER=anthropic` + key, or leave auto-detect. Cost note: strong-tier only on decision/verify keeps per-run cost ≈ 2 strong + 4 cheap calls.

**Effort:** ~0.5 day.

## Phase 3 — Verification pass ("verified by AI" becomes true) (P1)

**Goal:** every automated decision gets an adversarial AI check before it can gate an order.

1. `_verify_decision()` in `analysis_agents.py`: one strong-tier call with the four briefs + quant snapshot + the trader's JSON; instructed to **refute** the decision (checklist: does the evidence support the action? is confidence consistent with mixed signals? any veto conditions — event window, regime, psych-only?). Returns `{verdict: upheld|weakened|rejected, adjusted_confidence, reason}`.
2. Application rule (deterministic): `rejected` → action forced to `hold`; `weakened` → confidence = min(trader, adjusted); `upheld` → unchanged. Verifier failure = fail-open (decision stands, `verify: unavailable` recorded).
3. Cross-model option: `VERIFY_PROVIDER` env can point the verifier at a *different* provider than the decision for true two-model agreement (default: same provider, strong tier).
4. Rollout per house style: **advisory-first** — `VERIFY_ENABLED=advisory` logs verdicts into `automation_runs` telemetry without changing outcomes; after ≥200 logged verdicts are reviewed, flip to `enforce`. Default `advisory` in prod immediately (cost: +1 strong call per automated run).
5. Tests: rejected→hold, weakened→min-confidence, fail-open, telemetry shape. UI: verdict chip on automation run rows + AnalystPage report.

**Effort:** ~1.5 days.

## Phase 4 — Personalized mode foundations (P3, scoped)

**Goal:** close the mode-3 gap incrementally — guidelines first, conversation second.

1. **User guidelines (small, high-value):** `user_guidelines` text (≤2,000 chars) stored per user (new column on users or settings target `'guidelines'`); injected as a system-prompt section into `_brief` and `_trader_risk_decision` ("사용자 지침 — 준수하되 리스크 게이트를 우회할 수 없음"). Guardrail: guidelines can tighten but never loosen risk limits (deterministic gates always win). Settings-page textarea, 5-language labels. ~1 day.
2. **Risk tier as a first-class backend field:** persist `risk_level (stable|balanced|aggressive)` on automation rules; presets also set matching `risk_limits` (SL/TP/trailing) so the UI tiers finally propagate (closes the audit's preset gap). ~0.5 day.
3. **Consultation loop (larger, separate approval):** stateful `/api/analysis/chat` (session per agent+symbol, N-turn), with a final "execute this as a rule" handoff that pre-fills an automation rule. Estimate ~3-4 days — **not started until Henry approves scope.**

## Sequencing & verification

Order: Phase 1 → 2 → 3 (each: tests + tsc + suite green + deploy + live verification ≥2 passes, per house rules) → Phase 4.1/4.2 → Phase 4.3 on approval.
Total estimate excluding 4.3: ~4 days of sessions. Every phase lands default-safe (bug fix / defaults / advisory flag / additive schema).

*This plan follows the audit of 2026-07-16 (5 agents: math, psychology, modes, AI-layer, adversarial verifier). All file:line citations were independently confirmed by the verifier agent.*
