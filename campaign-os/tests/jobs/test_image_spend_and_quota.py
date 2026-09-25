"""P0 image fix — spend ordering, 402 raise, daily image cap."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import _purge_modules, _seed_brands, _seed_queue_row  # noqa: E402

PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture()
def spend_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "10.00")
    monkeypatch.setenv("CAMPAIGN_OS_MAX_IMAGES_PER_DAY", "2")
    _purge_modules()
    _seed_brands(tmp_path, brand="stick", campaign_id="camp-stick")
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": "cal-spend",
        "event_key": "cal-spend",
        "status": "approved",
        "title": "Spend test",
        "event_start": "2026-10-01",
        "type": "content",
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return tmp_path, f"calendar_candidate:stick:cal-spend"


def test_krea_async_submit_no_spend_record(spend_env):
    tmp_path, item_id = spend_env
    from _lib import llm_spend
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_image", item_id=item_id, brand="stick")
    before = llm_spend.status().get("calls") or 0

    mock_gen = MagicMock()
    mock_gen.model = "bfl/flux-1.1-pro"
    mock_gen.provider = "krea"
    mock_gen.bytes = b""
    mock_gen.provider_job_id = "async-job-1"
    mock_gen.saved_sidecar_path = str(
        tmp_path / "draft-assets" / "images" / "stick" / "images" / "gen.meta.json"
    )
    sidecar_parent = Path(mock_gen.saved_sidecar_path).parent
    sidecar_parent.mkdir(parents=True, exist_ok=True)
    Path(mock_gen.saved_sidecar_path).write_text(
        json.dumps({"provider_job_id": "async-job-1", "bytes_size": 0}),
        encoding="utf-8",
    )

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    assert (llm_spend.status().get("calls") or 0) == before
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    row = next(r for r in queue["rows"] if r.get("action") == "draft_image")
    assert row.get("status") == "waiting"
    assert row.get("provider_job_id") == "async-job-1"


def test_sync_bytes_records_spend_once(spend_env):
    tmp_path, item_id = spend_env
    from _lib import llm_spend
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_image", item_id=item_id, brand="stick")
    png_path = tmp_path / "draft-assets" / "images" / "out.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(PNG_1x1)
    before = llm_spend.status().get("calls") or 0

    mock_gen = MagicMock()
    mock_gen.model = "test-model"
    mock_gen.provider = "openrouter"
    mock_gen.bytes = PNG_1x1
    mock_gen.saved_path = str(png_path)
    mock_gen.saved_sidecar_path = str(png_path.with_suffix(".meta.json"))
    mock_gen.provider_job_id = None
    mock_gen.prompt_used = "prompt"

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    after = llm_spend.status().get("calls") or 0
    assert after == before + 1


def test_openrouter_402_raises_no_krea_fallback():
    from _lib.image_gen_router import ImageGenUpstreamError, generate_image

    with patch("_lib.image_gen_router.openrouter_credentials_present", return_value=True):
        with patch(
            "_lib.image_gen_router._call_openrouter_multimodal",
            side_effect=ImageGenUpstreamError("Payment Required", code=402, upstream={}),
        ):
            with patch("_lib.image_gen_router._krea_credentials_present", return_value=True):
                with pytest.raises(ImageGenUpstreamError) as exc:
                    generate_image(
                        "test prompt",
                        brand_id="stick",
                        provider="openrouter",
                        save=False,
                    )
    assert exc.value.code == 402


def test_image_daily_cap_blocks_third_submit(spend_env, monkeypatch):
    tmp_path, item_id = spend_env
    from _lib import image_submit_quota
    from _lib.jobs.layer5 import draft_assets

    image_submit_quota.record_brand_image_submit("stick")
    image_submit_quota.record_brand_image_submit("stick")
    _seed_queue_row(tmp_path, action="draft_image", item_id=item_id, brand="stick")

    with patch("_lib.image_gen_router.generate_image_with_persistence") as mock_gen:
        draft_assets.run()
        mock_gen.assert_not_called()
