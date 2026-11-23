#!/usr/bin/env bash
# The local CI gate: every job in .github/workflows/*.yml, run on this machine.
#
# Why this exists: the ship process is local-only (owner 2026-08-31: no GitHub
# CI, no GitHub PRs). The merge gate — "run every CI job locally before
# merging" — lived only as prose in CLAUDE.md and memory. GitHub CI still runs,
# but only AFTER the push to main, and nothing waited for it: deploy.sh checked
# main parity and nothing else, so a tree no test had run on could ship. This
# script is that gate as a check, and deploy.sh refuses to deploy without it.
#
# Usage:
#   scripts/ci-local.sh [BASE]
#     BASE  start of the secret-scan range BASE..HEAD (default origin/main —
#           right for a feature branch; deploy.sh passes the last deployed
#           commit so the scan covers exactly what is new on prod).
#
# Exit 0 only when every job passed; each job is reported separately. The last
# line of output on success is `GATED <commit>` — the commit that was tested.
#
# What is tested is a fresh clone of HEAD's commit, never the invoking
# checkout: ignored files there (a .env that config.py loads into os.environ,
# node_modules, a stray DB) would change what passes, and another session moving
# HEAD mid-run cannot change what this run tests. Jobs run with a scrubbed
# environment (env -i, TZ=UTC), as on a CI runner, so shell-exported API keys
# cannot reach the tests.
#
# Build and test jobs (install, ruff, pytest, npm ci, build) depend only on the
# tree, so a pass is recorded under the tree hash and a later run of the same
# tree — the deploy of a tree that passed at merge — reuses it instead of paying
# ~15 minutes again. The audits and the secret scan do not depend on the tree
# alone (advisories are published daily; the range moves), so they run every
# time.
#
# Deviations from the workflow files, each forced by this machine:
#   - deps install with `uv pip` into a fresh venv (no python3.12 here).
#   - pip-audit cannot bootstrap a resolver (`ensurepip` aborts in uv pythons),
#     so it audits the prod lock directly: service/constraints.txt with
#     --no-deps. requirements.txt is constrained by that file, so these are the
#     exact versions security.yml would resolve and the image installs.
#   - DB_PATH is per-run, not the fixed /tmp/sooppiy-ci.db.
#   - gitleaks scans BASE..HEAD only. security.yml's weekly scheduled run also
#     scans full history; a full scan here would report the five pre-existing
#     findings (docs/ops/apple-signin-setup.html x2, a test fixture, SKILL.md
#     x2) and fail every run.
#   - Node is the host's, not Node 22. The prod image builds the SPA again on
#     node:20 (Dockerfile) and a failing build there stops the deploy before
#     the swap, so a Node-version break is still caught before it serves.
# What a local run does NOT give: a clean-room runner, the hosted audit trail,
# and any check needing provider secrets.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

die() { echo "FATAL: $*" >&2; exit 1; }
say() { echo "▶ $*"; }

BASE="${1:-origin/main}"

for tool in git uv node npm gitleaks pip-audit; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is not installed — the gate cannot run, so it fails"
done
[ -z "$(git status --porcelain --untracked-files=all)" ] \
  || die "working tree has uncommitted or untracked files — the gate tests committed work only"
BASE_SHA=$(git rev-parse -q --verify "$BASE^{commit}") || die "base '$BASE' is not a commit in this checkout"

HEAD_SHA=$(git rev-parse HEAD)
TREE=$(git rev-parse "$HEAD_SHA^{tree}")
RECORD_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/sooppiy-ci"
RECORD="$RECORD_DIR/$TREE.pass"
mkdir -p "$RECORD_DIR"

TREE_JOBS="pip-install ruff pytest npm-ci frontend-build"
EVERY_RUN_JOBS="gitleaks pip-audit npm-audit"

# Decide ONCE whether the tree jobs are reused. A record that another session
# writes while this run is going must not shrink what this run reports. A
# record counts only if it names every tree job as passed — an empty or
# partial file does not. (It is a cache, not a signature: a file written by
# hand with all five PASS lines is trusted. Forging one is deliberate, not the
# forgetting this gate exists to stop.)
USE_RECORD=1
for name in $TREE_JOBS; do
  grep -qE "^$name PASS " "$RECORD" 2>/dev/null || USE_RECORD=0
done

WORK=$(mktemp -d "${TMPDIR:-/tmp}/sooppiy-ci.XXXXXX")
BPID="" FPID=""
cleanup() {
  for p in $BPID $FPID; do
    pkill -TERM -P "$p" 2>/dev/null || true
    kill -TERM "$p" 2>/dev/null || true
  done
  rm -rf "${WORK:?}"
}
trap cleanup EXIT
STATUS="$WORK/status"
: > "$STATUS"

# job <name> <cmd...> — runs in the current directory with a scrubbed
# environment, logs to $WORK/<name>.log, appends "<name> PASS|FAIL <seconds>"
# to $STATUS. Never pipes the command, so its own exit code is the one recorded.
# Pass job-specific variables as `env VAR=value cmd`.
job() {
  local name=$1; shift
  local t0=$SECONDS
  if env -i HOME="$HOME" PATH="$PATH" USER="${USER:-}" LOGNAME="${LOGNAME:-}" \
       TMPDIR="${TMPDIR:-/tmp}" LANG=en_US.UTF-8 TZ=UTC "$@" >"$WORK/$name.log" 2>&1; then
    echo "$name PASS $((SECONDS - t0))" >> "$STATUS"
  else
    echo "$name FAIL $((SECONDS - t0))" >> "$STATUS"
    return 1
  fi
}

