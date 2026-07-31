#!/bin/bash
# git-safe-push.sh — RACE-FREE Git push helper for cron jobs.
#
# Why this exists:
#   Crons run on a fixed schedule and assume their local branch is current.
#   If a human (or another cron) pushed between the cron's `git fetch` and `git push`,
#   the cron would either (a) fail with non-fast-forward, or (b) silently force-push
#   and wipe out the new commits. This script enforces:
#     1. `git fetch` BEFORE doing anything
#     2. Auto-rebase local main onto origin/main (only fast-forwardable changes)
#     3. Push with --force-with-lease (refuses if remote moved unexpectedly)
#     4. Fail loudly if anything diverges — cron caller decides whether to alert
#
# Usage:
#   git-safe-push.sh <repo_dir> <branch> [push_args...]
#
# Exit codes:
#   0 = success
#   2 = remote moved unexpectedly (lease failed — manual review needed)
#   3 = non-fast-forwardable divergence (manual merge needed)
#   4 = fetch failed (network/auth issue)
#
# Crons should pipe stderr to log and NOT silently swallow the failure.

set -euo pipefail

REPO_DIR="${1:-}"
BRANCH="${2:-main}"
shift 2 || true
PUSH_ARGS=("$@")

if [[ -z "$REPO_DIR" ]]; then
  echo "Usage: git-safe-push.sh <repo_dir> <branch> [push_args...]" >&2
  exit 1
fi

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repo dir not found: $REPO_DIR" >&2
  exit 1
fi

# Signal to pre-push hook that we're a sanctioned push (so it doesn't refuse our
# own push). Only set this when running git push internally below.
export GIT_SAFE_PUSH_ACTIVE=1

cd "$REPO_DIR"

# Make sure we're on the right branch (don't switch if already there, but bail if not)
current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$current_branch" != "$BRANCH" ]]; then
  echo "Not on branch '$BRANCH' (currently on '$current_branch') in $REPO_DIR" >&2
  exit 1
fi

echo "[git-safe-push] $(date -u +%FT%TZ) — repo=$REPO_DIR branch=$BRANCH"

# 1. Fetch latest from origin (without touching working tree)
if ! git fetch origin "$BRANCH" 2>&1; then
  echo "[git-safe-push] FETCH FAILED — network or auth issue" >&2
  exit 4
fi

# 2. Detect divergence BEFORE committing anything
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse "origin/$BRANCH")"
merge_base="$(git merge-base HEAD "origin/$BRANCH" 2>/dev/null || echo '')"

if [[ "$local_sha" == "$remote_sha" ]]; then
  echo "[git-safe-push] Already up to date with origin/$BRANCH"
elif [[ "$merge_base" == "$local_sha" ]]; then
  # Local is BEHIND remote — fast-forward
  echo "[git-safe-push] Local is behind origin/$BRANCH by $(git rev-list --count HEAD..origin/$BRANCH) commits — fast-forwarding"
  git merge --ff-only "origin/$BRANCH" || { echo "[git-safe-push] FF-ONLY FAILED" >&2; exit 3; }
elif [[ "$merge_base" == "$remote_sha" ]]; then
  # Local is AHEAD of remote — exactly what we want for a normal cron push
  echo "[git-safe-push] Local is ahead of origin/$BRANCH by $(git rev-list --count origin/$BRANCH..HEAD) commits — proceeding"
else
  # Truly diverged — neither side is a fast-forward of the other
  ahead=$(git rev-list --count "origin/$BRANCH"..HEAD)
  behind=$(git rev-list --count "HEAD..origin/$BRANCH")
  echo "[git-safe-push] DIVERGED — local is $ahead ahead and $behind behind origin/$BRANCH" >&2
  echo "[git-safe-push] Local:  $local_sha" >&2
  echo "[git-safe-push] Remote: $remote_sha" >&2
  if [[ "${GIT_SAFE_PUSH_FORCE:-0}" == "1" ]]; then
    echo "[git-safe-push] GIT_SAFE_PUSH_FORCE=1 — proceeding with force push despite divergence"
  else
    echo "[git-safe-push] Refusing to force-push. If you KNOW remote is wrong, retry with:" >&2
    echo "    GIT_SAFE_PUSH_FORCE=1 bash scripts/git-safe-push.sh . main" >&2
    exit 3
  fi
fi

# 3. Push with --force-with-lease — refuses if remote moved between fetch and push
# This catches the case where ANOTHER process pushes between our fetch and our push.
# If divergence was detected above, refuse UNLESS caller explicitly opted in via
# GIT_SAFE_PUSH_FORCE=1 (used when you KNOW remote is wrong and want to overwrite).
if [[ "${GIT_SAFE_PUSH_FORCE:-0}" == "1" ]]; then
  echo "[git-safe-push] GIT_SAFE_PUSH_FORCE=1 — proceeding with force push"
  push_cmd=(git push origin "$BRANCH" --force-with-lease="${BRANCH}:origin/${BRANCH}")
else
  push_cmd=(git push origin "$BRANCH" --force-with-lease="${BRANCH}:origin/${BRANCH}")
fi
if [[ ${#PUSH_ARGS[@]} -gt 0 ]]; then
  push_cmd+=("${PUSH_ARGS[@]}")
fi

if ! "${push_cmd[@]}" 2>&1; then
  echo "[git-safe-push] PUSH FAILED — remote moved or lease rejected" >&2
  exit 2
fi

echo "[git-safe-push] PUSH OK — origin/$BRANCH is now at $(git rev-parse --short HEAD)"
