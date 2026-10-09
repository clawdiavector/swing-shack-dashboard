"""The agent hooks, the CI guard and the known-failures plugin behind ./check.

Each test builds a throwaway git repo and drives the real scripts over stdin,
the way Claude Code and Cursor call them.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "agent-hooks"

# Passes once app.py says FIXED; counts its runs outside the repo so counting
# does not itself look like a change.
CHECK_STUB = """\
import os, sys
with open(os.environ["CHECK_MARKER"], "a") as fh:
    fh.write("run\\n")
ok = "FIXED" in open("app.py").read()
print("some test output")
print("CHECK: PASS" if ok else "CHECK: FAIL")
sys.exit(0 if ok else 1)
"""


def git(repo: Path, *args: str) -> str:
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "core.autocrlf=false", *args]
    return subprocess.run(cmd, cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """main: app.py, an old test, a snapshot, ./check.  feat: plus tests/test_new.py."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "snap").mkdir()
    (root / "other").mkdir()
    (root / "app.py").write_text("x = 1\n")
    (root / "tests" / "test_old.py").write_text("def test_old():\n    assert True\n")
    (root / "tests" / "ci-allowlist.txt").write_text("tests/test_old.py\n")
    (root / "tests" / "check-known-failures.txt").write_text("# header\ntests/test_old.py::test_broken\n")
    (root / "snap" / "orders.verified.json").write_text("{}\n")
    (root / "other" / "test_new.py").write_text("# same name, different folder\n")
    (root / "check").write_text(CHECK_STUB)
    (root / ".checks-locked").write_text("# comment\ncheck\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "feat")
    (root / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "repro test")
    monkeypatch.setenv("CHECK_BASE_BRANCH", "main")
    monkeypatch.setenv("CHECK_MARKER", str(tmp_path / "check-runs.txt"))
    for var in ("CHECK_LOCK_MODE", "CHECK_ON_STOP", "CHECK_CMD", "CHECK_MAX_RETRIES", "CHECK_TEST_RE"):
        monkeypatch.delenv(var, raising=False)
    return root


def hook(script: str, tool: str, repo: Path, payload: dict, **env: str) -> dict:
    """Run a hook; return its JSON output ({} when it printed nothing)."""
    proc = subprocess.run(
        [sys.executable, str(HOOKS / script), tool],
        input=json.dumps({"session_id": "s1", **payload}).encode(),
        cwd=repo, capture_output=True, env={**os.environ, **env},
    )
    assert proc.returncode == 0, proc.stderr.decode()
    out = proc.stdout.decode().strip()
    return json.loads(out) if out else {}


def protect(repo: Path, tool_name: str, tool: str = "claude", **kw) -> str:
    """The lock's verdict for one tool call: allow, deny or ask."""
    env = kw.pop("env", {})
    extra = kw.pop("extra", {})
    out = hook("protect_checks.py", tool, repo, {"tool_name": tool_name, "tool_input": kw, **extra}, **env)
    if tool == "cursor":
        return out["permission"]
    return out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")


def check_runs(tmp_path: Path) -> int:
    marker = tmp_path / "check-runs.txt"
    return len(marker.read_text().splitlines()) if marker.exists() else 0


# --- protect_checks: file tools --------------------------------------------------------

def test_test_committed_on_branch_is_locked(repo):
    assert protect(repo, "Edit", file_path="tests/test_new.py") == "deny"


def test_absolute_path_is_locked_too(repo):
    assert protect(repo, "Write", file_path=str(repo / "tests" / "test_new.py")) == "deny"


def test_test_from_main_is_not_locked(repo):
    assert protect(repo, "Edit", file_path="tests/test_old.py") == "allow"


def test_new_uncommitted_test_stays_editable(repo):
    (repo / "tests" / "test_draft.py").write_text("def test_draft():\n    pass\n")
    assert protect(repo, "Edit", file_path="tests/test_draft.py") == "allow"


def test_committed_snapshot_is_locked(repo):
    assert protect(repo, "Edit", file_path="snap/orders.verified.json") == "deny"


def test_checks_locked_file_is_honoured(repo):
    assert protect(repo, "Write", file_path="check") == "deny"


def test_code_and_test_lists_are_not_locked(repo):
    assert protect(repo, "Edit", file_path="app.py") == "allow"
    git(repo, "commit", "-q", "--allow-empty", "-m", "noop")
    (repo / "tests" / "ci-allowlist.txt").write_text("tests/test_old.py\ntests/test_new.py\n")
    git(repo, "commit", "-q", "-am", "allowlist")
    assert protect(repo, "Edit", file_path="tests/ci-allowlist.txt") == "allow"


def test_deny_message_tells_the_agent_what_to_do(repo):
    out = hook("protect_checks.py", "claude", repo,
               {"tool_name": "Edit", "tool_input": {"file_path": "tests/test_new.py"}})
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "tests/test_new.py" in reason and "not the check" in reason


# --- protect_checks: shell -------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "sed -i 's/False/True/' tests/test_new.py",
    "echo 'def test_new(): pass' > tests/test_new.py",
    "cat patch.py >> ./tests/test_new.py",
    "rm tests/test_new.py",
    "rm -rf tests",
    "git checkout main -- tests/test_new.py",
    "python3 -c \"open('tests/test_new.py','w').write('')\"",
    "cd tests && mv test_new.py test_gone.py",
    "pytest -q; cp /tmp/x snap/orders.verified.json",
    "echo x > \"tests/test_new.py\"",
    "cat <<'EOF' > tests/test_new.py\ndef test_new():\n    pass\nEOF",
    "find tests -name 'test_new.py' -exec rm {} +",
    "FORCE=1 rm -f check",
    "python3 - <<'PY'\nfrom pathlib import Path\nPath('tests/test_new.py').write_text('')\nPY",
])
def test_shell_writes_to_a_locked_file_are_blocked(repo, command):
    assert protect(repo, "Bash", command=command) == "deny"