say "gate for ${HEAD_SHA:0:7} (tree ${TREE:0:12}), secret range ${BASE}..HEAD"

# A private clone of exactly HEAD_SHA. Local clone = hardlinked objects, ~1 s.
SRC="$WORK/src"
git clone -q --no-checkout "$(git rev-parse --path-format=absolute --git-common-dir)" "$SRC" \
  || die "could not clone the repository for the gate"
git -C "$SRC" checkout -q --detach "$HEAD_SHA" || die "could not check out $HEAD_SHA in the gate clone"

# Secret scan — security.yml / secret-scan. Scoped to the range: a full-history
# scan reports five pre-existing findings and would fail every run. Runs in
# the gate clone (its .gitleaks.toml is HEAD_SHA's), over a range pinned to
# commits at start.
(cd "$SRC" && job gitleaks gitleaks detect --no-banner --redact --log-opts="$BASE_SHA..$HEAD_SHA") || true

# security.yml / python-audit, against the prod lock (see Deviations).
(cd "$SRC/service" && job pip-audit pip-audit -r constraints.txt --no-deps --disable-pip) || true

if [ "$USE_RECORD" = "1" ]; then
  say "build and test jobs already passed for this tree: $(head -n 1 "$RECORD")"
  # security.yml / npm-audit reads package-lock.json; it needs no node_modules.
  (cd "$SRC/service/frontend" && job npm-audit npm audit --audit-level=high --omit=dev) || true
else
  PY="$WORK/venv/bin/python"
  backend() {
    # ci.yml / backend: install, ruff, pytest.
    cd "$SRC/service"
    job pip-install sh -c "uv venv -q --python 3.12 '$WORK/venv' && uv pip install -q --python '$PY' -r requirements-dev.txt" || return 0
    job ruff "$PY" -m ruff check server/ --select F401,F811,F821,F841 || true
    cd server
    job pytest env DB_PATH="$WORK/sooppiy-ci.db" ALPHA_VANTAGE_API_KEY=demo "$PY" -m pytest -q || true
  }
  frontend() {
    # ci.yml / frontend: npm ci, tsc + vite build. security.yml / npm-audit.
    cd "$SRC/service/frontend"
    job npm-audit npm audit --audit-level=high --omit=dev || true
    job npm-ci npm ci || return 0
    job frontend-build npm run build || true
  }
  say "running backend and frontend jobs in parallel (pytest takes the longest)"
  backend & BPID=$!
  frontend & FPID=$!
  wait "$BPID" || true
  wait "$FPID" || true
  BPID="" FPID=""
fi

# Every expected job must have reported, or the gate fails: a job that never
# ran is not a pass.
EXPECTED="$EVERY_RUN_JOBS"
[ "$USE_RECORD" = "1" ] || EXPECTED="$EXPECTED $TREE_JOBS"

echo
printf '  %-16s %-6s %s\n' JOB RESULT SECONDS
FAILED=0
for name in $EXPECTED; do
  line=$(grep -E "^$name " "$STATUS" || true)
  if [ -z "$line" ]; then
    printf '  %-16s %-6s %s\n' "$name" "SKIP" "-  (did not run: an earlier step failed)"
    FAILED=1
  else
    read -r _ result secs <<<"$line"
    printf '  %-16s %-6s %s\n' "$name" "$result" "$secs"
    [ "$result" = "PASS" ] || FAILED=1
  fi
done
echo

if [ "$FAILED" = "1" ]; then
  LOGS="$RECORD_DIR/fail-${TREE:0:12}"
  rm -rf "${LOGS:?}" && mkdir -p "$LOGS" && cp "$WORK"/*.log "$LOGS"/ 2>/dev/null || true
  while read -r name result _; do
    [ "$result" = "FAIL" ] || continue
    echo "── $name (last 40 lines) ──"
    tail -n 40 "$WORK/$name.log"
  done < "$STATUS"
  die "local CI gate FAILED for ${HEAD_SHA:0:7} — full logs in $LOGS"
fi

# The jobs must not have rewritten the tree they tested (a test regenerating a
# fixture, a build step editing a tracked file): the pass would then describe a
# tree that differs from the commit deploy.sh ships.
[ -z "$(git -C "$SRC" status --porcelain --untracked-files=no)" ] \
  || die "the jobs modified tracked files in the gate clone — the result does not describe ${HEAD_SHA:0:7}"

if [ "$USE_RECORD" = "0" ]; then
  {
    echo "passed $(date -u +%Y-%m-%dT%H:%M:%SZ) at ${HEAD_SHA:0:7}"
    grep -E "^($(echo "$TREE_JOBS" | tr ' ' '|')) " "$STATUS"
  } > "$RECORD.tmp.$$" && mv "$RECORD.tmp.$$" "$RECORD"
fi
say "local CI gate PASSED for ${HEAD_SHA:0:7}"
echo "GATED $HEAD_SHA"
