"""P0 brand context pack — bibles, platform spec, thick brief (Track A)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import (  # noqa: E402
    _purge_modules,
    _seed_brands,
    l5_app,
)

_EXPECTED_SECTION_ORDER = (
    "JOB",
    "BRAND",
    "SUBJECT",
    "REFERENCE",
    "PRODUCT",
    "COMPOSITION",
    "LIGHTING",
    "CAMERA",
    "OUTPUT STYLE",
    "NEGATIVE",
)


@pytest.fixture(autouse=True)
def _bundled_data(monkeypatch):
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))


def test_load_brand_context_all_three_bibles():
    from _lib.creative_director import _load_brand_context

    for brand in ("swing-shack", "stick", "bag-drop"):
        ctx = _load_brand_context(brand)
        bible = ctx.get("bible") or {}
        assert "_placeholder" not in bible
        phil = (bible.get("philosophy") or bible.get("visual_philosophy") or "").strip()
        assert phil, f"{brand} missing philosophy"
        rules = bible.get("composition_rules") or []
        assert len(rules) >= 3, f"{brand} needs >=3 composition_rules"


def test_build_platform_spec_instagram_defaults():
    from _lib.jobs.layer5.image_draft_context import build_platform_spec

    spec = build_platform_spec("swing-shack", "instagram")
    assert spec["aspect_ratio"] == "1:1"
    assert spec["aspect_px"] == "1080x1080"
    assert spec["text_safety_zone"]
    assert isinstance(spec["model_hints"], list)


def test_build_platform_spec_facebook_channel():
    from _lib.jobs.layer5.image_draft_context import build_platform_spec

    spec = build_platform_spec("stick", "facebook")
    assert spec["aspect_ratio"] == "1.91:1"
    assert "1200x630" in spec["aspect_px"]


def test_compose_prompt_section_order_and_length():
    from _lib.creative_director import compose_prompt

    job = (
        'Social image for "TrackMan session: see your numbers" — Coaching pillar '
        "Angle: One golfer on the TrackMan bay, coach beside the screen, mid-swing, "
        "indoor studio light."
    )
    result = compose_prompt(
        brand_id="swing-shack",
        job=job,
        angle="One golfer on the TrackMan bay, coach beside the screen, mid-swing, indoor studio light.",
        pillar_name="Coaching",
        calendar_title="TrackMan session: see your numbers",
    )
    keys = [s["key"] for s in result["sections"]]
    filtered = [k for k in _EXPECTED_SECTION_ORDER if k in keys]
    assert keys == filtered
    master = result["master_prompt"]
    assert 400 <= len(master) <= 1200
    assert "photograph, no text, no logo, no watermark, no UI" in master
    assert "NEGATIVE" in master
    print("\n--- Swing Shack TrackMan composed prompt ---\n")
    print(master)
    print(f"\n(char count: {len(master)})\n")


def test_process_image_row_writes_brief_json(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _purge_modules()
    _seed_brands(tmp_path, brand="swing-shack", campaign_id="camp-ss")
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": "cal-trackman",
        "event_key": "cal-trackman",
        "status": "approved",
        "title": "TrackMan session: see your numbers",
        "angle": "One golfer on the TrackMan bay, coach beside the screen, mid-swing, indoor studio light.",
        "pillars": ["coaching"],
        "event_start": "2026-09-28",
        "type": "moment",
        "primary_channel": "instagram",
    }
    (cal_dir / "swing-shack.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    item_id = "calendar_candidate:swing-shack:cal-trackman"

    row = {"id": "q1", "action": "draft_image", "status": "pending"}
    mock_gen = MagicMock()
    png_path = tmp_path / "draft-assets" / "images" / "out.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    mock_gen.model = "test-model"
    mock_gen.provider = "openrouter"
    mock_gen.prompt_used = "prompt"
    mock_gen.bytes = png_path.read_bytes()
    mock_gen.saved_path = str(png_path)
    mock_gen.saved_sidecar_path = str(tmp_path / "draft-assets" / "images" / "out.meta.json")
    mock_gen.provider_job_id = None

    with patch("_lib.llm_spend.check", return_value=(True, "")), patch(
        "_lib.llm_spend.modelled_image_cost", return_value=0.04
    ), patch("_lib.llm_spend.write_approval_receipt"), patch(
        "_lib.llm_spend.record"
    ), patch(
        "_lib.image_submit_quota.check_brand_image_submit", return_value=(True, "")
    ), patch(
        "_lib.image_submit_quota.record_brand_image_submit"
    ), patch(
        "_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen
    ):
        asset_id, err = draft_assets._process_image_row(
            row,
            item_id=item_id,
            brand_id="swing-shack",
        )

    assert err is None
    assert asset_id
    brief_path = tmp_path / "draft-assets" / f"{asset_id}.brief.json"
    assert brief_path.is_file()
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    assert brief.get("platform_spec", {}).get("aspect_ratio")
    assert "sections" in brief
    assert brief.get("reference_id") is None