@pytest.mark.parametrize("command", [
    "python3 -m pytest tests/test_new.py -q",
    "python3 -m pytest tests/test_new.py > out.txt 2>&1",
    "pytest tests/test_new.py 2>&1 | tee run.log",
    "cat tests/test_new.py",
    "git diff main -- tests/test_new.py > /dev/null",
    "rm other/test_new.py",
    "./check",
    "git checkout -b another-branch",
    "sed -i 's/1/2/' app.py",
    # Prose that merely mentions a locked file is not a write to it.
    "git commit -m \"move check into scripts and copy tests -> check\"",
    "git commit -F - <<'EOF'\nmove tests -> check\n\n> check passes\nrm tests/test_new.py once it is obsolete\nEOF",
    "gh pr create --title x --body \"run ./check > see tests/test_new.py\"",
])
def test_ordinary_shell_use_is_not_blocked(repo, command):
    assert protect(repo, "Bash", command=command) == "allow"


def test_powershell_writes_are_blocked(repo):
    assert protect(repo, "PowerShell", command="Set-Content tests\\test_new.py 'x'") == "deny"
    assert protect(repo, "PowerShell", command="Get-Content tests\\test_new.py") == "allow"


# --- protect_checks: tools and modes ---------------------------------------------------

def test_cursor_gets_cursor_shaped_answers(repo):
    assert protect(repo, "Write", tool="cursor", path="tests/test_new.py") == "deny"
    assert protect(repo, "Write", tool="cursor", path="app.py") == "allow"
    assert protect(repo, "Shell", tool="cursor", command="rm tests/test_new.py") == "deny"


def test_ask_mode_prompts_instead_of_blocking(repo):
    ask = {"CHECK_LOCK_MODE": "ask"}
    assert protect(repo, "Edit", file_path="tests/test_new.py", env=ask) == "ask"
    # ...except where a prompt would never be shown.
    bypass = {"permission_mode": "bypassPermissions"}
    assert protect(repo, "Edit", file_path="tests/test_new.py", env=ask, extra=bypass) == "deny"


# --- require_check ---------------------------------------------------------------------

def stop(repo: Path, tool: str = "claude", active: bool = False, **env: str) -> dict:
    return hook("require_check.py", tool, repo, {"stop_hook_active": active}, **env)


def test_qa_chat_never_runs_the_check(repo, tmp_path):
    (repo / "app.py").write_text("x = 2  # someone else's uncommitted work\n")
    assert stop(repo) == {}
    assert check_runs(tmp_path) == 0


def test_tree_dirty_before_the_session_does_not_trigger_the_check(repo, tmp_path):
    (repo / "app.py").write_text("x = 2  # dirty before the session began\n")
    protect(repo, "Bash", command="git status")
    assert stop(repo) == {}
    assert check_runs(tmp_path) == 0


def test_failing_check_pushes_the_agent_back(repo, tmp_path):
    protect(repo, "Edit", file_path="app.py")
    (repo / "app.py").write_text("x = 3\n")
    out = stop(repo)
    assert out["decision"] == "block"
    assert "CHECK: FAIL" in out["reason"]
    assert check_runs(tmp_path) == 1


def test_cursor_gets_a_followup_message(repo):
    protect(repo, "Edit", tool="cursor", path="app.py")
    (repo / "app.py").write_text("x = 3\n")
    assert "CHECK: FAIL" in stop(repo, tool="cursor")["followup_message"]


def test_passing_check_lets_the_agent_stop_and_is_not_rerun(repo, tmp_path):
    protect(repo, "Edit", file_path="app.py")
    (repo / "app.py").write_text("x = 3  # FIXED\n")
    assert stop(repo) == {}
    assert check_runs(tmp_path) == 1
    assert stop(repo) == {}  # nothing changed since it passed
    assert check_runs(tmp_path) == 1


def test_a_commit_made_in_the_session_counts_as_a_change(repo, tmp_path):
    protect(repo, "Bash", command="git status")
    (repo / "app.py").write_text("x = 3\n")
    git(repo, "commit", "-q", "-am", "work")
    assert stop(repo)["decision"] == "block"


