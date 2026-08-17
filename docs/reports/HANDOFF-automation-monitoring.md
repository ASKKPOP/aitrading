# Handoff — Sooppiy automation monitoring loop

> ## ⚠️ THIS FILE IS THE AUTHORITY. READ IT FIRST, FOLLOW IT.
>
> **Owner rule 2026-08-05: the Claude account is rotated every ~3 days.**
> Everything on the Claude side — the `~/.claude/.../memory/` directory and
> every cron (session-only) — **is lost on rotation.** Nothing there can be
> load-bearing.
>
> Therefore this repo's markdown files are the only durable state:
>
> | file | role |
> |---|---|
> | **this file** | operating rules, cadence, access, ship pipeline, open decisions, traps |
> | `YYYY-MM-DD-automation-monitoring.md` | per-UTC-day cycle notes, newest-first |
> | `automation-snapshot.json` | machine-readable state carried between cycles |
>
> **Rules for every session:**
> 1. Read this file top to bottom **before the first cycle**. Do not rely on
>    recalled memory — it may be from a rotated account, or stale.
> 2. **Keep this file current as the work happens.** Any new rule, finding,
>    open decision, watch item, cadence change or trap is written HERE in
>    the same session it is learned. If it exists only in memory, it is lost.
> 3. When memory and this file disagree, **this file wins.**
> 4. **Re-arm both crons at the start of every session** (§1) — they never
>    persist.
>
> ### 📄 TAKEOVER BRIEF — 2026-08-17
>
> `HANDOFF-TAKEOVER-2026-08-17.md` is the point-in-time handover written at
> the end of the 2026-08-17 session: current fleet state, the eleven PRs that
> shipped that day **with honest status** (two of them moved nothing), the
> ten hypotheses tested and their verdicts, the evidence-gated backlog, and
> the SQL/method traps that cost that session hours. **Read it after this
> file and before the first cycle.**

