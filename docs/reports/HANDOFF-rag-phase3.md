# HANDOFF — Plan 22 Phase 3 daily build cadence

**Authority file for the `rag-phase3-daily-increment` scheduled task.** Written
2026-08-21 because the dev account rotates roughly every three days and the
Claude-side memory directory does not survive it. Anything a future session
must know lives HERE and in `docs/plan/22-desk-retrieval-rag.md` §7 — never in
account memory. (Standing rule: memory `monitoring-state-must-live-in-repo-md`.)

Read in this order:
1. `docs/reports/HANDOFF-automation-monitoring.md` — access, ship pipeline, traps.
2. `docs/plan/22-desk-retrieval-rag.md` §7 — the LEDGER. Never redo a done rung.
3. This file — where the ladder actually stands and what is owed.

---

## 1. First thing a new account must do

The scheduled task is a local Claude Code artifact and is **lost on account
rotation**. Re-create it:

- Name: `rag-phase3-daily-increment`
- Fires: daily 14:00 America/Los_Angeles (21:00 UTC)
- Path when present: `~/.claude/scheduled-tasks/rag-phase3-daily-increment/SKILL.md`

Its brief: advance Plan 22 Phase 3 by exactly ONE safe increment per day,
shipped to prod. Fresh worktree off `origin/main`, TDD, PR → CI → squash-merge
→ `scripts/deploy.sh` → verify on prod ×2 → dated line in §7 in the SAME PR.

---

## 2. Where the ladder stands (2026-08-21)

Rungs: (a) recall journaling → (b) attribution dataset → (c) shadow per-chunk
usefulness scores → (d) weighted retrieval behind a default-off flag.

| rung | state |
|---|---|
| (a) … (a8) | **ALL SHIPPED.** See §7 for each dated entry. |
| **(b)** | **UNBLOCKED as of 2026-08-21 — the gate is MET. This is the next increment.** |
| (c), (d) | not started; (d) is where a trading judgment actually changes |

### The (b) gate is MET — measured, not assumed

Gate (as amended 2026-08-17): **≥2 ε-scheme classes, each ≥30 events and ≥3
distinct chunk pairs.** It sat at 1-of-2 for four days. Measured 2026-08-21
~01:30Z, on flat rows alone, ~70 minutes after `DESK_RECALL_FLAT` was turned on:

| class | events | pairs | scheme |
|---|---|---|---|
| crypto / FLAT-entry | 95 | 5 | `eps-head-fixed-v1` |
| forex / FLAT-entry | 40 | 4 | `eps-head-fixed-v1` |
| crypto / giveback+winning | 77 | 10 | `eps-head-fixed-v1` |

Three ε classes clear the bar. **Build (b).**

