"""pytest plugin for ./check: tests already failing on main do not fail the run.

    pytest -p known_failures_plugin --known-failures tests/check-known-failures.txt ...

Each node id in the file is marked xfail (non-strict), so the run goes red only
for a failure that is NOT on the list, i.e. one this change introduced. Listed
tests that pass again are reported at the end so their lines can be deleted. The
list may only shrink; CI's guard refuses a PR that adds to it without approval.

A line may be limited to one platform: "[win32] path::test" applies only where
sys.platform starts with "win32".
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_KNOWN: set[str] = set()
_SEEN: set[str] = set()
_FILES: set[str] = set()


def load_known(path: Path) -> set[str]:
    known: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return known
    for line in lines:
        line = line.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            plat, _, line = line[1:].partition("]")
            if not sys.platform.startswith(plat.strip()):
                continue
        known.add(line.strip())
    return known


def pytest_addoption(parser):
    parser.addoption("--known-failures", default=None, help="file of node ids already failing on main")


def pytest_collection_modifyitems(config, items):
    path = config.getoption("--known-failures")
    if not path:
        return
    _KNOWN.update(load_known(Path(path)))
    for item in items:
        _FILES.add(item.nodeid.split("::", 1)[0])
        if item.nodeid in _KNOWN:
            _SEEN.add(item.nodeid)
            item.add_marker(pytest.mark.xfail(reason="known failure on main", strict=False))


def pytest_terminal_summary(terminalreporter):
    if not _KNOWN:
        return
    stats = terminalreporter.stats
    # A test whose only failures are subtests reports the subtests as xfailed and
    # the test itself as xpassed. That is still failing, so it is not "fixed".
    still_failing = {rep.nodeid for rep in stats.get("xfailed", [])}
    fixed = sorted({rep.nodeid for rep in stats.get("xpassed", []) if rep.nodeid in _KNOWN} - still_failing)
    # Only judge files this run collected (or that are gone from disk), so running
    # a subset of the suite does not report the rest of the list as missing.
    root = terminalreporter.config.rootpath
    gone = sorted(
        nodeid for nodeid in _KNOWN - _SEEN
        if nodeid.split("::", 1)[0] in _FILES or not (root / nodeid.split("::", 1)[0]).exists()
    )
    tr = terminalreporter
    if fixed:
        tr.section("known failures that now pass here")
        tr.write_line("If they also pass in CI, delete these lines from tests/check-known-failures.txt:")
        for nodeid in fixed:
            tr.write_line(f"  {nodeid}")
    if gone:
        tr.section("known failures that no longer exist")
        tr.write_line("Renamed or deleted tests; delete these lines from tests/check-known-failures.txt:")
        for nodeid in gone:
            tr.write_line(f"  {nodeid}")
