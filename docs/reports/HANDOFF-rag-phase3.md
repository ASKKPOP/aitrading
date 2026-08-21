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

**Abort rule, pre-committed:** revert `DESK_RECALL_FLAT=0` if buys reach 0
across a full 3,444-flat-cycle window, or on any recall-path traceback.

### 4b. The old (a7) criterion is WITHDRAWN — do not resurrect it

It required the entry action mix to stay "within a few points" of baseline. At
a **0.20%** base rate a few points is 10–50× the entire signal, so it can
never be evaluated. Writing a criterion that cannot be evaluated is the
08-09 and 08-17 mistake; it was retired on 08-21, not quietly passed.

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

- On flat cycles the desk says `buy` **7 times in 3,444 (0.20%)**, `short` zero.
- Cross-checked exactly: FLAT 3,444 + HOLDING 236 = **3,680** total decisions,
  and HOLDING 236 = the 236 recall rows. Holding-cycle recall coverage was
  100%; entry-cycle coverage was 0% until 08-21, now 100%.
- Trades placed per day 08-15→08-20: 21, 38, 15, 18, 10, **4**.
- Realized P&L since 08-15 (`pnl_audit.py`, authoritative): **+$5.62** — of
  which **+$5.65 is 08-16 alone**. Strip the largest contributor: **−$0.03**.
  Last three days: −0.94, −1.14, −1.46.

Per the owner's profit law, this outranks retrieval ranking. A future session
should treat **"why does the desk decline 97.4% of entries, and is that
judgment correct?"** as the profit question, with the outcomes of the 7 taken
entries as the first evidence. Ranking a prompt better optimises a desk that
is barely trading.

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