> **RE-MEASURED 2026-08-21 08:0xZ on all 833 `recall` rows — the gate is
> MET more widely than the table above, but the pair count is PARTLY
> CONFOUNDED and (b) must not treat it as exogenous.**
>
> **Six** ε classes clear ≥30 events and ≥3 distinct pairs, not three:
> crypto/giveback+winning 104/14, crypto/FLAT 101/5,
> futures/giveback+winning 90/4, forex/giveback+winning 82/6,
> forex/winning 49/3, forex/FLAT 42/4.
>
> **The confound.** The deterministic (greedy) arm's distinct pairs occupy
> **perfectly non-overlapping time blocks** — crypto/giveback+winning is
> `9d8b125b+c8559767` 08-12→08-14, `0e7a7833+9b9cd916` 08-15→08-17,
> `9b9cd916+c72e011b` 08-17→08-18, `818d9f91+c72e011b` 08-19; zero overlap,
> and the same pattern in every class. That variation is **corpus drift,
> perfectly confounded with calendar time and market regime.** A per-chunk
> score computed over it measures the week, not the chunk. **Only
> ε-exploration-induced sets are attributable.**
>
> | class | events | explore rows | ε-induced novel sets |
> |---|---|---|---|
> | crypto / giveback+winning | 104 | 22 | 10 |
> | crypto / FLAT-entry | 101 | 28 | 4 |
> | futures / giveback+winning | 90 | 29 | 3 |
> | forex / giveback+winning | 82 | 20 | 4 |
> | forex / FLAT-entry | 42 | 11 | 3 |
>
> Five classes clear on exogenous variance alone, so **(b) stays
> unblocked.** Two binding constraints on how it is built:
> 1. The effective sample is the **explore arm** — 11–29 rows per class,
>    ~2–3 observations per novel set. Size every claim off that n, not off
>    the events column.
> 2. (b) must record the **deterministic block in force at each row's
>    timestamp**, and never compare an explore row in block 3 against a
>    deterministic row in block 1.
>
> **Also corrected:** the "measured ~01:30Z … ~70 minutes after the flat
> promotion" stamp above is wrong. The first flat `recall` row is
> 08-21T00:24:21Z and the flat decision rate is ~18/h, so at 01:30Z at most
> ~19 flat rows existed — 95+40=135 is arithmetically impossible then. The
> counts match a measurement taken ~07:4xZ (≈ the commit time of #503).
> **The gate verdict is unaffected; the timestamp is not evidence of
> anything and must not be cited as "the gate opened within the hour".**

**Do NOT pool the FLAT rows with the HOLDING rows.** They answer different
questions (whether to OPEN vs whether to cut/hold/bank) and the ledger has
twice been burned by pooling populations. Separate them by the `query` string:
flat rows contain `flat considering entry`, holding rows contain
`holding position`.

### Known properties of the dataset (b) will join

- Rows are `run_events.event_type='recall'`, emitted beside the `decision`
  event. **Query `run_events` by the `ts` column — there is no `created_at`
  and filtering on it fails silently.**
- Each row carries `query`, `scheme`, `propensity`, and `chunks[]` with
  `sha`/`kind`/`source`/`score`. `propensity` is logged ALWAYS (1.0 under the
  deterministic policy) — pooling ε rows with deterministic rows unlabelled
  would corrupt every off-policy estimate.
- **A cycle that recalled and got nothing emits `chunks: []`; a cycle that
  never recalled emits no row at all.** Collapsing those two makes the dataset
  unreadable. As of 2026-08-21, **0 rows have ever had empty `chunks`** — the
  control group does not exist. Do not write (b) assuming it will.
- Survivorship: `adapt realized` omits `run:N:flatten` closes. Use
  `service/server/pnl_audit.py` (ledger replay) for any P&L join, never a
  hand-written SQL sum. Memory: `realized-pnl-misses-forced-flattens`.
- Reward signal for (b) is **behaviour surrogates**, not per-chunk raw P&L —
  the latter is unidentifiable at our volume (power math in
  `docs/plan/22-phase3-learning-to-profit.md` §5). Raw NET P&L enters only at
  the (d) promotion gate.

---

## 3. Live prod state

- Image: `sooppiy-backend:20260821-rag-flat-on`, from `761f9855`.
- `DESK_RECALL_ENABLED` default on · `DESK_RECALL_EXPLORE=1` · **`DESK_RECALL_FLAT=1`** (set 2026-08-21T00:22Z).
- **`DESK_REACHABILITY_AB=1` — LIVE since `2026-08-21T09:42:01Z`.**
  **THAT TIMESTAMP IS THE READOUT WINDOW START (`<flip-ts>` in §4b). Do not
  count a single decision before it.** Backup `.env.bak-reachab-20260821-094150`.
  Prod image `sooppiy-backend:20260821-reachability-ab` from `44ce164`.

  Rollback, no deploy and no image change:

  ```
  ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202
  cd /home/ec2-user/sooppiy
  sed -i 's|^DESK_REACHABILITY_AB=.*|DESK_REACHABILITY_AB=0|' .env
  docker compose --profile prod up -d --no-build worker
  ```
- Both flags live in `/home/ec2-user/sooppiy/.env`, so they survive a deploy.
- Backups: `.env.bak-recallflat-20260821-002238`, `.env.bak-20260821-013137`.

### Rollback for the flat promotion

```
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202
cd /home/ec2-user/sooppiy
sed -i 's|^DESK_RECALL_FLAT=.*|DESK_RECALL_FLAT=0|' .env
docker compose --profile prod up -d --no-build worker
```

No deploy and no image change required.

---

## 4. Open measurement obligations — DO NOT report these as settled

### 4a. The harm test on the flat promotion is INCONCLUSIVE until ~2026-08-26

Pre-flip baseline: **7 buys / 3,444 flat cycles (0.20%)**, `short` zero, over
08-15..08-20. The test is one-sided: over the NEXT 3,444 flat cycles, count
buys; 0/3,444 against 7/3,444 is a binomial at p≈0.008.

At ~01:30Z on 08-21 the count was **135 flat cycles, 133 `hold` + 2 `retire`,
0 buys**. The baseline predicts ~0.27 buys in 135 cycles, so **zero buys is
exactly what "no effect" looks like.** Any session reading this before the
window fills must report INCONCLUSIVE, never reassurance.

> **⚠️ CORRECTED 2026-08-21 08:0xZ — THIS TEST CANNOT ANSWER ITS OWN
> QUESTION, for two reasons, and both are worse than the one above.**
>
> **(i) The baseline population is wrong** — it counts only `buy` and so
> omits every short. See the §6 correction below: the true flat-cycle
> entry-intent baseline is **62/3,445 = 1.80%**, not 7/3,444 = 0.20%. On
> the corrected rate, 0 intents in 144 post-flip flat cycles is
> P(0) = 0.982^144 ≈ **0.073** — inconclusive, but ~8× more suggestive
> than "~0.27 expected" implies.
>
> **(ii) The baseline is NOT STATIONARY.** The entry rate was already
> collapsing before the flip — 08-15 7.77%, 08-18 0.86%, 08-20 0.44% —
> because of a separate cause (see §6). Against 08-20's own rate the same
> zero gives P(0) ≈ **0.53**, i.e. nothing at all. **A one-sided test
> against a pooled six-day rate cannot separate `DESK_RECALL_FLAT`'s
> effect from the pre-existing collapse.** Any session that reports this
> test as passing or failing is reporting an artifact.
>
> What IS measured and clean: the flag is mechanically healthy —
> **143/143** flat decisions carry a `recall` row (crypto 101 + forex 42,
> matching decisions per market exactly), **0** rows with empty `chunks`,
> **0** tracebacks in 8h. The traceback abort condition is not triggered.

**Abort rule, pre-committed:** revert `DESK_RECALL_FLAT=0` if buys reach 0
across a full 3,444-flat-cycle window, or on any recall-path traceback.

### 4b. The old (a7) criterion is WITHDRAWN — do not resurrect it

It required the entry action mix to stay "within a few points" of baseline. At
a **0.20%** base rate a few points is 10–50× the entire signal, so it can
never be evaluated. Writing a criterion that cannot be evaluated is the
08-09 and 08-17 mistake; it was retired on 08-21, not quietly passed.

---

## 4b. THE LIVE EXPERIMENT — `DESK_REACHABILITY_AB` (pre-registered 2026-08-21)

The entry collapse (§6) is traced to #484's reachability disclosure on
**observational** evidence. The owner's experimental-mindset rule forbids
shipping a fix on that, so what shipped is the **experiment**.

**Mechanism.** `run_engine._reachability_ab_arm(run_id)` returns `treat` or
`control`. Default **OFF** ⇒ every run is `treat`, prod behaviour unchanged.
When `DESK_REACHABILITY_AB=1`, odd `run_id` → `control` (no disclosure), even
→ `treat`. Deterministic in the id, never in the clock — a run that flipped
arm mid-life would contaminate its own history. An unusable id fails **toward
treatment**, because losing the line is the change under test and keeping it
is the status quo. Every `decision` event journals `reach_ab`.

**Scope, and why it is enough — measured, not assumed.** Only the LIGHT path
is gated (`run_engine._light_analysis`). Counted on prod 2026-08-21 over
08-15 → now: **3,595 flat decisions and 236 holding decisions, and every
single one is `route: light`** — the escalated `full` path has taken **zero**
cycles in that window. So the light path is not merely the entry population,
it is the whole decision population, and leaving
`analysis_agents._trader_risk_decision` ungated contaminates nothing. Its
signature is unchanged as a result. **If the router starts escalating again,
re-check this before trusting a readout** — a `full`-routed cycle would show
the disclosure to a control-arm run.

### Pre-registered readout — write it down BEFORE looking

**Window start: `2026-08-21T09:42:01Z`.** Anything earlier is journalled
`treat` because the flag was off, and pooling it with the live treatment arm
would silently inflate `treat`'s n with pre-experiment cycles.

**Primary metric:** flat-cycle entry-intent rate per arm =
`(action IN ('buy','sell')) / flat decisions`, crypto only, where a flat
decision is `payload LIKE '%"entry_rail"%'`. **Count `sell` — it is the short
verb; see §6.** Split on the `reach_ab` field, never on run-id parity
recomputed later (the flag may be toggled).

```sql
SELECT JSON_UNQUOTE(JSON_EXTRACT(re.payload,'$.reach_ab')) arm,
       COUNT(*) cycles,
       SUM(JSON_UNQUOTE(JSON_EXTRACT(re.payload,'$.action')) IN ('buy','sell')) intents
FROM run_events re JOIN trading_runs tr ON tr.id = re.run_id
WHERE re.event_type='decision' AND re.ts >= '<flip-ts>'
  AND re.payload LIKE '%"entry_rail"%' AND tr.market='crypto'
GROUP BY arm;
```

**Power, computed not guessed** (two-proportion, α=0.05, 80%), against the
treat arm's measured 1.23%:

| if control returns to | n per arm | days at ~120 crypto flat cycles/arm/day |
|---|---|---|
| 5.83% (the full PRE rate) | **252** | ~2 |
| 3.50% (half recovery) | 703 | ~6 |
| 2.50% (weak) | 1,781 | ~15 |

**Decision rule, pre-committed:**
1. First readout at **n ≥ 252 per arm**. Significant ⇒ #484's disclosure is
   causally suppressing entries, and the fix is designed from there.
2. Not significant ⇒ continue to **n ≥ 703 per arm**. Still not significant
   ⇒ report **the effect is ABSENT**, not "unproven", and #484 is exonerated
   — the entry collapse then has another cause and §6 must be reopened.
3. **Do not peek-and-stop.** Reading out at every cycle and stopping on the
   first favourable p-value is how this ledger would manufacture its own
   result. Two readout points, both listed above, and no others.

**Safety, also pre-committed.** The control arm REMOVES a truthful
measurement, so it can reinstate exactly the defect #484 fixed (authored
`target_pct` median 4.80% against a book that had never peaked above ~1%).
Secondary metrics, reported with the primary and never instead of it:
authored `target_pct` median per arm, and realized P&L per closed run per
arm via `pnl_audit.py` (never a hand-written sum — `adapt realized` omits
`run:N:flatten` closes).

