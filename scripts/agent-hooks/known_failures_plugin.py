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
        if item.nodeid in _KNOWN:
            _SEEN.add(item.nodeid)
            item.add_marker(pytest.mark.xfail(reason="known failure on main", strict=False))


def pytest_terminal_summary(terminalreporter):
    if not _KNOWN:
        return
    fixed = sorted({rep.nodeid for rep in terminalreporter.stats.get("xpassed", []) if rep.nodeid in _KNOWN})
    gone = sorted(_KNOWN - _SEEN)
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
