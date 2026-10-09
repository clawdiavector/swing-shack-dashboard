"""Shared by the agent hooks and the CI guard. Stdlib only.

What counts as a test, where per-session state lives, and how the working tree
is fingerprinted so "did this session change anything?" has an answer even in a
tree that was already dirty before the session began.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Files under a tests directory, plus test modules that live beside code (web/).
# The two lists under tests/ are left out on purpose: adding a test means adding a
# line to ci-allowlist.txt (CI's allowlist_ratchet refuses removals), and fixing one
# means deleting a line from check-known-failures.txt (the CI guard refuses additions).
TEST_RE = re.compile(
    os.environ.get("CHECK_TEST_RE")
    or r"(^|/)(tests?|self-tests|e2e|__tests__)/"
    r"|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$"
    r"|\.(test|spec)\.[jt]sx?$"
)
NOT_TEST_RE = re.compile(r"(^|/)tests/(ci-allowlist|check-known-failures)\.txt$|\.md$")
SNAPSHOT_RE = re.compile(r"(\.verified\.|__snapshots__/|-snapshots/)")
CODE_RE = re.compile(r"\.(py|js|jsx|ts|tsx|html|css|sql|sh)$")
KNOWN_FAILURES = "tests/check-known-failures.txt"
LOCK_FILE = ".checks-locked"
STATE_KEEP_DAYS = 14


def git(root: Path | str | None, *args: str) -> str:
    """stdout of a git command, or "" if it fails."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except OSError:
        return ""
    return out.stdout if out.returncode == 0 else ""


def repo_root(start: Path | str | None = None) -> Path | None:
    top = git(start, "rev-parse", "--show-toplevel").strip()
    return Path(top) if top else None


def is_test(rel: str) -> bool:
    return bool(TEST_RE.search(rel)) and not NOT_TEST_RE.search(rel)


def is_snapshot(rel: str) -> bool:
    return bool(SNAPSHOT_RE.search(rel))


def read_hook_input() -> dict:
    # Hook JSON is UTF-8; Windows would otherwise decode stdin as cp1252.
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    # Unparseable input raises: the caller reports it instead of silently allowing.
    data = json.loads(raw) if raw.strip() else {}
    return data if isinstance(data, dict) else {}


def session_key(data: dict) -> str:
    sid = str(data.get("session_id") or data.get("conversation_id") or "default")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", sid)[:80]


def base_ref(root: Path) -> str:
    for ref in (os.environ.get("CHECK_BASE_BRANCH", ""), "origin/main", "origin/master", "main", "master"):
        if ref and git(root, "rev-parse", "--verify", "-q", ref).strip():
            return ref
    return ""


def branch_tests(root: Path) -> set[str]:
    """Test files added or changed in commits on this branch: the agreed checks."""
    base = base_ref(root)
    mb = git(root, "merge-base", "HEAD", base).strip() if base else ""
    if not mb:
        return set()
    names = git(root, "diff", "--name-only", "--diff-filter=AMR", mb, "HEAD").splitlines()
    return {n for n in names if is_test(n)}


def lock_patterns(root: Path) -> list[str]:
    try:
        lines = (root / LOCK_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [p for p in (ln.split("#", 1)[0].strip() for ln in lines) if p]


def _norm(rel: str) -> str:
    # Windows hands hooks paths in whatever case the tool typed them.
    return rel.casefold() if os.name == "nt" else rel


def locked_files(root: Path) -> dict[str, tuple[str, str]]:
    """Every locked path, as normalised path -> (path as git has it, why).

    A file is locked when it is tracked AND is
      1. a committed snapshot, or
      2. matched by a glob in .checks-locked, or
      3. a test file committed on this branch.
    Untracked files are never locked: a new test stays editable until it is
    committed, which is what makes "write the test first, commit, then
    implement" work.
    """
    patterns = lock_patterns(root)
    on_branch = branch_tests(root)
    out: dict[str, tuple[str, str]] = {}
    for rel in git(root, "ls-files", "-z").split("\x00"):
        if not rel:
            continue
        why = ""
        if is_snapshot(rel):
            why = f"{rel} is a committed snapshot."
        elif rel in on_branch:
            why = f"{rel} is a test committed on this branch (the agreed check for this task)."
        else:
            pat = next((p for p in patterns if fnmatch.fnmatchcase(rel, p)), "")
            if pat:
                why = f"{rel} matches '{pat}' in {LOCK_FILE}."
        if why:
            out[_norm(rel)] = (rel, why)
    return out


def lock_reason(root: Path, rel: str) -> str:
    """Why a repo-relative path is locked, or "" if it is not."""
    return locked_files(root).get(_norm(rel), ("", ""))[1]


# --- per-session state ---------------------------------------------------------------

def state_dir(root: Path) -> Path | None:
    """Inside the git dir, so it is per-worktree and never shows up in `git status`."""
    p = git(root, "rev-parse", "--git-path", "agent-check").strip()
    if not p:
        return None
    path = Path(p)
    return path if path.is_absolute() else root / path


def fingerprint(root: Path) -> dict:
    """HEAD plus size and mtime of every uncommitted path.

    Comparing two of these says whether anything moved in between, without
    diffing file contents. An already-dirty tree fingerprints the same until one
    of its files is touched again.
    """
    files: dict[str, list[int]] = {}
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = status.split("\x00")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        code, rel = entry[:2], entry[3:]
        if code[0] in "RC":
            i += 1  # the rename/copy source follows as its own entry
        try:
            st = (root / rel).stat()
            files[rel] = [st.st_size, st.st_mtime_ns]
        except OSError:
            files[rel] = [-1, 0]
    return {"head": git(root, "rev-parse", "HEAD").strip(), "files": files}


def fingerprint_id(fp: dict) -> str:
    return hashlib.sha256(json.dumps(fp, sort_keys=True).encode()).hexdigest()


def read_state(root: Path, key: str) -> dict:
    sdir = state_dir(root)
    if not sdir:
        return {}
    try:
        data = json.loads((sdir / f"{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(root: Path, key: str, state: dict) -> None:
    sdir = state_dir(root)
    if not sdir:
        return
    try:
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / f"{key}.json").write_text(json.dumps(state), encoding="utf-8")
        cutoff = time.time() - STATE_KEEP_DAYS * 86400
        for old in sdir.glob("*.json"):
            if old.stat().st_mtime < cutoff:
                old.unlink()
    except OSError:
        pass


def ensure_baseline(root: Path, key: str) -> None:
    """Record the tree as this session first found it. Called before the
    session's first write-capable tool runs; later calls are no-ops."""
    if "baseline" not in read_state(root, key):
        write_state(root, key, {"baseline": fingerprint_id(fingerprint(root)), "retries": 0})
