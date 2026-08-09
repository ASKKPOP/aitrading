#!/usr/bin/env bash
# Deploy sooppiy.com.
#
# Why this exists: the procedure used to live only in an agent's memory, and two
# sessions deploying the same box within two hours on 2026-08-06 raced each other
# — one built from merged main and happened to carry the other's work, but that
# was luck, not coordination. This script makes the two protections mechanical:
#
#   1. An exclusive flock held on the box for the WHOLE deploy. A second deploy
#      waits or fails instead of interleaving with the first.
#   2. A drift guard: SOOPPIY_IMAGE is captured at the start and re-checked
#      immediately before the .env swap. If anything moved, the swap aborts.
#
# It also refuses to deploy anything that is not exactly origin/main, which is
# the other way prod has been broken here (a stale-base build reintroducing
# reverted work).
#
# Usage:
#   scripts/deploy.sh <tag-suffix>            # e.g. scripts/deploy.sh welcome
#   scripts/deploy.sh <tag-suffix> --dry-run  # every check + build, no mutation
#
# Env overrides: SOOPPIY_SSH_KEY, SOOPPIY_SSH_HOST, SOOPPIY_REMOTE_DIR

set -euo pipefail

SSH_KEY="${SOOPPIY_SSH_KEY:-$HOME/shell/sierrabiolab/sierrabiolab-aws.pem}"
SSH_HOST="${SOOPPIY_SSH_HOST:-ec2-user@52.9.147.202}"
REMOTE="${SOOPPIY_REMOTE_DIR:-/home/ec2-user/sooppiy}"
SSH="ssh -o ConnectTimeout=20 -i $SSH_KEY $SSH_HOST"

SUFFIX="${1:-}"
DRY_RUN=0
[ "${2:-}" = "--dry-run" ] && DRY_RUN=1

die() { echo "FATAL: $*" >&2; exit 1; }
say() { echo "▶ $*"; }

[ -n "$SUFFIX" ] || die "usage: scripts/deploy.sh <tag-suffix> [--dry-run]"
[[ "$SUFFIX" =~ ^[a-z0-9-]+$ ]] || die "tag suffix must be [a-z0-9-]+"

cd "$(git rev-parse --show-toplevel)"

# ── 1. refuse anything that is not exactly origin/main ───────────────────────
say "checking the tree is exactly origin/main"
git fetch origin --quiet
[ -z "$(git status --porcelain)" ] || die "working tree is dirty — commit or stash first"
HEAD_SHA=$(git rev-parse HEAD)
MAIN_SHA=$(git rev-parse origin/main)
[ "$HEAD_SHA" = "$MAIN_SHA" ] || die "HEAD ${HEAD_SHA:0:7} != origin/main ${MAIN_SHA:0:7} — deploy merged main only"
say "at origin/main ${MAIN_SHA:0:7}"

TAG="$(date -u +%Y%m%d)-$SUFFIX"
IMAGE="sooppiy-backend:$TAG"
say "target image $IMAGE"