**Abort — revert `DESK_REACHABILITY_AB=0` immediately if either fires:**
- any traceback on the recall/reachability path, or
- control-arm cumulative realized P&L trails the treat arm by more than
  **$5** once the control arm has **≥10 closes**.

No deploy is needed to abort — the flag lives in
`/home/ec2-user/sooppiy/.env`; `sed` it to 0 and
`docker compose --profile prod up -d --no-build worker`.

**What a null result would mean.** It would refute the strongest observational
finding this cadence has produced (z=4.43, p=9.5e-6, rival refuted and
inverted). That is the point — a measurement that cannot embarrass its author
is not an experiment.

---

## 5. Hypotheses already killed — do not re-run them

| hypothesis | verdict |
|---|---|
| journal-only flat recall (log without showing the desk) | **refuted 08-19** — a chunk the desk never read cannot be attributed to an outcome; manufactures variance with zero treatment effect |
| (a6) volume projection: `crypto/losing` joins the gate "on volume alone" | **refuted 08-19** — the shortfall was COVERAGE, not activity |
| a confidence gate blocks entries | **refuted 08-21** — `gate_source` is `confidence` on all 3,444 flat decisions (a constant); 243 scored ≥0.65 and stayed `hold`, and 4 of the 7 buys scored BELOW 0.65 |
| flat cycles route to a path that cannot enter | **refuted 08-21** — all 3,444 are `route: light`, including all 7 buys |
| the injected entry doctrine is bar-raising and shuts an already-shut door | **refuted as stated 08-21** — `reachable-exits#1` is execution guidance; `reentry-discipline#5`'s higher bar is CONDITIONAL on a same-symbol re-entry after a locked win |

