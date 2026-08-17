# Takeover brief — Sooppiy automation monitoring loop

**Written 2026-08-17 21:46Z, at the end of a ~22-hour session, for the next
Claude account.** The account rotates every ~3 days and everything on the
Claude side (memory dir, crons) is lost. This file and the ones it points to
are the only durable state.

> **Read order for the incoming session:**
> 1. `HANDOFF-automation-monitoring.md` — the standing authority: cadence,
>    access, ship pipeline. **It outranks memory.**
> 2. `HANDOFF-n-slot-monitoring.md` — the n-slot fleet rules (§7b the AI is
>    the final author of every order; §7c two-axis attribution; §7e the
>    two-subagent rule).
> 3. **This file** — what is true *right now*, what shipped, what is still
>    open, and the traps that cost me hours today.
> 4. `2026-08-17-automation-monitoring.md` — today's cycle notes, newest
>    first. Read the 24-HOUR VERIFICATION SWEEP section at minimum.
> 5. `recommendations-backlog.md` — evidence-gated queue.

---

## 1. The job, in one paragraph

Every ~30 minutes, observe the live auto-trading fleet on **sooppiy.com prod**
and improve it. **Monitor only — never create, stop, or modify fleets, runs,
or trades.** The daemon trades; you analyse and ship code. When a trade
closes, dispatch two subagents (A = AI/desk-authored, B = algorithm/rail-
authored) and cross-check them. Append a cycle note, refresh the snapshot,
commit. Batch a docs PR periodically — **notes only reach the RAG corpus
after merge AND deploy.**

## 2. Binding owner laws — quote them, do not paraphrase

**On analysis (2026-08-13):**

> "Do not make excuses, do not delude yourself into thinking your analysis is
> always correct, and do not justify losses with flawed logic; instead,
> always analyze the reasons behind the outcome of every trade. The ultimate
> goal of all analysis is profit or loss; conduct your analysis with that in
> mind."

**On method (2026-08-17, newest):**

> "all Analysis thinking about experiment ( Must be thinking Experimental
> mindset ) — also Implement by Experimental result"

Operationally, that second rule means: state the hypothesis and its falsifier
*before* the data; design the measurement so it can refute you; **implement
only on an experimental result**; **re-measure the same quantity after
shipping** and report a fix that moved nothing as FAILED; and name the n,
reporting figures with and without the largest contributor.

Both are written into `CLAUDE.md`. Also there: **verdicts are stated in
profit-or-loss terms first**, and **a favourable delta on a loss is not an
improvement.**

## 3. State as of 2026-08-17 21:46Z

| | |
|---|---|
| target | `info@askkpop.com` — user 5 / agent 6 / **fleet 35** |
| running image | `sooppiy-backend:20260817-railed-brief` |
| fleet 35 | **10 of 14 slots filled**, `n_runs=14`, budget $10,009.35, active |
| agent 6 running runs | 9 |
| **open positions** | **0** |
| closed legs since the 08-15 09:00Z reset | 42 |

**Realized P&L (`pnl_audit`, authoritative):**

| UTC day | ledger | resid | flat |
|---|---|---|---|
| 2026-08-15 | −3.42 | 0.00 | 3 |
| 2026-08-16 | +5.65 | 0.00 | 3 |
| 2026-08-17 | **+3.84** | −0.01 | 4 |
| **total since reset** | **+6.07** | | |

**The shape matters more than the total.** Of 39 legs measured at cycle 18,
the top 3 were 95% of everything and the median leg was **+$0.0093** — under
a cent, against round-trip fees of $0.04–$0.43. **36% of legs finish inside
their own fee.** And the single largest contributor traces to a sizing
defect (`order_params: absent` → default sizing, 8.2× the desk's own habitual
size), not to skill.

## 4. Access

```
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202
docker exec noesis-mysql mysql -usooppiy -p<PASSWORD> sooppiy -N -e "SQL"
docker exec -w /app/service/server sooppiy-worker python -m pnl_audit --since <YYYY-MM-DD>
```

**The DB password is NOT in this repo and must not be added** — gitleaks
scans it. It arrives in the owner's cron prompt each cycle; take it from
there.

Deploy: `./scripts/deploy.sh <tag>` **from the `wt-recall` worktree**, never
from the primary working tree (which sits on a branch with no `scripts/`).
Deploy rebuilds **from main**, so anything unmerged is lost — always verify
the feature in the running container afterwards.

## 5. Traps that cost me hours today — read this section twice