> ### ▶️ LOOP RESUMED — 2026-08-06 23:30Z (owner), NEW GROUND STATE
>
> The owner reset the balance to **1000** and cleared all history. Fleet 28
> rebuilt: runs **980 SOLUSDT, 981 SI, 982 BTCUSDT, 983 ETHUSDT, 984 HG,
> 985 ZC**, agent 6 seed 1000.
>
> **Owner's words that now govern the desk (verbatim):**
> - *"We must be make solution for get a profit ( It's our destiny and purpose )"*
> - *"MUST BE THINKING DEEPLY and do not make change lost profit"*
> - *"Sooppiy AI analysis each run 30 min ( make time gap each )"*
> - *"if got more -0.99 then clean that RUN. and make RUN again by AI Analysis"*
>
> **Shipped in response — PR #269, prod image `20260806-mandate30`:**
>
> 1. **The mandate is now the first line of every decision prompt.** The
>    skills `_HEADER` previously framed the whole block as a brake (*"they may
>    make you MORE cautious"*) and never said what the desk is FOR. It now
>    opens: `YOUR PURPOSE IS REALIZED PROFIT — not activity, not being right,
>    not holding on. THINK DEEPLY before every decision, and NEVER LET A GAIN
>    YOU HAVE TURN INTO A LOSS: banked beats bigger.`
>    *"REALIZED"* and *"not activity"* are deliberate: a bare "make profit"
>    would push toward more trades, and three runs have been underwater from
>    their entry fee alone.
> 2. **`RUN_INTERVAL_CAP_MIN` (default 30)** caps how long a live run may go
>    unanalysed — applied at SCHEDULING time, so no run's `config_snapshot_json`
>    is rewritten (that belongs to the desk).
> 3. **Per-run slots on an absolute grid.** Offsets `(run_id * 7) % interval`
>    → runs 980-985 sit at minutes **20, 27, 4, 11, 18, 25**.
>
> **⚠️ TRAP worth keeping: a relative elapsed test can never break lockstep.**
> Six runs shared `last_cycle_at = 22:57:00`. `elapsed >= interval` cannot
> separate them, because once a full interval has passed the slot has ALWAYS
> advanced too — the two conditions collapse into one and every run keeps its
> inherited phase forever. The fix needs ONE early fire (floored at half an
> interval) to snap a run onto its own slot.
>
> **⚠️ TRAP: changing the scheduler silently invalidates skill text.** The arm
> skill sizes reachable levels by quoting its own cycle gap ("~45 minutes").
> Moving to 30 would have left the desk sizing arms 1.5x too far — silently.
> It now tracks `run_engine.INTERVAL_CAP_MIN`, bound by a test.
>
> **Catalogue is at capacity.** `trader/us-stock` = 33994 / 34000. The mandate
> was funded by COMPRESSING text, not by raising `MAX_BLOCK_LEN` a fifth time.
> There are **6 characters** of headroom. The next addition must prune first.
> A test now fails if the header's share of the budget drops a skill.
>
> **Verification:** fail-before 4/5 cadence + 2/2 mandate tests; mutation on
> `MAX_BLOCK_LEN` proves the budget guard non-vacuous; 3574 tests pass; all 5
> CI jobs reproduced locally (GitHub Actions still `major_outage`); mandate,
> cap and offsets confirmed inside the running prod worker.
>
> **State at resume (23:30Z):** equity ~1000 (FLAT — cash 892.94 is seed minus
> ~107 of deployed margin, not a loss), 5 open positions, notional 214 at ~2x,
> unrealized -0.01.

> ### ⏸️ LOOP HELD — 2026-08-06 21:56Z (owner)
>
> Owner: *"hold monitoring, I will clean all history and then monitoring
> again."* **Both crons cancelled** (`688d79c1` 30-min, `d869c56a` 24h sweep);
> `CronList` confirms none scheduled. **Do not restart the loop until the
> owner says so** — and when they do, re-arm BOTH per §1.
>
> **State at hold:**
> - prod image **`20260806-lossfloor`**, prod == `main` (`e93cfb2`), 0 tracebacks
> - fleet **2/10** — the known universe-size problem; #265 shipped but its first
>   post-deploy research batch had not yet arrived
> - **⏸️ PR #267 is PARKED, fully verified, NOT merged.** A 4-line punctuation
>   fix to the loss-verdict brief (two sentences ran together on the live
>   render). fail-before 2/2, 3558 pass, ruff clean, CI reproduced locally
>   (Actions was in `major_outage`). **Merge + deploy it in one step when
>   monitoring resumes** — nothing else is in flight.
> - GitHub Actions was in **`major_outage`** since 16:33Z; check the status page
>   before assuming CI works.
>
> ⚠️ The owner intends to **clean all history**. Treat `docs/reports/` and this
> file as the durable record; do not assume any session state survives.

> ### ▶️ LOOP RESUMED — 2026-08-06 05:47Z (new account) — cadence now 30 MIN
>
> The owner stopped the loop at 05:45Z ("stop monitoring, I will use other
> Claude account") and resumed it minutes later from the new account:
> *"from now monitoring until when i say stop … checking … Every 30min."*
> **Cadence is now a 30-MINUTE cycle**, plus the unchanged 24-hour
> verification sweep (08:07 local = 15:07Z). Both session-only — re-arm
> per §1 every session; on the next re-arm reuse these prompts but refresh
> closed items (§10 trap).
>
> **Current cron IDs (re-armed cycle 77, 2026-08-06 07:00Z, new session):**
> 30-min `688d79c1` (`13,43 * * * *`), 24h sweep `d869c56a` (`7 8 * * *`).
> The prior session's `3e0160dc` was cancelled. Earlier IDs quoted in this
> file (`0ca09ff6`, `947fea0d`, `6f554382`) are DEAD — IDs change every
> session, the cadence does not.
>
> The owner's per-cycle ask: (1) working per plan? (2) losses and WHY —
> check/modify the RUN AI reading algorithm; (3) what we missed; (4)
> how-it-works + plan-16 docs healthy; (5) suggestions + shipped
> solutions. Report every cycle, EN then KO.

> ### 🚦 FIRST FIVE MINUTES OF A FRESH ACCOUNT
>
> 1. Read this file end to end. **§6 is current state, §7 is what to pick
>    up, §10 is what will bite you.**
> 2. Verify access: `ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202`
> 3. Anchor the clock: `SELECT NOW()` on the prod DB — never trust wall clock.
> 4. Confirm prod matches main before assuming anything:
>    `grep SOOPPIY_IMAGE /home/ec2-user/sooppiy/.env` and sha256 the app
>    tree against `origin/main`.
> 5. Get the day's P&L from the TOOL (§4), not a hand-written query.
> 6. **Re-arm BOTH crons** — hourly cycle at :17, 24-hour verification sweep
>    at 08:07 local (15:07Z, the KST day boundary). The prompts are in §1.
> 7. Then run a normal cycle.
>
> **Do not re-open anything marked CLOSED in §7 without new evidence**, and
> do not re-propose exit-blocking — it was measured and rejected (§7).


**Last updated 2026-08-06 05:53Z (prod DB clock), covering cycles 62–75.** For a fresh session — or
a fresh Claude account — picking up the indefinite monitoring loop. Read
this top to bottom before the first cycle. Cycle 75+ notes live in
`2026-08-06-automation-monitoring.md` (62–74 were appended to the 08-05
file before the roll).

---

## 1. What this job is

An **indefinite hourly loop** monitoring sooppiy.com's live auto-trading
fleet. Owner-set, no end date: *"keep going without end of time (I will give
you if I need stop monitoring and auto patch)."* Only an explicit owner stop
ends it.

### The cadence — TWO nested loops (owner, 2026-08-05)

> *"every hours monitoring and solve for issued, and then reach 24 hours
> then checking and verification again for 24 hours monitoring issued."*

| loop | cadence | job |
|---|---|---|
| **30-MIN cycle** (was hourly; owner tightened 2026-08-06) | cron `13,43 * * * *` | monitor **and solve** — diagnose the window's issues and ship the fix when evidence supports it |
| **24-HOUR verification sweep** | cron `7 8 * * *` (08:07 PDT = **15:07Z**, the KST day boundary) | re-check and **re-verify every issue raised and every fix shipped in the preceding 24 h** against live prod |

The 24-hour pass is **not** another hourly cycle. It is a verification sweep
over the loop's own output: build the day's ledger (issues, fixes, watch
items), re-prove each fix against live data (is it still rendering in the
running container? has the behaviour changed over a full day, or was the
deploy-time result an n=1 that did not hold?), check every watch trigger,
regression-check against yesterday, compute the true 24 h P&L
(flatten-reconciled, UTC **and** KST day), and answer what SHAPE wins vs
losses took. **Be adversarial about prior conclusions — if a fix did not
move anything, say so and say what you will do instead.**

**Both crons are session-only and die with the session.** Re-arm BOTH at the
start of every session; this has already cost a 3-hour gap and a 2.8-day
gap. They also only fire while the session is idle, so an hourly slot can be
skipped while work is in progress — that is a known limitation, not a bug.
Genuine unattended coverage would need a timer on the EC2 box (§12).

### The daily obligation (owner, 2026-08-05)

> *"AI trading monitoring must make solution minus profit everyday
> (24 hours monitoring) and report."*

Every day must produce a **solution** for that day's losses, not merely a
description. "Monitored, nothing to report" is not an acceptable day; on a
profitable day, find the losing SHAPE inside the winning day.

**This never licenses a thinly-evidenced ship.** Rule §2.3 still binds —
reproduced evidence only, never a single data point, 2+ cycles before
judging a fresh skill. When a day genuinely supports no change, say so
plainly and state what is being watched and what would trigger action.

## 2. Owner rules — non-negotiable

1. **No form of address, ever.** No name, no title, no honorific in either
   language half. **Never 사장님** in any grammatical position (including
   possessive 사장님의) — this has been corrected four times.
2. **Report English first, then a Korean mirror.** Every cycle.
3. **AI-FIRST (2026-08-05, strengthened):** *"from now all monitoring and get
   required fix or modify then thinking for solving by sooppiy AI first."*
   Every fix is first designed as something the **sooppiy AI itself** thinks
   and acts on — a skill, a prompt lesson. Platform code/gates are the
   fallback, only where the desk cannot be the actor (feeds, builders,
   parsers, perception plumbing).
4. **"We can not fix 100%."** Losses are not engineerable to zero. The target
   is the **SHAPE** of wins vs losses, never their absence.
5. **Role boundary:** `risk_limits`, `positions`, run configs are the sooppiy
   AI's — **never edit them**. Code fixes and SKILLS are mine to ship without
   asking (explicit owner exception).
6. **Verify ≥2×, up to 10×.** A single green check is never enough. Never
   claim something works until actually verified.
7. Never flatter; state disagreement firmly with evidence; surface own errors
   plainly.

## 3. Access

```bash
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202
```
- Server folder: `/home/ec2-user/sooppiy`; app tree `app/service/server/`.
- MySQL: `docker exec noesis-mysql mysql -uroot -p"$(docker exec noesis-mysql printenv MYSQL_ROOT_PASSWORD)" sooppiy -e "..."`
- Containers: `sooppiy-backend`, `sooppiy-worker` (same image), `sooppiy-admin`.
- Local venv: `~/Programming/src/ai-trade/.venv/bin/python`.

## 4. Cycle procedure

1. **ANCHOR FIRST: `SELECT NOW()` on the prod DB** before judging any event
   freshness; stamp the cycle note from that clock only. (A cycle note once
   carried a *future* timestamp; the next cycle read the resulting empty
   query as a dead event stream and restarted a healthy prod worker. An empty
   time-window query is evidence about the WINDOW before it is evidence about
   the system.)
2. Query `run_events` **by `ts`** (there is no `created_at`; filtering on it
   errors silently). `ts` is an **ISO string** — window predicates must use
   the ISO form (`>= "2026-08-05T10:44"`); a space-separated literal silently
   matches the whole day.
3. Pull `trading_runs` (running), `positions` (side-aware P&L), worker/backend
   logs for tracebacks; verify each active run's decision / confidence /
   intent / params / skills honesty.
4. Append the cycle note **newest-first** to
   `docs/reports/YYYY-MM-DD-automation-monitoring.md` (**roll the file per UTC
   day**), refresh `docs/reports/automation-snapshot.json`.
5. Report EN then KO.

**Realized P&L — USE THE TOOL, NOT A HAND-WRITTEN QUERY.**

```bash
docker exec -w /app/service/server sooppiy-worker python -m pnl_audit --since 2026-08-06
```

*(RESOLVED 06:40Z: image `20260806-armanchor` contains the module and the
`docker exec` form above works — verified live, 08-06 `ok` EXIT=0. The
mount fallback below is kept only for running the tool against an OLDER
image.)*

It prints, per UTC day, the **ledger replay** (authoritative), the
**adapt-stream sum** (the old runbook snippet), their **delta**, the flatten
count, and an `ok` / `*** DRIFT ***` verdict. **It exits non-zero on drift**,
so a scheduled run fails instead of printing into the void.

*(If the running image predates the tool, mount it into a one-off container:
`docker run --rm --network sooppiy_default -e DATABASE_URL="$DBURL"
-v /home/ec2-user/sooppiy/app/service/server/pnl_audit.py:/app/service/server/pnl_audit.py:ro
-w /app/service/server <image> python -m pnl_audit --since <date>`)*

**WHY the tool exists.** This section previously carried a hand-written SQL
snippet as the "authoritative" figure — a SECOND implementation of the
platform's accounting, which drifted and which nothing checked. It omitted
every forced flatten and stayed wrong for weeks. Live output 2026-08-06:

| day | ledger | adapt | delta | verdict |
|---|---|---|---|---|
| 08-01 | −6.96 | −5.64 | −1.32 | ok |
| 08-02 | −1.53 | +7.33 | −8.86 | **DRIFT** |
| 08-03 | +14.06 | +21.00 | −6.94 | **DRIFT** |
| 08-04 | −62.57 | −20.61 | −41.96 | **DRIFT** |
| 08-05 | +7.09 | +71.82 | −64.73 | **DRIFT** |
| 08-06 | −4.74 | −1.44 | −3.30 | ok |
| **total** | **−54.65** | **+72.46** | | |

**The platform was never wrong.** `realized_pnl_usd` / `compute_run_pnl`
replay SIGNALS and a flatten IS a signal — run 971's stored value is the
full −58.18. No user ever saw a bad number; the defect was confined to this
runbook and therefore to the cycle notes.

`replay_realized` is validated against the platform's own stored
`realized_pnl_usd` on **all 71 historical flatten runs — 71/71 within two
cents**. Two traps are pinned by tests: the **short-cover sign error** (a
naive signed-cost replay reported +116,756 on a run that made +13.19) and
**window-scoped replay** (invents a phantom opening leg for a position
carried across midnight).

A small delta is expected and benign: `adapt` nets exit-side fees only while
the ledger charges both sides, and a fresh close emits its adapt on the NEXT
cycle. Default tolerance is $5.

Note: the owner's trading day is **KST** (UTC+9) — a KST day starts at
**15:00Z the previous day**. Report both when they differ.

## 5. Ship pipeline (only on reproduced evidence)

code → **fail-before/pass-after test** → **verified-mutation check** (assert
the mutation actually applied; clear `__pycache__`) → ruff `F401,F811,F821,F841`
+ full pytest + tsc → build → **verify in image** → deploy with **sha256 drift
guard** → **verify 3×**.

Deploy detail:
- Work from a detached worktree off `origin/main` (parallel sessions edit the
  same files): `git worktree add /tmp/ai-trade-X --detach origin/main`.
- Drift guard: prod file hash must equal the **parent commit's** hash before
  copying. Abort on mismatch.
- `scp` changed files → `docker build -t sooppiy-backend:<tag> ./app` →
  run tests inside the image (**the prod image has no pytest** — use
  `python -m unittest tests.test_x`) → `sed -i` `SOOPPIY_IMAGE` in `.env` →
  `docker compose --profile prod up -d`.
- Verify 3×: containers on the new image; the changed behavior renders live
  (call it inside `sooppiy-worker`); events flowing (MAX(ts) near NOW);
  0 tracebacks.
- SPA changes need the **three static roots** republished (not needed for
  backend-only work).
- **Backend CI is slow (10–25 min).** Poll `gh run view <id>`. A background
  deploy script died silently once — prefer foreground, or check the output
  file if backgrounded.
- ⚠️ **ANY new desk brief line MUST ship with a WIRING test.** Unwiring
  `_brake_distance_line` from the light prompt **passed the entire
  3313-test suite** — the brief helpers are all tested by calling them
  directly, and nothing asserted the string is actually concatenated into
  the prompt. A line that renders but is not wired is a no-op that looks
  fully tested. Patterns in `tests/test_run_engine.py::BrakeDistanceBriefTests`
  and `ExitSizeBriefTests`: patch the helper to return a sentinel, patch
  `llm_client.generate_text` to capture `prompt`, call `_light_analysis`,
  assert the sentinel; for the full path assert via
  `inspect.getsource(run_engine.run_cycle)`.

## 6. Current state (2026-08-06 06:44Z, cycle 75 + #251 ship)

- **Prod image: `sooppiy-backend:20260806-armanchor`** (PR #251, deployed
  06:40Z). `origin/main` is `77c628a`. Host app tree ≡ main on the five
  load-bearing files; the image now contains `pnl_audit.py` (§4 caveat
  lifted). Rollback: `.env.bak-20260806-armanchor` /
  image `20260806-flatpnl`.
  **Always re-verify the hash before assuming** — parallel sessions deploy
  to the same box and one did so mid-session on 08-05.
- **Running (8):** 960 SI, 961 UBER, 968 USDKRW, 972 SLV, 974 SOLUSDT,
  975 BTCUSDT, 977 GC (976's slot, rebuilt after its retro-arm death —
  see §7), 978 ETHUSDT (969's slot; HG on 24h cooldown).
- **34 skills**; `MAX_BLOCK_LEN` = **34000**, raised FOUR times
  (14000→16000→28000→30000→34000). The catalogue only grows. **The real
  constraint is the desk's ATTENTION, not bytes.** Prefer extending an
  existing skill or pruning over adding a new one.
- **prod alembic head: 0043.** The SQLite ALTER list in `database.py` does
  NOT reach prod MySQL — a new column needs a revision AND a manual
  `alembic upgrade head` against prod before the swap.

### Shipped 2026-08-05/06 — the whole arc, and what each one actually proved

| PR | What | Status |
|---|---|---|
| #244 | Newborn guard (gate retire on the Streak line) + `_brake_distance_line` | **VERIFIED n=4** |
| #245 | `_exit_size_line` + exit-verb clause (`reduce` vs `close`) | **n=1 positive** |
| #247 | **Arm executor** — the desk's armed exits now fire between cycles | live, 1 arm standing |
| #249 | **Breakeven ratchet** + flatten realized-P&L journal | **both verified live** |
| #250 | `pnl_audit` — one tested P&L implementation + drift alarm | live, in use |
| #251 | **Ratchet arm anchored to the largest book ever held** — a reduce can no longer retro-arm the floor (976/973 both died to this on 08-06) | live 06:40Z, verified 3× |

**The through-line of all five:** every one came from the same class of
defect — *the desk (or the monitor) was judged against something it could
not perceive.* #241's Streak line, #244's rail line, #245's Exit scale
line, #247's arm executor, #250's drift alarm. When a rail or a lesson
names an action without naming the observable that licenses it, it fires
wrong or never fires at all. **Check that first on any new finding.**

## 7. Open items — pick these up first

### CLOSED, do not re-open

- **FINDING 1 (flatten P&L).** Fired live on run 969 at 05:05:24 emitting
  `adapt {trigger: flatten_close, realized: -3.2407}`. 08-06 with TWO
  flattens now reconciles (delta −0.20, `ok`) versus 08-05 which drifted
  **−64.73**. Validated **71/71** against the platform's own stored
  `realized_pnl_usd`. **Severity note: this was MONITORING-ONLY** — no
  product code reads adapt-realized, the platform was always correct, and
  no user ever saw a wrong number.
- **Newborn guard high-conviction caveat.** n=4, zero retires: 973
  `sell`@0.545, 974 `sell`@0.4525, 975 `hold`@0.665, **976 `buy`@0.8725** —
  the last above the 0.7025 at which run 970 used to quit. The pathology is
  covered. Keep counting, but stop treating it as unproven.

### OPEN — the live watches

- **Exit-verb (#245): n=2 POSITIVE.** 969 cycle 20 (adverse at 59% of an
  ordinary day) and 976 cycle 2 (adverse −0.08%; caveat: the ordinary-day
  sentence was likely absent — GC daily-bars fetch failed at its build —
  but the line itself rendered) both chose `reduce`, not `close`.
  ⚠️ **Only count an exit as evidence if the Exit scale line actually
  RENDERED** — it is silent when the position is in PROFIT. 960's reduces at
  cycles 25/28 were banking winners and do NOT count.
- **Breakeven ratchet retro-arm: FIXED — #251, live 06:40Z (owner: "fix
  2,3").** The defect: `_breakeven_arm_usd` sized off the CURRENT book
  while `peak_pnl_usd` is lifetime, so a reduce lowered the bar under an
  already-earned peak and instant-fired the floor — escalating the desk's
  cheap verb into a full close. **BOTH 08-06 fires were this defect
  (n=2):** 976 (arm 11.36→5.68 on its own reduce, fired at −5.10, GC then
  recovered — a cut winner) and 973 (live replay: max book 22.24 vs 11.12
  at fire; corrected from the earlier "clean fire" reading). Fix: the arm
  is anchored to the LARGEST book ever held (`_run_max_abs_qty` replays
  the run's own trade events); strictly conservative vs the old sizing;
  fail-soft to the current book. Verified 3× live incl. floor=False on
  976's exact death inputs.
  **POST-SHIP SAMPLE IS n=0 — but the watch is now AUTOMATIC (#253).**
  Both 08-06 fires (973, 976) predate the 06:40Z deploy. Run the auditor
  instead of hand-checking:

  ```
  docker exec -w /app/service/server sooppiy-worker python -m ratchet_audit --since 2026-08-01
  ```

  It replays each fire's trades, compares the book AT the fire against the
  largest book the run ever held, and **exits non-zero** on a shrunken-book
  fire after `FIX_TS`. Live now: 8 fires since 07-01, `0 post-fix, 0 to
  review`. ⚠️ A flagged fire is a CANDIDATE, not proof — the reason string
  is shared with the LEGACY trail, whose `activate_usd` is a fixed dollar
  figure set at build and therefore *cannot* retro-arm. Confirm against the
  worker log line `breakeven ratchet fired`. (854 and 921 carry the shrunken
  shape but predate the ratchet entirely — they are NOT extra instances.)
  **POST-SHIP WATCH:** ratchet fire rate should drop; audit every new
  `trailing_lock` fire against the log's peak/now/arm (a genuine fire has
  peak ≥ max-book arm); runs whose peak never covers their biggest book
  are backstopped by max_loss/drawdown-brake only — if a slow bleeder
  round-trips a big paper gain to the brake, that is the residual shape to
  bring back. `BREAKEVEN_ARM_FEES` untouched. Churn cost 08-06 pre-fix:
  −5.94 = 38% of the day's realized red; 971-class tail absent (largest
  single loss −5.24).
- **Arm executor (#247): reachability ASK NOW MET (cycle 77, 08-06 06:26Z).**
  977 GC armed `price_above 4350 → reduce 0.5` at 0.80% = **0.60 ordinary
  days** — inside one ordinary day, which is what the skill asked for.
  Progression: ~25 days (08-05) → 2.5 (968, 00:22) → **0.60** (977). But
  **`armed_exit` events are still 0 fleet-wide** — reachable ≠ fired, the
  executor is UNPROVEN end-to-end. Catching the first fire is the priority.
  **Armed full closes — CLAUSE SHIPPED #253 (owner asked for it at n=1).**
  968 armed `close 1.0` at 1.76 ordinary days. The gap was STRUCTURAL, not
  behavioural — the skill text carried no arm-sizing guidance at all — which
  is why it did not need a second occurrence. `position-management` now
  teaches the partial verb as an arm's default and names why an arm that
  merely repeats the stop with a full close buys nothing while spending the
  reassessment. **WATCH:** whether subsequent arms use the partial verb;
  count them.
- **FINDING 2 (n=1):** run 971's cycle-6 add took the position 2.7× and
  pulled the drawdown brake inside routine range (−58.18 on a −0.62% move).
  **Act only on a SECOND `drawdown_brake` with the same add-then-brake
  shape.**

### The measured baseline any new fix must beat

From the 2-day loss analysis (84 closes, 08-04/05), still the sharpest
statement of the problem:

- win rate **55%**; median win **+1.98** beats median loss **−1.29**
- **6 closes of 84 (7%) carried 74% of ALL loss**
- losing **trims** averaged −1.53 and were harmless; losing **FULL closes**
  averaged −6.68 and carried **91% of all loss**
- **exit-BLOCKING was measured and REJECTED** — holding gains only
  **+0.11pp** median, so the price drifts rather than recovers. Do not
  re-propose it without new evidence.

## 8. Standing watches

- **(NEW RESULT 2026-08-06 cycle 71) Exit-verb (#245) PASSED its first real
  test.** Run 969 HG, adverse (unrealized −6.42), Exit scale line showing
  "0.50% ... 59% of one ordinary day", chose **`reduce 0.5`** not
  `close 1.0`. That is the exact setup the lesson targets. n=1 — keep
  counting adverse exits before calling it fixed. `why` is still empty
  fleet-wide (not required for a reduce, but unpopulated).

- **(a)** sub-1% desk-authored stops — 2 casualties (941 −8.05, 955 −17.6).
  **RECALIBRATED 2026-08-06 (cycle 69): the flat 1% threshold is wrong in
  BOTH directions.** Measured against each symbol's own ordinary daily move
  (`_typical_daily_move_pct`): 968 USDKRW's 0.65-0.79% stops are **1.3-1.6
  ordinary days** and perfectly sound, while 949 HYPEUSDT's 1.63-2.7% on a
  2.15%/day mover is only **0.76-1.26** ordinary days and genuinely tight.
  Judge this watch in ORDINARY DAYS, not absolute percent. Not yet acted on:
  #231's shipped clause says "~1% on a leveraged crypto book", so 949 is
  compliant by the current standard and there is no loss attached yet.
  **Trigger:** a stop inside ~1.0 ordinary day collected by routine range.
  Then the AI-first fix is to state the ordinary daily move AT THE MOMENT
  THE BRACKET IS ASKED FOR — today it only appears on adverse drift via the
  Exit scale line, long after the stop was authored.
- **(b)** arm intents count — 36 lifetime; **all discarded, no executor
  exists**. Building one needs the owner's design input first (see §9).
- **(c)** confidence-cluster honesty — spreads have been healthy (0.25–0.79).
- **(d)** fabricated rationales — clean since #229; reviews now cite correct
  units.
- **(e)** the owner's stored `risk_limits` 8%/15% row — **report only, NEVER
  edit**.
- **FMP tier-thinness** — when a fleet symbol's print enters the 14-day window
  (~NVDA mid-August), verify the union actually carries it.
- Give a fresh skill **2+ cycles** before judging it.

## 9. Open decisions waiting on the owner

0. **Rail `close` → `reduce` in `order_intent`?** The measured killer is the
   whole-book dump: full closes are 71% of losing closes but **91% of all
   loss**. Converting an unjustified full close into a partial would target
   it directly. BUT `order_intent` documents an explicit safety asymmetry —
   *"close is never railed at all; refusing one is how a rail becomes the
   risk"* — and clamping an exit DOWN contradicts it. **Amending a
   documented safety invariant is the owner's call, not a monitoring-fix
   side effect. Do NOT ship unasked.** Escalate only if the desk's own verb
   choice (#245) does not move over several cycles.

1. **`risk_limits` 8%/15% row vs the 2:1 R:R floor** — 15 < 2×8, so every
   unbracketed entry seeded from that row is auto-refused. Options: change the
   row (≥16% target at 8% stop), change the floor, or rely on desks authoring
   their own brackets (#228). *Reported repeatedly; never answered.*
2. ~~Arm-executor~~ — **BUILT AND SHIPPED 2026-08-06 (PR #247, image
   `20260806-armexec`, alembic 0043).** The executor now fires the desk's
   armed exits on the CONTROL PASS — the only path that runs between
   decisions, which is where 08-05's profit lived (four of seven losing runs
   were never once seen in profit at a decision; dwell 5-20 min vs a ~45 min
   cycle). Gap-through was resolved from the module's own doctrine rather
   than deferred: ARM_THEN is exits-only so an arm can only SHED risk, and
   a risk-shedding intent is never refused — fire at the next mark, journal
   the slippage. `health_below` parses but is explicitly NOT executable.
   Paired skill: `position-management` gained "ARM THE LEVEL YOU CANNOT WAIT
   FOR" (arm whenever holding, REACHABLE level, arm to BANK not only
   protect). **Still to verify: the desk must actually arm reachable levels
   — every arm on 08-05 sat 11-13% from price and none would have fired.**
   FIRST RESULT (n=1, 08-06 00:22Z): run 968 armed `price_above 1440 ->
   reduce 0.5` at **1.21%** from price = **2.5 ordinary days** for that
   symbol, versus 11-13% (~25 days) before, and it is a BANKING arm rather
   than a protective one. ~10x more reachable and the right direction, but
   the skill asked for inside ~ONE ordinary day, so compliance moved without
   completing. Keep watching `armed_order_json` and `armed_exit` events.
   **The breakeven ratchet (#248) exists precisely so this does not have to
   land perfectly** — neither layer depends on the other.

3. **Noise-stop code rail** (deferred deliberately) — refusal vs
   volatility-aware floor vs skill-only. Note: `order_params`' monotone rule
   forbids *loosening* an authored stop (it raises targets, never stops), and
   refusal risks recreating the 956 refusal-churn class.

## 10. Traps that have already bitten

### Added 2026-08-17 (#475) — IN-IMAGE TESTS FAIL ON PROD'S OWN ENV

`docker exec … python -m unittest tests.test_x` inside the prod container
inherits the prod environment. **Prod sets `ENTITLEMENTS_ENFORCED=true`**,
so any fixture that creates a run from an unlinked agent 400s at setup
(`"runs require an agent linked to a user account"`) — 5 tests "failed"
in-image while the code was correct. Run in-image verification as
`docker exec -e ENTITLEMENTS_ENFORCED=false -w /app/service/server …`.
A setup-stage failure in-image is the environment until proven otherwise —
diagnose the traceback's stage before doubting the shipped change.

### Added 2026-08-17 (#475) — THE LEASE FENCE WAS EATING THE DESK'S OWN ORDERS

`RUN_LEASE_TTL` (300s) stopped covering the worst-case cycle once decision
LLM calls could take up to 300s (#468) — 21 authored orders (8 opens,
7 reduces, 1 close; ZERO holds — the fence only runs when there are steps)
died as `gate_skip: "fence: lease expired"` over 08-14..17, including BOTH
of fleet 36's only entry attempts. Fixed by `_renew_lease` before the trade
txn (#475, image `20260817-20260817-leaserenew`). **Standing watch: daily
`fence: lease expired` count must stay ~0; any fire post-08-17 means the
renewal has a residual gap and the fix must be re-reported as FAILED.**

### Added 2026-08-06 (#260/#261) — the skills catalogue is AT CAPACITY

- **`trader/us-stock` sits at ~33,890 of 34,000 — about 110 chars spare.**
  Every other site/market pair has 3,700–30,800. Adding ONE sentence to a
  trader-site skill overflowed it by 166 and **silently dropped
  `execution-plan-check`**, a 667-char safety skill. An over-budget block does
  not error — it prunes whichever skill sorts last.
- **Before adding any trader-site text**, run
  `tests/test_trading_skills.py::test_defaults_never_hit_the_budget` and
  expect to compress something first. Compress your OWN prose; do not raise
  `MAX_BLOCK_LEN` (that would be the fifth bump). The measurement recipe is
  documented at the constant.

### Added 2026-08-06 (#260) — an OBSERVABLE WITH NO LESSON is half a fix

- #259 gave the desk `_mark_freshness_line` — the fact of a motionless tape —
  and **no skill attached any judgment to it.** The desk got a number and no
  instruction about what it means for action.
- **Every brief line needs a matching skill clause**, or it is decoration.
  The pattern this file keeps recording is "the desk cannot perceive X";
  supplying X without teaching what to do about it only completes half of it.

### ⚠️ Added 2026-08-06 (#264) — FIXTURES USE ROUND NUMBERS; PROD HAS FLOAT DUST

**Fourth live-caught defect in these audit tools, and it corrected a number
I had reported.** `ratchet_audit` said "post-fix **6** survived" for #251;
the honest figure is **5**.

- Run 972 halved a 42.92-unit book six times; its final **full close** left
  **1.47e-08** units — above the absolute `1e-12` guard, functionally zero —
  and was counted as a *reduce* with a post-reduce arm of ~0, satisfying the
  in-band test trivially.
- **Absolute epsilons cannot express "essentially nothing left"** when the
  book size is not known in advance. Use a **relative** fraction of the book
  the leg started with (`_FLAT_FRACTION` 1e-6).
- **The running tally of live-caught tool defects:** #253 flatten-timestamp,
  #253 duplicate status rows, #261 seq-vs-time ordering, #264 float dust.
  **Every one came from fixtures with tidy round numbers and distinct
  timestamps.** When you write a fixture, use a real prod row.
- ⚠️ **Corrected #251 evidence: 5 post-fix in-band survivals** vs 976's
  single pre-fix FLATTENED. Direction unchanged, magnitude one weaker.

### ⚠️ Added 2026-08-06 — CI CAN FAIL FOR REASONS THAT ARE NOT THE DIFF

`"The job was not acquired by Runner of type hosted even after multiple
attempts"` and `"Failed to resolve action download info"` at the **Set up
job** step = a GitHub hosted-runner outage, not your change. Diagnose via
`gh run view <id>` **ANNOTATIONS**, confirm your own job's steps passed, and
**do not merge on red** — leave the PR and re-check next cycle. (Distinct
from the billing-limit signature, which kills every job in seconds.)

### 📊 Added 2026-08-06 (24h sweep) — NEW SHAPE BASELINE, and a fix that moved its metric without saving the day

**Replaces the old §7 baseline (55% win rate; 6/84 closes = 74% of loss) with
a measured two-day pair.** Measure **per closing leg**, not per run.

| metric | UTC 08-05 | UTC 08-06 |
|---|---|---|
| win rate | 57% | **39%** |
| median win | +3.52 | **+0.40** |
| median loss | −0.90 | **−2.87** |
| **full closes' share of loss** | **92%** | **19%** |
| worst-6 share | 93% | 69% |
| per-leg expectancy | +1.62 | **−1.60** |

- **The exit-verb work (#245/#253/#262) landed decisively** — whole-book
  closes fell from 92% of all loss to 19%, below even the old 74% baseline.
- **And the day lost far more.** The loss moved out of the tail into the
  body. **A fix can move its own metric decisively and not save the day** —
  always re-measure the whole distribution, not just the thing you fixed.
- **Split by feed health before blaming the feed.** 08-06: crypto (live)
  **−40.30 = 61% of the day at a 14% win rate**; yahoo-served (frozen)
  −26.00 = 39%. The frozen feed distorts **bookkeeping, not the outcome**.
- **975's shape, the day's −54%:** $4,739 notional, lifetime peak **6.5% of
  one ordinary day**, held 7h18m, four partial exits, −38.26. Never right.
  Not an exit failure — an entry that never worked, held long.

⚠️ **USE THE TOOLS.** Ad-hoc SQL counted 4 `trailing_lock` fires where
`ratchet_audit` reports 2 — the hand-written query matched **both** status
rows, the exact double-count bug the tool exists to avoid.

### ⭐ Added 2026-08-06 (#263, from the 24h sweep) — ASK WHETHER THE RAIL COULD EVEN HAVE FIRED

The most useful question a sweep can ask about a protective rail is not "did
it work" but **"could it have applied to the cases that hurt?"**

- **13 of 13 split.** Of the 22 runs that closed in the 24h window, **all ten
  losers had a peak BELOW their own arm threshold** — the breakeven floor
  could never have armed for any of them — and **all three winners** were
  above it.
- **The threshold scales with book size, so the protection arms LAST exactly
  where it would save most.** Run 971: a 15.81-unit ZEC book needed a peak of
  **$16.36**, reached **$16.15**, then lost **−$58.18**. Missed by 1.3%.
- **Not a tautology** — four losers had *positive* peaks (971 +16.15, 976
  +7.22, 975 +2.84, 973 +1.72) and still sat under threshold.
- Fixed AI-first in #263: `_floor_status_line` tells the desk whether the
  floor is switched on at all, using the same #251 max-book anchor as the
  floor itself. Re-check with the per-run render through
  `_position_state_line`.
- ⚠️ **This does not make the floor protect them.** It tells the desk it is
  uncovered so it can bank or arm. Whether the threshold itself should scale
  differently is an open question, deliberately not answered.

### ⚠️ Added 2026-08-06 (#262) — THE SKILLS CATALOGUE IS OUT OF ROOM

**`trader/us-stock` is 33,940 of 34,000 — SIXTY characters.** The next
addition has nowhere to go. Room for #262 was found by compressing that
lesson's own backstory and removing a duplication; there is no third time.
**Prune or market-scope a skill that has stopped earning its place** — do not
shave, and do not bump `MAX_BLOCK_LEN` (that would be the fifth).

### Added 2026-08-06 (#262) — a caveat in a DIFFERENT skill loses to a local imperative

- Reproduced n=2 with a clean n=1 control. #260 put "set no stop, target or
  arm off a motionless price" in **Data Honesty**. The arm lesson separately
  said "Whenever you hold a position, arm the level" — **unconditional, and
  in the skill actually about arming**. Of three arms authored after the
  clause deployed, the one on a live feed FIRED and **two were placed on
  frozen marks** where they can never fire.
- **Put the exception where the instruction is.** A distant caveat does not
  survive contact with a nearer imperative.
- **A lesson that states a fact must not keep stating it once it is untrue.**
  The same lesson still claimed "64 arms placed here, NOT ONE ever fired"
  hours after two had fired. When a watch resolves, grep the skills for the
  claim it invalidates.

### ⚠️ Added 2026-08-06 (cycle 102) — CHECK THE PROVIDER'S STATUS PAGE FIRST

Before theorising about a provider from its symptoms, ask it:

```bash
curl -s https://www.githubstatus.com/api/v2/components.json | \
  python3 -c "import json,sys; [print(c['name'], c['status']) for c in json.load(sys.stdin)['components']]"
gh api repos/<owner>/<repo>/actions/permissions      # billing / disabled?
gh api repos/<owner>/<repo>/actions/workflows        # workflow state
```

**2026-08-06:** I spent parts of two cycles inferring a CI outage from its
symptoms — first runner-acquisition failures, then no triggering at all. One
call settled it: **`Actions: major_outage`** while **`Webhooks: operational`**,
with the repo side healthy (`enabled: true`, workflows `active`). That
combination explains it exactly — webhooks created the branch and PR, Actions
could not run anything.

**Same class as the frozen-feed episode**, where querying Yahoo's own
timestamps settled in one call what the symptoms could only suggest. When a
dependency looks broken, **ask the dependency**.

### ✅ OWNER RULE 2026-08-06 — WHEN CI IS DOWN, RUN CI OURSELVES

**Owner, verbatim intent: "github fail then CI processing by us — all claude
level, not only this session but also other sessions."** Saved to the global
`~/.claude/CLAUDE.md` and to memory, so it survives account rotation.

**Procedure:**
1. **Confirm it is the provider**, not billing — status API +
   `gh api repos/<o>/<r>/actions/permissions`. Billing is the owner's to fix.
2. Take the **exact** commands/workdirs/env from `.github/workflows/*.yml`.
3. Run each job in a **fresh worktree of the PR branch** — clean checkout, not
   your dirty tree.
4. Run **every** job, audits and secret scans included.
5. **Report each separately and state what a local run does not give:** a
   clean-room runner, the PR audit trail, checks needing provider secrets.

**Applied 2026-08-06 to #264 and #265** (both merged, image `20260806-pool`):
ruff clean, pytest 3544/3549 under CI's env, frontend build OK, npm audit
exit 0. `pip-audit` (ensurepip SIGABRT) and gitleaks were **not runnable** —
closed by argument instead: neither PR touches a dependency and the manifests
are byte-identical to a commit whose Security run passed that day, and every
secret-keyword line in the diffs is an env-var *name*, not a value.

⚠️ **Deploy invariants are unchanged** — merge first, drift-guard against the
parent commit, keep prod == `main`.

### Superseded — the two PRs are now merged and deployed

**First thing next session: check if Actions recovered, then merge and deploy
in this order.**

| PR | what | verification |
|---|---|---|
| **#264** | `ratchet_audit` counted a full close's float dust as a reduce — corrects the published "post-fix survived" figure from **6 to 5** | FB 1/1, mutation 2/2, 3544 pass |
| **#265** | **the fleet fix** — survivor pool `4/4/2/2` = 12 → `8/8/4/4` = 24, env-overridable | FB 6/6, mutation 4/4, 3549 pass |

**#265 is the answer to the universe-size root cause.** `screen_universe`
already scores the whole universe (129 candidates) and then discards all but
12 — the fetches are already paid, so raising the cap costs nothing and stops
throwing away 117 finished results. Stage 2 is deliberately NOT widened
(theses chunk at 5, cap 2 LLM calls), so the pool widens **choice**, not
spend. Watch `'llm': N` in `[SymbolResearch]` (#95's tell).

⛔ **The blocker:** GitHub Actions stopped triggering **any** workflow for this
repo at **16:26:24Z**. A push creates the branch and PR but produces no run
(`gh pr checks` → *"no checks reported"*). Earlier it was runner-acquisition
failures; it escalated.

⚠️ **Do not merge without CI, and do not deploy an unmerged branch.** The
drift guard the entire deploy procedure rests on assumes **prod == `main`**;
bypassing it to move faster destroys the one invariant that makes every
future deploy verifiable.

### 🚨 URGENCY 2026-08-06 (cycle 101) — the fleet is EMPTYING, 8 → 2 in one day

The root cause below is diagnosed and unchanged. **What changed is the cost.**

- **8 runs this morning → 2 now** (target 10), and the replenish loop cannot
  refill.
- **The compounding shape:** each retire adds a 24-hour cooldown, which
  removes that symbol from a **~12-symbol universe** — so **the fleet's own
  losses shrink the pool it needs to recover from.** Cooldowns now hold
  SOLUSDT, HG, BTCUSDT, SI and ETHUSDT.
- **This is no longer an idle-slot inefficiency. It is a fleet emptying
  itself.** If the last two runs close without replacements the fleet reaches
  **0/10 and stops trading entirely.**
- Nothing to ship — the remedy (widen the universe, or lower the target) is
  the owner's design call. What a monitoring session can do is say plainly
  that the clock is now running.

### ✅ ROOT CAUSE, FINAL 2026-08-06 (cycle 100) — the research UNIVERSE is too small

**Investigation complete over cycles 97→100. Owner decision, not more
diagnosis. Do not re-diagnose.**

> **The research universe — ~12 symbols per batch, heavily repeated across
> batches — cannot sustain a 10-slot fleet. The fleet's own holdings, its
> 24-hour cooldowns, and structural infeasibility consume the entire batch.**

Worked example, batch `research:496122` (**zero** buildable):

| status | symbols |
|---|---|
| cooldown (retired today) | SOLUSDT, HG, BTCUSDT |
| running | GC, ETHUSDT |
| unpriceable | ZBTUSDT |
| negative expectancy | NVDA, SNOW |
| not selectable | DIS, PYPL, CHFJPY, USDKRW |

Across 496115→496122, CHFJPY/ETHUSDT/HG/NVDA/SNOW appear in **all eight**
batches; consecutive batches share **7 of 8** selectable symbols.

⚠️ **`selectable = 0` is NOT a bug — I nearly reported it as one.**
`selectable = ev_pct > 0 AND expressible AND feasible`. DIS scored 0.983
(2nd best in its batch) and is correctly refused because it is a **us-stock
SHORT and the book is spot-only**; PYPL/CHFJPY/USDKRW fail the **R:R
feasibility floor**. Score was never the criterion. **Check the reason before
calling a filter wrong.**

**Every gate is correct. Correct gates over a 12-symbol rotation leave zero.**
Coordinating research with cooldowns (the cycle-99 suggestion) helps at the
margin but **cannot create symbols that are not in the universe**.

**Owner decision:** widen what research covers, or lower the fleet's target
from 10. Both are design calls.

### Superseded (cycle 99) — "research proposes what the fleet just retired"

**The fleet-stuck-at-3/10 investigation is COMPLETE. What remains is an owner
decision, not more diagnosis.**

**The chain, verified read-only:**
1. `symbol_research.select_targets` reads **only the newest batch** with live
   selectable theses (`ORDER BY batch_id DESC LIMIT 1`). "200 theses / 21
   symbols today" was never the pool — **one batch is**.
2. That batch (`research:496121`) holds **8** theses.
3. **5 of the 8 are unusable**: SOLUSDT, HG, BTCUSDT are in 24h cooldown
   *because this fleet retired them today*; ETHUSDT and GC are running.
4. Three remain; the gate correctly refuses NVDA (−200.50/trade) and SNOW
   (−72.43/trade). Nothing builds.

**Proof:** `select_targets(agent 6, depth=10, exclude=∅, all six markets)`
returns **3 rows**. Depth 10 was asked for. Market scope and `exclude` are
eliminated.

**ROOT CAUSE: research and the cooldown list are not coordinated.** A symbol
is retired on a loss → 24h cooldown → research keeps proposing it → the
usable pool collapses. **63% of the newest batch was dead on arrival.** Every
component is doing its job; they do not talk to each other.

**Owner decision, not shipped:**
- **Primary:** pass the agent's busy + cooldown set into research target
  selection. ⚠️ Real consequence: biases research away from recently-traded
  symbols permanently.
- **Smaller:** let `select_targets` fall back to older still-unexpired
  batches when the newest yields too few eligible rows. Leaves research
  untouched.

⚠️ **Do not re-diagnose this.** Three cycles (97→98→99) narrowed it from "an
unpriceable symbol" to the exact line. Re-check with:
`SELECT batch_id, COUNT(*), GROUP_CONCAT(symbol) FROM research_theses WHERE
selectable=1 AND expires_at > NOW() GROUP BY batch_id ORDER BY batch_id DESC`.

### Superseded (cycle 98) — 13 symbols available, 2 offered

**The fleet has been 3/10 with no new candidate since 08:53:59.** Cycle 97
blamed an unpriceable sole survivor; cycle 98 measured it properly and that
was only the surface.

| | count | |
|---|---|---|
| researched today | **21 symbols** | 200 theses |
| active cooldown | 5 | BTCUSDT, HG, SI, SOLUSDT, ZECUSDT |
| busy (running) | 3 | ETHUSDT, GC, SLV |
| **available** | **13** | AVGO, BICOUSDT, CHFJPY, DIS, HYPEUSDT, LABUSDT, NG, NVDA, RIVN, SNOW, USDJPY, USDKRW, ZBTUSDT |
| **reaching the gate** | **2** | NVDA, SNOW — both correctly dropped on measured negative expectancy |

**ELIMINATED as causes:** research supply, symbol cooldowns, and the backtest
gate itself. **The filter is between "thesis exists" and "candidate presented
to the gate"** — the gate events carry `context: "replacement"`, so start in
the replacement-candidate selection path of `fleet_planner`.

⚠️ **Do NOT ship the priceability ordering fix expecting it to help.**
Cycle 97 predicted it would only change the log line; cycle 98 confirmed that
within 30 minutes when ZBTUSDT aged out on its own and the gate began
reporting `kept: []` **with the fleet still at 3/10**. Worth doing for
hygiene (7th instance of the infeasible-at-build class), never as the fix.

**Re-check:** `SELECT ... FROM fleet_candidates WHERE fleet_id=<n> ORDER BY id
DESC` (newest row's age) and the `backtest_gate` payloads in `fleet_events`.

### Superseded 2026-08-06 (cycle 97) — the unpriceable sole survivor

**Not shipped. Two separable problems and the easy one does not help.**

- Fleet 27 is `replenishing:3/10` and has **built nothing for 4h31m**.
  `[FleetPlanner] tick: {researched: 0, built: 0}` every tick.
- **The loop:** `backtest_gate` keeps only **ZBTUSDT** (drops NVDA −200.50/
  trade, SNOW −72.43/trade), then `candidate_skipped` — *"no price available
  for ZBTUSDT (crypto)"*. **Every empty slot draws the same unpriceable sole
  survivor. 271 skips, 13:18:38Z → 17:49:51Z.**
- **ZBTUSDT is genuinely untradeable**, not a freeze casualty: `Hyperliquid
  symbol not listed: ZBTUSDT -> ZBT`, while BTCUSDT and SOLUSDT price fine.
- **(a) Ordering defect — SEVENTH instance of the infeasible-at-build class.**
  `fleet_planner` has a build-time chain (`thesis_expired`, `symbol_busy`,
  `_thesis_fee_infeasible`, `_bucket_expectancy_block`) each justified
  *"decide once, before the run exists"* — **priceability is not in it** and
  fails later at run creation (`routes_runs.py:462`).
- **(b) The real cause of the empty slots is candidate SUPPLY.** The pool is
  **three symbols**: one untradeable, two dropped on measured negative
  expectancy. ⚠️ **Fixing (a) stops 271 futile attempts and makes the reason
  honest but fills ZERO slots.** Do not ship (a) alone and call the fleet
  fixed.
- **Recommended order:** (i) priceability into the build-time chain; (ii)
  find out why research emits symbols the exchange does not list, and why the
  pool is only 3.

**Re-check with:** `SELECT status_reason FROM fleets WHERE status='active'`
and `SELECT ... FROM fleet_events WHERE event_type='candidate_skipped'`.

### ⭐ RESOLVED 2026-08-06 17:00Z (cycle 96) — #257 FIRED, and the cycle-89 prediction held

**The open verification from cycle 84 is CLOSED, positive. Do not re-open.**

Run 968, 17:00: desk `reduce` 0.5 → trade signal 499 at 17:00:16 → equity
realized −3.351328 → **−3.346403 (+0.0049)** at 17:00:47 → the **control
pass** fires `conviction_collapse` at 17:00:48 → **`adapt: pending_close`
realized +0.0049** → flatten leg and #249's `flatten_close` +0.0046 → stopped.

- **The +0.0049 matches the equity delta to the cent.**
- **The flush ran BEFORE the flatten existed as a signal**, so #257 and #249
  both journalled with **no overlap** — the ordering the design depends on.
- **Cycle 89's structural prediction was exactly right**: a control-pass stop
  with a close from the last decision cycle still un-ingested.
  `conviction_collapse` fired **32 seconds** after the reduce.
- ⚠️ **The captured amount was POSITIVE.** The flush recovers wins as well as
  losses — the hole was never loss-specific, and describing it as "missing
  losses" would be wrong.

### Added 2026-08-06 (cycle 89) — #257's silence was STRUCTURAL, not a failure

- **`pending_close` has stayed 0 through several stops. That is correct.**
  The `adapt_retired` path runs `run_cycle`'s feedback pass, which calls
  `ingest_outcomes` FIRST and only then `retire_run` — so by the time
  `_control_stopping` runs, nothing is pending and the flush rightly emits
  nothing. **The path self-drains.**
- **#257's non-null case needs a CONTROL-PASS stop** (`at_time`, `max_loss`,
  `trailing_lock`, `profit_target`, idle/fee retire) **with a close from the
  last decision cycle still un-ingested** — exactly what runs 960 and 976
  were. Wait for one of those; do not read the silence as a broken fix, and
  do not "fix" it.

### Added 2026-08-06 (cycle 89) — arm-distance calibration, n=2

| run | distance when armed | time to fire |
|---|---|---|
| 975 BTCUSDT | 0.75 ordinary days | 4h32m |
| 978 ETHUSDT | **0.16** ordinary days | **1h44m** |

- Closer arm fired ~2.6× faster — the direction #259's re-anchor predicts.
- ⚠️ **Neither fired inside one cycle.** Even 0.16 ordinary days took ~2.3
  cycles. If the goal is a fire before the desk's next look, arms may need to
  be closer than #259 currently asks. Two points are not a curve — keep
  collecting before changing the lesson again.
- **Both fires were on crypto**, the only live-feed markets. Zero on
  Yahoo-served symbols: "dead on arrival" holds at 2/2.

### ⭐ RESOLVED 2026-08-06 (cycle 87) — #251 PROVEN LIVE, and the arm executor FIRED

Two long-standing open items closed on real evidence. **Do not re-open either
without new contrary data.**

- **#251 (max-book arm anchor) is proven.** The post-fix sample was n=0 from
  cycle 77 to 86. On 2026-08-06 run 975 produced **two in-band reduces that
  SURVIVED** (13:10:32 arm_after 1.8755 / peak 2.84 / arm_full 9.3777, and
  13:11:19 0.9378 / 2.84 / 9.3778) against run 976's pre-fix in-band reduce
  that **FLATTENED**. Under the old anchor both arms sat below the peak → the
  floor would have armed, and 975's P&L was far below breakeven → it would
  have fired. **#251 prevented two forced flattens**; 975 kept its remainder.
  Re-check any time with `python -m ratchet_audit --since <date>`.
- **Watch (ii) closed positive: the arm executor works.** 64+ arms, zero
  fires, until `run:975:arm:6` at 13:11:19 — predicate, 50%-of-remaining
  sizing, idempotent order id, telemetry, **−0.056% slippage**. It fired on
  BTCUSDT, the one live-feed symbol, confirming that Yahoo-served arms are
  inert *because of the freeze*, not because the mechanism is broken.
- **Calibration for #259:** that arm was **0.75 ordinary days** away and took
  **4h32m (~6 cycles)** to reach — the first live support for re-anchoring
  reachability from "one ordinary day" to "your next look, ~45 minutes". n=1.

### 🔓 RESOLVED 2026-08-06 15:41Z (cycle 93) — the freeze ENDED after ~8 hours

**The episode below is closed. Keep it for the method, not as a live alarm.**

- Ended ~15:41–15:44Z; at 15:54:06Z every ticker was 0–10 min fresh (SPY 0m,
  BTC-USD 0m). GC had been frozen since 07:57:40.
- **The concealed losses landed at once.** Every arriving price was lower and
  the desk was long: 979 SI −0.91% on a 20.714 book = **−11.70**, 972 SLV
  −1.20% = −0.91, 977 GC −0.24% = −0.85, 968 USDKRW −0.45% = −0.04 —
  **−13.49 of still-open exposure repriced**. 979 realized **−11.56 on one
  leg** at 15:41:23 the instant it could see the truth.
- ⚠️ **Which way the distortion ran — the naive reading is WRONG.** Frozen
  prices were HIGHER than reality and the book was LONG, so the fills made at
  stale prices were **favourable**: the $12,655.93 of frozen-price notional
  sold *better* than the market allowed. **The freeze deferred loss onto
  whatever stayed open; it did not lose money on those legs.** Do not report
  "stale fills lost us money".
- **What is unchanged and still the owner's call:** `mark_age_ok` measures
  OUR fetch time, so the platform remains blind to upstream staleness. Now
  with a measured cost attached (−13.49 revealed in minutes).
- Detection recipe kept below; `fill_audit` stops growing once prices move.

### 🚨 HISTORICAL (cycle 88) — Yahoo served this host a FROZEN SNAPSHOT

**Top open item. Conclusive. Needs an owner decision — every remedy is one
I deliberately did not take unattended.**

- **20 minutes into the US regular session** (opened 13:30Z, measured
  13:50:09Z): **SPY age 1070 min (17.8 h)**, SLV 1070 min, UBER 1070 min,
  BTC-USD 370 min. **SPY cannot go 17.8 hours without a print during market
  hours.** `marketState` is absent from the payload entirely.
- **BTC-USD's age grew 282 → 370 min across 88 minutes of wall clock — 1:1.**
  The data is not lagging, it is completely static.
- **The US open changed nothing**, which eliminates session semantics. Not
  Alpha Vantage (different provider). Not our clock (verified twice).
- **It is now filling orders inside a live session:** 972 filled SLV at
  56.07 at 13:41:30, eleven minutes into the session, against a 17.8-hour-old
  price. **4 of 7 live runs are priced off this snapshot** (GC, SI, SLV,
  USDKRW); only the Hyperliquid-served crypto runs have real marks.
- **The desk is not at fault and cannot fix it.** #260's clause endorses
  reduce/close on a frozen mark and the desk complied; it cannot control the
  price a fill receives.
- **Remedies, none shipped:** (a) halt the Yahoo-served markets — *halts
  trading*; (b) switch provider for futures/forex/us-stock — needs a decision
  and credentials; (c) record the upstream timestamp without gating — alembic
  column, no behaviour change.

### 🔍 Added 2026-08-06 (cycle 85) — the frozen feed is UPSTREAM Yahoo staleness

**Supersedes the cycle-82 framing. It is NOT the Alpha Vantage rate limit** —
that note reported the two together and implied a link that was never
established. AV serves Market Intel; the price path is Yahoo.

- **Yahoo returns ~4.8-hour-old data to this host on EVERY ticker**, measured
  from its own timestamps at 12:20:26Z: GC=F 290 min, SI=F 290 min,
  USDKRW=X 280 min, SLV 980 min, **BTC-USD 280 min**.
- **BTC-USD trades 24/7 and cannot be 4h40m without a print.** The last 1-min
  *candle* is equally old, so it is not a `regularMarketPrice`-outside-session
  artefact — that hypothesis was tested and refuted.
- The split is exact: **every Yahoo-served market frozen** (futures, forex,
  us-stock) and **every Hyperliquid-served market live** (crypto).
- **Verify the host clock before trusting any staleness claim.** `date -u`
  vs an external `Date` header, plus `chronyc tracking`. It was exact here.
- **Why it is invisible:** `mark_age_ok` measures OUR fetch time. Yahoo gives
  us its own timestamp and `_get_yahoo_chart_price` discards it. A stale
  upstream answering 200 OK looks identical to a live one.
- ⚠️ **Do NOT ship the obvious fix unattended.** Gating on true staleness
  would **halt the fleet the moment it deployed**, because the marks are
  stale right now. It also likely needs an alembic column for the upstream
  timestamp.

**Recipe to re-check (read-only, from the prod container):** fetch
`query1.finance.yahoo.com/v8/finance/chart/<ticker>` with the Yahoo UA and
compare `meta.regularMarketTime` and the last non-null 1-min candle timestamp
against `now`.

### 🚨 Escalated 2026-08-06 (cycle 83) — the freeze is a FILL-PRICE problem too

- **Trades are EXECUTING at frozen marks.** 977 exited GC at
  `4320.700195` — the identical price it had printed for 70+ minutes — and
  booked +1.65 measured against that stale number. Cycle 82 framed the freeze
  as a decision-quality issue; it is also a **fill-quality** one. The book is
  being marked *and transacted* at a number that is not moving.
- #259 shipped the desk's ability to SEE it (`_mark_freshness_line`). It does
  not change what price a fill gets. That remains part of the open provider
  decision below.

### 🚨 Added 2026-08-06 (cycle 82) — A FRESH TIMESTAMP IS NOT A FRESH PRICE

**TOP OPEN ITEM — needs an owner decision, deliberately not shipped.**

- **`mark_age_ok` checks `price_updated_at`, NOT whether the value moved.**
  A feed that keeps answering with a stale quote refreshes the timestamp
  every ~90s and is invisible to every staleness check in the engine.
- **Observed 2026-08-06:** GC frozen **2h26m** at `4320.700195`, SI frozen
  **2h05m** at `62.099998`, USDKRW static at `1428.310059` — while BTCUSDT
  moved normally. All four marks were 91s "fresh".
- **How to re-check it (cheap, read-only):** count consecutive `equity`
  events with identical `unrealized` (the emitter dedupes on a changed
  total, so repeats mean the mark truly did not move); confirm with
  `get_price_from_market` called twice in the image; then check
  `docker logs sooppiy-worker | grep -i "rate limit"`.
- **Alpha Vantage was fully rate-limited** (*"25 requests per day"*) across
  equities, macro, crypto and commodities. Relates to the existing "watch
  FMP tier thinness" item.
- ⚠️ **Do NOT ship a value-staleness guard casually — it HALTS TRADING when
  it fires.** Quiet markets are real. Two separable owner decisions: (a) the
  data provider/tier, (b) whether a frozen-value condition should pause
  runs, merely warn, or only be surfaced by a read-only detector.

### Added 2026-08-06 (cycle 82) — watch (ii) ANSWERED: the arm executor is sound

- **64 arms authored, 0 `armed_exit` events, ever** — and it is **not** a
  dead executor. Verified: `order_intent.arm_fires()` is 5/5 correct tested
  live in the image, and `_fire_armed_order` is provably reached because
  `_maybe_emit_equity` sits AFTER it in `_control_active` and equity events
  flow. **No arm level has ever been crossed** (all four standing arms
  0.48–0.88% short, price reconstructed from equity events).
- **`_store_armed_order` runs ONLY on `intent == "arm"`** (`run_engine:3796`),
  so a reduce/hold cycle leaves the previous arm standing. The comment "each
  cycle's arm replaces the last" is true only of arming cycles. Noted; not
  yet shown harmful.

### Added 2026-08-06 (cycle 81) — COMPARE THE IMAGE TAG EVERY VERIFICATION PASS

- **A parallel session can redeploy prod between your deploy and your next
  check.** Cycle 81's verification found `20260806-prunebackups` where
  `20260806-pendflush` had been 20 minutes earlier — another session shipped
  #258 on top of #257.
- **A green health check cannot see this.** Containers up, events flowing,
  0 tracebacks — all true, and all true of *someone else's build*. The only
  thing that catches it is reading `{{.Config.Image}}` and comparing.
- **When it happens, verify rather than assume:** re-check your own change is
  still wired (`inspect.getsource` from inside the image) and sha256 your
  files against `origin/main`. #257/#255 survived intact because the other
  session built from fresh main — but that was confirmed, not hoped.

### Added 2026-08-06 (cycle 80) — `[TradingRuns] tick` silence is NOT a dead loop

- **`tasks.py:795` prints that line ONLY when `dispatched` or `armed_started`
  or `stopping_finished` is truthy.** An empty grep across the whole worker
  log means *nothing was due*, not that the control loop stalled. Run cycles
  are ~45 min apart, so multi-minute silences are normal.
- **Positive liveness proof, use this instead:** `_maybe_emit_equity` is
  called from `_control_active`, on the SAME tick as `_control_stopping`.
  Fresh `equity` rows in `run_events` therefore prove the control loop — and
  #257's flush path — is running. Absence of a log line is not evidence;
  presence of an equity event is.

### Added 2026-08-06 (#257) — "fixed on the next cycle" means LOST when the run dies

- **Decompose a drift before naming it.** The standing `pnl_audit` DRIFT was
  labelled "the known adapt-omits-flattens gap" for days. Decomposed to the
  cent, the flatten gap was **+0.40 of a −9.56 delta**; the real term was
  **−6.69 (70%)** from a *different* defect, and −3.20 was by design. **A
  standing alarm with an inherited explanation is an unexamined alarm.**
- **When a fix's rationale explains a mechanism, check every instance of that
  mechanism.** #249's comment said "no later cycle ever processes this leg"
  — true of the flatten leg it fixed, and equally true of every other close
  pending when a run stops. It fixed one and left the rest for six days.
- **Anything journalled "next cycle" is lost exactly when the run dies** —
  which is exactly the worst moments. Same shape as #241/#244/#245: the
  system is blind precisely where it most needs to see.
- ⚠️ **The fix is forward-only.** `_control_stopping` visits `stopping`
  runs; already-`stopped` runs keep their hole, so a historical DRIFT line
  does NOT clear retroactively. Do not read that as the fix failing.
- ⚠️ **OPEN, deliberately not shipped:** entry-side fees (component (a)) keep
  the delta non-zero — ~−3.20 on a 4-newborn day against a $5.00 tolerance —
  so busy days still raise a BENIGN drift alarm. **Do not chase it as a bug.**

### Added 2026-08-06 (#254/#255) — the trap above repeated ONE PR LATER

The `#253` lesson below was written, and then broken immediately. #254's new
in-band table was unit-tested green and **got run 976 — the single case whose
outcome is known — exactly backwards**, printing the textbook retro-arm as
`survived`. Three live-only defects, all fixed in #255:

- **Same-second is not the only collision; the NEXT second is too.** 976
  reduced at `05:40:01`, the rail flattened it at `05:40:02`. Matching a fire
  to its reduce on second-equality missed it. Match on a **window**, and
  lower-bound it so a fire *before* the reduce cannot count.
- **Do not judge history against a rail that did not exist yet.** The
  breakeven ratchet merged `2026-08-06 01:45Z`. The table scored eight
  08-01/08-02 reduces against it and called them all "survived" — eight
  counts of evidence for nothing. **Gate every retrospective question on the
  feature's own arrival time** (`RATCHET_TS`).
- **Check your own column widths before believing the column.** A book
  reduced to a sliver has an arm of `$0.004`; at 2dp that printed `0.00` and
  made the band read as trivially satisfied on 9 of 11 rows.

⚠️ **973 IS NOT A RETRO-ARM.** An earlier session recorded it as the second
instance. Its fire (`2026-08-06T00:21:23`) predates the ratchet's own merge by
**84 minutes** and its reduce was 2h02m earlier. **Confirmed count is n=1
(976).** What actually fired 973 is unexplained by either emitter under its
stored config (legacy `activate_usd` 82.42 vs peak 1.72 — cannot arm; ratchet
did not exist). **Open question — do not assert either way without evidence.**

### Added 2026-08-06 (#253) — a monitoring TOOL can carry the same defects it hunts

- **RUN A NEW AUDIT TOOL AGAINST LIVE PROD BEFORE TRUSTING IT.**
  `ratchet_audit`'s unit tests all passed while the tool was wrong twice:
  (a) the fire's own **flatten leg shares the fire's timestamp**, so a
  `ts <= fire_ts` snapshot counted the liquidation as the book that
  preceded it — 15 of 16 historical fires read as flat, and post-fix the
  first genuine fire would have raised a false alarm; (b) a stop emits
  **two `run_status` rows both containing "stopping"**, double-counting
  every fire. Neither showed up in fixtures because fixtures use tidy
  distinct timestamps. Live data has same-second events.
- **A shared reason string means a shared alarm — check who else can raise
  it.** `stop_event:trailing_lock` is emitted by BOTH the breakeven ratchet
  and the legacy trail, and only the ratchet can retro-arm (the legacy
  `activate_usd` is a fixed dollar figure set at build). Declaring a
  shrunken-book fire a "regression" would have accused normal legacy
  behaviour. Flag for REVIEW and name the disambiguator instead.
- **Prefer tightening your own prose to raising `MAX_BLOCK_LEN`.** The
  first draft of the arm clause pushed `Execution Plan Check` out of the
  trader block. The budget test catches this; the fix is a shorter clause,
  not a fifth budget raise.

### Added 2026-08-05/06 — every one of these cost real time in one session

- **A reduce can retro-arm the breakeven floor.** The floor's arm
  threshold is recomputed from the CURRENT book at every evaluation while the
  peak is a lifetime high-water mark — shrinking the book shrinks the arm
  under an old peak and can fire an instant full flatten (run 976,
  cycle 75). When attributing any `stop_event:trailing_lock`, check
  whether a desk reduce landed in the same second before calling it a
  clean ratchet fire — and remember the reason string is SHARED by the
  legacy trail and the ratchet (the log line `breakeven ratchet fired`
  disambiguates).
- **A final-cycle close never emits its adapt.** `losing_close`/
  `winning_close` adapts fire on the NEXT cycle; a run that stops right
  after a reduce (976) leaves that leg permanently absent from the adapt
  stream. Entry fees likewise sit in ledger-realized before any close.
  Both are STRUCTURAL pnl_audit deltas — decompose before suspecting the
  flatten journal.

- **A brief line that renders but is not WIRED is a no-op that looks
  tested.** Unwiring `_brake_distance_line` from the light prompt passed the
  ENTIRE 3313-test suite. Helpers are tested by direct call; nothing
  asserted the string reaches the prompt. **Every new brief line ships with
  a wiring test** (patterns in `BrakeDistanceBriefTests` / `ExitSizeBriefTests`).
- **Ledger replay: SHORT-COVER SIGN.** A naive replay keeps a signed `cost`
  and does `cost -= avg*closed` on every close. A short's basis is NEGATIVE,
  so that drives it away from zero and corrupts every later average. It
  reported **+116,756 on a run that made +13.19** — and stays plausible on
  small runs. Track `avg` (always positive) and signed `qty` separately.
  Use `pnl_audit.replay_realized`; do not rewrite it.
- **Ledger replay: WINDOW-SCOPED = phantom opening leg.** Replaying only the
  query window invents an opening trade for any position carried across
  midnight. Always replay each run from INCEPTION and attribute per-leg.
- **`unrealized` snaps to 0 at the close.** Reading it instead of `total`
  made a simulation appear to show the breakeven ratchet cutting 969, the
  day's best run. It did not. **Use `total`, and evaluate only while a
  position is actually held.**
- **Recompute a rail before comparing against it.** 960 looked like it was
  ignoring the Risk rail (repeating a 3.05% stop against a 2.59% rail). It
  had REDUCED its position 4×, so its rail was 11.69% and the stop correctly
  bound first. Comparing to a stale rail figure would have filed a false
  finding.
- **Do not count a profitable exit as evidence for the exit-verb lesson.**
  The Exit scale line is SILENT when the position is in profit, so the
  lesson's trigger context is absent. Only an exit where the line actually
  rendered counts.
- **Match `signal_id` RUN-SCOPED, not globally.** A global `IN (...)` match
  reported "5 adapts reference a flatten signal" and appeared to contradict
  a no-double-count claim. Run-scoped the answer is 0 — signal_ids repeat
  across runs.
- **Equivalent mutants exist; report them as such.** Dropping an explicit
  `mark is None` check changed nothing because `float(None)` raises and the
  existing `except` already returned False. Do not claim it as a caught bug.
- **`git checkout <file>` DESTROYS uncommitted work.** Used to revert a
  mutation on a file with new uncommitted functions, it wiped them. Use a
  backup copy (`cp file /tmp/bak`) for mutation testing, never git.
- **A squash merge makes the next stacked PR `DIRTY`.** #247 squash-merged,
  then #248 conflicted with main. Rebuild the branch on fresh `origin/main`
  and open a new PR rather than fighting the conflict.
- **The cron prompt goes stale and will send the next cycle chasing solved
  work.** It listed FINDING 1 as unfixed two cycles after it shipped.
  **Refresh the cron prompt whenever a carried item closes.**

- **DB clock, not wall clock.** See §4.1.
- **`ts` is an ISO string.** Space-separated datetime literals match the whole
  day silently.
- **`created_at` does not exist** on `run_events`.
- **`run_events.seq` is NOT NULL** — test seeders must supply it.
- **Prod image has no pytest** — verify in-image with `unittest`.
- **Parallel sessions deploy to the same box.** Always drift-guard against the
  parent commit hash; another session's image may already be live.
- **`git checkout main` fails** in a worktree (main is checked out elsewhere)
  — use `git checkout --detach origin/main`.
- **A flag with no executor is a no-op** — grep consumers to a side effect
  before believing a feature is live (`consecutive_infeasible`, for instance,
  counts only insufficient-cash skips and is blind to rr_floor churn).
- **Mutation tests need `__pycache__` cleared**, and the mutation must be
  asserted as actually applied.

## 11. Where things live

- Cycle notes: `docs/reports/YYYY-MM-DD-automation-monitoring.md` (per UTC day)
- Snapshot: `docs/reports/automation-snapshot.json`
- Skills: `service/server/trading_skills.py` (`BASE_SKILLS`); catalogue
  auto-upgrades on edit via `catalog_hash` (`updated_by='seed-upgrade'`);
  admin edits win until reset.
- Desk brief lines: `run_engine.py` — `_position_state_line`,
  `_earnings_state_line`, `_breadth_state_line`, `_hold_streak_line`
  (wired on **both** the light and full prompt paths).
- ⚠️ Memory (`~/.claude/.../memory/`) is a **CACHE, never the source of
  truth** — it is wiped every ~3 days by account rotation. This file wins.
  While it exists it is a useful fast index:
  `~/.claude/projects/-Users-desirey-Programming-src-ai-trade/memory/`
  — read `MEMORY.md` first; `decisions-become-skills`,
  `automation-monitoring-operating-model`, `trading-skills-mechanism`,
  `never-touch-live-trading-config`, `call-user-henry` are the load-bearing
  ones for this job.

## 12. True unattended 24h coverage — the EC2 timer (DESIGNED, NOT BUILT)

**The problem.** Both crons are session-only: they die with the session and
only fire while it is idle. So "24-hour monitoring" is really "hourly
whenever a session happens to be open and idle." This has already cost a
3-hour gap and a 2.8-day gap, and slot 22:17 on 2026-08-05 was skipped.

**What a server-side timer can and cannot do.** It **cannot** replace the
analysis loop — designing skills, judging evidence and shipping fixes need
the model. What it CAN do is guarantee the *evidence* is captured and
pre-screened for every window, so a session gap becomes "review 8 hours of
recorded evidence" instead of "those 8 hours are unreviewed forever."

**Design (three parts):**

1. **Collector** — a systemd timer (or crontab) on the EC2 box, every
   15–30 min. Runs the standard read-only queries (`run_events` by `ts`,
   `trading_runs`, `positions`, worker traceback count), computes the
   **flatten-reconciled** P&L, and appends one compact JSON line to
   `~/sooppiy/monitor/YYYY-MM-DD.jsonl`. Rotates/prunes on a retention
   window.
2. **Deterministic alarms** — rules that need no AI, each writing an
   `ALERT` line: traceback count > 0; a run retired on **cycle 1** (newborn
   regression); a `drawdown_brake` fired; a **full close (`size_frac 1.0`)
   on a sub-1% move**; realized loss beyond a threshold; event stream
   stalled beyond N minutes.
3. **Review on connect** — the next session reads the jsonl since the last
   reviewed timestamp. The hourly cycle becomes "review captured evidence
   and act", and nothing is silently missed.

**Non-negotiable constraints if this is built:**
- **STRICTLY NON-ACTUATING.** Record and alarm only. It must never restart a
  container, never touch a run, never write to the DB. A healthy prod worker
  was once restarted on a false alarm (§10) — an automated actor with the
  same blind spot would be worse.
- **Read-only DB access** (SELECT only).
- Must not contend with the trading containers for CPU or DB connections.
- Disk retention bounded.

**Status: offered to the owner 2026-08-05, awaiting a decision.** It is new
prod infrastructure, so do not build it unasked.
