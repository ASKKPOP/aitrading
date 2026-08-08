# Plan 22 — Desk retrieval (RAG) for the decision prompt

Owner ask, 2026-08-06: *"make RAG daemon or any mechanism for: Improve the
Retrieval (Find Better Data), Optimize the Data Structure (Better Chunking),
Polish the Query and Prompt (Better Communication)"*.

## 1. The measured problem

`skills_for_prompt()` does **no retrieval**. It filters by prompt site and
market, sorts by a fixed priority, and truncates at `MAX_BLOCK_LEN`:

```python
for skill in all_skills():
    if not skill["enabled"] or site not in skill["prompts"]: continue
    if skill["markets"] and market not in skill["markets"]: continue
    out.append(skill)
```

Consequences we can measure today:

| fact | value |
|---|---|
| `trader/us-stock` block size | **33,994 / 34,000 chars** |
| headroom after the profit mandate (#269) | **6 chars** |
| times `MAX_BLOCK_LEN` has been raised | 4 |
| situational variation in what the desk is sent | **none** |

The block is a fixed wall of doctrine. A run that is flat and considering an
entry receives the identical text as a run sitting on a −0.9 loser. The budget
is spent on doctrine that does not apply, and the *situation-specific* data
that actually determines the decision competes with it for room.

## 2. Sequencing — the non-obvious part

The instinct is to build the learning daemon first. That cannot work, and the
reason is worth stating plainly:

> **Every skill is in every prompt today, so there is zero variance to learn
> from.** An attribution model over `run_events` would find that every skill
> was present at every good decision *and* every bad one. Attribution is
> unidentifiable until retrieval starts varying what is included.

So the order is forced: **chunk → retrieve → then the daemon can learn.**

## 3. Phase 1 — chunking (better data structure)

Skills today are monolithic. `Risk/Reward Structure` is one ~1,200-char blob
mixing stop placement, target placement, and rejection rules — three separate
claims that apply in three different situations.

Split `BASE_SKILLS` bodies into **atomic lessons**: one claim, one situation,
one piece of evidence. Retrieval can then pick the paragraph rather than the
whole skill.

Immediate benefit independent of retrieval: the capacity crisis eases, because
including 3 relevant lessons costs less than 1 whole skill.

**Risk to guard:** an atomised lesson loses the context that made it true. Each
lesson must carry its own evidence clause (the house style already does this —
*"of 60+ arms only TWO have ever fired"*), or it degrades into a slogan.

## 4. Phase 2 — retrieval (find better data)

Give each lesson `applies_when` tags and score against the live decision
context, which the engine already computes:

| signal | already available |
|---|---|
| flat vs holding | `pos_qty` |
| winning vs losing | run P&L vs peak (`_floor_status_line`) |
| distance to the equity rail | `_loss_verdict_line` |
| mark freshness | `_mark_freshness_line` |
| standing arm present | `_standing_arm_line` |
| regime / breadth | breadth + regime briefs |

Include top-K by relevance instead of everything by priority. The mandate
header stays unconditional — it is the one text that applies to every decision.

## 5. Phase 3 — the daemon (learn the weights)

Offline evaluator over `run_events`:

1. For each `decision` event, record which lessons were in context.
2. Join to the outcome — the subsequent `trade`, the realized close, whether a
   gain was banked or round-tripped.
3. Produce per-lesson, per-situation weights: which lessons correlate with
   **realized** profit, not with activity.
4. Feed the weights back as retrieval scores.

**Honest limits, stated up front:**

- **Correlation, not cause.** A lesson present at good decisions may be a
  passenger. Treat weights as a ranking prior, never as evidence a lesson works.
- **Sample size.** History was cleared 2026-08-06 and 6 runs are live. Useful
  weights are weeks away, not days.
- **Survivorship.** Losing runs get retired, so their decisions are
  under-represented unless the join is done on all closes including forced
  flattens — and `adapt realized` is known to omit `run:N:flatten` closes
  (see memory `realized-pnl-misses-forced-flattens`). **Fix that first or the
  daemon learns from a book that hides its worst days.**

## 6. Where this does and does not help

Mapping the standard claims onto what this platform actually does:

| claim | true here? |
|---|---|
| Processes vast data instantly | **No.** The desk sees a small brief. Retrieval is about sending the *right* small brief, not more data. |
| Removes human emotion | **Partly.** We measured full-book dumps on sub-2% moves — behaviourally identical to panic. |
| Executes split-second trades | **No.** Cycles are 30 min. The `arm` intent is the only sub-cycle execution path. |
| Backtests instantly | **Yes** — the Phase-4 replay gate. |

| risk | status here |
|---|---|
| Overfitting past data | **Live risk.** Skills are written from measured episodes; that *is* fitting to the past. The daemon amplifies it. Mitigation: every lesson keeps its evidence clause so a future session can re-test it. |
| Systemic tech failure | **Already happened** — the frozen Yahoo feed, 8h of stale marks. |
| High development cost | The 30-min cap raises LLM spend; `stable`-tier runs would go from 240m to 30m (8×). `RUN_INTERVAL_CAP_MIN` is the escape hatch. |
| Black-swan vulnerability | The equity rail and the −0.99 floor rule are the defense; neither is a guarantee. |

## 7. Status

- Phase 0 (this document) — done.
- Phase 1 (chunking) — next.

## 8. External design references (2026-08-07)

`tradermonty/claude-trading-skills` (MIT) — the repo the catalogue has mined
four times — contains a *manual* version of exactly the loop this plan
automates. Worth reading when building Phases 1–3; none of it ports as code:

- **`trader-memory-core`** — a thesis's full lifecycle (screening idea →
  active → closed → postmortem) as first-class state, with review due-dates
  and MAE/MFE attached at close. Our `desk_memory` rows are flat findings;
  the lifecycle framing is the chunking model Phase 1 wants: a chunk is a
  *thesis episode with an outcome*, not a paragraph.
- **`signal-postmortem`** — every closed signal is scored false-positive /
  missed / regime-mismatch, and the verdicts feed aggregator *weights*, not
  prose. That is Phase 3's daemon in manual form: outcomes adjust retrieval
  weight per situation class.
- **`edge-signal-aggregator` → `edge-strategy-reviewer` pipeline** — signals
  carry per-source reliability weights that decay when postmortems go
  against them. The decay rule (weights fall on evidence, never on opinion)
  is the guard Phase 3 needs against the overfitting risk in §6.

Two adjacent ideas parked here so they are not rediscovered:

- **13F / theme / sector trackers** (`institutional-flow-tracker`,
  `theme-detector`, `sector-analyst`) are data feeds, not judgment — if ever
  wanted they follow the psych/regime daemon pattern into a desk brief, not
  the skills registry.
- **`residual-edge-analyzer`** — OLS attribution separating a return series
  into baseline exposure vs. residual edge. A future `backtest_gate.py`
  quality gate ("is this thesis's replay P&L just beta?"), not a prompt
  skill.
