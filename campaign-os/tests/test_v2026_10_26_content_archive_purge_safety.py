"""T16 fix — retention floor, live gate, and legacy archive purge safety."""

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
    _purge_imports()
    yield tmp_path
    _purge_imports()


def test_archive_purge_days_rejects_zero_outside_pytest(monkeypatch):
    from _lib.archive_retention import ArchivePurgeConfigError, validate_production_purge_config

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ARCHIVE_PURGE_DAYS", "0")
    with pytest.raises(ArchivePurgeConfigError):
        validate_production_purge_config()


def test_archive_purge_days_enforces_minimum_seven(monkeypatch):
    from _lib.archive_retention import retention_days

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ARCHIVE_PURGE_DAYS", "3")
    assert retention_days() == 7


def test_legacy_archived_draft_without_archived_at_is_not_purged(_scratch):
    from _lib import content_archive as ca
    from _lib.library_shelf import _archive_draft

    brand = "swing-shack"
    asset_id = "legacy-arch-1"
    camp_id = "camp-legacy"
    sidecar = {
        "asset_id": asset_id,
        "brand_id": brand,
        "campaign_id": camp_id,
        "status": "archived",
        "created_at": "2026-01-01T10:00:00Z",
    }
    (_scratch / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    camp = {
        "campaigns": {
            camp_id: {
                "assets": {
                    asset_id: {
                        "caption": "Legacy archive",
                        "approvalStatus": "archived",
                        "updatedAt": "2026-01-01T10:00:00Z",
                    }
                }
            }
        }
    }
    (_scratch / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")
    assert _archive_draft(asset_id, camp_id)

    past = datetime.now(timezone.utc) + timedelta(days=400)
    out = ca.purge_expired(now=past, dry_run=False)
    assert out["purged"]["draft"] == 0
    assert out["purged"]["skipped_legacy"] == 1
    assert (_scratch / "draft-assets" / f"{asset_id}.json").is_file()


def test_purge_job_dry_run_until_live_armed(monkeypatch, _scratch):
    from _lib import content_archive as ca
    from _lib.jobs.layer2 import archive_purge

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("ARCHIVE_PURGE_LIVE", raising=False)
    monkeypatch.setenv("ARCHIVE_PURGE_DAYS", "7")

    aid = "dry-run-draft"
    brand = "swing-shack"
    camp_id = "camp-dry"
    sidecar = {
        "asset_id": aid,
        "brand_id": brand,
        "campaign_id": camp_id,
        "created_at": "2026-09-30T10:00:00Z",
    }
    (_scratch / "draft-assets" / f"{aid}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    camp = {
        "campaigns": {
            camp_id: {
                "assets": {
                    aid: {
                        "caption": "Dry run me",
                        "approvalStatus": "pending",
                        "updatedAt": "2026-09-30T10:00:00Z",
                    }
                }
            }
        }
    }
    (_scratch / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")
    ca.archive_item(brand, kind="draft", item_id=aid, actor="kyle")

    result = archive_purge.run()
    assert result.get("dry_run") is True
    assert result.get("live") is False
    assert (_scratch / "draft-assets" / f"{aid}.json").is_file()
    audit = ca.read_audit(brand_id=brand)
    assert any(row.get("action") == "purge_dry_run" for row in audit)
