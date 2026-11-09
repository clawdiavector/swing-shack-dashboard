"""Design taxonomy — seed load and approval overlay."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import design_taxonomy as dt


@pytest.fixture()
def taxonomy_env(monkeypatch, tmp_path):
    repo = CAMPAIGN_OS.parent
    bundled = repo / "data"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))
    approvals = tmp_path / "design-approvals.json"
    if approvals.exists():
        approvals.unlink()
    return tmp_path


def test_load_seed_has_snap():
    seed = dt.load_seed()
    snap = next(s for s in seed["styles"] if s["id"] == "snap")
    assert snap["name"] == "Snap"
    assert snap["approval"]["status"] == "not_approved"


def test_approve_snap_records_actor_and_time(taxonomy_env):
    del taxonomy_env
    approval = dt.set_approval("styles", "snap", approve=True, actor="pytest")
    assert approval["status"] == "approved"
    assert approval["by"] == "pytest"
    assert approval["at"]

    payload = dt.build_taxonomy()
    snap = next(s for s in payload["styles"] if s["id"] == "snap")
    assert snap["approval"]["status"] == "approved"
    assert snap["approval"]["by"] == "pytest"

    dt.set_approval("styles", "snap", approve=False, actor="pytest")
    payload2 = dt.build_taxonomy()
    snap2 = next(s for s in payload2["styles"] if s["id"] == "snap")
    assert snap2["approval"]["status"] == "not_approved"
    assert snap2["approval"]["by"] is None
    assert snap2["approval"]["at"] is None
