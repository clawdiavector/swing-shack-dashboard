"""T16 — archive drafts, plans, suggestions; restore; purge after retention."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _purge_imports() -> None:
    for mod in list(sys.modules):
        if mod == "_lib" or mod.startswith("_lib."):
            del sys.modules[mod]


@pytest.fixture(autouse=True)
def _scratch(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARCHIVE_PURGE_DAYS", "0")
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "plans" / "swing-shack").mkdir(parents=True, exist_ok=True)
    (tmp_path / "intelligence" / "marketing-calendar").mkdir(parents=True, exist_ok=True)
    _purge_imports()
    yield tmp_path
    _purge_imports()


def _seed_draft(tmp_path: Path, asset_id: str = "arch-draft-1") -> str:
    brand = "swing-shack"
    camp_id = "camp-arch"
    sidecar = {
        "asset_id": asset_id,
        "brand_id": brand,
        "campaign_id": camp_id,
        "created_at": "2026-09-30T10:00:00Z",
    }
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    camp = {
        "campaigns": {
            camp_id: {
                "assets": {
                    asset_id: {
                        "caption": "Archive me draft",
                        "approvalStatus": "pending",
                        "updatedAt": "2026-09-30T10:00:00Z",
                    }
                }
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")
    return asset_id


def _seed_plan(tmp_path: Path, plan_id: str = "plan-arch-1") -> str:
    brand = "swing-shack"
    plan = {
        "brand_id": brand,
        "plan_id": plan_id,
        "brief_id": "brief-arch",
        "event_name": "TEST plan archive",
        "status": "proposed",
        "items": [],
        "edit_log": [],
        "updated_at": "2026-09-30T10:00:00Z",
    }
    (tmp_path / "plans" / brand / f"{plan_id}.json").write_text(json.dumps(plan), encoding="utf-8")
    return plan_id


def _seed_suggestion(tmp_path: Path, calendar_id: str = "cal-sugg-arch") -> str:
    brand = "swing-shack"
    row = {
        "calendar_id": calendar_id,
        "event_key": calendar_id,
        "brand_id": brand,
        "status": "candidate",
        "type": "moment",
        "title": "Scout suggestion",
        "event_date": "2026-11-01",
        "revision": 1,
    }
    (tmp_path / "intelligence" / "marketing-calendar" / f"{brand}.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8"
    )
    return calendar_id


def test_draft_archive_restore_and_purge(_scratch):
    from _lib import content_archive as ca

    aid = _seed_draft(_scratch)
    brand = "swing-shack"
    ca.archive_item(brand, kind="draft", item_id=aid, actor="kyle")
    listed = ca.list_archived(brand)
    assert any(x["kind"] == "draft" and x["id"] == aid for x in listed)
    audit = ca.read_audit(brand_id=brand)
    assert audit[-1]["action"] == "archive" and audit[-1]["actor"] == "kyle"

    ca.restore_item(brand, kind="draft", item_id=aid, actor="kyle")
    assert not any(x["id"] == aid for x in ca.list_archived(brand))

    ca.archive_item(brand, kind="draft", item_id=aid, actor="kyle")
    past = datetime.now(timezone.utc) + timedelta(seconds=1)
    out = ca.purge_expired(now=past)
    assert out["purged"]["draft"] == 1
    assert not (_scratch / "draft-assets" / f"{aid}.json").is_file()


def test_plan_archive_restore_and_purge(_scratch):
    from _lib import campaign_plan as cp
    from _lib import content_archive as ca

    pid = _seed_plan(_scratch)
    brand = "swing-shack"
    ca.archive_item(brand, kind="plan", item_id=pid, actor="kyle")
    assert cp.get_plan(brand, pid)["status"] == cp.PLAN_ARCHIVED
    assert len(ca.list_archived(brand)) == 1

    ca.restore_item(brand, kind="plan", item_id=pid, actor="kyle")
    assert cp.get_plan(brand, pid)["status"] == "proposed"

    ca.archive_item(brand, kind="plan", item_id=pid, actor="kyle")
    past = datetime.now(timezone.utc) + timedelta(seconds=1)
    ca.purge_expired(now=past)
    assert cp.get_plan(brand, pid) is None


def test_suggestion_archive_restore_and_purge(_scratch):
    from _lib import calendar_suggestions as cs
    from _lib import content_archive as ca
    from _lib import marketing_calendar as mc

    cid = _seed_suggestion(_scratch)
    brand = "swing-shack"
    key = cs.row_key(cid)
    ca.archive_item(
        brand,
        kind="suggestion",
        item_id=cid,
        actor="kyle",
        suggestion_key=key,
    )
    row = mc._newest_row(brand, cid)  # noqa: SLF001
    assert row["status"] == "archived"
    assert len(ca.list_archived(brand)) == 1

    ca.restore_item(brand, kind="suggestion", item_id=cid, actor="kyle", suggestion_key=key)
    row = mc._newest_row(brand, cid)  # noqa: SLF001
    assert row["status"] == "candidate"

    ca.archive_item(brand, kind="suggestion", item_id=cid, actor="kyle", suggestion_key=key)
    past = datetime.now(timezone.utc) + timedelta(seconds=1)
    ca.purge_expired(now=past)
    row = mc._newest_row(brand, cid)  # noqa: SLF001
    assert row["status"] == "purged"


def test_archive_purge_button(_scratch):
    _seed_draft(_scratch)
    from _lib import content_archive as ca

    ca.archive_item("swing-shack", kind="draft", item_id="arch-draft-1", actor="job-test")
    result = ca.purge_brand("swing-shack", actor="job-test")
    assert result.get("ok") is True
    assert result.get("total", 0) >= 1


def test_retention_defaults_to_60_days(monkeypatch):
    from _lib import archive_retention as ar

    monkeypatch.delenv("ARCHIVE_PURGE_DAYS", raising=False)
    assert ar.retention_days() == 60
    assert ar.purge_at_iso("2026-10-27T00:00:00Z").startswith("2026-12-26")


def test_no_scheduled_purge_job():
    """Nothing deletes archived content on a schedule; purge is the Archive page button."""
    from _lib.jobs.layer2 import LAYER2_JOB_NAMES, layer2_specs
    from _lib.jobs.schedules import JOB_SCHEDULES

    assert "archive_purge" not in LAYER2_JOB_NAMES
    assert all(spec.name != "archive_purge" for spec in layer2_specs())
    assert "archive_purge" not in JOB_SCHEDULES
