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

This section is the LEDGER for the once-daily Phase 3 build cadence (below).
Every increment lands here as a dated line, in the same PR that ships it.

- Phase 0 (this document) — done.
- Phase 1 (chunking) — **LIVE** (`desk_memory.py` + `desk_memory_ingest.py`,
  alembic 0046; ingest rides the trading tick). Prod health 2026-08-08: 1,023
  chunks (437 decision / 562 monitoring / 24 outcome), 50 written in 6h, zero
  ingest failures. The `lesson` kind is defined but unwritten.
- Phase 2 (retrieval) — **LIVE** (`run_engine._recall_line`, situation-keyed
  query, kind=monitoring only, `DESK_RECALL_ENABLED` default on). Verified
  in-container 2026-08-08: flat and losing situations both recall relevant
  past findings on a live run. Known debts: decision/outcome chunks are
  write-only today (by design — Phase 3's training data); chunk hygiene
  carries markdown-table debris into recall bodies.
- Phase 3 (learn the weights) — **IN PROGRESS via a once-daily build
  cadence** (owner-directed 2026-08-08: one increment per day, shipped to
  prod). Increment ladder: (a) journal which chunk SHAs each decision's
  recall injected → (b) attribution dataset joining recalls to outcomes →
  (c) shadow per-chunk usefulness scores, journal-only → (d) weighted
  retrieval behind a default-off flag, promoted only on measured evidence.
  The sequencing rule in §2 stays binding: never build ahead of the
  variance data.
  - **Standing schedule (re-arm after account rotation):** a local Claude
    Code scheduled task `rag-phase3-daily-increment` fires daily at 14:00
    America/Los_Angeles (21:00 UTC) on the dev machine. The Claude side is
    lost on account rotation (~3 days) — any session that finds the task
    missing (`~/.claude/scheduled-tasks/rag-phase3-daily-increment/`)
    re-creates it: one increment from the ladder above per day, fresh
    worktree, TDD, PR → CI → merge → `scripts/deploy.sh` → prod
    verification ×2, and a dated line added HERE.
  - **2026-08-08 — increment (a) SHIPPED: recall journaling.** Every cycle
    that builds a position brief now emits a `recall` telemetry event beside
    its `decision` event, carrying the retrieval query and the chunk
    identities (`sha`, `kind`, `source`, `score`) the brief actually
    injected. `run_engine._recall_capture` records inside `_recall_line`,
    `_recall_reset(run_id)` clears at the top of `run_cycle`, and
    `_take_recall_journal(run_id)` pops at the decision emit.
    - Two distinctions are load-bearing for (b): a cycle that never recalled
      emits **no `recall` row at all** (a flat run has no position brief),
      while a cycle that recalled and the corpus returned nothing emits a row
      with `chunks: []` — that second case is the **control group** the
      attribution needs, and collapsing the two would make the dataset
      unreadable.
    - Popping rather than reading is deliberate: a cycle that recalls but
      never reaches a decision (a gate skip) must not have its chunks
      attributed to the NEXT decision. Reset-before-brief covers the mirror
      case.
    - Fail-soft at both levels — the capture swallows its own errors AND its
      call site is guarded, because an exception reaching `_recall_line`'s
      outer handler would silently strip the desk's recall (a degradation,
      not the no-op fail-soft requires). Pinned by
      `test_journaling_off_keeps_the_recall_line`.
    - No behavior change: no prompt, gate, size or order reads the journal.
      No new flag — the event rides `DESK_RECALL_ENABLED`, since journaling
      what recall injected is meaningless when recall is off.
    - Tests: `RecallJournalTests` in `tests/test_run_engine.py` (7), incl. a
      wiring test on `run_cycle`'s source — per the standing trap that brief
      lines are tested for rendering and never for being *called*.
    - **Next: increment (b)**, the attribution dataset, but only once the
      `recall` rows have accumulated. Threshold to proceed, recorded here so
      it is not argued from vibes: **≥200 `recall` events across ≥20 closed
      runs**, with at least two distinct chunk shas appearing in ≥20 events
      each — below that there is no retrieval VARIANCE to attribute, and §2's
      sequencing rule forbids building on it.
      **↑ SUPERSEDED 2026-08-09 — this was a VOLUME gate for a VARIANCE
      question, and it would have opened on a dataset that cannot answer it.
      See the next entry.**
  - **2026-08-09 — increment: analysis only. The (b) gate above is wrong,
    and (a2) is inserted before (b).** No code shipped; the finding is the
    increment. Measured on prod at 22:20Z, first full day of (a) journaling
    (101 `recall` events, 11 runs, window 08-08 21:35Z → 08-09 22:17Z):

    | measure | value | yesterday's gate |
    |---|---|---|
    | `recall` events | 101 | ≥200 — not met |
    | distinct runs (all closed) | 11 | ≥20 — not met |
    | shas appearing in ≥20 events | **4** (54/47/47/46) | ≥2 — **met** |
    | distinct chunk shas, all time | **5** | — |
    | distinct queries | **5** | — |
    | **distinct chunk-pairs per query** | **1, for every query** | — |
    | rows with `chunks: []` (the control group) | **0** | — |

    - **Retrieval is a deterministic function of the query string.** Every
      one of the 5 queries returned the same pair of shas on every one of its
      101 firings, across 11 runs and 25 hours; scores moved for one query
      and the ranking still did not. So the per-chunk usefulness score (b)
      would compute is **perfectly collinear with the situation class that
      retrieved it** — "chunk `a5c29c` is bad" and "crypto losing positions
      lose" are the same number wearing two labels. That is not a weak
      dataset, it is an **unidentifiable** one.
    - **Volume cannot fix it, and the old gate would have opened anyway.**
      At 4.1 events/h the 200-event leg lands ~08-10 21Z and the sha leg is
      already met — two of three conditions green on a dataset with zero
      within-class variance. §2's sequencing rule was right; the number
      chosen to enforce it measured the wrong quantity.
    - **Why it is structural, not "not yet".** Three multipliers are each
      pinned to one: (1) `_recall_query` is a pure function of `market` ×
      holding × gave-back-peak × winning/losing — ~4 reachable classes per
      market, all crypto ones already seen; (2) `search()` is a
      deterministic scorer over a **frozen pool** — retrieval reads
      `kind="monitoring"` only, and monitoring chunks sit at **562, exactly
      where they were on 08-08**, while the corpus grew 1,023 → 1,197 (all
      of it `decision`/`outcome`, which recall never reads). Monitoring
      chunks come from `ingest_reports(docs/reports)`, so the retrievable
      pool only moves when a monitoring session's markdown is **deployed**;
      (3) `limit=_RECALL_MAX` = 2, always filled — hence zero control rows.
      Constant query space × constant pool × constant top-2 = constant
      output. Waiting changes none of the three.
    - **Therefore (a2) is inserted before (b): make retrieval stochastic
      behind a default-off flag.** The minimum that creates within-class
      variance is an epsilon draw from the top-k pool instead of a fixed
      top-2 (e.g. `DESK_RECALL_EXPLORE`, default **off**, sampling below the
      head some fraction of the time), with the journal already recording
      what was drawn. This is the `edge-signal-aggregator` decay loop in §8
      run forward: weights may only fall on evidence, and evidence requires
      a counterfactual. It is a behaviour change on the trading path, so it
      ships default-off and is promoted only on measured evidence — same
      bar as (d).
    - **Corrected gate for (b)** — a VARIANCE gate, replacing the volume
      one: **≥3 distinct chunk-pairs observed for each of ≥2 situation
      classes, with ≥30 events per class**, and ≥20 closed runs. Until
      exploration is live and on, that gate cannot be met by waiting — which
      is the point of stating it this way.
    - Also recorded, since (b) will need it: `desk_memory` holds **39**
      `outcome` chunks (24 on 08-08), and all 11 journalled runs are closed,
      so the right-hand side of the join exists and is growing. The left
      side is what is degenerate.
    - **Same-day follow-up: the 562 is no longer frozen, deliberately.** A
      second PR that evening (owner-ordered hygiene, not a ladder increment)
      added a trap section to `HANDOFF-automation-monitoring.md`, which lives
      under `docs/reports` — the ingest root. So `kind=monitoring` moves off
      562 on that deploy. **This does not weaken the finding above:** the
      frozen pool is one of three multipliers, and the other two (a query
      space that is a pure function of ~4 situation classes, and an always-
      filled top-2) are untouched. A pool that grows by a handful of chunks
      per deploy also cannot manufacture *within-class* variance — it can
      only, rarely, swap one incumbent for another, which is exactly the
      slow confounded-with-time drift §2 forbids learning from. Retrieval
      output was re-checked after that deploy and the pairs were unchanged.
      Recorded here so a later session does not read a moved count as this
      entry being wrong.
  - **2026-08-10 — increment (a2) SHIPPED: ε-exploration with logged
    propensities, default-off.** Retrieval can now differ from its own
    ranking, and every `recall` row records the policy that produced it.
    `run_engine._recall_select(hits, explore)` chooses what the brief
    carries; `DESK_RECALL_EXPLORE` (default **off**) and
    `_recall_explore_allowed` gate it.
    - **First, the 08-09 finding re-measured at scale — it held exactly.**
      262 `recall` events (was 101), 14 (market × situation) cells, and
      `COUNT(DISTINCT sha)` = **1 for both slots in every one of the 14
      cells**. A day of extra volume produced zero extra variance, which is
      what "unidentifiable, not weak" predicted.
    - **Scheme `eps-head-fixed-v1`.** The rank-1 chunk is never displaced;
      with ε=0.25 the SECOND slot is drawn uniformly from the above-floor
      candidates ranked below the incumbent pair (search widens to 5 only
      when exploring). Consequences, all deliberate:
      - min propensity = ε/|alts| ≈ **0.083** on the measured pools. IPS
        blows up on small propensities, so the design is few arms and a fat
        ε — never a long tail of rarely-drawn options.
      - the head is common to every arm, so **the head chunk is not
        scoreable under v1**. That is the price of bounding exploration to
        one slot, and it is exactly why the scheme VERSION is journaled: a
        later v2 that also drops the head is a *different dataset*, not more
        of this one.
      - up to **1 + |alts| distinct pairs per class**; measured pools give
        3–4, so the corrected variance gate for (b) becomes reachable.
    - **The relevance floor is a FRACTION OF THE HEAD (0.60), not an
      absolute score** — and the measurement is why. Retrieval scores for
      the four live classes, probed in-container 2026-08-10:

      | class | r1 | r2 | r3 | r4 | r5 |
      |---|---|---|---|---|---|
      | gave-back + losing | 26.83 | 20.99 | 18.78 | 18.24 | 18.06 |
      | gave-back + winning | 30.27 | 22.48 | 21.97 | 21.19 | 18.57 |
      | losing | 11.92 | 10.97 | 10.02 | 9.90 | 9.80 |
      | winning | 15.03 | 14.34 | 11.18 | 9.93 | 8.94 |

      Scales differ 2–3× across classes: the gave-back class's **eighth**
      chunk (17.2) outscores the winning class's **first** (15.0). One
      absolute floor would mean two different things in two situations —
      admitting near-duplicates in one class while starving another.
    - **Losing classes are excluded** (`_recall_explore_allowed`): the
      mandate's asymmetry — never loosen an unproven thing on the losing
      side — applies to advice as much as to rails. They join after the
      first §7 promotion gate passes. Flat is unreachable from this call
      site (`_recall_line` runs only inside the holding branch), so in
      practice (a2) explores the winning and gave-back-while-positive
      classes.
    - **The propensity and scheme are journaled on EVERY row, including
      when exploration is off** (`deterministic-top2`, propensity 1.0).
      Pooling deterministic rows with ε-scheme rows unlabelled would
      silently corrupt every estimate (c) computes, and it cannot be
      retrofitted onto rows already written.
    - Fail-soft at a third level: a selector that raises falls back to the
      **incumbent ranking**, not to no recall — reaching `_recall_line`'s
      outer handler would strip the desk's brief, a degradation rather than
      the no-op fail-soft requires. Pinned by
      `test_a_broken_draw_never_costs_the_desk_its_brief`.
    - Tests: `RecallExploreTests` (10) + `RecallExploreWiringTests` (4) in
      `tests/test_run_engine.py`. **Mutation-checked ×7** — floor removed,
      never-explores, losing-class explored, head displaced, propensity
      dropped from the emit, fail-soft guard removed, off-rows unlabelled.
      The propensity-drop mutation initially **survived**: the wiring test
      grepped `run_cycle`'s source and the word appeared in a *comment*.
      The test now strips comments before grepping — a source grep that
      prose satisfies is not a wiring test.
    - **Next: turn the flag on for a measurement window, then (a3).** (a2)
      shipping default-off means the dataset is still degenerate until
      `DESK_RECALL_EXPLORE=1` is set on prod. Sequence: enable → confirm
      ≥2 distinct second-slot shas per active class in `run_events` →
      then (a3) pool enrichment, since the deep analysis's ≥3-above-floor
      precondition is only just met (3–4 alternates) on today's frozen
      563-chunk monitoring pool.
  - **2026-08-10 — ε-exploration ENABLED on prod by the owner (23:30Z).
    Retrieval variance exists for the first time.** `DESK_RECALL_EXPLORE=1`
    added to `/home/ec2-user/sooppiy/.env` (backup `.env.bak-preexplore-*`),
    both `sooppiy-worker` and `sooppiy-backend` recreated — **both**, because
    `routes_automation.py` can also invoke `run_cycle`, and a split policy
    would log two schemes for the same run.
    - First three live cycles under the new policy, three markets, two
      situation classes:

      | run | class | explored | slot 1 | slot 2 | propensity | pool |
      |---|---|---|---|---|---|---|
      | 1047 futures | gave-back+winning | no | `9d8b125b` | `c8559767` (22.48) | 0.75 | 3 |
      | 1044 crypto | gave-back+winning | **yes** | `9d8b125b` | **`595eac1b`** (21.97) | 0.0833 | 3 |
      | 1053 forex | winning | **yes** | `161f2451` | **`6f8f522e`** (9.93) | **0.125** | 2 |

    - **3 distinct chunk-pairs where the previous 262 consecutive events had
      exactly 1.** The head is preserved in every row; propensities are
      exactly ε/pool for each observed pool size.
    - Row 1053 is the useful independent check: the *winning* class has pool
      **2**, not 3, because its rank-5 chunk (8.94) falls below
      0.60 × 15.03 = 9.02. The relative floor reproduces on live data exactly
      what the measured score table predicted — which is the evidence that
      0.60-of-head is a real threshold and not a number that happened to fit.
    - Health after the recreate: both containers up, `/` and
      `/api/subscriptions/plans` 200, no worker exceptions.
    - **✅ CLOSED 2026-08-11 00:53Z — the losing-class exclusion is verified on
      live data.** Recorded as open above at 23:5xZ because the whole book was
      in profit; run 1056 (SI, futures) then went to −1.33 and its next cycle
      produced the first losing-class recall since cutover:

      ```
      1056  00:53:25Z  deterministic-top2  explore=false  prop=1.0  pool=NULL  LOSING
      ```

      …with `DESK_RECALL_EXPLORE=1` confirmed in **both** containers at that
      moment, so the row reads "deterministic *despite* the flag being on".
      Alongside it, all 7 win/flat rows carried `eps-head-fixed-v1` (2 of them
      explored).
      - **`pool: NULL` is the load-bearing detail, not a missing value.** The
        deterministic branch returns only `{scheme, explore, propensity}`,
        while the ε branch always writes `eps` and `pool`. So a row with no
        `pool` key proves `_recall_select`'s `if not explore:` early return
        fired. Had the class gate wrongly *allowed* the run and simply found
        no alternates, the row would instead read `eps-head-fixed-v1` with
        `pool: 0`. The two failure modes are distinguishable in the journal —
        which is worth knowing for every future gate audit.
    - **Also proved exhaustively, because one live row only samples the
      space.** In-container probe over 117 combinations of
      (unrealized × peak × quantity) — including shorts, ±1e-9, exact 0.0,
      `None`, `""`, `"abc"`, `NaN` — found **0 violations** of the invariant
      *"if `_recall_query` says losing, `_recall_explore_allowed` must be
      False."* Two findings from it worth keeping:
      - the gate tests `if not pos_qty`, **not `pos_qty > 0`**, so a SHORT
        (negative quantity) is correctly treated as holding rather than flat.
        This is the same family as the documented `quantity > 0` monitoring
        trap; this code does not have it.
      - malformed input (`NaN`, `"abc"`) makes the query say *winning* while
        the gate still returns False — divergent, but conservative in the
        safe direction (no exploration). Recorded so a later reader does not
        "fix" the divergence into an unsafe agreement.
      - The invariant is a COUPLING between two functions written separately
        that both read `pnl["unrealized"]`. Nothing in the unit suite pins the
        coupling itself, only each side — the standing "brief-line wiring is
        untested by default" shape. A regression test for it belongs with the
        next increment that touches either function.
    - Rollback remains one line: delete `DESK_RECALL_EXPLORE=1` from `.env`
      and `docker compose --profile prod up -d --no-build`.
  - **2026-08-11 23:1xZ — the (b) variance gate re-measured on prod, one day
    after exploration went on. It is 1 class of the 2 it needs.** 130
    `recall` rows, 14 runs (9 closed), window 08-10 23:39Z → 08-11 21:11Z:

    | class | events | distinct pairs | distinct slot-2 |
    |---|---|---|---|
    | crypto gave-back+winning | **37** | **4** | 4 |
    | forex gave-back+winning | 24 | 3 | 3 |
    | futures gave-back+winning | 23 | 3 | 3 |
    | crypto winning | 9 | 2 | 2 |
    | every losing class | 10 / 7 / 6 / 1 | **1** | 1 |

    The gate is *≥3 distinct pairs for each of ≥2 classes with ≥30 events
    per class, and ≥20 closed runs*. Only crypto gave-back+winning clears
    both legs; forex and futures have the pairs and are 6–7 events short.
    Closed runs are 9 of the 20 wanted. **Both shortfalls are volume, not
    structure — which is the opposite of the 08-09 finding, and the reason
    waiting is the right move this time.** Every losing class sits at
    exactly 1 pair, as designed (`_recall_explore_allowed`), so the losing
    side contributes no variance and cannot until the first promotion gate
    passes. Projected at the observed ~5.4 recall/h: the two 30-event legs
    land ~08-12, the 20-closed-run leg is the binding one.
  - **2026-08-11 — increment (a3)(i) SHIPPED: the skills catalogue is now a
    retrievable pool.** `desk_memory_ingest.ingest_skill_lessons()` atomises
    every enabled skill body into single claims stored as `kind="lesson"`;
    it rides the same ~30-min ingest tick as the other three sources.
    **132 lessons from 39 enabled skills** (the deep analysis estimated
    120–180), against a `lesson` count that had been **zero** since the kind
    was defined.
    - **No behavior change, and that is pinned.** `_recall_line` still
      searches `kind="monitoring"`, so nothing a lesson says can reach a
      live position brief today
      (`test_lessons_stay_out_of_the_pool_recall_actually_reads`). Letting
      recall read `lesson`+`outcome` is (a3)(ii), tomorrow.
    - **A multi-market skill is stored once PER market.** `_candidates`
      filters on a single `market` column, so one row carrying only the
      first of `["crypto","futures"]` would make that lesson unreachable
      from futures — silently, and only at retrieval time. Two tests pin
      both directions (reachable from each; does not leak into a third).
    - **Atoms are whole sentences.** The join of a body's atoms is asserted
      equal to the body, so a splitter can never teach the desk a clause its
      author did not write. A trailing fragment below 120 chars folds back
      into the previous claim (a two-line atom retrieves as noise); a body
      short in its ENTIRETY is still kept, unlike a markdown heading — a
      short skill body IS the doctrine.
    - Fail-soft: `_lessons_fail_soft` returns 0 on any catalogue error, so a
      corpus that cannot read the skills table never costs the tick its
      other three ingests.
    - **The (a3) gate — ≥3 above-floor chunks per active class — is met in
      all EIGHT live cells by the lesson pool alone.** Measured on the real
      catalogue with the exact strings `_recall_query` builds, scored with
      the shipped 0.60-of-head relative floor:

      | market | gave-back+winning | winning |
      |---|---|---|
      | crypto | head 14.93, floor 8.96 → **3** | head 6.42 → **13** |
      | forex | head 14.18, floor 8.51 → **3** | head 6.49 → **8** |
      | futures | head 14.38, floor 8.63 → **3** | head 6.43 → **9** |
      | us-stock | head 15.23, floor 9.14 → **3** | head 6.92 → **5** |

      The gave-back cells sit at exactly 3 because that query is long and
      specific — its head scores 14–15 and drags the relative floor up with
      it. Three is the gate, not a comfortable margin, so **(ii) must count
      lessons AND monitoring together**, which is what it was always going
      to do. The plain winning cells are 5–13. This is what (ii) has to work
      with, and it is why (ii) is worth doing.
    - **Known debt, to be resolved before (ii) promotes anything:** an
      EDITED skill stores a new lesson and the stale one is not deleted
      (`desk_memory` has no delete; the same is already true of edited
      monitoring notes). Harmless while nothing retrieves `lesson`;
      once (ii) is on, a retired claim could still be recalled. The fix
      belongs with (ii), not here.
    - Tests: `SkillLessonTests` (11) in `tests/test_desk_memory.py`.
      **Mutation-checked ×8** — enabled-check removed, only the first market
      stored, fold-back removed, kind written as `monitoring`, market
      dropped to NULL, fail-soft guard removed, sentence split replaced by a
      hard 150-char slice. Every one was caught.
  - **2026-08-11 — owner directive, binding on this ladder:** *"everything
    for sooppiy AI"* / *"if we find that we must be implement trading logic
    and sooppiy AI"*. Journal-only and default-off increments are a STAGING
    step, never the destination: every rung of this ladder must name the
    trading judgment it will eventually change, and (d)/(e) — weighted
    retrieval, then the skills wall — are where that lands. An increment
    that cannot state which desk decision it will alter does not belong on
    the ladder. See memory `decisions-become-skills`.
  - **2026-08-09 — deep analysis shipped:**
    [22-phase3-learning-to-profit.md](22-phase3-learning-to-profit.md) — the
    owner-requested full analysis of the path from retrieval variance to
    attributed NET profit. Its deltas to this ladder, binding from here on:
    (1) **(a2) must log propensities** (and the scheme version) and sample
    only above a relevance floor — without logged propensities the (c)/(d)
    evaluation cannot be computed offline; (2) **(b)'s reward signal is
    behavior surrogates** (dump-vs-reduce, round-trip, add-into-loser, fee
    hurdle, arm usage), each pre-validated by an existing loss-shape audit —
    per-chunk raw P&L is shown to be unidentifiable at our volume (power
    math in §5 there); raw NET P&L enters only at the (d) promotion gate,
    treatment vs control runs; (3) **(a3) is inserted**: pool enrichment —
    skills atomised into `lesson` chunks, recall reading lesson+outcome
    kinds — because several situation classes cannot have ≥3 above-floor
    candidates in a 562-chunk frozen pool; (4) **Phase 4 named**: the same
    machinery applied to the 48,000-char skills wall, which still has zero
    variance by construction and is where both the deterministic cost win
    and the material profit effect live.

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
