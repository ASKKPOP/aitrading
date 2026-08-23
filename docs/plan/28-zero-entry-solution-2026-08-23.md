# Plan 28 — Zero-Entry Solution (2026-08-23)

Status: proposed. Authority for ordering: the three judge reports of 2026-08-23 (critical paths agree on items 0→2; this document follows them). Evidence base: `docs/reports/2026-08-23-deep-analysis-24h.md`, `docs/research/05-full-logic-audit-2026-08-22.md`, `docs/research/06-redesign-experiments-2026-08-22.md`, ten lens analyses and three judgments (2026-08-23).

## 1. The problem, in profit-or-loss terms

Realized P&L over the last 24h is $0 because the platform has made 0 fills since 2026-08-20T07:10Z. Over the last four daily windows the desk proposed 11, 16, 82 and 68 buys (n=177) and the order-discussion panel kept 0. Since the panel went live on 2026-08-13 it has kept 11 of ~693 buy proposals (1.6%) and 60 of ~337 sell proposals (17.8%). Phase 1 (image `20260822-redesign-phase1`, removed the crypto reachability record line) cut the line's citation rate 21%→0.9% and moved kept buys 0→0: not the binding channel. The 30-day realized baseline is −$175.53 over n=540 runs, of which −$178.71 is two full-book dump days (08-12/08-13); the post-panel regime since 08-14 is +$3.18 over 463 runs — a $0 machine. No proposal in this document earns a dollar inside 30 days at current size ($500 notional/entry); the program's purpose is to create the first measurable entry channel and to measure it honestly. The only positive-sign evidence anywhere is research/06 Exp 1 (crypto demoted buys, n=74, +$145 net/8d, +$84.54 with the largest winner stripped), contradicted in sign by the only recent same-method window (n=7, −$33.6, 0 targets). It is a hypothesis, not a lever.

## 2. Decided facts

