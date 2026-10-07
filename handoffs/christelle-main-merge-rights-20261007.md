# Handoff — let Christelle approve her own merges to `main`

**Date:** 2026-10-07 · **Owner:** Kyle · **Repo:** `clawdiavector/swing-shack-dashboard`

## Goal

Christelle should be able to merge into `main` on her own say-so, without Kyle
approving each time. Her Claude should still ask *her* to confirm in the same
message before it pushes or merges `main`. That stops agents shipping to prod
unasked without making Kyle a gate.

## What's verified (2026-10-07)

- **GitHub is not the blocker.** `main` has no branch protection (`protected: false`,
  no required reviews or checks). Christelle (`christelleweilbach-cloud`) pushed
  `fix/organic-brand-isolation` straight to the repo for PR #43, so she has write
  access. There is no CODEOWNERS file.
- **The repo's instructions are the blocker.** Her Claude reads these and refuses to
  merge without Kyle:

| File | Line | Current text |
|---|---|---|
| `CLAUDE.md` | 92 | Never push `main` without Kyle approving it in the current message. |
| `AGENTS.md` | 18–19 | …until Kyle merges at program end / without Kyle naming that branch |
| `docs/ONBOARDING-MARKETING.md` | 220–222 | Kyle merges it… don't talk it out of that. |
| `docs/dev/conventions.md` | 7 | `main` — Kyle merges |
| `plugins/campaign-os/skills/campaign-os/SKILL.md` | 52 | Kyle approves `main` push |
| `plugins/campaign-os/skills/campaign-os/modules/dev.md` | 28 | without Kyle approval |
| `plugins/campaign-os/skills/campaign-os/modules/jobs.md` | 91 | without Kyle approval |
| `plugins/campaign-os/skills/campaign-os/modules/mac-build-deploy.md` | 45 | without Kyle naming that branch |
| `plugins/campaign-os/skills/campaign-os-template/SKILL.md` | 26 | `main` = Kyle names it |

- PR #43 has one failing CI check (`pytest`). The other four pass. This doesn't block
  merging but should be looked at before it goes to prod.

## Why the previous agent was blocked

The session was running Claude Code in **auto mode**. In that mode a safety
classifier reviews each tool call before it runs. It refused the edit with reason
**"Instruction Poisoning"**: an agent rewriting its own instruction files
(`CLAUDE.md`, `AGENTS.md`, skills) to loosen a "don't push to production" rule
looks the same as a prompt-injection attack. That holds even when the user asked
for it in chat.

The block applies to the outcome, not one command. A different tool, a script, a
subagent or a later turn is refused the same way. Nothing in the repo causes this,
so there is nothing in the repo to "fix". **Do not try to disable the classifier,
edit permission settings yourself, or route around it.** The fix is to put Kyle's
hand on the change.

## How to unblock (pick one)

**A — Kyle runs it (fastest).** Kyle pastes the script below into his own terminal.

**B — Run the agent in default (ask) permission mode, not auto mode.** The
classifier only runs in auto mode. In default mode each edit shows up as an
approval prompt and Kyle clicks Allow. Nothing persists afterwards. *Recommended if an
agent should do it.*

**C — Kyle adds an allow rule.** Kyle (not the agent) adds `Edit` allow rules for
the files above, in `.claude/settings.local.json` under `permissions.allow` or via
`/permissions` in an interactive `claude` terminal. Remove the rules afterwards. This is
more permanent than B for a one-off change.

## The change

Every "Kyle" gate becomes "Kyle or Christelle". `CLAUDE.md` and the onboarding doc
also say plainly that she has full merge rights. The script checks that every target
string matches exactly once before writing anything:

