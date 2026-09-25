"""L5 krea_poll_draft_images — poll waiting rows (mocked Krea, no network)."""

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

from tests.jobs.test_layer5_create import _purge_modules, _seed_brands  # noqa: E402

PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture()
def poll_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "10.00")
    _purge_modules()
    _seed_brands(tmp_path, brand="stick", campaign_id="camp-stick")
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": "cal-1",
        "event_key": "cal-1",
        "status": "approved",
        "title": "Demo",
        "event_start": "2026-10-01",
        "type": "content",
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    item_id = "calendar_candidate:stick:cal-1"
    img_dir = tmp_path / "draft-assets" / "images" / "stick" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    meta_path = img_dir / "gen-stick-1.png.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "provider_job_id": "krea-job-1",
                "brand_id": "stick",
                "size": "1024x1024",
                "cost_estimate_usd": 0.04,
                "bytes_size": 0,
            }
        ),
        encoding="utf-8",
    )
    queue = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-25T00:00:00Z",
        "rows": [
            {
                "id": "wait-1",
                "layer": "L5",
                "agent": "cos-image",
                "brand": "stick",
                "action": "draft_image",
                "payload_ref": f"inbox/{item_id}",
                "status": "waiting",
                "provider_job_id": "krea-job-1",
                "router_sidecar_path": str(meta_path),
                "image_size": "1024x1024",
                "image_cost_estimate_usd": 0.04,
            }
        ],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(queue), encoding="utf-8")
    return tmp_path, item_id, meta_path


def test_krea_poll_registered():
    from _lib.jobs.registry import JOBS

    assert "krea_poll_draft_images" in JOBS
    assert JOBS["krea_poll_draft_images"].upstream == ("draft_assets",)
    assert JOBS["asset_qc"].upstream == ("krea_poll_draft_images",)


def test_poll_completed_writes_png_and_records_spend(poll_env):
    tmp_path, item_id, meta_path = poll_env
    from _lib import llm_spend
    from _lib.jobs.layer5 import krea_poll_draft_images

    before = llm_spend.status().get("calls") or 0
    completed_payload = json.dumps(
        {"status": "completed", "result": {"urls": ["https://example.test/out.png"]}}
    )
    mock_resp = {"content": [{"text": completed_payload}]}

    def fake_urlopen(url, timeout=60):  # noqa: ARG001
        mock = MagicMock()
        mock.read.return_value = PNG_1x1
        mock.headers = {"Content-Type": "image/png"}
        mock.__enter__ = lambda s: mock
        mock.__exit__ = lambda *a: None
        return mock

    with patch("_lib.krea_mcp.get_job", return_value=mock_resp):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = krea_poll_draft_images.run(brand="stick")

    assert result.get("ok") is True
    assert result.get("completed") == 1
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["status"] == "done"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta.get("bytes_size", 0) > 0
    assert (llm_spend.status().get("calls") or 0) > before
    drafts = list((tmp_path / "draft-assets").glob("*.json"))
    assert any("cal-1" in p.read_text() or item_id in p.read_text() for p in drafts)


def test_poll_still_running_no_spend(poll_env):
    tmp_path, _item_id, _meta_path = poll_env
    from _lib import llm_spend
    from _lib.jobs.layer5 import krea_poll_draft_images

    before = llm_spend.status().get("calls") or 0
    running_payload = json.dumps({"status": "running"})
    mock_resp = {"content": [{"text": running_payload}]}

    with patch("_lib.krea_mcp.get_job", return_value=mock_resp):
        result = krea_poll_draft_images.run(brand="stick")

    assert result.get("still_waiting") == 1
    assert (llm_spend.status().get("calls") or 0) == before
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["status"] == "waiting"


def test_poll_failed_sets_pending(poll_env):
    tmp_path, _item_id, _meta_path = poll_env
    from _lib.jobs.layer5 import krea_poll_draft_images

    failed_payload = json.dumps({"status": "failed", "error": "upstream error"})
    mock_resp = {"content": [{"text": failed_payload}]}

    with patch("_lib.krea_mcp.get_job", return_value=mock_resp):
        result = krea_poll_draft_images.run(brand="stick")

    assert result.get("failed") == 1
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["status"] == "pending"
    assert rows[0].get("krea_poll_failed") is True