| # | Fact | Evidence | Conflict settled |
|---|---|---|---|
| F1 | The binding channel is the panel's technical read, and its verdict words are CODE-authored. | `quant_crypto.py` L235-238 appends `RSI(14) xx overbought (≥70 sell trigger)` and scores −2 with no trend check; L272-275 `crowded long (≥2.0, squeeze risk)`; L298 `momentum_12_1_pct` unlabelled. Prod n=110 crypto buy→hold (08-21..08-23): RSI cited 88%, overbought 72%, pullback 61%, crowded 56%; 14/68 reports misread the 12-1 factor as current momentum ("LINK −67%"). | L10 H-PRIOR (model hold prior) vs L1/L9 H-TECH: settled for H-TECH by directional asymmetry (sell→sell 17.8% vs buy→buy 1.6%, same gpt-oss:120b). H-PRIOR stays as a calibration arm only. |
| F2 | Proposer and panel read different data. | `_light_analysis` (run_engine.py L5751-5870) sees closes-only; the panel's Technical Analyst gets `build_crypto_analysis()` with RSI/long-short/funding/volume. The Technical Analyst has NO skill site (`PROMPT_SITES` = light, trader, verifier, planner; `_brief` L253-264 takes role+instruction+data only). | L1 (trader-site skill) vs L9 (new technical site): measured prior for a trader-site skill is 2/68 uptake (`measured-entry-record`, verified rendered at offset 34,310). Settled for L9's site, with L1's regime instruction merged; arms B vs C decide it in the replay. |
| F3 | The panel is NOT followed by a hidden second block. | Runs 1417 (08-18T09:54Z) and 1556 (08-20T00:35Z) were fail-open buys that emitted trade in the same second; run 1419 (kept buy) filled AUDUSD long. Fleet runs since 08-19 carry `min_confidence` 0.50-0.57 (n=226), not 0.65. gate_skip 24h = 541 market-closed + 209 decision-is-hold. | Judge 1 extended L10's "downstream block"; Judges 2 and 3 refuted it on tape. Settled: refuted. What survives: the confidence gate IS in series (run 1148 fail-open buy died at `gate_skip confidence 0.58 below threshold 0.66`), so every kept-buy metric counts only kept buys whose final confidence clears the run's `min_confidence`. Judge 1's two unexplained no-fill kept buys (1224, 1296) get a $0 tape trace inside item 0, not a new workstream. |
| F4 | agent_memory is a contributing echo (~30% of demotions), not binding. | analysis_memory.py: recall L82-108 (200 newest, same-symbol first, 5 rows, no outcome), remember L185-225 (2 outcome-less lessons/panel), `_prune` L168-177 deletes 1 row per write (agent 6 holds 925 vs cap 200). 420/458 demotions carried ≥1 pullback lesson; median lesson age at recall 1.5h. Verdicting lessons at +24h: crypto 27% right / 30% wrong / 42% flat. | Citation rates 10.8% / 24% / 28% / 30% are different denominators; 30% (139/458 demotions) is the right one. L2's per-row outcome weighting is REFUTED by L2's own replay (pullback lines 2.71→3.16/5). L10's "no outcomes exist" misreads L2 (claims are verdicted, not holds). |
| F5 | desk_memory flat recall is live on prod and reaches only the proposer. | 615/616 decisions in 48h carry `recall_entry`; 615/615 head = `skill:reachable-exits#1` (pooled-IDF artefact: 670 outcome docs score ~0.35 and set IDF). Lesson-only ranks `measured-entry-record` #1 crypto/forex/futures, #5 us-stock. | Memory "desk recall covers only holding cycles" is STALE (`DESK_RECALL_FLAT` on in prod) — update it. L3 concedes $0: the light tier already proposes buy in 24% of cycles. |
| F6 | The demoted proposal is destroyed. | 592/592 order_discussion payloads carry only `{action, confidence}` (run_engine.py L6127-6128, L6147-6148); no reader depends on the event (git grep). 21/71 salvaged truncations are <500 chars, below the 380-token cap — the token budget is not the sole truncation mechanism. | L4 ≤3KB snapshot vs L9/L10 four briefs: one owner, L4 shape + technical dict + briefs clamped 600 chars each (≤~6KB). |
| F7 | The bucket expectancy gate's crypto/long veto rests on n=3 fills. | fleet_planner.py L449-456 counts `status='stopped'` (110/113 are $0 idle-retired runs); docstring and `_expectancy_min_trades` (L418-422, default 8) intend closed TRADES. Crypto/long: 3 fills, −$1.31, −$0.35 stripped. Crypto/short "+6.66" is two FIL runs (+$0.42 stripped one, −$1.94 stripped two). Gate called only at L1807 (build); `_build_replacement` never calls it. | L8 "leave the split, parity is wrong-signed" and L10 "parity is a tightening" are right ONLY before the recount; after n=fills the gate fails open on crypto/long and parity refuses nothing. Settled for L6's order: recount → parity. |
| F8 | Auto-tune raises n it cannot fund. | fleet_planner.py L788-795 `recommended_max_slots` = budget // $100 clamped; fleet_auto_tune.py L144-170 never reads committed budget. Fleet 39: 7 slots hold $10,005.32 of $10,005.35; `auto_tune_slots {7→25}` with 0 `slot_created`; growth loop L838-842 breaks every pass ("replenishing:7/25" phantom). | None. |
| F9 | Fleet starvation is the 12h cooldown × ~22-name pool, but it costs $0. | Fleet 38 7-slot phase: 63.1% occupancy over 512.6 slot-h; 7×12/5.26 ≈ 16 benched > 15 free names; replacement latency mean 146.9 min (n=87); 23/89 retires benched a name the PANEL (not the desk) refused. 101 runs realized −$6.90 (99 at $0). `bracket_infeasible` retried 153×/7d (ADBE 70, MA 43, ENA 28) because `_REGATE_MEMO` never records raises inside `_try_build`. | L5 cooldown rules 1-2 vs L10/L8: deferred — re-offers panel-refused names into an LLM tier measured ~5× oversubscribed, for $0 until entries exist; they also inflate F7's hollow n. Memo + journaling accepted. |
| F10 | Weekend-closed slots are the owner's explicit-scope rule, not a defect. | 373 rotations audited: 37 into closed markets, only 4 had an open in-scope alternative (SI, HG, INTC, BAC = 30.4 slot-h/7d). Fleet 37's other 33 are the forex fee floor (373 fee_gate drops) and weekends. | L7 Experiment B (per-market cap over open markets) needs owner sign-off (#359, 2026-08-12 rule). Reorder alone is allowed, $0. |
| F11 | Exp 1's +$145 is a hypothesis. | Plan-replay diverged from live by $158 on Exp 2's n=104 (plan −$337 vs live −$180 — harsher, not kinder); recent same-method window n=7 = −$33.6; no desk bracket persisted; no lens discounted by the confidence gate. | No skill text may carry a dollar figure; no lens may book +$317..$544. |

## 3. The program (critical path first)

Items marked **[MONEY PATH]** change what enters the tape. Everything else is $0 by construction. Every prompt/brief change ships with a wiring test (memory: brief-line wiring is untested by default). All PRs rebase on origin/main after Phase 1, never on the local `feat/i18n-followups` checkout.

### Item 0 — Persist the destroyed proposal (observability) — ships now

- **Change (code, ours):** run_engine.py `_order_discussion` L6090-6160. Add pure `_proposal_snapshot(decision) -> dict` returning `{action, confidence, conviction: compute_conviction(scores), scores (4 keys), entry, order: {stop_pct, target_pct}, order_intent, outlook: {bias, entry{kind,low,high}, exit{target_px,stop_ref_px}, horizon_hours, invalidation} via _parse_outlook, plan_adherence, report[:500]}`. Use at L6127 (`payload['proposed']`) and L6147 (`payload['final']`, the panel's own). Add `payload['technical'] = {rsi_14, trend_status, long_short_ratio, funding_rate, volume_ratio, momentum_12_1_pct}` from the technical dict and `payload['briefs'] = {technical, news, sentiment, macro}` each clamped to 600 chars. In the rule-fallback branch (L6141-6143) add `payload['panel_text_tail'] = (final.get('report') or '')[-400:]` before raising. `final['escalated_from']` byte-identical. Payload ≤~6KB (592 events/7d ≈ 3.5MB/week, negligible beside 154k equity events/7d).
- Also: journal a `gate_skip` reason on every no-fill path after a kept buy (currently confidence and market-closed are journaled; assert there is no silent path by tracing runs 1224 and 1296 on tape — $0 probe).
- **Tests** (`tests/test_order_discussion.py`): `test_demoted_proposal_survives_in_the_event` (fails on origin/main with KeyError 'order'); `test_snapshot_has_no_effect_on_the_final_decision` (decision event conviction is the PANEL's); `test_panel_fallback_journals_its_text`; `test_briefs_are_clamped_to_600`.
- **Experiment:** none required (no money path). Post-ship check: 100% of order_discussion events in 48h carry `proposed.order` and `technical.rsi_14` keys.
- **Expected NET 30d:** $0. **Risk:** untested wiring silently no-ops (the tests are the guard); ingest must stay OFF for the new fields (memory: journal-only flat rows refuted as treatment). **Owner rule:** measure-after-shipping is impossible for any panel change without it. **Rollback:** revert; nothing reads the keys.

### Item 1 — Merged offline replay (the experiment everything in Item 2 waits on)

- **Where:** `research/` script, executed read-only inside `sooppiy-worker` off-peak (LLM tier ~5× oversubscribed on 2026-08-17; the run must not share the live window). No `emit_telemetry_event`, no DB writes.
- **Set:** the 110 crypto buy→hold order_discussion events 2026-08-21T00Z..08-23T10Z (21 symbols) + the 68 from the deep-analysis window if disjoint + every event persisted by Item 0 after ≥48h. Control set: forex buy→hold (n=4) + research/06's 73 futures/forex demoted episodes.
- **Reconstruction:** technical dict as-of `ts` from OKX daily(400)+hourly(100) via `quant_crypto`'s pure functions (add `as_of`); long/short and funding from OKX history where available, else `None` (count reported). News/sentiment/macro briefs regenerated ONCE per event and held IDENTICAL across arms (for Item-0 events, the persisted briefs are used). Memory block frozen to agent_memory rows as of `ts`. Temperature 0.3, 2 seeds (3 on the 110 set); a buy counts as kept only if a majority of seeds say buy AND final confidence ≥ the run's `min_confidence`.
- **Arms:** A = production inputs (calibration gate: must reproduce ≥55/68 holds or no arm is readable); ii = technical brief replaced by neutral RSI-50/balanced text; iii = memory block ''; iv = skills '' and record ''; v = ii+iii+iv; B = `momentum-regime-read` at trader site only; C = at new technical site + trader; D = C + neutral quant_crypto labels + regime-first Technical Analyst instruction; vi = D + "DESK PROPOSAL UNDER REVIEW" block (L1 piece 2, as an ARM only).
- **H-POOL probe (same run):** for every crypto long thesis built since 08-13, join build-time RSI to direction; share built at RSI>70.
- **Hypotheses / falsifiers (pre-registered):** H-TECH: arm ii raises kept-buy rate ≥10 pts and arm D ≥15% (≥17/110); dead if ii moves <10 pts. H-PRIOR: dead if arm v ≥30% buys. H-SITE: dead if B ≈ C (site is not the lever, only text). H-POOL: dead if <40% of crypto longs were built at RSI>70; if ≥60%, the generator manufactures the refusal and Item 2 is insufficient alone. H-ANCHOR: arm vi keeps buys outside `trend_status='uptrend'` at a higher rate than D → proposal visibility is rejected.
- **Counterfactual walk (money):** for each arm's kept buys, take the arm's own `order.stop_pct/target_pct/horizon_hours` (house defaults when `defer`), walk OKX 1h candles first-touch (stop if low≤stop before high≥target; target if high≥target first; else horizon mark); size = current slot size; fee 1.08% round trip; report NET with and without the largest contributor; if stripping flips the sign → INCONCLUSIVE, nothing ships. Control set kept rate must not rise above arm A.
- **Metric:** kept-buy rate per arm per set (above the confidence gate); NET $ per arm (n, stripped); outcome class counts; count of events with unreconstructible long/short or funding.
- **Cost:** ~110 × 9 arms × ~6 calls ≈ 6,000 calls; run on the local tier over two off-peak nights or cap the set at 68 for arms B/C/vi (~2,500 calls).
- **Expected NET 30d:** $0. **Rollback:** n/a.

### Item 2 — Crypto-scoped technical fix **[MONEY PATH]** — ships only on Item 1

Ship gate: arm D (or C) ≥15% kept on crypto, control set unchanged, kept-buy NET >0 with and without the largest contributor, H-ANCHOR not violated. If C ≈ D, skip the label change (fewer lines).

- **(a) quant_crypto.py L235-238, L272-275, L298:** labels become facts, score arithmetic untouched (feeds only the rule fallback, which cannot originate a position): `RSI(14) 80.6, above 70`; `long/short 2.1, above 2.0`; rename/annotate `momentum_12m_minus_1m_pct (long-horizon factor, not the current move)`.
- **(b) analysis_agents.py L1019-1021** Technical Analyst instruction: `Read trend, momentum, and key support/resistance. State the regime first: trend-continuation or reversal. An overbought oscillator inside a stacked uptrend is extension, not a sell signal — call a pullback only if you can name the failure trigger in the data shown; otherwise say the trend is intact and name the level that would break it.`
- **(c) trading_skills.py L43** `PROMPT_SITES += ("technical",)`; `_brief` for the Technical Analyst only receives `skills=_skills_block("technical", market)` rendered after the instruction, before the data.
- **(d) New skill** (BASE_SKILLS), slug `momentum-regime-read`, name "Momentum Regime Read", prompts `["technical","trader"]`, markets `["crypto"]`, priority 13, description: `RSI above 70 is a regime label, not a verdict: in a trending tape with participation it is continuation; a pullback call needs a trigger and a level.` Lessons (verbatim; all dollar/count claims stripped per the judges):
  1. applies_when [flat]: `An RSI(14) above 70 tells you the tape is trending, not that it is about to reverse. Read it WITH the trend structure and participation shown: when price sits above MA20 and MA20 is above MA60 (or MA5 above MA20 and rising) and the volume ratio is at or above 1, RSI 70-85 is CONTINUATION and the correct analyst read is "trend intact, entries on a shallow dip or on a reclaim of the prior session's high". "Overbought" alone is not a pullback call.`
  2. [flat]: `A pullback call requires a FAILURE TRIGGER in the data shown — a lower high, a break of the prior session low, a volume climax followed by a lower close, or price losing MA5 — plus the LEVEL at which you would then buy. If you write "pullback likely" you must name the trigger and the level in the same sentence; "stay flat and monitor" with neither is not a read.`
  3. [flat, holding]: `The volume ratio is the last hour against the recent hourly average; it is a liquidity reading that is structurally low on weekends and off-hours and says nothing about whether a daily trend is fading. Never convert a ratio below 1 into "low conviction" — say "thin hour" and judge the trend from the daily structure.`
  4. [flat, holding]: `A long/short account ratio above 2 is positioning context, not a signal: crowded longs in a rising tape are the trend's fuel until a lower high prints. A squeeze needs the failure trigger of lesson 2; without it, "crowded long" adds nothing to the decision.`
  5. [any]: `momentum_12m_minus_1m is a twelve-month window with the last month removed — a long-horizon factor for ranking, NOT the current move. A reading of -67% on a coin that is up this week means the coin fell last year; it is never "momentum sharply negative" today. Current momentum is price versus MA5/MA20 and the day's change, nothing else.`
  Headroom: trader/crypto 43,185 of 48,000 chars; technical site starts at 0.
- **Tests:** rendered technical block contains the skill for crypto and NOT for futures/forex/us-stock; the instruction text assertion; quant_crypto label snapshot test; mutation test (remove the `skills=` kwarg → test fails).
- **Post-ship experiment (7d):** same kept-buy rate above the confidence gate; kept→fill ratio; realized NET of fills with fees stated ($5.40/episode at $500; ~$1,500/30d at 9/day must be out-earned); sell→hold (22/window) and holding-cycle exits must not loosen; memory citation rate. A result that does not move kept buys is reported as FAILED in these terms.
- **Expected NET 30d:** $0 proven. Bracket if the Exp 1 sign holds: −$150..+$540 at current size; the honest number is $0 until fills exist, and the first kept buys fill into a tape the panel called crowded — a squeeze-down loss must be reported as a loss.
- **Risk:** echo flips sign (panel writes outcome-less "continuation" lessons) — Item 6 must follow; label change is visible to manual /analysis users; Phase 1's 48h clock (ends ~08-25T05Z) — ship after it closes or declare Phase 1 closed (0→0 already measured).
- **Owner rules:** AI-FIRST (code-authored judgment returned to the AI at a skill site; no gate touched); never loosen without a replay (Item 1); measure again after shipping. **Rollback:** disable the skill row (`enabled=0`), revert (a)-(c); one deploy.

### Item 3 — Bucket gate evidence, parity, auto-tune cap (must land before Item 2's re-measure)

- **(1) fleet_planner.py L449-456:** n = `COUNT(realized_pnl_usd <> 0)`, SUM over the same rows; refusal string `X over N fills (M closed runs)`; behind `FLEET_EXPECTANCY_COUNT_FILLS` (default off until the per-bucket recount table — sum, strip-largest, n_fills per agent/market/direction — is published in docs/reports). `FLEET_EXPECTANCY_MIN_TRADES` stays 8. Effect today: crypto/long fail-open (n=3); agent 5 crypto/short (5 fills, −$98.23, one −$69.56 run) and us-stock/long (5 fills, −$55.33) flip open — stated risk; report weekly.
- **(2) fleet_supervisor.py `_try_build` L1280-1292:** `neg = fp._bucket_expectancy_block(fleet['agent_id'], thesis); if neg: raise ValueError(neg)` so the candidate loop journals `candidate_skipped` and continues; rewrite L1070-1073 docstring. Ships ONLY after (1) (before it, parity would have refused ~108 replacement builds in 8 days to save $1.31). Mutation-tested wiring test (8 fills summing −$10 → ValueError; remove call → test fails). Offline replay of 08-15..08-23 replacement candidates through the fixed gate must refuse 0.
- **(3) fleet_auto_tune.py L144-150:** `uncommitted = total − Σ original_allocation_usd (non-closed slots)`; `rec = min(rec, cur + int(uncommitted // (total / rec)))` as the LAST min() below entitlement and `user_size_cap` (owner 2026-08-15); emit `auto_tune_slots {from, to, capped_by:'uncommitted', uncommitted}`. Tests: 100%-committed fleet → rec = cur; 2×$500 on $10k → rises to fundable count.
- **Hypotheses:** H-GATE-EVIDENCE falsified if an unblocked bucket reaches ≥8 fills with sum < −(8 × fee floor) surviving strip-largest within 7d. H-PARITY falsified by any `candidate_skipped negative_expectancy` with `context:replacement` while the build path allows the bucket. H-AUTOTUNE falsified by one raise with no `slot_created` within 2 passes, or a fleet with uncommitted ≥ total/(2n) not raised.
- **Expected NET 30d:** ≈ $0 (−$1 to $0). **Owner rule:** "never loosen a gate without a replay" — the 8-day replacement-path natural experiment (113 runs, 3 fills) plus the published table is the replay; flag-gated. **Rollback:** flag off / revert.

### Item 4 — $0 hygiene with no LLM cost (Lens 5 rules 3-4)

- `bracket_infeasible` skip memo in `_build_replacement` (fleet_supervisor.py L1184-1207) keyed `(thesis_key, market, symbol, round(funding, 0), feedback)` with the thesis `expires_at`; one `candidate_skipped` per key; behind `FLEET_BRACKET_SKIP_MEMO`. Replaces 153 retries/7d with ≤7. Test: second pass with the same key raises nothing and journals nothing.
- Journal `candidates: len(theses)` in `rotation`/`slot_waiting` payloads and `no_candidates` once per 15 min per slot. Test: payload key asserted.
- Cooldown rules 1-2 (pool-scaled 5.6h, 2h panel-demoted) are DEFERRED until Item 2 produces kept buys; if revisited, replay them together with Item 3(2).

### Item 5 — Lens 3 flat recall lesson-only (hygiene, proposer only)

- `_recall_flat_line` (run_engine.py L4895-4912) calls `_recall_line(run, {}, 0.0, kinds=("lesson",))`; `_recall_line` gains `kinds=_RECALL_KINDS` default so the holding path is byte-identical; recall rows carry scheme `eps-head-fixed-v1/lesson-flat` (Plan 22 §7 forbids unlabelled policy pooling). Wiring test: flat brief with a lesson corpus renders `measured-entry-record`.
- Falsifier post-deploy: <90% of crypto flat recall rows carry `skill:measured-entry-record` in chunks[0..1] within 48h (pre: 0/468) = FAIL; crypto buy proposals/day falling >50% vs 82/68 = revert. Predicted: kept buys unchanged (panel does not read desk_memory) — "ranking fixed, profit unmoved".
- Update memory `desk-recall-covers-only-holding-cycles.md`: DESK_RECALL_FLAT is ON in prod (615/616).

### Item 6 — agent_memory family scoreboard (one week AFTER Item 2's 7-day window)

- analysis_memory.py: write `metadata += {claim: down|up|none, px0, horizon_h: 24, family, count}`; same (agent, family, symbol) within 7d increments `count` instead of inserting; `attach_verdicts(limit=200)` from the housekeeping tick (closed markets defer via `markets.is_session_open`, never "flat"); `claim none → n/a` enforced so hold lessons never score; recall renders ONE line per family: `<newest text> [this desk: seen N×, verdicted M: right r%, wrong w%, flat f%; unproven U]` — three numbers, never a verdict word; fix `_prune` to `LIMIT 10000 OFFSET ?`. No row deletion until the verdict pass has run ≥7d. Behind `ANALYSIS_MEMORY_SCOREBOARD`, A/B by fleet (crypto treatment, futures/forex control). Line is customer-visible in /analysis — wording fit for users.
- Falsifier: crypto kept-buy share stays 0/N (N≥50) in 7d, or kept buys' bracketed NET ≤ $0 stripped, or memory citation in demotions stays ≥30% with pullback primary → channel closed as non-binding. Baselines: 2.71 pullback lines/5, 139/458 citation, 0% verdict coverage.

### Item 7 — Truncation contract (Lens 4 phase B)

- `llm_client.generate_text` records provider `finish_reason` in a thread-local reset at call entry; `_no_verdict_diagnostic` journals `finish` and a tail up to 2000 chars; light prompt L5928 adds `single-line JSON, no whitespace` (A/B by run-id parity, 48h); `RUN_LIGHT_MAX_TOKENS` env floor defaulting to 380/460, raised ONLY if finish=length dominates the ≥800-char salvaged cohort; panel-side unparseable text routed through `_salvage_truncated_json` behind a flag after replaying the 5 unparseable/7d. Baseline 73/4036 = 1.81% truncated+no-verdict. Test: prompt-text assertion; `test_salvaged_event_carries_finish_reason`.

### Item 8 — Session-aware stable reorder (Lens 7)

- symbol_research.py `select_targets` between the scope filter (~L1505) and `_select_from_eligible` (L1510): key `(0 if is_market_open(m) and session_minutes_left ≥ need else 1, final_score DESC)`; behind `FLEET_SESSION_PREFER`. Closed theses stay in the pool (deferred, never vetoed); empty scope∩open = byte-identical to today. Deterministic replay over the 373 rotations must change exactly 4 picks (SI→LTCUSDT, HG→ASTERUSDT, INTC→GBPCHF, BAC→GBPCHF) and 0 open picks. Metric: tradeable occupancy (baseline 63.9%, fleet 39 49.1%); +30.4 slot-h/7d. $0 (crypto +$0.003/slot-h, −$3.78 stripped).

## 4. Rejected proposals (do not re-run)

| Proposal | Why |
|---|---|
| L8 lever 1 `crypto-overbought-is-not-a-veto` skill carrying "+$145/8d, 55% win"; L9 lessons 1-2 with "+$145" / "56 of 68" | An unproven counterfactual written as doctrine — the pullback echo with the sign flipped; trader-site uptake prior 2/68. Regime lessons survive without numbers (Item 2d). |
| L1 piece (2) live "DESK PROPOSAL UNDER REVIEW" block | Anchoring; brushes the 2026-08-13 rule (panel replaces wholesale). Demoted to replay arm vi with falsifier H-ANCHOR; if it wins, it goes to the owner as a rule question. |
| L1 trader-site `momentum-regime-lens` as the lever | Trader-site skill prior 2/68; folded into arms B/C. |
| L8 "leave the gate split / do not ship parity" | Rests on the hollow −1.31 over 109 $0 runs; after the fills recount parity refuses nothing. |
| Gate parity BEFORE the fills recount | Would have refused ~108 replacement builds in 8 days for $1.31 and parked weekend slots on closed markets. |
| L10 "ship nothing" taken literally; L10 downstream second-gate hypothesis; L10 H-PRIOR as lead | Persistence and gate-recount are $0 prerequisites; runs 1417/1556/1419 traded; 17.8% vs 1.6% directional asymmetry. |
| L2 per-row outcome weighting; L8 1(b) per-row outcome attachment; 7-day expiry deletion before a verdict pass exists | Self-refuted: pullback lines 2.71→3.16/5; deletes rows with no evidence. |
| L3 options C (per-kind quota surfaces 0.35-score "nothing was learned" outcomes), D (query stuffed with the skill's words), E (tag boost, fails 3/4 markets) | Refuted by L3's replay. |
| L5 cooldown rules 1 (pool-scaled) and 2 (2h panel-demoted) now | $0 at current panel behaviour; re-offers panel-refused names; +62 cycles/day on a ~5× oversubscribed tier; inflates the hollow gate n. Revisit only after Item 2 moves kept buys. |
| L7 Experiment B (per-market cap over open-in-scope markets) | Edits the owner's #359 diversity algorithm and the 2026-08-12 rule; concentrates Sunday fleets in crypto/long. Owner sign-off only. |
| `RUN_LIGHT_MAX_TOKENS` raise before `finish_reason` data | 21/71 cuts are below the cap; #468's shape. |
| ATR-of-hold brackets wired live; $5,200 sizing rung | Exp 2: 7/104 targets hit, holding to plan −$158 worse; sizing only after ≥30 entries net >0 stripped plus a slippage probe. |
| Any change to the futures/forex panel | Panel RIGHT there (0/73 targets); every crypto change carries a futures/forex control arm. |
| Booking any 30-day dollar figure | Every lens's honest number is $0; the only positive sign is a plan-replay whose sign reversed on n=7. |
| Re-adding the crypto reachability record line | Phase 1 measured it as not binding (21%→0.9% cites, 0→0 kept). |

Refuted hypotheses by name: H-PRIOR (lead), H-DOWNSTREAM-BLOCK, H-IDLE-PREMATURE (192 decisions, 0 buys), H-RECALL-LINE-BINDING (Phase 1), H-TOKEN-CAP-SOLE-MECHANISM, L2-PER-ROW-WEIGHTING, L3-C/D/E.

## 5. Zero-dollar hygiene items

| Item | Cost today | Test |
|---|---|---|
| Gate n = fills + parity (Item 3.1-3.2) | Build path vetoes crypto/long on 3 fills; two answers 60s apart (04:57Z refused, 04:59Z built); ~108 builds/8d would be refused if parity shipped first | Recount table reproduces the event string; parity ValueError on 8 fills/−$10; mutation test; replay refuses 0 |
| Auto-tune committed budget (Item 3.3) | 1 phantom raise per 30-min tick on fleet 39; floor_usd 714→200 side effect | 100%-committed → rec=cur; $1k of $10k committed → fundable count; prod tick shows `capped_by:'uncommitted'` |
| bracket_infeasible memo (Item 4) | 153 identical retries/7d; ~0.5 slot-h/day on one-candidate passes | Second pass same key: no raise, no event |
| Candidates-per-pass journaling (Item 4) | Candidates/pass reconstructible only from 134 backtest_gate events (lower bound) | Payload key asserted |
| Market-hours parking/reorder (Item 8) | 30.4 slot-h/7d reclaimable of 1028.5 closed (3%); the rest is the forex fee floor + owner weekend rule (~74 slot-h fleet 39, by rule) | Exactly 4 picks change, 0 open picks change |
| Flat recall lesson-only (Item 5) | 615/615 constant head; Plan 22 (b) dataset has no variance | Lesson rendered in flat brief; scheme label present |

## 6. Measurement after shipping

Read via the prod read-only SQL path (`run_events` by `ts`, never `created_at`). Cadence: 48h read after each ship (items 0, 2, 3), then 7d read; Item 2 additionally at n=30 fills.

```sql
-- Q1 kept-buy rate per day, above the run's confidence gate
SELECT DATE(e.ts) d,
       SUM(JSON_EXTRACT(e.payload,'$.proposed.action')='buy') proposed_buy,
       SUM(JSON_EXTRACT(e.payload,'$.proposed.action')='buy'
           AND JSON_EXTRACT(e.payload,'$.final.action')='buy') kept_buy,
       SUM(JSON_EXTRACT(e.payload,'$.proposed.action')='buy'
           AND JSON_EXTRACT(e.payload,'$.final.action')='buy'
           AND JSON_EXTRACT(e.payload,'$.final.confidence') >=
               JSON_EXTRACT(r.config_snapshot_json,'$.min_confidence')) kept_buy_above_gate
FROM run_events e JOIN trading_runs r ON r.id=e.run_id
WHERE e.event_type='order_discussion' AND e.ts>=NOW()-INTERVAL 7 DAY AND r.market='crypto'
GROUP BY 1;

-- Q2 kept -> fill ratio (trade within 10 min of a kept buy)
SELECT COUNT(*) kept, SUM(EXISTS(SELECT 1 FROM run_events t WHERE t.run_id=e.run_id
       AND t.event_type='trade' AND t.ts BETWEEN e.ts AND e.ts+INTERVAL 10 MINUTE)) filled
FROM run_events e WHERE e.event_type='order_discussion' AND e.ts>=NOW()-INTERVAL 7 DAY
 AND JSON_EXTRACT(e.payload,'$.proposed.action')='buy' AND JSON_EXTRACT(e.payload,'$.final.action')='buy';

-- Q3 realized NET with and without the largest contributor (use pnl_audit.py for the ledger replay)
SELECT COUNT(*) n_fills, SUM(realized_pnl_usd) net,
       SUM(realized_pnl_usd)-MAX(realized_pnl_usd) net_ex_largest_win,
       SUM(realized_pnl_usd)-MIN(realized_pnl_usd) net_ex_largest_loss
FROM trading_runs WHERE created_via='fleet' AND realized_pnl_usd<>0 AND started_at>=NOW()-INTERVAL 7 DAY;

-- Q4 control: sell->hold and futures/forex demotions must not move
SELECT r.market, JSON_EXTRACT(e.payload,'$.proposed.action') p, JSON_EXTRACT(e.payload,'$.final.action') f, COUNT(*)
FROM run_events e JOIN trading_runs r ON r.id=e.run_id
WHERE e.event_type='order_discussion' AND e.ts>=NOW()-INTERVAL 7 DAY GROUP BY 1,2,3;

-- Q5 citation counts in demotion reports
SELECT SUM(JSON_EXTRACT(e.payload,'$.final.report') LIKE '%overbought%') overbought,
       SUM(JSON_EXTRACT(e.payload,'$.final.report') LIKE '%pullback%') pullback,
       SUM(JSON_EXTRACT(e.payload,'$.final.report') LIKE '%memory%') memory,
       SUM(JSON_EXTRACT(e.payload,'$.final.report') REGEXP 'trigger|level') trigger_or_level, COUNT(*) n
FROM run_events e WHERE e.event_type='order_discussion' AND e.ts>=NOW()-INTERVAL 7 DAY
 AND JSON_EXTRACT(e.payload,'$.proposed.action')='buy' AND JSON_EXTRACT(e.payload,'$.final.action')='hold';

-- Q6 verdict health (Item 7 guard): truncations / no-verdict per decision
SELECT event_type, COUNT(*) FROM run_events WHERE ts>=NOW()-INTERVAL 7 DAY
 AND event_type IN ('decision','verdict_salvaged','no_verdict') GROUP BY 1;

-- Q7 gate recount table (Item 3) and parity check
SELECT agent_id, market, direction, COUNT(*) closed_runs, SUM(realized_pnl_usd<>0) n_fills,
       SUM(realized_pnl_usd) s, SUM(realized_pnl_usd)-MIN(realized_pnl_usd) s_ex_largest_loss
FROM trading_runs WHERE created_via='fleet' AND status='stopped' GROUP BY 1,2,3;
SELECT JSON_EXTRACT(payload,'$.context') ctx, COUNT(*) FROM fleet_events
 WHERE event_type='candidate_skipped' AND JSON_EXTRACT(payload,'$.reason') LIKE 'negative_expectancy%'
 AND ts>=NOW()-INTERVAL 7 DAY GROUP BY 1;

-- Q8 occupancy + phantom auto-tune (Items 3.3, 4, 8)
SELECT fleet_id, event_type, COUNT(*) FROM fleet_events WHERE ts>=NOW()-INTERVAL 7 DAY
 AND event_type IN ('auto_tune_slots','slot_created','candidate_skipped','no_candidates','rotation') GROUP BY 1,2;
```

Kill criteria:
- Item 2: at 48h, crypto kept-buy-above-gate / proposals < 5% with n≥40 → not read (same class as Phase 1) → revert, report FAILED. First 30 fills NET ≤ $0 with AND without the largest winner → revert, report as a loss. Any rise in futures/forex kept rate, or sell→hold falling >30% (loosened exits) → revert. Verdict-null rate (Q6) doubling → revert.
- Item 3.1: an unblocked bucket reaches ≥8 fills with sum < −(8 × fee floor) surviving strip-largest → flag off, report.
- Item 5: crypto proposals/day falling >50% within 48h → revert.
- Item 6: primary metric unmoved at 7d → flag off, channel closed as non-binding.
- Item 8: any open pick turned closed → revert.
- Every read names n and reports the figure with and without the largest contributor; a sign flip on stripping = inconclusive, never "improvement".

## 7. Summary table

| Item | Owner-rule fit | Evidence | Expected $ (30d) | Experiment | Status |
|---|---|---|---|---|---|
| 0 Persist proposal + technical dict + briefs | Measure-after-shipping prerequisite; no money path | 592/592 payloads {action, confidence}; no reader depends | $0 | Key-presence check at 48h | proposed |
| 1 Merged offline replay (arms A, ii-v, B, C, D, vi; H-POOL) | Implement only on an experimental result | n=110+68 crypto demotions; control n=4+73 | $0 | Pre-registered falsifiers H-TECH/H-PRIOR/H-SITE/H-POOL/H-ANCHOR; own-bracket walk, fee 1.08%, stripped | proposed |
| 2 Crypto technical fix: neutral labels + technical site + regime instruction + `momentum-regime-read` **[MONEY PATH]** | AI-FIRST (judgment returned to the AI); no gate touched | 67/68 primary cause; 2/68 trader-site prior; 17.8% vs 1.6% asymmetry | $0 proven; −$150..+$540 bracket if Exp 1 sign holds | Ships only on Item 1; 7d re-measure Q1-Q5 | proposed |
| 3.1 Gate n = fills (flag) | Gate's own standard; flag-gated loosening | n=109 → 3 fills, −$1.31 (−$0.35 stripped) | ≈ $0 | Recount table published; 7d H-GATE-EVIDENCE | proposed |
| 3.2 Parity in `_try_build` (after 3.1) | Code paths agree | Docstring claims parity; 60s two-answer asymmetry | $0 | Replay refuses 0; mutation test | proposed |
| 3.3 Auto-tune uncommitted cap | Allocation arithmetic; below user_size_cap | Fleet 39 7→25 with $0.03 headroom | $0 | Phantom rate 1/1 → 0 | proposed |
| 4 bracket_infeasible memo + candidates journaling | $0 waste removal | 153 retries/7d; 91/134 one-candidate passes | $0 | Retries per key ≤1 | proposed |
| 5 Flat recall lesson-only + scheme label | Plan 22 §7; proposer only | 615/615 constant head; pooled #11 vs lesson-only #1 | $0 | ≥90% rows carry the skill in top-2 at 48h | proposed |
| 6 agent_memory family scoreboard (after Item 2 window) | Scoreboard, not arbitration | 92% demotions carry pullback lesson; 27/30/42 verdicts | $0 | A/B by fleet, 7d | proposed |
| 7 Truncation contract | Refutes #468's shape before any cap raise | 21/71 cuts below cap | $0 | finish_reason share on ≥800-char cohort; 48h parity A/B | proposed |
| 8 Session-aware reorder | 2026-08-12 scope rule honoured | 4/37 closed rotations had an open alternative | $0 (+30 slot-h/7d) | Exactly 4 picks change in replay | proposed |
| Deferred: L5 cooldown rules 1-2; L7 Exp B; sizing rung; ATR brackets | — | — | $0 | Only after Item 2 produces kept buys / owner sign-off | deferred |

Memory updates required with this plan: `desk-recall-covers-only-holding-cycles.md` (stale: DESK_RECALL_FLAT on in prod, 615/616); record the refuted hypotheses in §4 by name.

## 한국어 요약

- 문제: 2026-08-20T07:10Z 이후 체결 0건, 최근 4개 일간 윈도우에서 매수 제안 177건 중 패널 통과 0건. 실현 손익 $0. 30일 기준 −$175.53 중 −$178.71은 08-12/13 덤프 이틀분이며, 패널 이후 체제는 +$3.18(463 런)인 $0 기계.
- 구속 채널은 패널의 기술 분석 읽기이며, 그 판정어(“sell trigger”, “squeeze risk”)는 quant_crypto.py L235-238/L272-275에서 코드가 쓴 것. 12-1 모멘텀 팩터는 14/68 리포트에서 현재 모멘텀으로 오독됨.
- 제안자(종가만 봄)와 패널(RSI/롱숏/펀딩)은 다른 데이터를 읽고, 기술 분석가에는 스킬 사이트가 없음. 트레이더 사이트 스킬은 68건 중 2건만 인용됨.
- 판정 해결: “패널 뒤 숨은 2차 차단”은 런 1417/1556/1419 체결로 반증; 다만 신뢰도 게이트는 직렬로 실재(런 1148, 0.58<0.66)하므로 kept-buy 지표는 게이트 통과분만 센다. 모델 hold 선입견(H-PRIOR)은 매도 17.8% vs 매수 1.6% 방향성 비대칭으로 후순위.
- Exp1 +$145/8d는 가설이지 레버가 아님(최근 n=7은 −$34). 어떤 스킬 텍스트에도 달러 수치를 넣지 않는다.
- 크리티컬 패스: (0) 폐기되던 제안·기술 딕셔너리·브리프를 order_discussion 페이로드에 영속화 → (1) 오프피크 오프라인 리플레이(절제 암 + 기술 사이트 암, 자체 브래킷 손익, 수수료 1.08%, 최대 기여분 제거, 선물/외환 대조군) → (2) 결과가 살아남을 때만 크립토 한정 기술 수정(중립 라벨 + technical 프롬프트 사이트 + 레짐 우선 지시 + momentum-regime-read 스킬) 배포.
- (3) 버킷 게이트 n을 체결 수로 재계산(플래그, 표 공개 후) → 그 다음에야 리플레이스먼트 경로 패리티 → 오토튠 미커밋 예산 캡. 순서는 구속력 있음.
- $0 위생: bracket_infeasible 메모, 후보 수 저널링, 플랫 리콜 lesson-only(스킴 라벨 필수), 절단 finish_reason 기록, 세션 우선 안정 정렬(정확히 4건만 바뀌어야 함).
- agent_memory 패밀리 스코어보드는 항목 2의 7일 윈도우가 닫힌 뒤 플릿별 A/B로만.
- 기각: 달러 수치 스킬, 패널에 제안 노출(리플레이 암으로만), 재계산 전 패리티, 쿨다운 단축, 오픈마켓 캡(소유자 승인 필요), 토큰 캡 인상, ATR 브래킷·$5,200 사이징.
- 모든 항목의 정직한 30일 기대값은 $0. 체결이 생긴 뒤 n과 최대 기여분 제거 수치로 재측정하고, 지표가 움직이지 않으면 같은 용어로 실패로 보고한다.
- 킬 기준: 48h 내 kept-buy(게이트 통과) <5%(n≥40) 또는 첫 30체결 순손익 ≤$0(제거 전후 모두) → 롤백.
- 메모리 갱신: “desk recall covers only holding cycles”는 프로드에서 stale(DESK_RECALL_FLAT 켜짐, 615/616).