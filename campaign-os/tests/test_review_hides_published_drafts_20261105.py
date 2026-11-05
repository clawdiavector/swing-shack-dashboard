"""Approve drafts must not list a draft that has already gone out (audit, 5 Nov 2026).

Titleist Tour Soft (Swing Shack, 31 Oct) and Takomo 101U (Stick, 23 Oct) were posted
but still sat in Approve drafts as pending, and the archive refused them as published.
Both use the same rule: content_archive.draft_is_published.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _write(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_published_asset_ids_reads_every_published_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from _lib import content_archive

    _write(tmp_path / "published-items.json", {"published": [{"asset_id": "from-items"}]})
    _write(
        tmp_path / "meta-post-index.json",
        {"by_asset_id": {"from-link": {"published_at": "2026-10-31T07:00:00Z"}, "not-yet": {}}},
    )
    campaigns = {"c1": {"assets": {"from-campaign": {"approvalStatus": "published"}, "draft": {}}}}

    ids = content_archive.published_asset_ids(campaigns)

    assert {"from-items", "from-link", "from-campaign"} <= ids
    assert "not-yet" not in ids
    assert "draft" not in ids


def test_published_asset_ids_agrees_with_draft_is_published(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from _lib import content_archive

    _write(tmp_path / "published-items.json", {"published": [{"assetId": "shipped"}]})

    assert content_archive.draft_is_published("shipped")
    assert "shipped" in content_archive.published_asset_ids({})


def test_pending_draft_already_published_is_not_listed(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from _lib import intelligence, unified_inbox

    _write(tmp_path / "published-items.json", {"published": [{"asset_id": "titleist-tour-soft"}]})
    monkeypatch.setattr(intelligence, "set_request_brand", lambda brand: None)
    monkeypatch.setattr(
        intelligence,
        "review_inbox",
        lambda: {
            "pending": [{"campaignId": "swing-shack-calendar", "assetId": "titleist-tour-soft", "brand": "swing-shack"}],
            "approved": [],
            "rejected": [],
        },
    )
    monkeypatch.setattr(unified_inbox, "_load_campaign_data", lambda: {"campaigns": {}})

    items = unified_inbox._draft_items(
        brand="swing-shack", status="pending", now=datetime(2026, 11, 5, tzinfo=timezone.utc)
    )

    assert [i["meta"]["asset_id"] for i in items] == []