---

## 6. The finding that outranks this ladder

**The desk has nearly stopped trading, and the ladder was starving because of
that, not because of instrumentation.**

- ~~On flat cycles the desk says `buy` **7 times in 3,444 (0.20%)**, `short`
  zero.~~ **WRONG — CORRECTED 2026-08-21. The `short` zero is a STRUCTURAL
  ARTIFACT and the 0.20% understates entry intent by 8.7×.**
  - The decision prompt fixes the schema at `{"action": "buy"|"sell"|"hold"}`
    (`run_engine.py:5919`), and the `decision` event is emitted at **line
    6572** while the futures `sell`→`short` remap runs at **line 6775**.
    The event is written BEFORE the remap. **`short` can never appear in a
    `decision` payload** — all-time, 5,103 rows: `hold` 4668 / `sell` 239 /
    `buy` 128 / `retire` 68 / **`short` 0**. Meanwhile `signals` carries
    **48 `short` opens all-time.** Counting a token the schema forbids and
    reporting the zero as behaviour is the error.
  - **Corrected, 08-15 → 08-21 08:0xZ, n = 3,588 flat decisions:** `sell`
    (→ short on a futures book) **55 → 36 executed**, `buy` **7 → 6
    executed**; entry intent **62 = 1.73%**, executed **42 = 1.17%**;
    `hold` 3,498, `retire` 28. **86% of executed entries are SHORTS.**
    Read `signals.side`, never the decision action, to count entries.
- Cross-checked exactly: FLAT 3,444 + HOLDING 236 = **3,680** total decisions,
  and HOLDING 236 = the 236 recall rows. Holding-cycle recall coverage was
  100%; entry-cycle coverage was 0% until 08-21, now 100%.
