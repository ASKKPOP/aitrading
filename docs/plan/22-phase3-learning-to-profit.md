# Plan 22 · Phase 3 deep analysis — from retrieval variance to attributed profit

Companion to [22-desk-retrieval-rag.md](22-desk-retrieval-rag.md). That
document is the ledger; this one is the full analysis the owner asked for on
2026-08-09: *"target: make automated learning implemented so it makes plus
profit."* Everything here is measured against that target — not "does the
daemon learn," but "does what it learns show up in NET realized P&L."

All prod numbers in this document were measured 2026-08-09 23:33Z unless
dated otherwise.

## 1. What is actually live, and what is actually frozen

| component | state | evidence |
|---|---|---|
| Corpus (`desk_memory`) | LIVE, growing | 1,216 chunks: 614 decision / 562 monitoring / 40 outcome / 0 lesson |
| Recall into the prompt (`_recall_line`) | LIVE | 109 `recall` events, 14 runs, 08-08 21:35Z → 08-09 23:33Z (≈4.2/h) |
| Recall journaling (increment a) | LIVE | every event carries query + chunk SHAs + scores |
| Retrieval variance | **ZERO** | 5 queries → 5 fixed chunk-pairs, deterministic (ledger 08-09) |
| Monitoring pool (what recall reads) | **FROZEN at 562** | only moves when `docs/reports` markdown is deployed |
| `lesson` kind | defined, **never written** | 0 rows |
| Skills block (`skills_block`) | **NO retrieval at all** | every enabled skill in every prompt, `MAX_BLOCK_LEN` 48,000 |

Two of these rows carry the whole analysis, so they are worth stating as
findings rather than status:

**Finding 1 — the learning loop under construction covers the smallest
channel of the prompt.** The decision prompt has three doctrine-bearing
channels: the mandate header (unconditional, ~small), the skills wall (up to
48,000 chars, 36 skills, all of them, every cycle), and the recall line
(≤2 chunks × 700 chars ≈ 1,400 chars). Phase 3 as currently laddered —
journal → attribution → weights → weighted retrieval — operates **only on the
recall line**, roughly **3% of the doctrine text** the desk reads. The
per-decision causal effect of swapping 2 recall chunks is bounded by how much
those 1,400 chars can move a decision that also just read 48,000 chars of
fixed doctrine. That bound works in both directions (§5): it makes
exploration cheap, and it makes the learnable profit small.

