"""Regenerate caption must clear a finished poster, not only a draft_caption sidecar."""

from __future__ import annotations

import json
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def test_retire_clears_composed_sidecar(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    moment = "calendar_candidate:stick:cal-1"
    asset_id = "draft-abc"
    (tmp_path / "draft-assets").mkdir()
    sidecar = {
        "asset_id": asset_id,
        "campaign_id": "cos-drafts-stick",
        "source_inbox_item_id": moment,
        "action": "compose_post",
        "composed": {"headline": "FREE CLUB"},
    }
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    (tmp_path / "campaign-data.json").write_text(
        json.dumps(
            {
                "campaigns": {
                    "cos-drafts-stick": {
                        "assets": {
                            asset_id: {
                                "caption": "A TPI assessment can reveal what you're really working with.",
                                "composed": {"headline": "FREE CLUB"},
                                "copy_package": {"body": "old"},
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    from _lib.draft_review_actions import retire_caption_drafts_for_moment
    from _lib.jobs.layer5.draft_assets import _explicit_caption_regen

    retired = retire_caption_drafts_for_moment(moment)
    assert retired == [asset_id]

    saved = json.loads((tmp_path / "draft-assets" / f"{asset_id}.json").read_text(encoding="utf-8"))
    assert saved["action"] == "superseded_caption"
    assert "composed" not in saved

    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    asset = data["campaigns"]["cos-drafts-stick"]["assets"][asset_id]
    assert asset["caption"] == ""
    assert "composed" not in asset
    assert "copy_package" not in asset

    assert _explicit_caption_regen(
        [({"id": "manual-stick-cos-caption-cap-regen-abc", "action": "draft_caption"}, "draft_caption")]
    )
    assert _explicit_caption_regen(
        [({"id": "manual-stick-cos-caption-cap-keep-draft-abc123", "action": "draft_caption"}, "draft_caption")]
    )
    assert not _explicit_caption_regen(
        [({"id": "manual-stick-cos-caption-weekly", "action": "draft_caption"}, "draft_caption")]
    )
    assert not _explicit_caption_regen(
        [({"id": "manual-stick-cos-image-compose-regen-abc", "action": "compose_post"}, "compose_post")]
    )


def test_caption_regen_keeps_poster(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    moment = "calendar_candidate:stick:cal-1"
    asset_id = "draft-abc123def456"
    (tmp_path / "draft-assets").mkdir()
    sidecar = {
        "asset_id": asset_id,
        "campaign_id": "cos-drafts-stick",
        "brand_id": "stick",
        "source_inbox_item_id": moment,
        "action": "compose_post",
        "composed": {"instagram": "/brand-images/stick/composed-draft-abc123def456-instagram.png"},
    }
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    (tmp_path / "campaign-data.json").write_text(
        json.dumps(
            {
                "campaigns": {
                    "cos-drafts-stick": {
                        "identity": {"brand": "stick"},
                        "assets": {
                            asset_id: {
                                "caption": "Old TPI caption",
                                "composed": {"instagram": "/brand-images/stick/old.png"},
                                "image_url": "/brand-images/stick/old.png",
                                "copy_package": {"body": "old"},
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    from _lib.draft_review_actions import regenerate_caption

    result = regenerate_caption(
        draft_id=f"draft_asset:cos-drafts-stick:{asset_id}",
        reason="from review",
        recompose=False,
        run_now=False,
    )
    assert result["ok"] is True
    assert result["enqueued"] == ["draft_caption"]
    assert result["retired_asset_ids"] == []

    saved = json.loads((tmp_path / "draft-assets" / f"{asset_id}.json").read_text(encoding="utf-8"))
    assert saved["action"] == "compose_post"
    assert saved["composed"]["instagram"].endswith("instagram.png")
    assert saved["source_inbox_item_id"] == moment

    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    asset = data["campaigns"]["cos-drafts-stick"]["assets"][asset_id]
    assert asset["caption"] == ""
    assert asset["image_url"] == "/brand-images/stick/old.png"
    assert "composed" in asset

    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    row_ids = [row["id"] for row in queue["rows"]]
    assert any("cap-keep-draft-abc123def456" in row_id for row_id in row_ids)
    assert all(row["action"] != "compose_post" for row in queue["rows"])


def test_restore_poster_from_publish(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    moment = "calendar_candidate:stick:cal-1"
    asset_id = "draft-abc123def456"
    other_id = "draft-ffffeeee1111"
    (tmp_path / "draft-assets").mkdir()
    (tmp_path / "publish-sandbox").mkdir()
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(
        json.dumps({
            "asset_id": asset_id,
            "campaign_id": "cos-drafts-stick",
            "brand_id": "stick",
            "source_inbox_item_id": moment,
            "action": "superseded_caption",
        }),
        encoding="utf-8",
    )
    (tmp_path / "draft-assets" / f"{other_id}.json").write_text(
        json.dumps({
            "asset_id": other_id,
            "campaign_id": "cos-drafts-stick",
            "brand_id": "stick",
            "source_inbox_item_id": moment,
            "action": "compose_post",
        }),
        encoding="utf-8",
    )
    (tmp_path / "campaign-data.json").write_text(
        json.dumps({
            "campaigns": {
                "cos-drafts-stick": {
                    "identity": {"brand": "stick"},
                    "assets": {
                        asset_id: {"caption": "", "approvalStatus": "draft"},
                        other_id: {"caption": "new", "approvalStatus": "draft"},
                    },
                }
            }
        }),
        encoding="utf-8",
    )
    (tmp_path / "publish-sandbox" / "queue.jsonl").write_text(
        json.dumps({
            "idempotency_key": f"qc-{asset_id}-instagram",
            "platform": "instagram",
            "caption_preview": "Is your swing controlled by your body or just your off-rack clubs?",
            "image_url": f"/brand-images/stick/composed-{asset_id}-instagram.png",
            "image_path": f"/data/campaign-os/draft-assets/images/stick/composed-{asset_id}-instagram.png",
            "status": "pending",
        }) + "\n",
        encoding="utf-8",
    )

    from _lib.draft_review_actions import restore_poster_from_publish

    result = restore_poster_from_publish(
        f"draft_asset:cos-drafts-stick:{asset_id}",
        detach_asset_id=other_id,
    )
    assert result["ok"] is True
    assert result["image_url"].endswith("instagram.png")

    saved = json.loads((tmp_path / "draft-assets" / f"{asset_id}.json").read_text(encoding="utf-8"))
    assert saved["action"] == "compose_post"
    assert saved["source_inbox_item_id"] == moment
    assert saved["composed"]["instagram"].endswith("instagram.png")

    other = json.loads((tmp_path / "draft-assets" / f"{other_id}.json").read_text(encoding="utf-8"))
    assert other["action"] == "superseded_caption"
    assert other["source_inbox_item_id"] == ""

    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    asset = data["campaigns"]["cos-drafts-stick"]["assets"][asset_id]
    assert asset["caption"].startswith("Is your swing controlled")
    assert asset["image_url"].endswith("instagram.png")
