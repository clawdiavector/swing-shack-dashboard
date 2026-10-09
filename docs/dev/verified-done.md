# Verified done — `./check`, the hooks, the CI guard

An agent saying "done" is worth nothing on its own. The rule here:

> Agree on a check before the work starts. The agent is not done until `./check`
> passes, and it may not edit a check once it is committed.

Adapted from the "Verified Done" kit (written for .NET + bash + `jq`) to this repo:
Python and pytest, no `jq`, and it has to run on the Windows desk as well as Linux
and the Mac. Everything is stdlib Python.

## The pieces

| Piece | File | Strength |
|---|---|---|
| One command for "green" | [`check`](../../check) | – |
| The rules, in words | `AGENTS.md` §12a, `CLAUDE.md` | Soft |
| Lock on committed checks | `scripts/agent-hooks/protect_checks.py` | Hard for file edits, heuristic for shell |
| "Not done while red" | `scripts/agent-hooks/require_check.py` | Claude Code yes; Cursor see below |
| PR guard | `scripts/agent-hooks/guard_test_changes.py`, `ci.yml` → `guard_test_changes` | Hard, whatever tool was used |

Hook wiring: `.claude/settings.json` (Claude Code) and `.cursor/hooks.json` (Cursor).

## `./check`

`./check`, or `python3 check` from PowerShell. It runs `scripts/check_lib_modules.py`,
then pytest over `tests/ci-allowlist.txt`, then confirms the run left `data/` as it
found it. CI's `pytest` job runs the same command. Last line: `CHECK: PASS` or
`CHECK: FAIL`.

### Known failures

When this landed, 389 allowlisted tests were already failing on `main` and CI had not
been green since 2026-09-17, so "make the check pass" was not achievable by anyone.
`tests/check-known-failures.txt` lists those tests; `known_failures_plugin.py` marks
them `xfail`, so the run goes red only for a failure that is **not** on the list.
Green therefore means "nothing new broke", not "everything works".

- The list may only shrink. Fix a test, delete its line. `./check` prints listed tests
  that pass again, and listed tests that no longer exist.
- Adding a line needs the `test-change-approved` label on the PR (the guard enforces it).
- `[win32] path::test` limits a line to one platform, for a test that is only broken there.

### Speed

About 90 seconds of pytest in CI. On the Windows desk the same list takes far longer
than the stop hook's 15-minute limit (measured 2026-10-09: a few tests per minute where
a test builds its own app), so set `CHECK_ON_STOP=0` there and let CI decide.

## What is locked

`protect_checks.py` refuses an agent's edit when the file is tracked and is

1. a test committed **on the current branch** — the repro or acceptance test written first, or
2. a committed snapshot (`*.verified.*`, `__snapshots__/`, `*-snapshots/`), or
3. matched by a glob in `.checks-locked` (ships with `check` and the hooks themselves;
   add `campaign-os/tests/*` to lock every test during a refactor).

New, uncommitted tests stay editable, which is what makes "write the test, commit it,
then implement" work. `tests/ci-allowlist.txt` and `tests/check-known-failures.txt` are
deliberately not locked; CI ratchets both.

The lock covers the edit tools and shell commands (`Bash`, `PowerShell`, Cursor's
`Shell`) that redirect into a locked file or name one alongside `sed -i`, `tee`, `mv`,
`cp`, `rm`, `git checkout`, `Set-Content` and similar. Reading is never blocked. The
shell side is pattern matching: it can be fooled, and it will occasionally refuse
something harmless such as copying a locked file elsewhere.

## Not done while red

When the agent tries to finish, `require_check.py` runs `./check` **only if this session
changed something** since the check last passed. It compares against a fingerprint of
the working tree taken before the session's first write-capable tool, so a tree that
was already dirty (the image ingest leaves ~57 modified files) and a pure Q&A chat both
skip the suite. On failure the last 40 lines go back to the agent and it keeps working,
up to 5 times, then it is allowed to stop and the person is told the work is not verified.

## Knobs (environment variables)

| Variable | Default | Effect |
|---|---|---|
| `CHECK_ON_STOP` | `1` | `0` never runs `./check` at stop on this machine |
| `CHECK_LOCK_MODE` | `deny` | `ask` turns a refused edit into a permission prompt a person can approve |
| `CHECK_MAX_RETRIES` | `5` | Push-backs per turn (Claude Code; Cursor uses `loop_limit`) |
| `CHECK_TIMEOUT` | `840` | Seconds before the stop hook gives up waiting |
| `CHECK_BASE_BRANCH` | `origin/main` | What "committed on this branch" is measured against |
| `CHECK_TEST_RE` | see `_common.py` | What counts as a test file |

Per-machine values go in `.claude/settings.local.json` under `"env"`.

## When a locked check really is wrong

The agent stops and says why. Then either a person edits the test in its own commit,
or — with `CHECK_LOCK_MODE=ask` — approves the agent's edit at the prompt. If code
changed in the same PR, the guard then asks for the `test-change-approved` label.

## What has and has not been tested

Tested here (`scripts/tests/test_agent_hooks.py`, 45 cases, on the CI allowlist): both
hooks driven with Claude Code- and Cursor-shaped JSON, the guard, and the plugin.

Not tested here:

- **Cursor.** The JSON shapes are carried over from the upstream kit, which tested
  Cursor IDE 3.23. Upstream also found the `stop` hook does **not** fire in
  `cursor-agent -p`, which is what the Mac bridge runs: on the Mac the lock applies,
  the auto-loop does not.
- **MCP tools that write files.** Only `Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell`
  are matched.
- **`web/` (vitest, Playwright)** is not part of `./check`; neither is `tests/smoke_boot.sh`,
  which needs Docker and stays its own CI job.

CI is the backstop for all of it.
