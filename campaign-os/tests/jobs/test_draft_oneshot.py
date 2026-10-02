"""draft_oneshot cook path — provider always mocked."""

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
def oneshot_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(CAMPAIGN_OS.parent / "data"))
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "10.00")
    monkeypatch.setenv("CAMPAIGN_OS_MAX_IMAGES_PER_DAY", "2")
    _purge_modules()
    _seed_brands(tmp_path, brand="stick", campaign_id="camp-stick")
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": "cal-os",
        "event_key": "cal-os",
        "status": "approved",
        "title": "Hello world",
        "event_start": "2026-10-01",
        "type": "content",
        "render_mode": "oneshot",
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    item_id = "calendar_candidate:stick:cal-os"
    return tmp_path, item_id


def test_cook_writes_draft_mocked(oneshot_env):
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_oneshot", item_id=item_id, brand="stick")
    png_path = tmp_path / "out.png"
    meta_path = tmp_path / "out.meta.json"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(PNG_1x1)
    meta_path.write_text(json.dumps({"prompt_used": "wire", "model": "m", "cost_usd": 0.05}), encoding="utf-8")

    mock_gen = MagicMock()
    mock_gen.model = "ideogram/ideogram-3"
    mock_gen.provider = "krea"
    mock_gen.bytes = PNG_1x1
    mock_gen.saved_path = str(png_path)
    mock_gen.saved_sidecar_path = str(meta_path)
    mock_gen.prompt_used = 'Render "Hello world"'
    mock_gen.provider_job_id = None
    mock_gen.cost_usd = 0.05
    mock_gen.cost_source = "estimate"

    pick_calls = []

    def spy_pick(req, **kw):
        pick_calls.append(req)
        return {"model": "ideogram/ideogram-3", "provider": "krea", "reason": "test"}

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen) as gen_mock, patch(
        "_lib.creative_director.pick_model", side_effect=spy_pick
    ), patch("_lib.brand_overlay.overlay_logo_only", side_effect=lambda b, *a, **k: b):
        draft_assets.run()

    gen_mock.assert_called_once()
    assert gen_mock.call_args.kwargs["size"] == "1024x1280"
    assert gen_mock.call_args.kwargs.get("background_plate") is True
    assert pick_calls and pick_calls[0].get("typography") is True
    sidecars = list((tmp_path / "draft-assets").glob("draft-*.json"))
    assert sidecars
    sidecar = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert sidecar.get("action") == "draft_oneshot"
    assert sidecar.get("literal_text") == "Hello world"
    assert sidecar.get("image_size") == "1024x1280"


def test_krea_submit_sets_waiting(oneshot_env):
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_oneshot", item_id=item_id, brand="stick")
    mock_gen = MagicMock()
    mock_gen.model = "ideogram/ideogram-3"
    mock_gen.provider = "krea"
    mock_gen.bytes = b""
    mock_gen.provider_job_id = "krea-job-99"
    mock_gen.saved_path = None
    mock_gen.saved_sidecar_path = None

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen), patch(
        "_lib.creative_director.pick_model",
        return_value={"model": "ideogram/ideogram-3", "provider": "krea", "reason": "test"},
    ):
        draft_assets.run(brand="stick")

    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    assert queue["rows"][0]["status"] == "waiting"
    jobs = json.loads((tmp_path / "draft-assets" / "_image-jobs.json").read_text(encoding="utf-8"))
    assert jobs["jobs"][item_id]["job_id"] == "krea-job-99"


def test_krea_poll_finalizes_oneshot(oneshot_env):
    tmp_path, item_id = oneshot_env
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    (cal_dir / "stick.jsonl").write_text(
        json.dumps(
            {
                "calendar_id": "cal-os",
                "event_key": "cal-os",
                "status": "approved",
                "title": "Hello world",
                "event_start": "2026-10-01",
                "type": "content",
                "render_mode": "oneshot",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    from _lib.jobs.layer1._io import utc_now_iso

    jobs_doc = {
        "schema": "campaign-os/image-jobs/v1",
        "generated_at": utc_now_iso(),
        "jobs": {
            item_id: {
                "job_id": "j-os",
                "brand": "stick",
                "size": "1024x1280",
                "est_usd": 0.04,
                "submitted_at": utc_now_iso(),
                "last_status": "running",
                "polls": 0,
                "retry_count": 0,
            }
        },
    }
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "draft-assets" / "_image-jobs.json").write_text(json.dumps(jobs_doc), encoding="utf-8")
    queue = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-25T00:00:00Z",
        "rows": [
            {
                "id": "wait-os",
                "layer": "L5",
                "agent": "cos-image",
                "brand": "stick",
                "action": "draft_oneshot",
                "payload_ref": f"inbox/{item_id}",
                "status": "waiting",
            }
        ],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(queue), encoding="utf-8")
    png = tmp_path / "draft-assets" / "images" / "stick" / "images" / "krea-stick-j-os.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(PNG_1x1)

    from _lib.jobs.layer5 import krea_poll_draft_images

    with patch("_lib.brand_overlay.overlay_logo_only", side_effect=lambda b, *a, **k: b):
        krea_poll_draft_images.run(brand="stick")

    sidecars = list((tmp_path / "draft-assets").glob("draft-*.json"))
    assert sidecars
    sidecar = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert sidecar.get("action") == "draft_oneshot"
    assert sidecar.get("literal_text") == "Hello world"
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["status"] == "done"