def test_gives_up_after_max_retries_and_says_so(repo, tmp_path):
    protect(repo, "Edit", file_path="app.py")
    (repo / "app.py").write_text("x = 3\n")
    limit = {"CHECK_MAX_RETRIES": "2"}
    assert stop(repo, **limit)["decision"] == "block"
    assert stop(repo, active=True, **limit)["decision"] == "block"
    out = stop(repo, active=True, **limit)
    assert "decision" not in out and "NOT verified" in out["systemMessage"]
    assert check_runs(tmp_path) == 2


def test_check_on_stop_can_be_switched_off(repo, tmp_path):
    protect(repo, "Edit", file_path="app.py")
    (repo / "app.py").write_text("x = 3\n")
    assert stop(repo, CHECK_ON_STOP="0") == {}
    assert check_runs(tmp_path) == 0


# --- guard_test_changes ----------------------------------------------------------------

def guard(repo: Path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / "guard_test_changes.py"), "main"],
        cwd=repo, capture_output=True, text=True, env={**os.environ, **env},
    )


def test_guard_passes_new_tests_with_code(repo):
    (repo / "app.py").write_text("x = 3\n")
    git(repo, "commit", "-q", "-am", "fix")
    assert guard(repo).returncode == 0


def test_guard_fails_code_plus_edited_existing_test(repo):
    (repo / "app.py").write_text("x = 3\n")
    (repo / "tests" / "test_old.py").write_text("def test_old():\n    pass  # weakened\n")
    git(repo, "commit", "-q", "-am", "fix and weaken")
    proc = guard(repo)
    assert proc.returncode == 1 and "tests/test_old.py" in proc.stdout
    assert guard(repo, ALLOW_TEST_CHANGES="1").returncode == 0


def test_guard_allows_test_only_and_allowlist_changes(repo):
    (repo / "tests" / "test_old.py").write_text("def test_old():\n    assert 1 == 1\n")
    (repo / "tests" / "ci-allowlist.txt").write_text("tests/test_old.py\ntests/test_new.py\n")
    git(repo, "commit", "-q", "-am", "tests only")
    assert guard(repo).returncode == 0


def test_guard_lets_known_failures_shrink_but_not_grow(repo):
    known = repo / "tests" / "check-known-failures.txt"
    known.write_text("# header\n")
    git(repo, "commit", "-q", "-am", "fixed one")
    assert guard(repo).returncode == 0
    known.write_text("# header\ntests/test_new.py::test_new\n")
    git(repo, "commit", "-q", "-am", "hide a failure")
    proc = guard(repo)
    assert proc.returncode == 1 and "may only shrink" in proc.stdout


# --- known_failures_plugin -------------------------------------------------------------

def run_pytest(tmp_path: Path, known: str) -> subprocess.CompletedProcess:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "test_demo.py").write_text(
        "def test_ok():\n    assert True\n\n"
        "def test_broken():\n    assert False\n\n"
        "def test_healed():\n    assert True\n\n"
        "import unittest\n\n"
        "class Subs(unittest.TestCase):\n"
        "    def test_subs(self):\n"
        "        for n in (1, 2):\n"
        "            with self.subTest(n=n):\n"
        "                self.assertEqual(n, 1)\n"
    )
    (proj / "known.txt").write_text(known)
    env = {**os.environ, "PYTHONPATH": str(HOOKS)}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "known_failures_plugin", "--known-failures", "known.txt",
         "-p", "no:cacheprovider", "test_demo.py"],
        cwd=proj, capture_output=True, text=True, env=env,
    )


BROKEN = "test_demo.py::test_broken\ntest_demo.py::Subs::test_subs  # fails in a subtest only\n"


def test_listed_failures_do_not_fail_the_run(tmp_path):
    proc = run_pytest(tmp_path, "# header\n" + BROKEN)
    assert proc.returncode == 0, proc.stdout
    # A listed test whose subtests still fail must not be reported as fixed.
    assert "now pass" not in proc.stdout


def test_unlisted_failure_fails_the_run(tmp_path):
    proc = run_pytest(tmp_path, "test_demo.py::Subs::test_subs\n")
    assert proc.returncode == 1 and "test_broken" in proc.stdout


def test_listed_test_that_passes_again_is_reported(tmp_path):
    proc = run_pytest(tmp_path, BROKEN + "test_demo.py::test_healed\ntest_demo.py::test_deleted\n")
    assert proc.returncode == 0
    assert "now pass" in proc.stdout and "test_demo.py::test_healed" in proc.stdout
    assert "Subs::test_subs" not in proc.stdout.split("now pass")[1].split("no longer exist")[0]
    assert "no longer exist" in proc.stdout and "test_demo.py::test_deleted" in proc.stdout


def test_platform_tag_limits_a_line(tmp_path):
    proc = run_pytest(tmp_path, "[no-such-platform] test_demo.py::test_broken\ntest_demo.py::Subs::test_subs\n")
    assert proc.returncode == 1
