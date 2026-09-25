"""P0 image fix — spend ordering, double-charge guard, by_brand rollup."""

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


def test_no_spend_when_provider_returns_no_bytes(spend_env):
    tmp_path, item_id = spend_env
    from _lib import llm_spend
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_image", item_id=item_id, brand="stick")
    mock_gen = MagicMock()
    mock_gen.model = "bfl/flux-1.1-pro"
    mock_gen.provider = "krea"
    mock_gen.bytes = b""
    mock_gen.provider_job_id = "async-job-1"
    mock_gen.saved_sidecar_path = str(
        tmp_path / "draft-assets" / "images" / "stick" / "images" / "gen.meta.json"
    )

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    assert llm_spend.today_spend()["usd"] == 0.0
    assert llm_spend.today_spend()["calls"] == 0
    jobs = json.loads((tmp_path / "draft-assets" / "_image-jobs.json").read_text(encoding="utf-8"))
    assert jobs["jobs"][item_id]["job_id"] == "async-job-1"


def test_spend_recorded_once_on_real_bytes_krea(spend_env):
    tmp_path, item_id = spend_env
    from _lib import llm_spend
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_image", item_id=item_id, brand="stick")
    png_path = tmp_path / "draft-assets" / "images" / "out.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(PNG_1x1)

    mock_gen = MagicMock()
    mock_gen.model = "test-model"
    mock_gen.provider = "krea"
    mock_gen.bytes = PNG_1x1
    mock_gen.saved_path = str(png_path)
    mock_gen.provider_job_id = None
    mock_gen.prompt_used = "prompt"

    qc_pass = {"verdict": "pass", "reasons": [], "ocr_available": True, "scores": {}}
    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen), patch(
        "_lib.jobs.layer5.visual_qc.visual_check", return_value=qc_pass
    ):
        draft_assets.run()

    assert llm_spend.today_spend()["calls"] == 2
    assert llm_spend.today_spend()["usd"] == pytest.approx(2 * llm_spend.modelled_image_cost("1024x1024"))


def test_no_double_charge_on_openrouter_provider(spend_env):
    tmp_path, item_id = spend_env
    from _lib import llm_spend
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_image", item_id=item_id, brand="stick")
    png_path = tmp_path / "draft-assets" / "images" / "out.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(PNG_1x1)

    def fake_gen(**kwargs):
        llm_spend.record(0.04, route="image_gen_router.generate", model="or-model", kind="image")
        mock = MagicMock()
        mock.model = "or-model"
        mock.provider = "openrouter"
        mock.bytes = PNG_1x1
        mock.saved_path = str(png_path)
        mock.provider_job_id = None
        return mock

    qc_pass = {"verdict": "pass", "reasons": [], "ocr_available": True, "scores": {}}
    with patch("_lib.image_gen_router.generate_image_with_persistence", side_effect=fake_gen), patch(
        "_lib.jobs.layer5.visual_qc.visual_check", return_value=qc_pass
    ):
        draft_assets.run()

    assert llm_spend.today_spend()["calls"] == 2


def test_by_brand_rollup_sums_to_total(spend_env):
    from _lib import llm_spend

    llm_spend.record(0.01, route="a", kind="text", brand_id="swing-shack")
    llm_spend.record(0.02, route="b", kind="image", brand_id="swing-shack")
    llm_spend.record(0.03, route="c", kind="image")
    day_path = Path(spend_env[0]) / "llm-spend"
    files = list(day_path.glob("*.json"))
    data = json.loads(files[0].read_text(encoding="utf-8"))
    by_brand = data.get("by_brand") or {}
    total = sum(float(v.get("usd") or 0) for v in by_brand.values())
    assert total == pytest.approx(float(data.get("usd") or 0))
    assert by_brand.get("_unattributed", {}).get("usd") == pytest.approx(0.03)


def test_image_daily_cap_blocks_third_submit(spend_env):
    tmp_path, item_id = spend_env
    from _lib import image_submit_quota
    from _lib.jobs.layer5 import draft_assets

    image_submit_quota.record_brand_image_submit("stick")
    image_submit_quota.record_brand_image_submit("stick")
    _seed_queue_row(tmp_path, action="draft_image", item_id=item_id, brand="stick")

    with patch("_lib.image_gen_router.generate_image_with_persistence") as mock_gen:
        draft_assets.run()
        mock_gen.assert_not_called()
