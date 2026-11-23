# Handoff — the local CI gate (2026-11-22)

For the next programmer picking up Sooppiy's ship process. Read this before
changing `scripts/ci-local.sh` or `scripts/deploy.sh`.

## 1. Why this exists

The ship process is local-only (owner rule 2026-08-31: no GitHub CI and no
GitHub PRs as the gate; see `CLAUDE.md` → "Ship Process — LOCAL ONLY"). Until
this change, the rule "run every CI job locally before merging" existed only
as prose in `CLAUDE.md` and in agent memory:

- GitHub Actions still runs `ci.yml` and `security.yml`, but only **after**
  the push to `main`, and nothing waits for the result.
- `scripts/deploy.sh` checked that the tree is clean and equals
  `origin/main`, and ran a **warn-only** pip-audit. It never ran pytest, ruff
  or any other job.

So a commit no test had ever run on could reach production. The gate turns
that prose rule into a check: **`deploy.sh` now refuses any tree that has
not passed every CI job.**

The trigger was a review of Lauren Tan's talk "All Code Is Slop (Except
Mine)" (via a Korean AgentOS walkthrough,
https://www.youtube.com/watch?v=ueA116hO_ho). Its rule: every time you correct
an agent, the correction becomes a deterministic check, not another line in a
rules file. Its second rule: fix the inner loop before you automate it. Our
inner loop was "remember to run CI locally".

## 2. What shipped

| File | Change |
|---|---|
| `scripts/ci-local.sh` (new) | Runs every job in `.github/workflows/*.yml`. Exits 0 only if all pass and prints `GATED <sha>` as its last line. |
| `scripts/deploy.sh` step 1b | Runs the gate before the lock, the upload and every mutation (`--dry-run` included), then re-checks that the tested commit is still the one being shipped. Replaces the old warn-only pip-audit. |
| `scripts/deploy.sh` step 3 | `git archive "$MAIN_SHA"` instead of `HEAD`, so the archive is exactly the gated commit. |
| `CLAUDE.md` ship step 2 | Points to `scripts/ci-local.sh`. |

## 3. How to use it

```bash
# on a feature branch, before merging (secret scan covers origin/main..HEAD)
scripts/ci-local.sh

# with an explicit start for the secret-scan range
scripts/ci-local.sh <base-commit>

# deploy: runs the gate itself, scanning secrets since the last deploy
scripts/deploy.sh <tag-suffix>
```

A full run takes about 13 minutes; pytest (5,663 tests) is the long job. A
later run of the **same tree** reuses the earlier pass and takes seconds. The
normal flow is gate at merge, then deploy: a squash or fast-forward merge
keeps the tree identical, so the deploy only re-runs the fast jobs.

## 4. How it works

**What is tested.** The gate never tests the checkout you run it from. It
makes a private `git clone` of HEAD's commit in a temp directory and runs
every job there. Why:

- Ignored files in a checkout change results. The root `.env` is loaded into
  `os.environ` by `service/server/config.py` and holds real keys and trading
  flags; `node_modules` and stray DBs matter too.
- Another session moving HEAD mid-run cannot change what is tested.

The gate refuses to start if the invoking tree has uncommitted or untracked
files, so nobody assumes their edits were tested.

**Environment.** Jobs run under `env -i`, keeping only HOME, PATH, USER,
LOGNAME, TMPDIR, `LANG=en_US.UTF-8` and `TZ=UTC`, as on a CI runner. Keys
exported in your shell never reach the tests.

**Jobs**, each reported separately:

| Job | From | Command (cwd) |
|---|---|---|
| gitleaks | security.yml | `gitleaks detect --redact --log-opts=BASE..HEAD` (clone root) |
| pip-audit | security.yml | `pip-audit -r constraints.txt --no-deps --disable-pip` (`service`) |
| npm-audit | security.yml | `npm audit --audit-level=high --omit=dev` (`service/frontend`) |
| pip-install | ci.yml | `uv venv --python 3.12` + `uv pip install -r requirements-dev.txt` (`service`) |
| ruff | ci.yml | `ruff check server/ --select F401,F811,F821,F841` (`service`) |
| pytest | ci.yml | `DB_PATH=<per-run> ALPHA_VANTAGE_API_KEY=demo pytest -q` (`service/server`) |
| npm-ci | ci.yml | `npm ci` (`service/frontend`) |
| frontend-build | ci.yml | `npm run build` = `tsc && vite build` (`service/frontend`) |

The backend chain and the frontend chain run in parallel. A job that never
ran (because an earlier step in its chain failed) is shown as SKIP, and SKIP
counts as a failure.

**The pass record.** The five build and test jobs depend only on the tree. On
success they are recorded in `~/.cache/sooppiy-ci/<tree-hash>.pass`
(`$XDG_CACHE_HOME` is honoured).

- A record counts only if it names all five jobs as PASS; an empty or
  partial file is ignored.
- The decision to use a record is made once, at start, so a record another
  session writes mid-run cannot hide this run's failures.
- **gitleaks, pip-audit and npm-audit run every time** and are never cached:
  new advisories appear daily, and the secret-scan range moves.
- The record is a cache, not a signature. A hand-written file with all five
  PASS lines is trusted. Forging one is a deliberate act; the gate exists to
  stop forgetting, not sabotage.

**The deploy wiring** (`deploy.sh` step 1b):

1. Read the last deployed commit from the box: the third field of the last
   row with 3+ fields in `/home/ec2-user/sooppiy/deploy-log.tsv`. It must
   exist in local history.
2. Run `scripts/ci-local.sh <last-deployed>`, so the secret scan covers
   exactly what is new on prod. Capture the `GATED` line.