# ── 2. take the lock, capture the drift guard ───────────────────────────────
say "acquiring the deploy lock"
GUARD=$($SSH "
  exec 9>$REMOTE/.deploy.lock
  flock -n 9 || { echo 'LOCKED'; exit 7; }
  grep -E '^SOOPPIY_IMAGE=' $REMOTE/.env | cut -d= -f2
") || die "another deploy holds the lock on $SSH_HOST — wait for it, do not force"
[ "$GUARD" != "LOCKED" ] || die "another deploy holds the lock"
say "guard captured: SOOPPIY_IMAGE=$GUARD"

# The lock above is released when that ssh exits, so every mutating step below
# re-takes it and re-checks the guard. A racing deploy therefore loses at its
# own guard check rather than silently interleaving.
remote_locked() {
  $SSH "
    exec 9>$REMOTE/.deploy.lock
    flock -w 300 9 || { echo 'LOCK TIMEOUT' >&2; exit 7; }
    CUR=\$(grep -E '^SOOPPIY_IMAGE=' $REMOTE/.env | cut -d= -f2)
    if [ \"\$CUR\" != '$GUARD' ]; then
      echo \"ABORT: SOOPPIY_IMAGE drifted \$CUR != $GUARD (another deploy landed)\" >&2
      exit 8
    fi
    set -e
    $1
  "
}

if [ "$DRY_RUN" = "1" ]; then
  say "DRY RUN — stopping before any mutation. Guard and lock both verified."
  exit 0
fi

# ── 3. upload the exact merged-main tree ────────────────────────────────────
# One scratch dir for every local temp file, removed on ANY exit path.
#
# This used to be `TARBALL=$(mktemp -t sooppiy-app.XXXXXX).tgz`, which leaks:
# mktemp CREATES the file it names, then `.tgz` is appended to the variable,
# so the archive is written to a DIFFERENT path and the trap removed only that
# one. The 0-byte mktemp file stayed behind on every deploy — 93 of them had
# accumulated locally by 2026-08-09. The marketing tarball had the same shape
# plus no trap at all, so a failure between its mktemp and its `rm -f` leaked
# the whole archive.
WORKDIR=$(mktemp -d "${TMPDIR:-/tmp}/sooppiy-deploy.XXXXXX")
trap 'rm -rf "$WORKDIR"' EXIT
TARBALL="$WORKDIR/app.tgz"
say "packing $MAIN_SHA"
git archive --format=tar.gz -o "$TARBALL" HEAD

# The bulk upload is the one step that fails on a flaky path: 2026-08-06 saw
# three of four deploys die here with `message authentication code incorrect`
# or `connection reset by peer` — corrupted packets during the ~7MB transfer,
# not a fault on the box. Everything before this point is read-only and
# everything after is guarded, so a bounded retry here is safe and turns a
# hand-retried deploy back into a mechanical one.
UPLOAD_TRIES=${SOOPPIY_UPLOAD_TRIES:-4}
for attempt in $(seq 1 "$UPLOAD_TRIES"); do
  if scp -q -o ConnectTimeout=30 -o ServerAliveInterval=15 \
         -o ServerAliveCountMax=4 -i "$SSH_KEY" \
         "$TARBALL" "$SSH_HOST:/tmp/sooppiy-deploy.tgz"; then
    break
  fi
  [ "$attempt" -eq "$UPLOAD_TRIES" ] && die "upload failed after $UPLOAD_TRIES attempts"
  say "upload attempt $attempt failed; retrying in $((attempt * 5))s"
  sleep $((attempt * 5))
done

# A truncated tarball would extract a partial tree and build a broken image.
LOCAL_SUM=$(shasum -a 256 "$TARBALL" | awk '{print $1}')
REMOTE_SUM=$($SSH "sha256sum /tmp/sooppiy-deploy.tgz | awk '{print \$1}'")
[ "$LOCAL_SUM" = "$REMOTE_SUM" ] || die "tarball checksum mismatch after upload"
say "upload verified $LOCAL_SUM"

TS=$(date -u +%Y%m%d-%H%M%S)
say "swapping app/ (backup app.prev-$TS)"
remote_locked "
  mv $REMOTE/app $REMOTE/app.prev-$TS
  mkdir -p $REMOTE/app
  tar xzf /tmp/sooppiy-deploy.tgz -C $REMOTE/app
"

# ── 4. build + migrate (both safe while the old image still serves) ─────────
say "building $IMAGE"
$SSH "cd $REMOTE && docker build -q -t $IMAGE app" >/dev/null

say "running migrations"
$SSH "docker run --rm --env-file $REMOTE/.env -w /app/service/server $IMAGE python -m alembic upgrade head"
$SSH "docker run --rm --env-file $REMOTE/.env -w /app/service/server $IMAGE python -m alembic current"

# ── 5. the swap — guard re-checked inside the lock ──────────────────────────
say "swapping SOOPPIY_IMAGE (guard re-checked)"
remote_locked "
  cp $REMOTE/.env $REMOTE/.env.bak-$TS
  sed -i 's|^SOOPPIY_IMAGE=.*|SOOPPIY_IMAGE=$IMAGE|' $REMOTE/.env
  cd $REMOTE && docker compose --profile prod up -d --no-build
  printf '%s\t%s\t%s\t%s\n' '$TS' '$TAG' '$MAIN_SHA' \"\$(whoami)\" >> $REMOTE/deploy-log.tsv
"

# ── 6. all THREE static roots — skipping one silently serves an old build ───
#
# `cp -r src/*` and `rm -rf dir/*` both use a glob, and a glob does NOT match
# dotfiles. That silently dropped every hidden path — most importantly
# `.well-known/`, which is where domain-verification files for Apple, and any
# future ACME or security.txt, have to live. The bug was invisible because the
# visible site kept working; only the hidden path went missing, on every single
# deploy. `find -mindepth 1 -delete` clears dotfiles too, and `cp -a src/.`
# copies them. Canary: service/frontend/public/.well-known/README.txt must
# answer 200 at https://sooppiy.com/.well-known/README.txt after a deploy.
say "publishing the SPA to all three static roots"
$SSH "
  set -e
  rm -rf /tmp/newdist && docker cp sooppiy-backend:/app/service/frontend/dist /tmp/newdist
  sudo cp -a /usr/share/nginx/sooppiy /usr/share/nginx/sooppiy.prev-$TS
  sudo find /usr/share/nginx/sooppiy -mindepth 1 -delete && sudo cp -a /tmp/newdist/. /usr/share/nginx/sooppiy/
  sudo restorecon -R /usr/share/nginx/sooppiy
  sudo cp -a $REMOTE/admin-site $REMOTE/admin-site.prev-$TS
  sudo find $REMOTE/admin-site -mindepth 1 -delete && sudo cp -a /tmp/newdist/. $REMOTE/admin-site/
  sudo chown -R root:root $REMOTE/admin-site
  docker restart sooppiy-admin >/dev/null
  rm -rf /tmp/newdist
"

say "building and publishing the marketing pages"
( cd marketing && npm run build --silent >/dev/null )
MKT="$WORKDIR/mkt.tgz"
tar czf "$MKT" -C marketing/dist .
scp -q -i "$SSH_KEY" "$MKT" "$SSH_HOST:/tmp/sooppiy-mkt.tgz"
$SSH "
  set -e
  rm -rf /tmp/newmkt && mkdir -p /tmp/newmkt && tar xzf /tmp/sooppiy-mkt.tgz -C /tmp/newmkt 2>/dev/null
  sudo cp -a /usr/share/nginx/sooppiy-marketing /usr/share/nginx/sooppiy-marketing.prev-$TS
  for d in privacypolicy termsconditions pricing smsoptin _astro; do
    [ -e /tmp/newmkt/\$d ] && sudo rm -rf /usr/share/nginx/sooppiy-marketing/\$d && sudo cp -r /tmp/newmkt/\$d /usr/share/nginx/sooppiy-marketing/
  done
  sudo restorecon -R /usr/share/nginx/sooppiy-marketing
  rm -rf /tmp/newmkt /tmp/sooppiy-mkt.tgz /tmp/sooppiy-deploy.tgz
"

# ── 7. prune superseded backups ────────────────────────────────────────────
# Every deploy leaves a .prev-*/.env.bak-* per surface. Left alone they pile up
# and the real rollback path hides among a dozen lookalikes — which is how a
# previous session ended up with ten near-identical copies. Keep the two newest:
# one to undo this deploy, one to undo the deploy before it.
#
# .env.bak-* matters most. Each is a full copy of the live secret set, so an
# unbounded pile is extra copies of every API key sitting on disk.
#
# Sort by mtime, never by name — tags are not lexically ordered (.env.bak-welcome
# has no date in it at all).
say "pruning superseded backups (keeping the 2 newest per surface)"
$SSH "
  prune() { sudo ls -dt \$1 2>/dev/null | tail -n +\$((${KEEP_BACKUPS:-2} + 1)) | xargs -r sudo rm -rf; }
  prune '$REMOTE/app.prev-*'
  prune '$REMOTE/admin-site.prev-*'
  prune '$REMOTE/.env.bak-*'
  prune '/usr/share/nginx/sooppiy.prev-*'
  prune '/usr/share/nginx/sooppiy-marketing.prev-*'
"

# Stale upload tarballs in the box's /tmp. This deploy removes its own two
# (step 6), but hand deploys from before this script existed did not: five
# were still sitting there on 2026-08-09 — 15.5 MB dated Jul 31 – Aug 3, on a
# disk at 78%. Age-based, so it can never race an upload in flight, and
# tarballs-only, so it can never touch /tmp/sooppiy-deploy.lock — the flock
# target that serialises deploys.
say "pruning /tmp upload tarballs older than ${TMP_TARBALL_DAYS:-7} days"
$SSH "sudo find /tmp -maxdepth 1 -type f \\( -name '*.tar.gz' -o -name '*.tgz' \\) \
        -mtime +${TMP_TARBALL_DAYS:-7} -print -delete 2>/dev/null | sed 's/^/  removed /' || true"

# ── 8. verify, and say plainly if someone raced us ─────────────────────────
say "verifying"
sleep 8
RUNNING=$($SSH "docker inspect sooppiy-backend --format '{{.Config.Image}}'")
[ "$RUNNING" = "$IMAGE" ] || echo "WARNING: sooppiy-backend runs $RUNNING, not $IMAGE — another deploy landed after ours"
$SSH "docker ps --filter name=sooppiy --format '{{.Names}} {{.Image}} {{.Status}}'"
for u in / /pricing /privacypolicy /termsconditions /api/subscriptions/plans; do
  printf '  %-32s %s\n' "$u" "$(curl -s -o /dev/null -w '%{http_code}' -m 20 "https://sooppiy.com$u")"
done

say "deployed $IMAGE from ${MAIN_SHA:0:7}. Rollback: set SOOPPIY_IMAGE=$GUARD in $REMOTE/.env and re-run compose up."
