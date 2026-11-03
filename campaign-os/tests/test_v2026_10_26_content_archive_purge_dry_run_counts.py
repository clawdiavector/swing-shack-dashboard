"""Dry-run purge counts only items past retention (same eligibility as live purge)."""

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
    monkeypatch.setenv("ARCHIVE_PURGE_DAYS", "7")
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    _purge_imports()
    yield tmp_path
    _purge_imports()


def _seed_two_drafts(tmp_path: Path, fresh_id: str, expired_id: str) -> str:
    brand = "swing-shack"
    camp_id = "camp-dry-count"
    for asset_id in (fresh_id, expired_id):
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
                    fresh_id: {
                        "caption": "Still in retention",
                        "approvalStatus": "pending",
                        "updatedAt": "2026-09-30T10:00:00Z",
                    },
                    expired_id: {
                        "caption": "Past retention",
                        "approvalStatus": "pending",
                        "updatedAt": "2026-09-30T10:00:00Z",
                    },
                }
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")
    return brand


def test_dry_run_counts_only_past_retention(_scratch):
    from _lib import content_archive as ca

    brand = _seed_two_drafts(_scratch, "fresh-archived", "expired-archived")
    ca.archive_item(brand, kind="draft", item_id="fresh-archived", actor="kyle")
    ca.archive_item(brand, kind="draft", item_id="expired-archived", actor="kyle")

    camp_path = _scratch / "campaign-data.json"
    camp = json.loads(camp_path.read_text(encoding="utf-8"))
    camp_id = json.loads((_scratch / "draft-assets" / "expired-archived.json").read_text())["campaign_id"]
    old = datetime.now(timezone.utc) - timedelta(days=30)
    camp["campaigns"][camp_id]["assets"]["expired-archived"]["archived_at"] = old.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    camp_path.write_text(json.dumps(camp), encoding="utf-8")

    now = datetime.now(timezone.utc)
    out = ca.purge_expired(now=now, dry_run=True)
    assert out["dry_run"] is True
    assert out["total"] == 1
    assert out["purged"]["draft"] == 1
    assert out["purged"]["dry_run"] == 1
    assert (_scratch / "draft-assets" / "fresh-archived.json").is_file()
    assert (_scratch / "draft-assets" / "expired-archived.json").is_file()