**SQL / data:**

| trap | consequence |
|---|---|
| `run_events` has **`ts`**, not `created_at` | filtering on `created_at` errors or silently returns nothing |
| `signals.created_at` is an ISO string with `T`/`Z` | comparing to `"2026-08-17 00:00:00"` (space form) silently matches the **whole day**, because `'T' > ' '` |
| **On a CLOSING `signals` row, `entry_price` is overwritten with the exit price** | every computed move comes out **exactly 0.00%** — looks like a clean null result, is a bug. Take entry from the OPENING row (`exit_price IS NULL`) |
| `CONCAT()` with any NULL returns NULL | the row **vanishes** from output; use `CONCAT_WS`/`COALESCE`. A silently missing row is how a missed close looks |
| the DB wrapper mangles a quoted `IN ('a','b')` list | filter in Python or use `?` placeholders |
| `dec` is a reserved word in MySQL | `AS dec` is a syntax error |
| payloads contain bytes that make `grep` treat output as binary | pipe through `mysql -N \| tr -d '\000'` |
| an **unquoted** ssh heredoc (`<<PYEOF`) | the shell eats `$.json.paths`; use `<<"PYEOF"` |
| `positions` holds only OPEN positions | you cannot survey historical brackets from it |
| `positions.quantity` is **signed** | uPNL = `(current_price − entry_price) * quantity`, never × a side sign |
| `signals.pnl` nets **only the closing fee** | true net = `pnl − open_fee`. **Always state true net.** Cross-check `trading_runs.realized_pnl_usd` |

**Method traps I actually fell into:**

1. **A clean null is a smell, not a result.** Two of my measurements returned
   perfect zeros because the *method* excluded the population under test
   (no-verdict cycles emit no `order_intent`, so matching decisions to
   `order_intent` dropped exactly the cases being counted). Check that your
   denominator can contain the thing you are looking for.
2. **Don't split by a criterion derived from the outcome.** I once compared
   "minutes containing a failure" against minutes outside them and got 0%
   outside — a tautology.
3. **A true number can carry a false inference.** `0 of 210 runs closed on a
   take-profit` was true; "take-profit is dead code" was false — the watcher
   exists and the level is set, it is simply unreachable. Read the code
   before concluding from a count.
4. **Local CI replication does not outrank real CI once CI is readable.** I
   blocked a merge for two cycles on a local `pip-audit` result that CI
   contradicts. During a provider outage, replicate locally as merge evidence
   — but re-check against CI the moment reads recover.
5. **A probe of a mutating endpoint is a mutation.** I tested whether GitHub
   writes had recovered by POSTing a PR and created a junk PR.
6. **Commit before mutation testing.** `git checkout --` wipes uncommitted
   work.
7. **Mutants that survive are usually a weak test, not an equivalent one** —
   but sometimes they really are equivalent. I proved one equivalent by
   differential-testing 490 truncation points rather than asserting it.

## 6. What shipped 2026-08-17 — with honest status

Eleven PRs. **Two of them moved nothing and must not be described as
working.**

| PR | change | status |
|---|---|---|
| #459 | `_no_verdict_diagnostic` — why a light cycle produced no verdict | **worked** — produced the timeout answer |
| #460 | loss floor reads `run_budget_usd` from `cfg`, not the run row (it was **always $0.99** for 4 days; 20/20 runs misjudged) | **correct, but 0 fires all day — UNEXERCISED, not working** |
| #462 | salvage a truncated verdict instead of discarding it | **worked** — 10 fires |
| #463 | a silent cycle records no `plan_adherence` (63% of "revised" stamps were fabricated) | **worked** — 15 silent cycles correctly unstamped |
| #465 | split `error` from `empty` | superseded within a cycle by #466 |
| #466 | `no_response` — a provider failure is not a silent model | **worked** |
| #468 | decision-tier LLM timeout 120s → 300s | **FAILED** — rate went 18.5% → 23.1%; the later fall was the episode ending, not the fix |
| #471 | **R:R ceiling** — caps `target_pct` at 3× stop | **P&L effect $0.00** — all 4 fires landed on `action=hold`, which compiles to `steps: []`; the clamp is discarded |
| #472 | `classify_arm` protective/defensive + `arm_level_implausible` | deployed; **nothing consumes the label yet** |
| #473 | `_railed_params_line` — tell the desk what a rail changed | deployed 21:22Z; **test not yet run** |
| — | docs PRs | merged |

## 7. Hypotheses tested today, with verdicts

