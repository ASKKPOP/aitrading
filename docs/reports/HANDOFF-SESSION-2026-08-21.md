# SESSION HANDOFF — Sooppiy automation monitoring (2026-08-18 → 08-21)

**Written because the owner is switching Claude Code accounts.** The session
directory does NOT survive the switch; this file and the two authority
handoffs in this folder are the only durable state. Read this first, then
[HANDOFF-automation-monitoring.md](HANDOFF-automation-monitoring.md)
(authority) and [HANDOFF-n-slot-monitoring.md](HANDOFF-n-slot-monitoring.md).

---

## 1. What this session is

An indefinite 30-minute monitoring loop over prod **sooppiy.com**, plus a
daily 24-hour verification sweep. Purpose is **analysis and improvement of
the live auto-trading fleet — never trading**; every trading decision
belongs to the Sooppiy AI (§7b of the n-slot handoff).

**Targets (both, every cycle):**

| account | user | agent | fleet | scope | notes |
|---|---|---|---|---|---|
| info@askkpop.com | 5 | 6 | **38** | crypto | 7 slots (user-pinned), $10,005 |
| forevery1969@gmail.com | 25 | 60 | **37** | us-stock + forex | **10 slots** (owner resized 08-21), $100,000, EXTREME |

us-stock runs are actively monitored only inside NYSE 13:30–20:00Z.
Fleet 35 was stopped by the owner 08-19; fleet 38 replaced it.

## 2. Binding owner laws (verbatim, non-negotiable)

1. **2026-08-13:** "Do not make excuses, do not delude yourself into thinking
   your analysis is always correct, and do not justify losses with flawed
   logic; instead, always analyze the reasons behind the outcome of every
   trade. The ultimate goal of all analysis is profit or loss; conduct your
   analysis with that in mind."
2. **2026-08-17 (experimental mindset):** "all Analysis thinking about
   experiment ( Must be thinking Experimental mindset ) — also Implement by
   Experimental result." Hypothesis before data; the measurement must be able
   to refute you; implement only on an experimental result; **re-measure the
   same quantity after shipping and report failure in the same terms**.
3. **Two-subagent law:** every cycle with a closed leg dispatches TWO agents
   in parallel — A = AI/desk-authored outcomes, B = algorithm/rail-authored —
   then the main session cross-checks both against law 1. Where they
   disagree, the disagreement is the finding.
4. **Profit is the target.** ±$1 days on $110k are failure, not success.
5. **Reporting:** English first, Korean second. **No form of address in
   either language** (never 사장님/대표님/boss/name).

## 3. State at handoff (anchor 2026-08-21T07:42:09Z prod MySQL)

- **Prod image:** `sooppiy-backend:20260821-rag-flat-on` (a PARALLEL session
  deployed this after my last ship — main-based, my fixes ride along).
- **P&L ledger:** 08-17 +$3.63 · 08-18 −$0.94 · 08-19 −$1.14 · 08-20 −$1.46 ·
  **08-21: no realized row — ZERO trades since 08-20 07:10Z.**
- **Books:** no open positions. Fleet 38 6/7 running, fleet 37 8/10.
- **Rails:** lease fence **0 all-time**; null-size cap **5 fires all-time**;
  0 tracebacks.

## 4. Shipped this session (all live-verified on prod)

| PR | What | Post-ship metric |
|---|---|---|
| #492 (R23) | Outlook sweeper never writes for stopped runs — was burning ~14 LLM calls/h on dead runs (19.8% of all outlook writes) | PASSED, retired to standing |
| #494 | **Fleet profit-goal removed from the UI/API** — profit realization is the AI's decision (owner order). AI setter + supervisor harvest kept; guides updated ×6 langs; fleets 37/38 values cleared to NULL | verified |
| #495 (R26) | Backtest expectancy gate is **long-only** — it may now veto only LONG theses. It had been stripping the most liquid names (LLY 315×, MRK 233×, AAVE 207×, NVDA, AAPL, TSLA…) from fleets whose entries are 87.5% SHORT | **trades/day has NOT moved — reported as not-moved, see §6** |
| #497 (R25) | Fill-mark refresh at the execution boundary + 0.75% entry drift cap. Fixed the stale-fill defect that authored the −$5.44 FIL phantom loss | 3 fills exercised it, all silent-correct, 0 false refusals |
| #498 (R27) | A FLAT run past the house loss floor now sees its carried total BEFORE re-entering ("clean the RUN: retire") — fixes floor-carry churn | 0 renders yet (no past-floor flat run exists — correct) |
| #499, #502 | Docs batches → main → RAG | merged |

