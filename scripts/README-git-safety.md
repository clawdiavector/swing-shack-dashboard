# Git Safety Layer — Campaign OS

This directory contains the **race-condition protection layer** for git operations
on the swing-shack-dashboard repo.

## Files

### `git-safe-push.sh`
The only authorized way to push to `main` from a cron/automation context.

**What it does:**
1. `git fetch origin main` — get latest remote state
2. Detect divergence: local ahead / local behind / diverged
3. If local behind: `git merge --ff-only origin/main` (fast-forward)
4. If diverged: **refuse with exit 3** (cron caller must alert)
5. If aligned: `git push origin main --force-with-lease` (lease catches races)
6. Set `GIT_SAFE_PUSH_ACTIVE=1` so the local `pre-push` hook allows our push

**Exit codes:**
- `0` = success
- `2` = remote moved during push (--force-with-lease refused)
- `3` = diverged — manual merge required
- `4` = fetch failed (network/auth)

### `.git/hooks/pre-push`
Local git hook that refuses direct `git push origin main` from automated contexts.

**Blocks:**
- Any push to main from process tree containing `cron`/`launchd`/`node`/`openclaw`
- Any force-push to main without `ALLOW_DIRECT_MAIN_PUSH=1`
- Allows when `GIT_SAFE_PUSH_ACTIVE=1` (set by `git-safe-push.sh`)

## Usage

**Crons / automation:**
```bash
bash scripts/git-safe-push.sh /path/to/repo main
```

**Humans, normal push from terminal:**
```bash
git push origin main
# (allowed — interactive shell context)
```

**Humans, emergency force-push (NOT RECOMMENDED):**
```bash
ALLOW_DIRECT_MAIN_PUSH=1 git push origin main --force-with-lease
```

## Why this exists

On 2026-07-30, Railway stopped deploying new work because the `main` branch on
GitHub was being silently force-pushed by a research cron to a state without
the visualizer/meme-lab commits. The cron had no fetch/rebase step, so whenever
a human pushed between the cron's fetch (which didn't exist) and push, the cron
would silently drop the human's commits.

This layer makes that failure mode **impossible**: crons MUST go through the
safe wrapper, and the wrapper refuses to do anything destructive.

## See also

- `~/hermes-fleet/shared/handoff/git-safety-2026-07-30.md` — full incident timeline + postmortem
