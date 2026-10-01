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
    assert not _explicit_caption_regen(
        [({"id": "manual-stick-cos-caption-weekly", "action": "draft_caption"}, "draft_caption")]
    )