Pipeline used for every one: fail-before test → mutation check → ruff +
full suite (4526–4545 passed + 1349 subtests) → CI 5/5 → merge → deploy →
verify ≥3× live → rollback path recorded.

## 5. The owner diagnosis (2026-08-19, "find what is wrong with us")

Two measurement agents (entry funnel + P&L engine). **My own leading
hypothesis was refuted**; record it so nobody re-runs it:

- **REFUTED — "the confidence gates are strangling entries."** Gates in force
  are 0.50–0.57 and killed exactly **2 proposals in 4.8 days**; 55% of holds
  sit at/above their own gate. The desk itself chooses hold.
- **REFUTED — "the expectancy gate is contaminated by R17-era sizing
  losses."** Those stats are a simulated long-only $100k replay, not live
  trades. (The real defect was direction-blindness → R26.)
- **CONFIRMED — the historical loss is one bug, already fixed.** Of −$173.84
  over 8 days, **93.2% came from the default-size class** (worst single trip
  −$71.31 on $9,127 notional). #480/#481 killed it; the cohort is extinct.
- **CONFIRMED — the post-fix engine is weakly positive but microscopic:**
  win rate 53.7%, expectancy **+12.8bp/trade** — statistically UNPROVEN
  (t=0.77, n=41; stripping the largest winner ≈ zero). Median trade **$52**
  on a $110k book; utilization **0.18%**; fees eat 37% of gross; 46% of
  trades are sub-$50 probes. $50/day needs ~350× today's trades×size.
- **CONFIRMED — 72.7% of all desk LLM cycles** were burning in
  build→hold×12→retire loops on candidates never worth entering.

**Actions taken:** R26 + R25 + R27 shipped; owner adopted the 6–8 slot
concentration (fleet 38 → 7). **Untested and named as the next experiment:
whether the 12.8bp edge survives 100×+ sizing.**

## 6. HONEST OPEN VERDICT — read before claiming success

**R26's binding metric (trades/day vs the 8.2/day baseline) has NOT moved —
it fell: ~5 on 08-20, then 0 for 24h.** The gate fix works and slots fill
(both proven), but the desks now see the candidates and decline ~100% on
conviction. The falsification sample says those declines are approximately
right (declined entries ≈ −0.24%/trade gross, below the fee hurdle).
**The binding constraint has migrated to candidate quality — not rails.**
Do not "fix" this by loosening gates or forcing entries; that is the
negative-expectancy garbage the profit law forbids. If the owner wants
throughput, the lever is research depth/coverage.

## 7. Open watches to carry forward

1. **#475 lease fence — must stay 0** (baseline was 8/1/3/9 per day). Any
   fire = FAILED, say so plainly.
2. **#480/#481 null-size cap** — 5 fires; honest ledger: **−$1.13 cost** on
   the 1479 winner vs **≈+$2.15 saved** on losers = net-positive insurance.
   Measure every new fire's save/cost at the live mark once the leg closes.
3. **#473** clamp→next-request pairs — still counting.
4. **R:R ceiling/floor** — count actionable fires by action.
5. **Loss floor #460** — zero ENFORCEMENT fires ever (it is a brief line
   only; that advisory is R27's subject).
6. **R21 CLOSED VALIDATED** (2 live fires, both epoch-baseline exact). New
   dimension: degenerate-scale fires on probe books (arm is fee-anchored at
   0.1%/side vs actual 0.045%; a fire stops the WHOLE run).
7. **R22 STAGED — the ratchet/trail dead zone.** Quantified on LTC 1556: the
   breakeven floor protects **$0.00** of any peak while trail activation sat
   at **$11.21** against a realistic peak of **$2.06** — the unprotected band
   spans the entire excursion range this book can produce, and both post-R21
   fires landed inside it. Needs counterfactual replay before shipping.
