"""L5 compose_post — per-asset composed paths and archetype sidecar."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import _purge_modules, l5_app  # noqa: E402


@pytest.fixture
def compose_env(l5_app, tmp_path):
    _purge_modules()
    brand = "stick"
    asset_id = "draft-compose-lineage"
    item_id = "calendar_candidate:stick:cal-tip"
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    (cal_dir / f"{brand}.jsonl").write_text(
        json.dumps(
            {
                "calendar_id": "cal-tip",
                "event_key": "cal-tip",
                "status": "approved",
                "title": "Tip moment",
                "post_type": "tip",
                "template_id": "ss-did-you-know",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    draft_dir = tmp_path / "draft-assets"
    draft_dir.mkdir(parents=True, exist_ok=True)
    sidecar = {
        "asset_id": asset_id,
        "brand_id": brand,
        "source_inbox_item_id": item_id,
        "action": "draft_photo",
        "qc": {"verdict": "pass", "selected": None, "candidates": [], "compose_only": True},
    }
    (draft_dir / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    campaign = {
        "campaigns": {
            "camp-stick": {
                "assets": {
                    asset_id: {
                        "name": "Tip",
                        "caption": "Hook line",
                        "approvalStatus": "pending",
                    }
                }
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(campaign), encoding="utf-8")
    yield tmp_path, brand, item_id, asset_id


def test_compose_post_writes_asset_scoped_paths_and_archetype(compose_env):
    tmp_path, brand, item_id, asset_id = compose_env
    fake_png = b"\x89PNG\r\n\x1a\n" + b"z" * 32

    def _fake_compose(**_kwargs):
        return {"instagram": fake_png, "facebook": fake_png}

    from _lib.jobs.layer5.create_photo_compose import process_compose_post_row

    with patch("_lib.archetype_compose.compose_post_for_channels", side_effect=_fake_compose):
        out_id, err = process_compose_post_row(
            {"action": "compose_post"},
            item_id=item_id,
            brand_id=brand,
        )

    assert err is None
    assert out_id == asset_id
    out_dir = tmp_path / "draft-assets" / "images" / brand
    assert (out_dir / f"composed-{asset_id}-instagram.png").is_file()
    assert (out_dir / f"composed-{asset_id}-facebook.png").is_file()
    assert not (out_dir / "composed-instagram.png").exists()

    saved = json.loads((tmp_path / "draft-assets" / f"{asset_id}.json").read_text(encoding="utf-8"))
    arch = saved.get("archetype") or {}
    assert arch.get("id")
    assert arch.get("template_id") == "ss-did-you-know"

    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    asset = data["campaigns"]["camp-stick"]["assets"][asset_id]
    assert asset_id in Path(asset["image_path"]).name