```bash
cd ~/finder-workspace/repos/work/swing-shack-dashboard-main && python3 - <<'EOF'
import pathlib
edits = {
 "CLAUDE.md": [("**Never push `main` without Kyle approving it in the current message.**",
   "**Never push `main` without Kyle or Christelle approving it in the current message.**\nEither of them can approve their own merge — the rule stops agents shipping to prod\nunasked, not people.")],
 "AGENTS.md": [
   ("never `main`, until Kyle merges at program end.", "never `main`, until Kyle or Christelle merges at program end."),
   ("without Kyle naming that branch in-session.", "without Kyle or Christelle naming that branch in-session.")],
 "docs/ONBOARDING-MARKETING.md": [("""**3. Never push `main`.** It auto-deploys to Railway the moment it lands. Program
work goes on a branch and Kyle merges it. Claude is instructed not to push `main`
without Kyle approving it in the same message — don't talk it out of that.""",
"""**3. `main` is prod.** It auto-deploys to Railway the moment it lands. Work goes
on a branch and you merge it yourself — you have full merge rights, no sign-off
from Kyle needed. Claude will ask you to confirm in the same message before it
pushes or merges into `main`; that's a guard against agents shipping unasked,
not a permission gate.""")],
 "docs/dev/conventions.md": [("`main` — Kyle merges;", "`main` — Kyle or Christelle merges;")],
 "plugins/campaign-os/skills/campaign-os/modules/dev.md": [("without Kyle approval.", "without Kyle or Christelle approving it.")],
 "plugins/campaign-os/skills/campaign-os/SKILL.md": [("Kyle approves `main` push", "Kyle or Christelle approves `main` push")],
 "plugins/campaign-os/skills/campaign-os/modules/jobs.md": [("without Kyle approval", "without Kyle or Christelle approval")],
 "plugins/campaign-os/skills/campaign-os/modules/mac-build-deploy.md": [("without Kyle naming that branch", "without Kyle or Christelle naming that branch")],
 "plugins/campaign-os/skills/campaign-os-template/SKILL.md": [("`main` = Kyle names it.", "`main` = Kyle or Christelle names it.")],
}
out = {}
for f, subs in edits.items():
    s = pathlib.Path(f).read_text()
    for a, b in subs:
        if s.count(a) != 1: raise SystemExit(f"STOP: text not found once in {f}: {a[:50]}")
        s = s.replace(a, b)
    out[f] = s
for f, s in out.items(): pathlib.Path(f).write_text(s)
print("Updated", len(out), "files")
EOF
```

If the script stops on a mismatch, edit that line by hand to the same meaning. Don't
loosen the "found exactly once" check.

## Commit and ship

The working tree has unrelated local changes (`data/integrations/stick/instagram.json`,
weekly snapshots, untracked plans). Commit **only** the files above:

```bash
git add CLAUDE.md AGENTS.md docs/ONBOARDING-MARKETING.md docs/dev/conventions.md plugins/campaign-os/skills
git commit -m "docs: Christelle can approve her own merges to main"
```

Pushing `main` deploys to Railway. **Kyle approves that push himself**, under the
current rule.

## Done when

- `grep -rn "Kyle" CLAUDE.md AGENTS.md docs/dev/conventions.md plugins/campaign-os/skills | grep -iE "approv|merges|names it|naming"`
  shows no Kyle-only gate on `main`.
- The commit is on `origin/main`.
- Christelle has pulled `main` and updated the plugin
  (`/plugin marketplace update campaign-os`, reinstall if her Claude still quotes
  the old rule). If her Claude saved a memory saying "Kyle approves main", she
  deletes it.

## Out of scope

- `AGENTS.md` cites `context/protected-branch-push.md` in the **agent-control** repo
  (Kyle's machine, not hers). Leave it unless Kyle asks.
- The Hermes fleet and scheduled jobs on the Mac stay Kyle-only because of where they
  run, not because of permissions.
- Suggested follow-ups for Kyle: invite Christelle to the Railway project (logs and
  rollback), give her `COS_JOB_TOKEN`, and add a rollback section to her onboarding
  guide (`git revert` the merge, or roll back in Railway).