- Trades placed per day 08-15→08-20: 21, 38, 15, 18, 10, **4**.
- Realized P&L since 08-15 (`pnl_audit.py`, authoritative): **+$5.62** — of
  which **+$5.65 is 08-16 alone**. Strip the largest contributor: **−$0.03**.
  Last three days: −0.94, −1.14, −1.46.

Per the owner's profit law, this outranks retrieval ranking.

### ✅ 2026-08-21 — that profit question is ANSWERED to the limit of observation

**The entry engine did not slow down. It was switched off at a deploy
boundary.** Full working in the 2026-08-21 cycle note, §§3-7.

- **Level shift, not a trend.** Crypto flat entry-intent rate, 6h buckets,
  split at the `20260818-ai-first-batch` image build (**08-18T11:49:34Z**):
  PRE 33/566 = **5.83%**, POST 8/649 = **1.23%**. Two-proportion
  **z = 4.427, two-sided p = 9.5e-6**; exact binomial P(≤8 in 649 at the
  PRE rate) = **2.3e-9**. The ten PRE buckets oscillate around 5.8% with
  **no downward trend**; POST decays to zero.
- **Confirmed from a second table and a second definition** — executed
  opens from `signals`: PRE **0.368/h** (22 in 59.8h) → POST **0.102/h**
  (7 in 68.5h). Last executed open **08-20T06:40:29Z**.
- **The batch delta is four commits.** #483/#486 docs; **#485 is an EXIT
  rail**; **#484 is the only entry-side behavioural change** —
  `desk_record.record_line()` wired into both bracket prompts.
- **The desk quotes it.** All 15 crypto flat cycles scoring confidence
  ≥0.65 on 08-21 said `hold`; **11 of 12** give one reason, in
  `record_line()`'s own vocabulary — *"the required stop is too wide
  relative to the expected move, yielding negative expectancy"*,
  *"historical reachability limits"*, *"the expected 4% move exceeds
  observed historic upside"*. The line ends: *"Judge whether this trade
  is worth taking at all."*
- **Confidence and action DECOUPLED.** Avg confidence rose 0.499 → 0.563
  and the ≥0.65 share rose 5.8% → 14.4% while entries fell 16 → 0.

**Rivals refuted, do not re-run:**

| hypothesis | verdict |
|---|---|
| the tape went quiet — declining is correct | **REFUTED AND INVERTED.** Same 17 symbols in both arms, deploy day excluded: per-cycle absolute move PRE median **0.140%** → POST **0.291%**, mean 0.210% → **0.499%**, p90 0.444% → **1.044%**. Volatility roughly **DOUBLED** as entries went to zero. The POST median move now EXCEEDS the p75 (0.33%) ceiling the desk is shown — **the disclosure is stale against its own live tape** |
| the record ratcheted more pessimistic | **REFUTED** — it improved: n 26→33, best 0.969%→**1.438%**, never-positive 42%→**39%** |
| population mix diluted the rate | **REFUTED for crypto**, the entire entry engine — its own rate fell 7.77% → 0.86% → **0.00%** on stable run and cycle counts |

**What this does NOT establish.** It is **observational, not an
experiment** — per the owner's experimental-mindset rule the next
increment is the EXPERIMENT (a per-run randomised A/B on the reachability
line, default-off), never a naive revert. #484 was itself shipped on a
real measurement (authored `target_pct` median 4.80% against a book that
had never peaked above ~1%); reverting reinstates that defect. And the
profitable tape is thin: +9.16 over the three high-activity days is **2
days**, and stripping each day's largest contributor leaves ≈ **+0.10**
on n = 42 opens. **"Trading more makes money" is NOT established.**

---

## 7. Traps this cadence has actually hit

- **Docs are not in the container image** (only `service/` is). Verify a
  shipped doc at `/home/ec2-user/sooppiy/app/docs/...` on the box, not inside
  the container.
- **The full backend suite takes ~12 min locally and ~24 min in CI.** Never
  run two copies at once — on 08-20 two concurrent runs contended and crawled
  to 26% in 25 minutes; killing one took the survivor to 100% in minutes.
- **`| tail -N` on a backgrounded pytest loses all output** if the process is
  killed. Redirect to a file instead.
- **`rm` is aliased on this machine**; use `/bin/rm` in cleanup scripts.
- **Deploy from a fresh worktree needs `npm ci` in `marketing/` first**, or
  the marketing build step fails.
- Owner rule: clean up every temp artifact — worktrees, tarballs, scratch
  files, box `/tmp` debris — in the same session.
