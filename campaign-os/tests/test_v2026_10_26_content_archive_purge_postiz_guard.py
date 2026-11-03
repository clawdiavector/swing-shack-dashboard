"""T16 fix — purge skips published drafts; Postiz delete on purge when scheduled."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

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
    (tmp_path / "publish-sandbox").mkdir(parents=True, exist_ok=True)
    (tmp_path / "publish-sandbox" / "receipts.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "publish-sandbox" / "queue.jsonl").write_text("", encoding="utf-8")
    _purge_imports()
    yield tmp_path
    _purge_imports()


def _seed_archived_draft(tmp_path: Path, asset_id: str = "arch-pub-guard-1") -> str:
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
                        "caption": "Shipped draft",
                        "approvalStatus": "archived",
                        "archived_at": "2026-09-30T10:00:00Z",
                        "archived_by": "kyle",
                        "updatedAt": "2026-09-30T10:00:00Z",
                    }
                }
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")
    return asset_id


def test_purge_skips_published_draft_and_logs(_scratch):
    from _lib import content_archive as ca

    aid = _seed_archived_draft(_scratch)
    index = {
        "by_asset_id": {
            aid: {
                "brand_id": "swing-shack",
                "asset_id": aid,
                "postiz_post_id": "postiz-live-99",
                "published_at": "2026-10-01T12:00:00Z",
                "channel": "postiz",
            }
        },
        "by_media_id": {},
    }
    (_scratch / "meta-post-index.json").write_text(json.dumps(index), encoding="utf-8")

    past = datetime.now(timezone.utc) + timedelta(seconds=1)
    with mock.patch("_lib.postiz_client.delete_post") as mock_del:
        out = ca.purge_expired(now=past)
        mock_del.assert_not_called()

    assert out["purged"]["draft"] == 0
    assert out["purged"]["skipped_published"] == 1
    assert (_scratch / "draft-assets" / f"{aid}.json").is_file()
    audit = ca.read_audit(brand_id="swing-shack")
    assert audit[-1]["action"] == "purge_skipped"
    assert audit[-1]["reason"] == "published"


def test_purge_calls_delete_post_before_removing_scheduled_draft(_scratch):
    from _lib import content_archive as ca

    aid = "arch-sched-purge-1"
    brand = "swing-shack"
    _seed_archived_draft(_scratch, asset_id=aid)
    receipt = {
        "schema": "campaign-os/publish-receipt/v1",
        "mode": "live",
        "brand_id": brand,
        "idempotency_key": f"qc-{aid}-instagram",
        "platform": "instagram",
        "postiz_post_id": "postiz-sched-42",
        "dispatched_at": "2026-10-01T08:00:00Z",
    }
    (_scratch / "publish-sandbox" / "receipts.jsonl").write_text(
        json.dumps(receipt) + "\n", encoding="utf-8"
    )

    past = datetime.now(timezone.utc) + timedelta(seconds=1)
    with mock.patch("_lib.postiz_client.delete_post", return_value=({}, None)) as mock_del:
        out = ca.purge_expired(now=past)

    mock_del.assert_called_once_with("postiz-sched-42")
    assert out["purged"]["draft"] == 1
    assert not (_scratch / "draft-assets" / f"{aid}.json").is_file()