8. **OWNER-ORDERED churn/exit-discipline tally** (classify every closed leg):
   **a** noise-churn n=4 (counterfactual ≈ −$5.2…−5.6, sign robust to
   outlier strip) · **b** bank-into-strength n=5 (all green — the validated
   harvest template, incl. run 1462's +$4.32 life) · **c**
   re-entry-vs-own-invalidation n=4 (all losers) · **d** contradiction-
   override n=2 (−$0.41 / +$0.08 — not one-sided) · **e** anchor-echo ·
   **f** narrative-vs-order. **Lesson candidate not yet at decisive weight:
   profit leaks through EXIT-AUTHORSHIP gaps and the R22 dead zone, not
   entry quality.**
9. **SPCX tripwire** — any single-leg loss > $10 → immediate two-agent pass.
10. **R24 STAGED** — the deferred-params branch defeats "AUTHOR IT EVERY
    TIME": 2/2 deferred actionable decisions produced `outcome: absent` →
    cap fired; 3/3 non-deferred authored params. Money-path fix, needs design.
11. **Empty-why authorship watch** — 1462 had 7/17 intents with `why: ""`
    (3 provably `verdict_salvaged` truncations; one executed a trade with no
    stated reason). **Rate has since gone to 0/15 and 0/8 — the R-item stays
    unfired; keep counting.** Related, measured on LTC 1556: the desk's ONLY
    in-position look returned an empty no_verdict while recall had staged the
    harvest lessons — the forfeited bank was +$0.31.
12. **Fleet build behavior** — R20 hot-tech seed guarantees 5 US tech names
    in the candidate universe (working: CRM/ORCL/PYPL/NOW/NFLX/MA all built);
    presence does not compel entries, by design.
13. **R25 forward metric** — `mark_refresh` events (drift ≥0.05% at a fill)
    and `gate_skip stage=mark_drift` refusals now make fill-time mark age
    measurable. Both 0 so far with only 3 fills; needs tape.

## 8. Operating mechanics the next session must re-create

- **Crons are session-only and die with the account.** Re-arm two:
  30-minute cycle `13,43 * * * *`, and the daily 24h sweep (~15:07Z).
  The cycle prompt is reproduced in the cycle notes; the watch list is §7.
- **Every cycle:** anchor `SELECT NOW()` on prod MySQL FIRST; query
  `run_events` by **`ts`** (ISO strings — there is no `created_at`);
  overlap the close-detection window by 2 minutes (seam fix); P&L via
  `docker exec -w /app/service/server sooppiy-worker python -m pnl_audit`.
- **Append the cycle note newest-first** to
  `docs/reports/2026-08-DD-automation-monitoring.md` (roll per UTC day),
  refresh `automation-snapshot.json`, commit. **Batch docs to main via a
  clean worktree off origin/main** — a local commit reaches no RAG.
- **Access:** `ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem
  ec2-user@52.9.147.202`; MySQL `docker exec noesis-mysql mysql -uroot
  -p"$(docker exec noesis-mysql printenv MYSQL_ROOT_PASSWORD)" sooppiy`.
  **Never put the password in the repo** (gitleaks scans).

## 9. Traps that cost time this session

- **A displaced cron can fire a duplicate sweep** — check the last sweep's
  anchor before re-running a full one.
- **In-image pytest is unavailable** on recent image variants — verify
  shipped code with an in-container `grep` plus local/CI suites instead.
  (Older images also need `-e ENTITLEMENTS_ENFORCED=false` for tests.)
- **A test subclass inherits its parent's tests** — a new env-forced class
  re-ran the whole parent suite under the wrong conditions (36 red). Borrow
  helpers explicitly instead.
- **Draft 1 of R25 refetched unconditionally** and broke 36 mocked-entry
  tests; the cycle-age gate is both greener and more correct.
- `trading_runs` has **no** `max_bet_usd`/`config_json` columns — read
  `config_snapshot_json` (and note it STRIPS `thesis.factor_scores_json`).
- Post-stop `outlook` rows with `source:"cycle"` are a benign in-flight
  race, NOT an R23 regression — check `source` and the 30–40s gap.
- Parallel sessions deploy to the same prod box; always re-read the running
  image rather than assuming your own tag is live.

## 10. If the next session wants the highest-value next move

In order of expected profit impact, all measurement-first:

1. **Re-measure the sizing experiment** once tape exists — does +12.8bp
   survive at the concentrated 7-slot size? (n was 3 legs at handoff.)
2. **R22** — the ratchet/trail dead zone is the largest quantified leak
   (a $1.74 achievable peak protected at $0.00). Counterfactual replay
   across historical fires/non-fires, then ship.
3. **Candidate quality**, per §6 — the funnel's last binding constraint.
4. **R24** — deferred-params → absent-size, if the cap ledger turns negative.