| # | hypothesis | verdict |
|---|---|---|
| H1 | my probing caused the no-verdict spike | **refuted** — the worst hour predates every probe |
| — | the LLM host is ~5× oversubscribed | **RETRACTED** — CI passes; local latency re-measured at 3.9–7.0s → 0.29× |
| H2 | panel-fallback exits realize worse | **refuted** — mean −$0.263 vs −$0.802 for others |
| H3 | P&L is dominated by outliers; median leg is a fee-scale scratch | **confirmed** — ex-top-3 = +$0.46 over 36 legs |
| H4 | the entry fee-hurdle ratio predicts scratches | **refuted** — medians 34.8 vs 36.6; **kills the "raise min_edge" remedy** |
| H5 | `target_pct` is a gate-satisfying number, not a forecast | **supported** — r² 0.024, 0/36 targets ever reached |
| H6 | targets were sound but cut off by early exits | **refuted** — only 4/34 reached even given the run's OWN full horizon, and **all four were ≤2.00%** |
| H7 | the market does not offer what the R:R gate demands | **confirmed** — available excursion median **1.14%**, p75 1.89%, max 4.24% vs a median target of 4.55%; offered on **1 leg in 28** |
| H8 | a tighter (stop, target) pair has better expectancy | **refuted** — the tight band is the WORST (16–17 of 30 stop out). Best pair keeps the stop and cuts the target |
| H9 | no-verdicts concentrate on held books | **confirmed** — 9.23% held vs 2.82% flat |
| H10 | that excess is just shared host load | **refuted** — 3.33× *within the same hours* |

## 8. Open, evidence-gated

1. **Ratchet defect (a) — fix it ALONE, first.** `_breakeven_floor_hit` takes
   no `baseline_pnl` while its sibling `_trailing_lock_hit` does. Recomputing
   run 1335: fixing (a) alone **suppresses the fire and saves +$0.1414**;
   fixing (a)+(b) together does **not**. This reverses an earlier spec of
   mine — (a) governs *whether it arms*, the floor governs *what happens once
   armed*. Ratchet record: **3 fires, −$0.252934, zero net gains.**
2. **`RR_CEILING=2.0`** — the shipped default is 3.0 and inert against
   existing cases by design; 2.0 is H8's measured optimum but contradicts
   nine existing tests encoding earlier deliberate decisions. **Config
   change, owner's call.**
3. **The ceiling never reaches an order** — every fire so far is on a `hold`
   cycle. Until one lands on a buy/sell, its effect is $0.00.
4. **43% of arms (57/134) fire on the losing side of breakeven.** The label
   now exists; nothing consumes it.
5. **`plan_adherence` measures obedience, not viability** — a "followed"
   stamp certified a plan needing 4% in 2 hours in a 0.94% tape.
6. **Fleet slot ledger over-commits**: 10 filled slots hold 99.9% of budget
   while empty slots are stamped $400 each; headroom $9.79 against a $200
   floor. **Blocked on the book-size expectancy replay.**
7. `_order_discussion` **fails open** — 10 closes/reduces authored by a path
   labelled "not the AI". **Governance item; the P&L argument was refuted.**

## 9. Standing watches — corrected values

* **empty-why arms: 133/134 (99.3%)**, not the "n=6" older notes carry.
* **arm-reachability spec: STRUCK** — levels sit 0.1–1.5% from entry; the
  problem was never placement.
* `#446` unit-slip: 8 fires. **It rails `order_params` percentages and does
  NOT cover arm levels** — run 1297 armed at 44700.00 against an entry of
  44.09.
* `#439` BYPASSED: still unexercised.
* AUDCHF 1147 and fleet 33: both **stopped** — drop them.
* Mark cadence is **~5 minutes** (`POSITION_REFRESH_INTERVAL=300`), while
  `_mark_staleness_max()` is 900s — so `mark_age_ok` never trips on ordinary
  5-minute blindness. Exit rails effectively run at 5-minute resolution.

## 10. The one number to re-check first

`_railed_params_line` (#473) deployed at **21:22:13Z**. Its "before" is on
tape: **run 1375 requested `target_pct` 3.02% three times in 95 minutes**
(17:56, 18:27, 19:30) while receiving 1.41 / 1.425 / 1.44, because rail notes
never reached the prompt.

**Test:** on the next run that gets a clamp, does the *requested* target
change after the line renders? `railed_params` should appear in the decision
`brief` array. **If requests do not move, report the line as FAILED** — the
same treatment #468 got.
