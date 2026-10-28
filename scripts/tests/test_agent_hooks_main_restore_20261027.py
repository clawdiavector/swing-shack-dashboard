"""protect_checks lets a locked test be put back exactly as it is on main."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "agent_hooks_base", Path(__file__).resolve().parent / "test_agent_hooks.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
git, protect = base.git, base.protect

MAIN_TEXT = "def test_old():\n    assert True\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """test_old.py is on main, then loosened in a commit on feat (so it is locked)."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_old.py").write_text(MAIN_TEXT)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "feat")
    monkeypatch.setenv("CHECK_BASE_BRANCH", "main")
    monkeypatch.delenv("CHECK_LOCK_MODE", raising=False)
    (root / "tests" / "test_old.py").write_text("def test_old():\n    assert 1 <= 15\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "loosen old test on branch")
    return root


@pytest.mark.parametrize("tool", ["claude", "cursor"])
def test_old_test_is_locked_after_branch_edit(repo, tool):
    assert protect(repo, "Edit", tool, file_path="tests/test_old.py",
                   old_string="15", new_string="16") == "deny"


@pytest.mark.parametrize("tool", ["claude", "cursor"])
def test_write_exact_main_content_is_allowed(repo, tool):
    assert protect(repo, "Write", tool, file_path="tests/test_old.py", content=MAIN_TEXT) == "allow"
    assert protect(repo, "Write", tool, file_path="tests/test_old.py", contents=MAIN_TEXT) == "allow"


def test_edit_that_lands_on_main_content_is_allowed(repo):
    assert protect(repo, "Edit", file_path="tests/test_old.py",
                   old_string="    assert 1 <= 15\n", new_string="    assert True\n") == "allow"


def test_write_close_to_main_but_not_exact_is_denied(repo):
    assert protect(repo, "Write", file_path="tests/test_old.py", content=MAIN_TEXT + "\n") == "deny"
    assert protect(repo, "Write", file_path="tests/test_old.py", content=MAIN_TEXT.rstrip("\n")) == "deny"


def test_partial_edit_is_denied(repo):
    assert protect(repo, "Edit", file_path="tests/test_old.py",
                   old_string="15", new_string="12") == "deny"


@pytest.mark.parametrize("command", [
    "git checkout main -- tests/test_old.py",
    "git restore --source main -- tests/test_old.py",
    "git restore --source=main -- tests/test_old.py",
])
def test_exact_restore_command_is_allowed(repo, command):
    assert protect(repo, "Bash", command=command) == "allow"


@pytest.mark.parametrize("command", [
    "git checkout HEAD~1 -- tests/test_old.py",
    "git checkout main -- tests/test_old.py && echo x >> tests/test_old.py",
    "git checkout main -- tests/test_old.py; rm tests/test_old.py",
    "git show main:tests/test_old.py > tests/test_old.py",
    "git checkout main tests/test_old.py",
    "sed -i 's/15/12/' tests/test_old.py",
])
def test_other_shell_writes_stay_denied(repo, command):
    assert protect(repo, "Bash", command=command) == "deny"


def test_file_not_on_main_stays_locked(repo):
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add new test on branch")
    text = (repo / "tests" / "test_new.py").read_text()
    assert protect(repo, "Write", file_path="tests/test_new.py", content=text) == "deny"
    assert protect(repo, "Bash", command="git checkout main -- tests/test_new.py") == "deny"
    assert protect(repo, "Bash", command="git restore --source main -- tests/test_new.py") == "deny"