3. Die unless `GATED == MAIN_SHA`.
4. Re-fetch, and die if origin/main moved, if HEAD moved, or if the checkout
   changed during the gate. Otherwise a slower deploy could overwrite a newer
   one.
5. Only then take the lock, capture the guard, upload and build.

## 5. Deviations from the workflow files (forced by this machine)

- **Install:** `uv pip` into a fresh venv; there is no python3.12 on this
  Mac.
- **pip-audit:** it cannot bootstrap a resolver here (`ensurepip` aborts in
  uv pythons), so it audits the prod lock `service/constraints.txt` with
  `--no-deps`. `requirements.txt` is constrained by that file, so these are
  the exact versions the image installs.
- **DB_PATH:** per run, so two gates can run at once.
- **Node:** the host's version (v26), not the Node 22 that ci.yml uses. The
  prod image rebuilds the SPA on `node:20` (Dockerfile); a failure there
  stops the deploy before the swap.
- **gitleaks:** scans only the range. A full-history scan reports five
  pre-existing findings (`docs/ops/apple-signin-setup.html` ×2, a test
  fixture, `skills/sooppiy/SKILL.md` ×2) and would fail every run.
  security.yml's weekly scheduled full scan is not reproduced.

What a local run does **not** give: a clean-room runner, the hosted audit
trail, and any check that needs provider secrets.

## 6. Behaviour change you must know about

**An advisory published today now blocks deploys** until the pin in
`service/constraints.txt` is bumped. The old step 1b was deliberately
warn-only ("an advisory published this morning must not block an unrelated
trading fix"). That conflicted with the owner's merge rule, which already
required pip-audit to pass. The gate follows the merge rule.

Fix path: bump the pin, keeping pip-freeze spelling and transitives (see the
lock-bump recipe in the deps memory), re-run the gate, then deploy. Do not
add a skip switch without the owner's decision.

## 7. Evidence (2026-11-22)

**Probe runs** in scratch clones:

| Run | Commit | Result |
|---|---|---|
| Clean | `79ad229` | All 8 jobs PASS. Real pytest 776 s (5,663 passed, 1,349 subtests) under `env -i`. `GATED` printed, exit 0. |
| Broken on purpose | `616efc9` | Unused import, failing test, TS type error and fake AWS key planted. Exactly gitleaks, ruff, pytest and frontend-build FAIL (pytest: 1 failed = the probe, 5,663 passed). Audits and installs PASS. Exit 1, no record. |
| Cached tree + secret | `b1a9f1a` + probe | Build and test jobs skipped from the record; gitleaks still FAIL. Exit 1. |

**Two-agent review** (owner rule): one adversarial reviewer, one independent
verifier, two rounds each.

- **Round 1** found two blockers, both fixed:
  - The tested tree was never re-checked against what ships; deploy now
    re-asserts and archives `MAIN_SHA`.
  - A cached tree skipped the audits; audits now run every time.
- **Round 1** should-fix items, all fixed:
  - Record checked twice (race).
  - Gate ran in place (`.env` leak).
  - Untracked files hidden by `status.showUntrackedFiles`.
  - Shared `node_modules`.
  - deploy-log parse.
- **Round 2:** no false PASS and no blocker. Should-fix: jobs rewriting the
  clone; now checked.
- **Round 2** nits fixed: `TZ=UTC`, a message on fetch failure, gitleaks
  inside the clone over a range pinned at start.
- **Verifier, both rounds:**
  - Every refusal case exits 1 with no job run.
  - Every stubbed failure fails the gate and writes no record.
  - deploy.sh dies before any upload in every failure case.
  - With a passing gate, the uploaded tarball's commit id equals
    `MAIN_SHA`.

## 8. Known limits left open (nits, none gives a false pass)

- **Ctrl-C cleanup:** `pkill -P` kills only the direct children of the job
  chains, so grandchildren (tsc/vite under npm, uv under `sh -c`) can outlive
  it. The gate still exits non-zero.
- **`tee /dev/stderr` in deploy.sh:** if stderr is closed (`deploy.sh 2>&1 |
  head`), the gate pipeline dies with a misleading "gate failed". It fails
  closed.
- **Old copy of the script:** `ci-local.sh` gates the repo of the current
  directory. Running an old copy from another checkout would use old logic.
  `deploy.sh` always calls its own copy.
- **Audit failure costs a full re-run:** when the tree jobs pass but an audit
  fails, no record is written, so the next run repeats the ~13-minute tree
  jobs.
- **Docs-only commits** change the tree and so pay a full run.
- **GitHub CI** still runs after the push; it is now redundant evidence, not
  the gate.

## 9. Remaining gaps from the same review (not done)

Ranked, from the review of the "pyramid" layers:

1. **No test touches real MySQL**, though prod runs MySQL 8. The 9
   MySQL-related test files use fake URLs or mocks. Memory records at least
   six MySQL-only traps: FOUND_ROWS, FK on deleted rows, VARCHAR(64),
   `T`-vs-space timestamps, `LIKE ESCAPE '\'`, and SQLite-only migration
   blocks. Next step: a MySQL 8 container job in `ci-local.sh` for those
   paths and for `alembic upgrade head`.
2. **Lint is 4 rules.** Ruff's bugbear rules report 156 hits, including B023
   (1), B006 (2) and B905 (29); none has been checked yet. Python has no type
   checker. The frontend has no ESLint and **0 tests**.
3. **No property-based or formal tests.** Candidates: ledger and P&L replay
   invariants (`pnl_audit`), and the signed-quantity / uPNL sign convention.
4. **Lessons still only in prose.** Sampled: "never re-add authlib" and
   "`MARKET_I18N_MODEL` must be empty" have no check. The installed
   `pstack:correct` skill is designed to turn a repeated correction into a
   lint rule or test.
