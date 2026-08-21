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
  - **HANDOFF FILE (read first after an account rotation):**
    [docs/reports/HANDOFF-rag-phase3.md](../reports/HANDOFF-rag-phase3.md) —
    where the ladder stands, the live prod flag state and its rollback, the
    open measurement obligations, the hypotheses already killed, and the
    traps this cadence has hit. Account memory does not survive rotation;
    that file and this section do.
  - **2026-08-21 (pass 2, 08:0xZ) — the ladder is not the constraint; the
    desk stopped trading, and the cause is now traced.** No code shipped;
    the measurement IS the increment. Full working in
    [docs/reports/2026-08-21-automation-monitoring.md](../reports/2026-08-21-automation-monitoring.md).
    - **The entry engine was switched off at a deploy boundary, not slowly
      starved.** Crypto flat entry-intent rate, 6h buckets, split at the
      `20260818-ai-first-batch` build (08-18T11:49:34Z): PRE 33/566 =
      **5.83%**, POST 8/649 = **1.23%**, two-proportion **z = 4.427,
      p = 9.5e-6** (exact binomial P(≤8 in 649 at the PRE rate) = 2.3e-9),
      with **no downward trend in the ten PRE buckets**.
      Confirmed from `signals` independently: executed opens **0.368/h →
      0.102/h**. The only entry-side behavioural change in that batch is
      **#484** (`desk_record.record_line()` in both bracket prompts); the
      desk's own free-text gives that line's reasoning in **11 of 12**
      high-confidence holds. Rival hypotheses refuted: the tape did NOT go
      quiet — matched-symbol per-cycle volatility roughly **DOUBLED**
      (median 0.140% → 0.291%) as entries went to zero; the record did not
      ratchet worse (best 0.969% → 1.438%); the population did not shift.
      **Observational, not an experiment — the next increment is a
      per-run randomised A/B on the reachability line, default-off, never
      a naive revert.**
    - **Two numbers in the authority docs are artifacts, now corrected in
      place.** (i) "`short` zero" is structural: the decision schema is
      `buy|sell|hold` and the `sell`→`short` remap runs AFTER the
      `decision` event is emitted (`run_engine.py` 6572 vs 6775), so
      `short` is 0 in all 5,103 decision rows and can never be anything
      else — while `signals` holds 48 short opens. The real flat entry
      rate is **62/3,588 = 1.73% intent / 42 = 1.17% executed**, and
      **86% of executed entries are SHORTS**, not zero. (ii) §4a's harm
      test therefore uses a wrong baseline AND a non-stationary one, and
      **cannot separate `DESK_RECALL_FLAT`'s effect from the collapse**.
      The flag itself is mechanically clean: 143/143 flat decisions carry
      a `recall` row, 0 empty-`chunks` rows, 0 tracebacks.
    - **(b) re-measured: MET more widely (six ε classes, not three) but
      the pair count is partly confounded.** The deterministic arm's
      distinct pairs sit in **perfectly non-overlapping time blocks** —
      corpus drift, collinear with calendar time. Only ε-induced sets are
      attributable; five classes still clear on those alone (10/4/3/4/3
      novel sets). **(b) must key on the deterministic block in force at
      each row's `ts`, and size its claims off the explore arm (11-29
      rows/class), not off the events column.**
  - **2026-08-21 — the (b) gate is MET, ~70 minutes after the flat
    promotion.** Measured ~01:30Z on flat rows alone: crypto/FLAT **95 events
    / 5 pairs** and forex/FLAT **40 / 4**, both `eps-head-fixed-v1`, joining
    crypto/giveback+winning (77 / 10). That is **three** ε-scheme classes
    clearing ≥30 events and ≥3 distinct pairs, against a gate that had been
    frozen at 1-of-2 for four days. **(b) is the next increment.** Two
    standing cautions carry into it: do NOT pool the FLAT rows with the
    HOLDING rows (they answer different questions, and pooling populations is
    the mistake this ledger has made twice), and do NOT assume the empty-
    `chunks` control group will ever exist — it still has zero rows.
    Safety, stated as inconclusive rather than as reassurance: 135 flat
    cycles post-flip, 133 `hold` + 2 `retire`, **0 buys** — the 0.20%
    baseline predicts ~0.27 buys in 135 cycles, so this is exactly what "no
    effect" looks like and is NOT evidence of harm or of safety.
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
    - **Verified on prod, image `20260811-rag-lessons` (23:33Z).** Code
      present in the running image; corpus went 1201/564/81 with **no
      `lesson` kind at all** → **132 lessons covering all 39 enabled
      skills**, the same count as local, which also proves prod's catalogue
      carries no admin drift from `BASE_SKILLS`. The no-op held: an
      in-container `search(kind="monitoring")` for all four markets returns
      **only monitoring chunks**, headed by sha `9d8b125b` — the exact
      incumbent recorded in the 08-10 table above, so the retrieval path is
      byte-for-byte what it was before the deploy.
    - **⚠️ FINDING THAT RE-SPECS (ii): a naive lesson+monitoring UNION
      admits ZERO lessons.** Probed on the live prod pool with the same
      queries: the combined head is a **monitoring** chunk at **30.44**, so
      the shipped 0.60-of-head floor sits at **18.3** — above the best
      lesson in every class (max 15.23). Six chunks clear it, all
      monitoring.
      - The cause is scale, not quality: monitoring chunks are long
        multi-paragraph findings and score 2× what a single-sentence claim
        can, for the same relevance. This is the SAME failure the 08-10
        entry documented across situation classes ("the gave-back class's
        eighth chunk outscores the winning class's first"), reappearing
        across *kinds* — and the fix has to rhyme: the floor must be
        relative to the head **of its own kind**, or the pools get a
        per-kind quota, not one merged ranking.
      - **If (ii) had shipped as `kind in (monitoring, lesson)`, it would
        have deployed clean, changed nothing, and read as working.** That is
        exactly the class of silent no-op this ladder exists to avoid;
        writing it down before building is why the pool step came first.
    - Tests: `SkillLessonTests` (11) in `tests/test_desk_memory.py`.
      **Mutation-checked ×9** — enabled-check removed, only the first market
      stored, fold-back removed, kind written as `monitoring`, market
      dropped to NULL, fail-soft guard removed, sentence split replaced by a
      hard 150-char slice, no split at all. Every one was caught.
    - **Next: (a3)(ii) — let recall read `lesson` (and `outcome`) behind the
      explore flag, per-kind scored.** It is NOT a widened `kind` filter:
      the finding above shows that merges to a no-op. The shape it has to
      take is one retrieval per kind, each floored against its OWN head,
      with a per-kind slot budget — and the acceptance test is that a live
      `recall` row carries a `skill:` source, which no row can do today. The
      trading judgment it changes, stated as the owner directive below
      requires: which doctrine the desk is holding in mind at the moment it
      decides to bank, hold or add on a position that has given back its
      peak — the single behaviour that carried 74% of measured loss.
  - **2026-08-15 — (a3)(ii) SHIPPED OUT-OF-BAND as PR #432**, from a
    monitoring session rather than this cadence, which is why the five days
    between it and this line carry no ladder entry. Recorded here because
    §7 is the ledger and an unrecorded rung reads as an undone one.
    - `_RECALL_KINDS = ("outcome", "lesson")` with
      `_RECALL_KINDS_FALLBACK = ("monitoring",)` — two **tiers**, not one
      merged pool, exactly the shape the 08-11 finding above said it had to
      take. `desk_memory.search` now accepts several kinds as one pool (IDF
      and the length norm are computed over the candidate pool, so scores
      from two separate calls are not the same unit and must never be merged
      by the caller).
    - The defect it fixed is worth keeping: the desk was being handed our
      **engineering commentary** as its trading memory. Prod run 1274 asking
      *cut or hold* on a losing SOL short was given, as rank 1, a monitoring
      note concluding *"…and that is why nothing ships"* — 16 of the 636
      monitoring chunks carry deliberately-inconclusive markers and no other
      kind carries any.
    - **The cutover splits the attribution population in two, and the split
      is the first thing (b) must respect.** Measured 2026-08-17 over all 662
      journalled `recall` rows: **459 rows before 08-15T02:48Z, every chunk
      `monitoring`; 203 rows after, every chunk `lesson` (244 slots) or
      `outcome` (162 slots), zero monitoring.** Pooling them would attribute
      outcomes across two different corpora.
    - **PR #432's own stated limitation is now refuted by the journal.** It
      reported *"no `outcome` chunk surfaced in any of the 12 cells"* from a
      one-shot probe; live, outcome chunks take **162 of 406** chunk slots
      and hold the **head** in every one of the 83 give-back/winning rows
      (`run:1013:outcome` in 80 of them, `run:1358:outcome` in 3). The probe
      measured one moment of a corpus that grows with every close.
  - **2026-08-17 — increment (a4) SHIPPED: journal the candidates that were
    PASSED OVER.** The row now carries `cands` — every chunk the selector
    ranked and did not emit, with its score — plus the `floor` the ε draw was
    made under. `run_engine._recall_cands(hits, chosen)`; the shortlist is
    always widened to `_RECALL_EXPLORE_POOL`.
    - **The measurement that forced it, on the 203 post-cutover rows:**

      | measure | value |
      |---|---|
      | rows carrying any candidate IDENTITY | **0 of 203** |
      | rows carrying `pool` (a COUNT only) | 83 |
      | deterministic rows (losing classes, no count at all) | **120 (59%)** |
      | rows that were actual explored draws | **15 (7.4%)** |

      So for 100% of the journal a chunk's absence from a row is ambiguous
      between *ranked and not drawn* and *not in the pool at all*. Every
      off-policy estimator (c) needs the action **set**; the cardinality of
      it is not enough, and for the losing classes — 59% of rows, and the
      side that carries the loss — not even the cardinality was written.
    - **Second reason, measured the same day: the deterministic classes
      DRIFT.** `crypto/losing` produced 3 distinct chunk-pairs across 53
      deterministic rows — not policy variance but the corpus moving under a
      fixed ranking, and the pairs are **time-disjoint blocks** (08-15 →
      `exit-discipline#4|horizon-discipline#2`, 08-16 →
      `exit-discipline#3|#2`, 08-16/17 → `#3|#4`). The head itself changed.
      Without a record of what else was on offer, that drift is
      unattributable — and it is the exact confound §2 forbids learning
      from. `cands` makes an entering or departing chunk visible in the row.
    - **`cands` is defined by EXCLUSION, never by a rank slice.** When the ε
      draw displaces rank 2, rank 2 is itself a passed-over arm; a fixed
      `hits[2:]` would drop the one candidate the counterfactual most needs.
      Mutation-checked (M2, M7).
    - **The widened shortlist is provably not a retrieval change.**
      `desk_memory.search` slices **after** scoring over a 2,000-row
      candidate pool, so the top-2 of a 5-hit search is byte-identical to the
      top-2 of a 2-hit search — same head, same brief, no extra DB work.
      Pinned by `test_widening_the_shortlist_changes_nothing_the_desk_reads`,
      which runs the real corpus twice and byte-compares the rendered line —
      and verified in-container against the **live prod corpus** before
      deploy, in all 16 (market × class) cells: `limit=2` and `limit=5`
      returned identical shas AND identical scores in every one.
    - That probe also surfaced why `cands` is worth more than it looks: the
      runners-up are frequently **tied**. crypto/give-back scores
      15.77 / 15.62 / 15.62 / 15.62 / 15.62 — four chunks at the same score,
      so which one holds slot 2 is decided by the sort's tiebreak, not by
      relevance. A chunk that occupies a slot by tiebreak is the textbook
      passenger (c) is meant to find, and without `cands` the journal cannot
      even show that the tie existed.
    - **`pool` and `floor` stay ABSENT on deterministic rows.** Their absence
      is the load-bearing tell recorded on 08-11 that proves
      `_recall_select`'s early return fired, which is how the losing-class
      exclusion is audited in the journal. Enriching the row must not blur
      it; pinned by `test_pool_stays_absent_on_a_deterministic_row`
      (mutation M6).
    - No new flag — the row rides `DESK_RECALL_ENABLED`, same reasoning as
      (a): journaling what recall passed over is meaningless when recall is
      off. Journal-only: no prompt, gate, size or order reads `cands`.
      Fail-soft path also journals its runners-up.
    - Tests: `RecallCandidateTests` (5) + `RecallCandidateWiringTests` (3) in
      `tests/test_run_engine.py`. **Mutation-checked ×7** — cands dropped
      from the deterministic branch, cands as a fixed slice, floor dropped,
      shortlist narrowed again, cands dropped from the `run_events`
      whitelist, `pool` leaked onto a deterministic row, cands not recomputed
      after the draw. All seven killed.
    - **The trading judgment it will change**, as the owner directive below
      requires: none today, and that is the honest answer — (a4) is the last
      piece of evidence-plumbing before (c) can say *"this lesson is a
      passenger"* and (d) can stop showing it at the moment the desk decides
      to bank, hold or add on a position that has given back its peak.
  - **2026-08-17 — the (b) variance gate, re-measured on the post-cutover
    population. One class clears it honestly; the letter of the gate is met
    and the letter is not enough.** 203 rows, 20 runs (**all closed** —
    that leg is met exactly), window 08-15T02:48Z → 08-17T20:24Z, all crypto:

    | class | events | pairs | scheme | variance is… |
    |---|---|---|---|---|
    | crypto/giveback | 62 | **6** | ε | **policy** — head fixed, 5 distinct alternates |
    | crypto/losing | 53 | 3 | deterministic | **time** — three disjoint blocks |
    | crypto/giveback+losing | 67 | 1 | deterministic | none |
    | crypto/winning | 21 | 4 | ε | policy, but 21 < 30 events |

    - The corrected gate (*≥3 pairs for each of ≥2 classes, ≥30 events per
      class, ≥20 closed runs*) reads MET if `crypto/losing` counts. **It must
      not count**: its three pairs are consecutive time blocks under a fixed
      ranking, which is corpus drift confounded with calendar time — the
      thing §2 exists to refuse. Counting it would repeat the 08-09 mistake
      in a new costume: a number that opens on a dataset that cannot answer
      the question.
    - **Amended gate for (b), stated so it cannot be argued from vibes: the
      ≥2 classes must each be ε-SCHEME classes with ≥30 events and ≥3
      distinct pairs.** Today that is 1 of 2 (`crypto/giveback` 62/6;
      `crypto/winning` 21/4 is 9 events short). This is a VOLUME shortfall,
      not a structural one — and the fleet rebuilt on 08-17 into 13 runs
      across crypto, futures, forex and us-stock, where the previous window
      was crypto-only, so the class count widens on its own.
    - Also recorded: **0 of 203 rows have empty `chunks`** — the control
      group (recalled, corpus returned nothing) still does not exist, nine
      days of journalling in. (b) must not assume it ever will.
  - **2026-08-18 — increment (a5) SHIPPED: the desk is told when its recall
    was a COIN FLIP. The first rung that changes what the desk READS.**
    Owner directive, verbatim: *"must be sooppiy AI know you finding that"* —
    a finding that lives only in this ledger is engineering trivia, not
    trading logic (memory `decisions-become-skills`).
    - **The finding, measured on the live prod corpus across all 16
      (market × situation) cells:** in **7 of them (44%)** the SECOND chunk
      the desk is handed is **exactly tied on score** with a chunk it was
      never shown; in 2 more the head itself is tied. Slot 2 is decided by
      the sort's tiebreak, not by relevance — and the block is headed *"What
      this desk has already learned about cycles like this"*, which reads as
      precedent. The desk has been weighing a coin flip as a precedent, in
      the cut/hold/bank decision that carries 74% of measured loss.
    - Live confirmation from the first organic (a4) row, run 1419 forex
      AUDUSD 08:03:58Z: heads tied at **18.4282 / 18.4282**, candidates tied
      at **17.9115 / 17.9115**. Before (a4) the journal could not have shown
      the tie existed; it showed up on the very first row.
    - **`_recall_contest_line(hits, cands)`** appends one line when a
      passed-over candidate scored within **1%** of the WEAKEST emitted
      chunk: *"Retrieval note: N other past findings scored within 1% of the
      last item above, so which of them you were shown is close to
      arbitrary. Weigh these as general doctrine for this situation, NOT as
      a specific precedent for this position."*
    - **It is a DISCLOSURE, not a weighting.** We do not yet know which of
      the tied chunks is better — that is (c)/(d). We do know the choice
      between them was arbitrary, and the desk is entitled to that. This is
      also why it ships now rather than waiting on the (b) gate: the fact is
      already established and needs no attribution to be true.
    - **Silent when uncontested**, deliberately. An unconditional caveat
      would teach the desk to discount every recollection including the
      uncontested ones that ARE precedent — the opposite of the intent.
    - **The margin is the MARGINAL chunk, not the head.** Slot 2 is what a
      tie decides and what an unshown equal would have replaced; measuring
      against the head would call a strong recall contested whenever its
      runner-up was weak. Mutation-checked (N4, N8).
    - **NOT rendered as a bullet.** `test_recall_is_bounded` counts `"\n- "`
      to cap how many past FINDINGS reach the prompt; the pre-existing guard
      caught the first draft. Widening that guard to fit an annotation would
      have quietly raised the recall budget — the guard was right and the
      line shape was wrong.
    - Fail-soft at the render site as well as inside: a disclosure that
      raises costs the desk the NOTE, never the recall it annotates.
    - Tests: `RecallContestDisclosureTests` (6) + `RecallContestWiringTests`
      (3). **Mutation-checked ×10, and two mutants initially SURVIVED — both
      of which changed the code, not the tests.** A NaN guard turned out to
      be dead (NaN comparisons are always False, so a NaN score already
      falls through to silence) and was **deleted** rather than propped up by
      a test written to justify it. A zero-score guard was unpinned because
      it depends on `desk_memory.search` filtering `score > 0` — another
      module's invariant — and was **pinned with a test**, since depending on
      a foreign invariant untested is the standing brief-line trap.
    - **The trading judgment it changes, stated plainly:** how heavily the
      desk weighs a recalled past finding when deciding to cut, hold or bank
      a position that has given back its peak. It cannot make the recall
      better; it stops an arbitrary one from being read as authoritative.
    - **VERIFIED ON PROD, image `20260818-recall-contest`.** The rendered
      block is header + exactly 2 finding bullets + the note as a non-bullet
      line, so `_RECALL_MAX` is untouched. Five of sixteen cells stay silent,
      which verifies the negative case on live data as well as the positive.
    - **Post-ship re-measurement, per the experimental-mindset rule — and it
      moved the headline number, so it is recorded rather than buried.** The
      note fires in **11 of 16 live cells (69%)**, against the **7 of 16
      (44%)** EXACT ties that justified building it. These are two different
      quantities, not a discrepancy: 44% is `score == score`, 69% adds the
      1% band. A later reader must not treat 11 vs 7 as a regression.
    - **What the 69% actually says is bigger than this increment: retrieval
      at the MARGIN is nearly flat.** It is not that the ranking occasionally
      ties — it is that in roughly two thirds of live situations the second
      slot carries almost no information over the chunks below it. BM25 over
      single-claim `lesson` chunks of similar length produces a flat tail by
      construction. That is direct evidence FOR (c)/(d): weights are the only
      thing that can make the marginal slot mean something, and it is also
      why (a2) exploration is cheap here — the arms really are near-equal.
    - **Watch item, stated before anyone argues it later:** a note that fires
      69% of the time is close to unconditional, which is the failure mode
      this line was explicitly designed against. It is honest today — the
      retrieval really is that contested — but if the desk visibly discounts
      recall across the board, the 1% band (`_RECALL_TIE_BAND`) is the knob,
      NOT the wording. Do not tune it without a measured behaviour change;
      the fix of record is (c).

  - **2026-08-17 — owner asked whether us-stock also gets RAG. It already
    does; measured, not assumed.** The recall path has never been
    crypto-only — `_recall_query` opens with the run's `market` and
    `desk_memory._candidates` filters `(market IS NULL OR market = ?)`, so
    every market reaches both its own chunks and the market-agnostic ones.
    Corpus on prod at 02:0xZ:

    | market | outcome | lesson | tier-1 pool incl. the 116 market-agnostic lessons |
    |---|---|---|---|
    | crypto | 135 | 17 | 268 |
    | **us-stock** | **124** | **29** | **269** |
    | futures | 56 | 8 | 180 |
    | forex | 52 | 4 | 172 |

    - us-stock is the **best-stocked market in the corpus**, marginally ahead
      of crypto and ~50% larger than futures or forex. Live retrieval
      in-container returns 5 above-zero **tier-1** hits for us-stock in every
      situation class — lessons for `losing`, outcome chunks for
      `give-back` — and never falls through to the monitoring tier.
    - **The ranking is market-sensitive, not market-blind.** All four markets
      head the losing class on the same market-agnostic chunk
      (`skill:exit-discipline#3`, sha `b14d72c1`, `market=NULL`), but slot 2
      splits by market: us-stock and forex take `#2`, crypto and futures take
      `#4`. The market token in the query is doing real work.
    - Worth keeping for (c): a market-agnostic lesson is **one sha shared by
      all four markets**, so its evidence pools rather than splitting four
      ways — the opposite of the market-scoped skills, which are stored once
      per market (08-11 entry) and will each be estimated on a quarter of the
      data. Any per-chunk estimator must not treat those two storage shapes
      as the same population.
    - **What us-stock actually lacks is journal representation, not
      retrieval:** 0 of the 203 post-cutover `recall` rows are us-stock,
      purely because that window's fleet was crypto-only. The 08-17 rebuild
      put run 1380 (ORCL) live alongside futures and forex, so this closes
      on its own — and it is the same volume shortfall the amended (b) gate
      above is waiting on.
  - **2026-08-18 — increment (a6) SHIPPED: tie-scoped exploration on the
    LOSING side. This is the change that opens the (b) gate.** Owner
    direction: *"(b) 게이트를 여는 것이 최우선"* — opening the gate is the
    priority.
    - **The measurement that inverts the exclusion's premise.** (a2) refused
      to explore any losing position, on the mandate's asymmetry: never
      loosen an unproven thing on the losing side. That was right **while the
      incumbent was a CHOICE.** It is not. Measured on prod 2026-08-18:
      **every journalled crypto losing-class row has slot 2 EXACTLY TIED**
      with chunks the desk was never shown — margin ~9.52 with three
      candidates at the same score, decided by the sort's tiebreak. Across
      all 16 live cells, 7 have a tied slot 2; on the live journal the (a5)
      disclosure fires on **6 of 9** rows.
    - **So the losing side — the cut/hold/bank decision carrying 74% of
      measured loss — has been reading an ARBITRARY pick, and contributes
      zero variance by design.** That is precisely what kept the (b) gate
      shut at one qualifying class.
    - **Drawing among exact ties cannot loosen anything**, because the drawn
      chunk scored within 1% of the one it replaces. The asymmetry is
      honoured by construction, not by exception.
    - **`eps-tie-only-v1`** — a DIFFERENT scheme string, because it is a
      different policy and pooling it with `eps-head-fixed-v1` unlabelled
      would corrupt every estimate (c) computes. Same reason (a2) versioned
      its scheme at all. The floor is `slot-2 score x (1 - 1%)`, not the
      0.60-of-head floor; the head is still never displaced.
    - **Verified on the live corpus BEFORE shipping — and it refuses where it
      should:**

      | cell | tied arms | pairs (was 1) |
      |---|---|---|
      | **crypto/losing** | 3 | **4** |
      | futures/losing | 3 | **4** |
      | futures/gave-back+losing | 2 | **3** |
      | forex/gave-back+losing | 1 | 2 |
      | crypto/gb+losing, forex/losing, us-stock x2 | 0 | **1 — unchanged** |

      Four cells gain nothing because their incumbent is a genuine choice
      rather than a tiebreak. That is the safety property holding on real
      data, not an argument about it.
    - **Projected effect on the (b) gate:** `crypto/losing` (53 events in the
      last measured window, now 4 reachable pairs) joins `crypto/giveback`
      (62 events, 6 pairs) as the **second qualifying class** as soon as it
      accumulates 30 events under the new policy. futures adds two more
      cells. The gate was 1 of 2; it becomes 2 of 2 on volume alone.
    - **Kill switch `DESK_RECALL_EXPLORE_TIES`, default ON** — unlike (a2)'s
      own flag, and the reason is stated so it is not read as carelessness: a
      default-off flag here would leave the gate shut, which is the thing
      this increment exists to fix. It remains disableable without a deploy
      because it is still the losing side, and the kill switch reproduces the
      pre-2026-08-18 behaviour exactly, `deterministic-top2` label included
      (pinned by a test).
    - **A losing row with NO tie is now journaled `eps-tie-only-v1` with
      `pool: 0`, not `deterministic-top2`.** That is deliberate and the
      existing test was UPDATED rather than weakened: the policy ran and
      found no arm, which is a different fact from the policy never having
      run. Its original intent — a losing run's ranking must not change — is
      now asserted on the emitted CHUNKS, which is what it was really
      protecting.
    - Tests: `TieScopedExplorationTests` (9) + 2 updated/added in
      `RecallExploreWiringTests`. **Mutation-checked x6** — tie band replaced
      by the 0.60 floor (i.e. the losing side actually loosened), losing side
      never reaching the tie path, tie rows mislabelled as the v1 scheme,
      kill switch disabled, and the band anchored to the head instead of
      slot 2. A length guard written first was DELETED after mutation showed
      it changed nothing (`hits[2:]` is already empty when the head is short).
    - **The trading judgment it changes:** which doctrine the desk holds in
      mind while deciding to cut, hold or reduce a LOSING position — and,
      more importantly, it makes that choice measurable for the first time.
  - **2026-08-19 — the (b) gate re-measured, and (a6)'s volume projection is
    REFUTED. The shortfall is COVERAGE, not fleet activity.** Hypothesis
    going in (from (a6)): `crypto/losing` joins `crypto/giveback` "on volume
    alone" within days. Measured on prod over the 234 post-cutover rows:

    | market/class | events | pairs | scheme | post-(a6) events |
    |---|---|---|---|---|
    | crypto/giveback+winning | 76 | 10 | ε-head-fixed | 11 |
    | crypto/giveback+losing | 66 | 1 | deterministic → tie | **1** |
    | crypto/losing | 56 | 3 | deterministic → tie | **1** |
    | crypto/winning | 23 | 5 | ε-head-fixed | 2 |
    | us-stock/losing, us-stock/gb+losing | 4, 4 | 1, 1 | deterministic | 0 |
    | forex/gb+winning, us-stock/gb+winning | 3, 2 | 2, 2 | ε | 0 |

    - The amended gate (≥2 ε-scheme classes, each ≥30 events and ≥3 distinct
      pairs) is **still 1 of 2**. `crypto/losing` has **1** event under
      `eps-tie-only-v1`, not 30 — 15 recall rows total in the ~18h since the
      (a6) deploy, across 4 runs.
    - **Why, measured rather than assumed.** Recall fires only from the
      position brief, so the journal accrues at the rate of HELD positions.
      Per day, `decision` events vs the subset carrying the `position_state`
      brief token:

      | day | decisions | HOLDING | FLAT | recall rows |
      |---|---|---|---|---|
      | 08-19 | 785 | 11 | **774** | 11 |
      | 08-18 | 972 | 40 | **932** | 40 |
      | 08-17 | 525 | 25 | 500 | 25 |
      | 08-16 | 413 | 124 | 289 | 124 |
      | 08-15 | 240 | 34 | 206 | 34 |

      Recall rows equal the holding count **exactly, every day** — coverage of
      the holding cycle is 100% and nothing is broken. Coverage of the ENTRY
      cycle is **0%**, and the entry cycle is **98.6% of the desk's decisions**
      (774 of 785 on 08-19). Waiting on volume is waiting on the 1.4%.
    - **`_recall_query`'s flat branch has never executed.** The
      `"flat considering entry fee hurdle expected move"` text has been in the
      code since Phase 2 and is unreachable: its only caller sits behind
      `_position_state_line`'s `if not pos_qty: return ""`. Confirmed in the
      data — **0 of 234** post-cutover rows are the flat class.
    - **Hypothesis KILLED before it cost a day: journal-only flat recall.**
      The obvious fix is to run the flat selection and journal it without
      showing the desk anything — obeying "journal-only" to the letter and
      multiplying journal volume ~50×. It is wrong, and the ladder must not
      re-run it: **a chunk the desk never read cannot be attributed to an
      outcome.** Those rows would carry variance with zero treatment effect
      and, pooled with the holding rows, would dilute the only real signal —
      the 08-09 mistake in a new costume. Flat recall is worth building only
      if the desk actually reads it.
    - **The corpus is NOT the shortfall.** Probed in-container against the
      live prod corpus before any code was written: the flat query returns
      **5 tier-1 hits in all four markets**, never falling through to the
      monitoring tier — crypto 7.81 / us-stock 7.83 / futures 7.39 / forex
      7.25 at the head, on `skill:reentry-discipline#5`,
      `skill:reachable-exits#1/#0`, `skill:mean-reversion-guard#0`. That is
      entry doctrine, correctly ranked, that the desk has never been shown.
      Recorded for (c): **every flat hit is a `lesson`; zero `outcome` chunks
      surface for the entry query**, unlike the give-back class where outcome
      chunks hold the head.
  - **2026-08-19 — increment (a7) SHIPPED: the entry decision can reach the
    corpus, behind `DESK_RECALL_FLAT` (default OFF).**
    `_recall_flat_line(run, pos_qty)` wired into `_compose_position_state`
    under its own brief token `recall_entry`, so entry-recall coverage is
    measurable from the decision event without reading prompts.
    - **Guarded on `pos_qty` as well as on the flag.** A holding cycle
      already recalls inside `_position_state_line`; reaching this path too
      would double-inject the block AND overwrite the journal row with a
      query that does not describe the decision made (mutation M2).
    - **No new scheme string, deliberately.** The POLICY is unchanged — the
      same head-fixed draw the giveback class has run since 08-10 — and only
      the population differs, which the row's `query` already names. Inventing
      a scheme label would falsely tell (c) that a different logging policy
      produced these rows, the mirror of the mistake (a6) versioned to avoid.
    - **Default OFF, and the reasoning is stated so it is not read as
      timidity or as carelessness.** (a6) defaulted ON because drawing among
      exact ties cannot loosen anything — safety by construction. **There is
      no such argument here:** this adds doctrine to a prompt that carried
      none, on the largest decision population the desk has. A prompt change
      of that blast radius is not for an unattended daily increment. The flag
      is an env var, so promotion needs a container restart, **not a deploy**.
    - **Promotion criterion, so the next session need not re-argue it:** set
      `DESK_RECALL_FLAT=1`, then after ≥200 flat rows confirm (i) entry
      action mix (`buy`/`short` vs `hold`) has not shifted by more than a few
      points against the 08-15..08-19 baseline, and (ii) the flat rows show
      ≥3 distinct pairs. On that evidence the (b) gate clears on the FLAT
      class alone within a day or two, at ~800 rows/day against the holding
      path's ~30.
    - Tests: `FlatRecallTests` (8) in `tests/test_run_engine.py`.
      **Mutation-checked ×7** — flag defaulted ON, holding guard removed,
      unwired from the composer, holding P&L passed so the query became the
      losing-class one, brief token renamed, function always silent, journal
      row not written. All seven killed.
    - **A defect the promotion must fix first, recorded rather than left to
      be discovered on prod.** (a5)'s contest note ends *"…NOT as a specific
      precedent for this position"*, and on a FLAT cycle there is no
      position. The wording is a holding-path artefact; it is harmless while
      the flag is off and must be made situation-aware before it is turned
      on. Deliberately NOT fixed here — the string is shared with the live
      holding path, and rewording it is a change to what the desk reads
      TODAY, which is not this increment.
    - **Confirmed on prod before shipping:** `DESK_RECALL_EXPLORE=1`, so flat
      rows will be journaled `eps-head-fixed-v1` with genuine ε variance the
      moment the flag is turned on — not a deterministic block that would
      repeat `crypto/losing`'s time-confounded shape.
    - **The trading judgment it will change:** whether to OPEN a position at
      all, and at what size — the decision the desk makes 774 times a day
      with no access to its own corpus. Today it changes nothing on prod,
      which is the honest statement: (a7) makes the entry decision
      *reachable*, and the promotion above is what makes it *reached*.
  - **2026-08-20 — increment (a8) SHIPPED: the contest note now describes
    the decision it is qualifying. The last code blocker on promoting
    `DESK_RECALL_FLAT` is cleared.**
    (a7) recorded this defect rather than fixing it: (a5)'s note closes
    *"…NOT as a specific precedent for this position"*, and on a FLAT cycle
    there is no position. Telling the desk to discount a tie against a thing
    it does not hold, in the one decision the note exists to inform, is not a
    cosmetic flaw — it is the note contradicting itself at the exact moment
    it is read.
    - **`_recall_contest_line(hits, cands, holding=True)`.** The flat clause
      reads *"…NOT as a specific precedent for the entry you are weighing"*;
      the disclosure half (count + the 1% band) is identical in both. The
      call site passes `holding=bool(pos_qty)`, which `_recall_flat_line`
      already supplies as `0.0`.
    - **The holding string is byte-identical, and the default is what makes
      it so.** That is the whole reason this could ship unattended while
      (a7) could not: `DESK_RECALL_FLAT` is confirmed unset on the prod
      worker today, so the changed branch is unreachable on prod and this
      deploy changes nothing the desk reads. A `holding=False` default would
      have silently switched the live wording — mutation M1, killed.
    - Tests: `RecallContestSituationTests` (4) +
      `RecallContestSituationWiringTests` (2, through the real corpus, one
      per branch) in `tests/test_run_engine.py`. **Mutation-checked ×7** —
      default flipped, call site pinned True, call site inverted, kwarg
      dropped, tails swapped, flat tail left claiming a position, band text
      dropped. All seven killed.
    - **The trading judgment it changes:** none today, stated plainly. It
      makes (a7)'s entry-recall block *correct* so that promoting it is a
      one-line env change rather than a change that ships a self-contradicting
      sentence into 99.7% of the desk's decisions.
  - **2026-08-20 — the (b) gate re-measured: it has STOPPED MOVING, and that
    is the finding.** Hypothesis going in: the gate creeps toward 2-of-2 as
    the fleet trades. Refuted. 236 rows, window 08-15T12:22Z → 08-20T07:10Z:

    | market/class | events | pairs | scheme | Δ vs 08-19 |
    |---|---|---|---|---|
    | crypto/giveback+winning | 77 | 10 | ε-head-fixed | **+1 / +0** |
    | crypto/giveback+losing | 66 | 1 | det → tie (1 ε) | +0 / +0 |
    | crypto/losing | 57 | 3 | det → tie (2 ε) | **+1 / +0** |
    | crypto/winning | 23 | 5 | ε-head-fixed | **+0 / +0** |
    | us-stock/losing, us-stock/gb+losing | 4, 4 | 1, 1 | det | +0 |
    | forex/gb+winning, us-stock/gb+winning | 3, 2 | 2, 2 | ε | +0 |

    - The amended gate (≥2 ε-scheme classes, each ≥30 events and ≥3 distinct
      pairs) is **still 1 of 2**, unchanged for a fourth day.
      `crypto/winning` is 7 events short and gained **zero** in 24h, so the
      honest ETA on the current supply is not "days" — it is **never**.
    - **The supply is collapsing, not merely slow.** Recall rows per day:
      124 (08-16), 25, 40, 11, **2** (08-20, against **622** decisions —
      0.3% coverage). Recall still fires on 100% of holding cycles; there are
      almost no holding cycles left to fire on.
    - **0 of 236 rows are the FLAT class**, and `DESK_RECALL_FLAT` is
      confirmed absent from the prod worker's environment. (a7) is live code
      on a dormant path, exactly as shipped.
    - Also still true, nine days on: **0 rows with empty `chunks`**. The
      control group (recalled, corpus returned nothing) does not exist and
      (b) must not be written assuming it will.
    - **Consequence for the ladder, so tomorrow does not re-derive it:** no
      further (a)-rung code can move the (b) gate. Everything reachable from
      the holding brief is instrumented, and the holding brief has run out of
      cycles. The gate opens on the FLAT population or it does not open.
      With (a8) the flat path is correct, tested and dormant; the remaining
      step is **`DESK_RECALL_FLAT=1` + worker restart — an environment
      change, not a deploy, and an OWNER decision**, because it adds doctrine
      to the prompt on 99.7% of the desk's decisions. The promotion criterion
      from (a7) stands unchanged: after ≥200 flat rows, confirm (i) the entry
      action mix (`buy`/`short` vs `hold`) has not shifted more than a few
      points against the 08-15..08-20 baseline and (ii) ≥3 distinct pairs
      appear. At ~620 flat cycles/day that is met in under a day.
  - **2026-08-21 — `DESK_RECALL_FLAT` PROMOTED TO ON on prod, by this session
    under explicit owner delegation ("you can make decision not owner" /
    "YOU = SOOPPIY AI", 2026-08-20). The entry decision now reads the corpus.**
    Env change on the worker only (`.env` + `compose up -d worker`), image
    unchanged at `20260820-rag-phase3-a8`; backup `.env.bak-recallflat-
    20260821-002238`. Reverts in seconds.
    - **Three hypotheses were tested and REFUTED before the flip. Recorded so
      no future session re-runs them:**
      - **H1 "a confidence gate is blocking entries."** REFUTED. `gate_source`
        is `confidence` on all 3,444 flat decisions — it is a CONSTANT and
        discriminates nothing. 243 flat decisions scored ≥0.65 and stayed
        `hold`; **4 of the 7 buys scored BELOW 0.65** (0.55, 0.56, 0.58,
        0.62). Confidence is not the discriminator.
      - **H2 "flat cycles are routed to a path that cannot enter."** REFUTED.
        All 3,444 flat cycles are `route: light` — **including all 7 buys**.
        The light route can and does open positions.
      - **H3 "the injected doctrine is bar-raising and will shut an
        already-shut door."** REFUTED as stated. The two chunks the flat query
        returns in all four markets are `skill:reachable-exits#1` (how to set
        a reachable stop/target IF you enter — execution guidance, not a
        veto) and `skill:reentry-discipline#5`, whose higher bar is
        CONDITIONAL on a same-symbol re-entry right after a locked win. At 4
        trades/day that condition is rare. This was the hypothesis that made
        this session first announce it would NOT flip; reading the actual
        payload refuted it.
    - **What the measurement DID establish — the finding that outranks the
      ladder.** On flat cycles the desk says `buy` **7 times in 3,444
      (0.20%)** and `short` **zero** times, over 08-15..08-20. Cross-checked
      exactly: FLAT 3,444 + HOLDING 236 = 3,680 total decisions, and HOLDING
      236 = the 236 recall rows, so recall coverage of the holding cycle is
      100% and of the entry cycle was 0%. Trades placed per day: 21, 38, 15,
      18, 10, **4**. The (b) gate is not starving because instrumentation is
      missing — **it is starving because the FLEET is**.
    - **Profit, stated first and with the outlier stripped** (`pnl_audit.py`
      ledger replay, the authoritative number): since 08-15 the book is
      **+$5.62**. Of that, **+$5.65 is 08-16 alone** — strip the largest
      contributor and it is **−$0.03**, and the last three days are −0.94,
      −1.14, −1.46. The desk's 97.4% selectivity is not banking anything; it
      is idling with a slow bleed.
    - **Why that inverted the decision.** The risk of injecting doctrine here
      was framed as "the desk enters even less". But the entries it is
      currently taking produced **−$3.54 over three days**. Fewer entries is
      not a measurable cost at this base rate; the asymmetry runs the other
      way, the (b) payoff is ~700 rows/day, and the flag reverts in seconds.
    - **The (a7) promotion criterion is WITHDRAWN as unmeasurable, and this
      is a correction to this ledger's own entry from hours earlier.** It
      required the entry action mix to stay "within a few points" of
      baseline. At a **0.20%** base rate, "a few points" is 10–50× the entire
      signal — a shift from 0.20% to 0.00% is ~1.4 events/day and cannot be
      distinguished from noise inside a day. Writing a criterion that cannot
      be evaluated is the 08-09 and 08-17 mistake a third time; it is retired
      here rather than quietly passed.
    - **Replacement criteria, both computable at the measured base rate:**
      1. **(b) gate (fast, ~1 day):** ≥2 ε-scheme classes with ≥30 events and
         ≥3 distinct pairs. Flat rows accrue at ~700/day under
         `eps-head-fixed-v1` (`DESK_RECALL_EXPLORE=1` confirmed on), so this
         is decidable on 08-21 data alone.
      2. **Harm (slow, ~5 days, one-sided):** baseline is **7 buys / 3,444
         flat cycles**. Over the NEXT 3,444 flat cycles count buys; 0/3,444
         against 7/3,444 is a one-sided binomial at p≈0.008. Any session
         reading this before 5 days have passed must report the count as
         INCONCLUSIVE rather than as reassurance.
      **Abort rule, fixed in advance:** revert `DESK_RECALL_FLAT=0` + restart
      the worker if buys reach 0 across a full 3,444-flat-cycle window, or on
      any recall-path traceback in the worker log.
    - Verified on prod after the flip: `_recall_flat_enabled()` True, flat
      line renders 807 chars, does NOT claim a position (the (a8) clause is
      doing its job on the live path), worker tracebacks 0.
    - **The trading judgment this changes, plainly:** whether to OPEN, and at
      what size — 3,444 decisions in six days that until today had no access
      to the desk's own entry doctrine.
  - **2026-08-21 — the entry decision is where the desk is stuck, and that is
    the next real work.** Not a RAG increment: `buy` 7/3,444 with `short` at
    zero, no mechanical block found (H1/H2 both refuted), and P&L flat-to-
    negative. Ranking the prompt better is optimising a desk that is barely
    trading. A future session should treat "why does the desk decline 97.4%
    of entries, and is that judgment correct?" as the profit question, with
    the 7 taken entries' outcomes as the first evidence.
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
