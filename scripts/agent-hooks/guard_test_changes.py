#!/usr/bin/env python3
"""CI guard: a PR may not quietly move the goalposts.

Fails when a PR
  * changes code AND edits or deletes EXISTING tests or snapshots, or
  * adds entries to tests/check-known-failures.txt,
unless ALLOW_TEST_CHANGES=1, which CI sets from the 'test-change-approved' PR
label after a person has looked. New test files are always fine.

Usage: guard_test_changes.py [base-ref]      e.g. origin/main
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    root = c.repo_root()
    if not root:
        print("guard_test_changes: not in a git repository")
        return 1
    if not c.git(root, "rev-parse", "--verify", "-q", base).strip():
        print(f"guard_test_changes: base ref {base} not found (CI needs fetch-depth: 0)")
        return 1

    touched_tests: list[str] = []
    touched_code: list[str] = []
    for line in c.git(root, "diff", "--name-status", "-M", f"{base}...HEAD").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, old, new = parts[0][0], parts[1], parts[-1]
        if c.is_test(old) or c.is_snapshot(old):
            if status in "MDR":
                touched_tests.append(old)
        elif c.CODE_RE.search(new) and not c.is_test(new):
            touched_code.append(new)

    added_known = [
        ln[1:].strip()
        for ln in c.git(root, "diff", "-U0", f"{base}...HEAD", "--", c.KNOWN_FAILURES).splitlines()
        if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip() and not ln[1:].lstrip().startswith("#")
    ]
    # The first version of the list is the baseline, not a goalpost move.
    if not c.git(root, "ls-tree", "--name-only", base, "--", c.KNOWN_FAILURES).strip():
        added_known = []

    problems: list[str] = []
    if touched_tests and touched_code:
        problems.append("This PR changes code AND edits/deletes existing tests or snapshots:")
        problems += [f"  - {t}" for t in touched_tests]
    if added_known:
        problems.append(f"This PR adds {len(added_known)} entries to {c.KNOWN_FAILURES} (the list may only shrink):")
        problems += [f"  + {t}" for t in added_known[:20]]

    if not problems:
        print("guard_test_changes: OK")
        return 0
    print("\n".join(problems))
    if os.environ.get("ALLOW_TEST_CHANGES", "0") == "1":
        print("\nApproved by a reviewer (ALLOW_TEST_CHANGES=1). guard_test_changes: OK")
        return 0
    print(
        "\nIf that is intended (behaviour really changed), a reviewer approves it by adding the\n"
        "'test-change-approved' label to the PR. Otherwise fix the code instead."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