**Finding 2 — Plan 22 Phase 1 was implemented as a different thing than
designed, and the original zero-variance problem is still unsolved.** Phase 1
as written in §3 of the plan was "split `BASE_SKILLS` bodies into atomic
lessons." What shipped as "Phase 1 LIVE" is `desk_memory` — a corpus of
monitoring/decision/outcome chunks. Valuable, but different: the skills wall
itself was never atomised, still goes into every prompt whole, and its cap
was raised to 48,000 (#334, #287) instead. The sentence that justified the
whole plan — *"every skill is in every prompt, so there is zero variance to
learn from"* — is still true today for 97% of the doctrine. The daemon being
built cannot learn anything about the skills, because the skills never vary.

## 2. The causal model — what "learn" can mean here

The unit the daemon wants to estimate is:

> effect of chunk *c* being in context, in situation class *s*, on the
> outcome of the decision that read it.

The causal chain has two links, and they have wildly different
signal-to-noise:

```
chunk in context ──(1)──▶ desk behavior ──(2)──▶ realized P&L
```

- Link (1) — did the lesson change what the desk *did*: reduce instead of
  full-book dump, arm a level after giving back peak, decline a fee-hurdle
  entry, hold instead of add into a loser. Binary-ish, observable within one
  or two cycles, moderate base rates. **Learnable at our volume (§5).**
- Link (2) — did the behavior make money. Per-close P&L is heavy-tailed: the
  measured book had 6 of 84 closes carrying 74% of all loss
  (memory `losses-are-full-book-dumps-not-bad-timing`). Mean effects drown
  in tail variance. **Not learnable per-chunk at our volume (§5).**

The literature name for resolving this is the surrogate/credit-assignment
split: when the terminal reward is sparse, delayed and noisy, attribute to
intermediate outcomes that are themselves validated against the terminal
reward — see step-level credit assignment for LLM agents ([survey and
taxonomy](https://github.com/xxzcc/Awesome-Credit-Assignment-in-LLM-RL),
[consistency-guided credit assignment](https://arxiv.org/html/2605.20061v1)).
We are in the lucky position that link (2) has **already been measured in
bulk** by the loss-shape audits: full-book dumps on sub-2% moves are proven
expensive; banked-then-round-tripped peaks are proven expensive; adds into
losers are proven expensive. So:

> **The daemon's reward signal must be behavior surrogates, each one
> pre-validated by an existing loss-shape audit — never raw per-decision
> P&L.** A chunk earns or loses weight for changing behavior the book has
> already priced; P&L enters only at the promotion gate (§7), where it is
> evaluated at portfolio level, not per-chunk.

Concretely, all computable today from `run_events` + `trading_runs` (with the
`run:N:flatten` closes included via the `pnl_audit` ledger replay — the §5
trap in the main plan stands):

| surrogate | definition (per decision, in class) | validated by |
|---|---|---|
| dump vs reduce | close ≥90% of book in one leg on <2% adverse move | #245 audit: 74% of loss |
| round-trip | peak_pnl > fee hurdle at decision, later realized ≤ 0 | give-back audits |
| add-into-loser | add while unrealized < 0 | run_feedback rails, #79 |
| fee-hurdle discipline | entry with expected move < fee hurdle | #94 dead-capital audit |
| arm usage | standing arm placed after give-back flag | #244/#249 rail-vs-desk |

## 3. Why (a2) exploration must log more than the draw

The ledger's (a2) — epsilon-sample below the head, default-off — creates
variance. It does not yet create an *evaluable* dataset. Three requirements,
from the off-policy-evaluation literature
([practical guide to OPE](https://arxiv.org/abs/2010.12470),
[OPE tutorial](https://towardsdatascience.com/a-complete-tutorial-on-off-policy-evaluation-for-recommender-systems-e92085018afe/)),
each cheap now and impossible to retrofit:

1. **Log the propensity, not just the choice.** Every `recall` event must
   record the probability the emitted chunk-set had under the sampling
   scheme (and the scheme version). Without it, none of the standard
   estimators (IPS/SNIPS, doubly-robust) can be computed, and (c)'s shadow
   scores plus (d)'s promotion case degrade to eyeballing. IPS is exactly
   the tool for "we chose with known randomness, what would another ranking
   have earned" — and it is also
   [notoriously high-variance](https://arxiv.org/pdf/2308.03443) when
   propensities get small, which fixes the design: **few arms, fat epsilon,
   never a long tail of rarely-sampled options.** Sample uniformly from a
   small candidate set (top-5 above floor), ε in 0.2–0.3, so min propensity
   stays ≥ ~0.05 and importance weights stay bounded.
2. **Relevance floor.** Sample only among chunks above a score floor.
   Exploration exists to compare *plausible* lessons, not to inject noise
   for variance's sake — a drawn chunk with near-zero BM25 score costs
   prompt budget and desk attention and can never win weight honestly.
   Corollary: for a class whose above-floor pool holds ≤2 chunks,
   exploration is vacuous — and at 562 frozen monitoring chunks that is likely
   for several classes. Pool enrichment (§4) is therefore not an
   optimization; for those classes it is the *precondition* of learning.
3. **Class-scoped safety asymmetry.** Exploration on the "losing position"
   classes swaps the advice a run reads while it is losing. The deterministic
   rails (adapt ladder, equity rail, −0.99 floor) bound the damage, and
   recall is advisory prose — but the mandate's own asymmetry (weights fall
   on evidence; never loosen a rail) suggests the same shape here: **start ε
   on the flat/winning classes, extend to losing classes after the first
   promotion gate passes.** [Safe-exploration bandit
   work](https://arxiv.org/pdf/2002.00467) formalizes the same instinct:
   bound the regret of exploration against the incumbent policy.

## 4. Pool economics — the corpus must grow on the retrieval side

Recall reads `kind="monitoring"` only: 562 chunks, frozen since 08-08,
because monitoring chunks come from deployed `docs/reports` markdown and
nothing else. Meanwhile the corpus's growth is all in `decision` (614) and
`outcome` (40) — which recall never reads — and `lesson` sits at zero.

The enrichment ladder, cheapest first:

- **(i) Write `lesson` chunks from the skills catalogue.** This is the
  original Phase 1, finally done — but into `desk_memory` rather than a new
  registry: split each of the 36 skills' bodies into atomic claims (one
  claim, one situation, one evidence clause), stored as `kind="lesson"`
  with `applies_when`-style tags. ~36 skills → est. 120–180 lessons. No
  prompt change yet; this only populates the pool.
- **(ii) Let recall read `lesson` and `outcome` kinds** behind the same
  explore flag. Outcome chunks are the desk's own closed-run postmortems —
  exactly the *"when you last reasoned like this, what happened"* material
  the corpus was built for, and currently write-only.
- **(iii) Auto-mine lessons from closed runs.** A postmortem job (rides the
  existing daily cadence) converts each closed run's decision+outcome pair
  into a *candidate* lesson: claim, situation tags, evidence clause with
  run id and numbers. **This is the step where the system begins writing
  its own knowledge** — the "expand algorithms on its own" capability the
  owner is asking about — and it is exactly where the echo-chamber risk
  lives, so: candidates land **quarantined** (a `candidate` tag recall's
  floor excludes). A candidate becomes retrievable only when (b)'s
  attribution can score it or a replay-gate check passes it. An
  auto-written slogan must never teach the desk by default.

## 5. The statistics, honestly — what our volume can and cannot identify

Current recall volume: 109 events / 25.9h ≈ **101/day**, spread over ~4–8
(market × situation-class) cells → **~15–25 events/day per active cell**,
split again across arms once exploration runs.

**Behavior surrogates (link 1): feasible in weeks.** Two-proportion test,
80% power, α=0.05: detecting a dump-rate shift of 30%→15% needs ≈ 120–150
decisions per arm. At ~20/day in a cell with ε=0.25 (≈5 explored + 15
incumbent per day), the first per-cell verdicts on the *incumbent vs pooled
alternatives* contrast land in **3–6 weeks**; per-chunk verdicts on the top
2–3 candidates in **1–2 months**. Slow, but real — and every widening of
the funnel (more runs, more markets live, recall reading more kinds)
shortens it linearly.

**Direct per-chunk P&L (link 2): out of reach, and the ladder should say
so.** With per-close P&L where 7% of closes carry 74% of loss, the
per-decision σ is a large multiple of any plausible per-chunk mean effect δ
— and the effect itself is diluted by Finding 1 (2 chunks against a 48k
wall). At σ/δ ≥ 10 the two-sample requirement is n ≈ 16(σ/δ)² ≥ 1,600 per
arm **per cell** — years at current volume. Any (c) that ranks chunks by
mean attached P&L will be ranking noise, with the survivorship and
tail-sensitivity failure modes on top. This is not a reason to skip P&L —
it is the reason P&L enters at the **portfolio level, at the promotion
gate**, where one number (treatment-runs NET realized vs control-runs, plus
replay non-inferiority) is estimated instead of hundreds.

## 6. The learning rule (c) — pruning before ranking

Given §5, the shadow score design:

- **Estimator:** per (class, chunk): SNIPS estimate of each behavior
  surrogate under "always include c" vs "never include c", from the
  propensity-logged journal; empirical-Bayes shrinkage toward weight 1.0
  (prior = incumbent), so early noise cannot move rankings; a discounted
  window (or sliding window) for regime non-stationarity.
- **Asymmetry, by design:** weights may only **fall** on evidence
  (tradermonty's `edge-signal-aggregator` decay rule, §8 of the main plan;
  it is also the same monotone-tightening shape as `run_feedback`).
  Statistically this converts the problem from "rank ~600 chunks" to
  "identify the few demonstrably harmful or passenger chunks" — far fewer
  hypotheses, honest at small n, and it caps the damage of a wrong verdict
  at "a useful chunk is shown less," never "a harmful chunk is promoted."
- **Journal-only until (d):** scores are computed by the offline daily job,
  written as telemetry, read by nobody on the trading path.

## 7. Promotion gate for (d) — pre-registered, or it will be argued from vibes

Weighted retrieval turns on for a **canary subset of runs** (treatment vs
control at run level — cleaner inference than within-run switching) only
when ALL of:

1. Shadow OPE shows surrogate improvement with a CI excluding zero for at
   least one pre-validated surrogate, and degradation for none.
2. Replay gate (Phase-4 backtest) shows P&L non-inferiority of the weighted
   policy on the same episodes.
3. Zero increase in the critical behaviors (dump rate, add-into-loser) in
   the explored arms during the observation window.
4. Kill-switch: one env flag back to deterministic top-K; weights are data,
   not code, so rollback is instant.

And the promotion verdict itself is measured on **NET realized P&L of
treatment vs control runs** over a pre-stated window — the only place raw
P&L has the power to speak (§5).

## 8. The profit ledger — where "plus profit" actually comes from

Decomposed per the mandate (deterministic first, speculative last):

1. **Deterministic — prompt-budget cost.** The skills wall alone is up to
   48,000 chars ≈ ~12k tokens *per decision prompt*, sent on every trading
   cycle of every run, forever. Atomised, situational top-K doctrine (§9)
   cuts that by 60–80% — a guaranteed, compounding reduction in LLM spend,
   which is NET P&L by definition. Nothing else in this plan is guaranteed;
   this is.
2. **Deterministic — headroom.** The cap has been raised 4× and at one point
   had 6 chars of headroom; #287 showed the cap itself costing a lesson.
   Retrieval ends the recurring "raise the cap" tax and the silent skips.
3. **Behavioral — the measured loss shapes.** 74% of loss came from one
   behavior class. Lessons that demonstrably reduce that behavior (link 1)
   attack the largest measured leak in the book. This is where learned
   weights earn their keep — not by finding alpha, but by making the desk
   *reliably* apply the doctrine that already exists, in the situations
   where it applies.
4. **Speculative — retrieval alpha.** Ranking 2 recall chunks better is
   unlikely to create new alpha, and this document deliberately does not
   claim it will. If the machinery ever produces measurable positive P&L at
   the promotion gate beyond cost savings and loss-shape reduction, that is
   upside, not the plan.

## 9. The real lever — Phase 4, skills-wall retrieval

Once (a2)→(d) machinery is proven on the recall channel — which is the
right testbed *because* its blast radius is 1,400 chars — the identical
machinery applies to the channel that matters:

- Atomise the 36 skills into `lesson` chunks (§4-i) — done as pool work
  before this phase starts.
- Replace "every skill, priority order, 48k cap" with: mandate header
  (unconditional) + situational top-K lessons + ε-exploration with logged
  propensities, behind a default-off flag, canaried and promotion-gated
  exactly as §7.
- Effect sizes at this level are large (it is most of what the desk reads),
  the deterministic cost win lands on day one, and the variance the daemon
  needs finally exists at the doctrine level — Finding 2 closes.

This — not the recall line — is where "automated learning" and "plus
profit" become the same sentence.

## 10. Revised increment ladder

Superset of the ledger's (a2)→(d), gates pre-registered:

| step | what ships | gate to proceed |
|---|---|---|
| a2 | ε-exploration on recall, **with propensity + scheme-version logging and relevance floor**, flat/winning classes first, default-off | flag on after in-container verification; losing classes after first §7 pass |
| a3 | pool enrichment: skills→`lesson` chunks; recall reads lesson+outcome kinds under the explore flag | ≥3 above-floor chunks per active class |
| b | attribution dataset: journal ⨝ surrogates ⨝ pnl_audit-replayed closes (flattens included) | the variance gate as corrected 08-09 |
| c | shadow per-chunk scores: SNIPS on surrogates, shrinkage, decay-only, journal-only | ≥120 events/arm on some (class, surrogate) |
| d | weighted retrieval, canary treatment/control runs, default-off | ALL of §7 |
| e | skills-wall atomised retrieval (Phase 4) | (d) promoted and stable; deterministic cost win measured |
| f | auto-mined candidate lessons, quarantined until scored | (b) live; quarantine enforced by retrieval floor |

Step f is the honest boundary of autonomy: after it, the system writes its
own lessons, weighs them by its own measured outcomes, and retires them on
its own evidence — while gates, sizing, risk rails and the mandate remain
code the daemon cannot touch. That is "learn, grow, and expand on its own,"
delivered inside the only safety envelope this platform trusts:
monotone-tightening, flag-gated, journal-first, promoted on NET realized
P&L or not at all.

## Sources

Internal: [Plan 22](22-desk-retrieval-rag.md) (incl. 08-09 identifiability
measurement), `desk_memory.py`, `desk_memory_ingest.py`,
`run_engine._recall_*`, `trading_skills.py`, prod MySQL (2026-08-09 23:33Z),
memories `losses-are-full-book-dumps-not-bad-timing`,
`realized-pnl-misses-forced-flattens`, `profit-is-the-target-every-layer`.

External:
[A Practical Guide of Off-Policy Evaluation for Bandit Problems](https://arxiv.org/abs/2010.12470) ·
[OPE for recommender systems — tutorial](https://towardsdatascience.com/a-complete-tutorial-on-off-policy-evaluation-for-recommender-systems-e92085018afe/) ·
[Doubly-robust OPE under large action spaces](https://arxiv.org/pdf/2308.03443) ·
[Safe exploration for contextual bandits](https://arxiv.org/pdf/2002.00467) ·
[Logging-policy design for OPE](https://arxiv.org/html/2605.15108) ·
[Credit assignment in agentic LLM RL — curated taxonomy](https://github.com/xxzcc/Awesome-Credit-Assignment-in-LLM-RL) ·
[Consistency-guided credit assignment for long-horizon agents](https://arxiv.org/html/2605.20061v1)
