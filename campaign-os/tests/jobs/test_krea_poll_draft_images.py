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

from tests.jobs.test_layer5_create import _purge_modules, _seed_brands, l5_app  # noqa: E402

PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _seed_waiting(tmp_path: Path, *, brand: str = "swing-shack", job_id: str = "j1") -> str:
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
    (cal_dir / f"{brand}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    item_id = f"calendar_candidate:{brand}:cal-1"
    jobs_doc = {
        "schema": "campaign-os/image-jobs/v1",
        "generated_at": "2026-09-25T00:00:00Z",
        "jobs": {
            item_id: {
                "job_id": job_id,
                "brand": brand,
                "size": "1024x1024",
                "est_usd": 0.04,
                "submitted_at": "2026-09-25T07:15:04Z",
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
                "id": "wait-1",
                "layer": "L5",
                "agent": "cos-image",
                "brand": brand,
                "action": "draft_image",
                "payload_ref": f"inbox/{item_id}",
                "status": "waiting",
            }
        ],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(queue), encoding="utf-8")
    return item_id


@pytest.fixture()
def poll_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "10.00")
    _purge_modules()
    _seed_brands(tmp_path, brand="swing-shack", campaign_id="camp-ss")
    return tmp_path


def test_krea_poll_registered():
    from _lib.jobs.registry import JOBS
    from _lib.jobs.descriptions import description_for

    assert "krea_poll_draft_images" in JOBS
    assert JOBS["krea_poll_draft_images"].upstream == ("draft_assets",)
    assert JOBS["asset_qc"].upstream == ("krea_poll_draft_images",)
    assert description_for("krea_poll_draft_images")["summary"]


def test_poll_completed_writes_png_and_draft(poll_env):
    tmp_path = poll_env
    _seed_waiting(tmp_path, job_id="j1")
    from _lib.jobs.layer5 import krea_poll_draft_images

    completed_payload = json.dumps({"status": "completed", "result": {"urls": ["https://example.test/out.png"]}})
    mock_resp = {"content": [{"text": completed_payload}]}

    def fake_urlopen(url, timeout=30):  # noqa: ARG001
        mock = MagicMock()
        mock.read.return_value = PNG_1x1
        mock.__enter__ = lambda s: mock
        mock.__exit__ = lambda *a: None
        return mock

    with patch("_lib.krea_mcp.get_job", return_value=mock_resp):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = krea_poll_draft_images.run(brand="swing-shack")

    assert result.get("completed") == 1
    png = tmp_path / "draft-assets" / "images" / "swing-shack" / "images" / "krea-swing-shack-j1.png"
    assert png.is_file() and png.stat().st_size > 0
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["status"] == "done"
    assert not (tmp_path / "draft-assets" / "_image-jobs.json").read_text().count("j1")


def test_polled_png_is_served_by_brand_images(l5_app, poll_env):
    tmp_path = poll_env
    _seed_waiting(tmp_path, job_id="j1")
    from _lib.jobs.layer5 import krea_poll_draft_images

    completed_payload = json.dumps({"status": "completed", "result": {"urls": ["https://example.test/out.png"]}})
    mock_resp = {"content": [{"text": completed_payload}]}

    def fake_urlopen(url, timeout=30):  # noqa: ARG001
        mock = MagicMock()
        mock.read.return_value = PNG_1x1
        mock.__enter__ = lambda s: mock
        mock.__exit__ = lambda *a: None
        return mock

    client, _, _ = l5_app
    with patch("_lib.krea_mcp.get_job", return_value=mock_resp):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            krea_poll_draft_images.run(brand="swing-shack")

    resp = client.get("/brand-images/swing-shack/krea-swing-shack-j1.png")
    assert resp.status_code == 200


def test_poll_still_running_no_spend(poll_env):
    tmp_path = poll_env
    _seed_waiting(tmp_path)
    from _lib import llm_spend
    from _lib.jobs.layer5 import krea_poll_draft_images

    before = llm_spend.today_spend()["calls"]
    running_payload = json.dumps({"status": "running"})
    with patch("_lib.krea_mcp.get_job", return_value={"content": [{"text": running_payload}]}):
        result = krea_poll_draft_images.run(brand="swing-shack")
    assert result.get("still_running") == 1
    assert llm_spend.today_spend()["calls"] == before
    jobs = json.loads((tmp_path / "draft-assets" / "_image-jobs.json").read_text(encoding="utf-8"))
    item_id = "calendar_candidate:swing-shack:cal-1"
    assert jobs["jobs"][item_id]["polls"] == 1


def test_poll_records_spend_exactly_once(poll_env):
    tmp_path = poll_env
    _seed_waiting(tmp_path, job_id="j1")
    from _lib import llm_spend
    from _lib.jobs.layer5 import krea_poll_draft_images

    completed_payload = json.dumps({"status": "completed", "result": {"urls": ["https://x/y.png"]}})

    def fake_urlopen(url, timeout=30):  # noqa: ARG001
        mock = MagicMock()
        mock.read.return_value = PNG_1x1
        mock.__enter__ = lambda s: mock
        mock.__exit__ = lambda *a: None
        return mock

    with patch("_lib.krea_mcp.get_job", return_value={"content": [{"text": completed_payload}]}):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            krea_poll_draft_images.run(brand="swing-shack")
            krea_poll_draft_images.run(brand="swing-shack")
    assert llm_spend.today_spend()["calls"] == 1


def test_poll_failed_sets_pending(poll_env):
    tmp_path = poll_env
    _seed_waiting(tmp_path)
    from _lib.jobs.layer5 import krea_poll_draft_images

    failed_payload = json.dumps({"status": "failed", "error": "upstream error"})
    with patch("_lib.krea_mcp.get_job", return_value={"content": [{"text": failed_payload}]}):
        result = krea_poll_draft_images.run(brand="swing-shack")
    assert result.get("failed") == 1
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["status"] == "pending"


def test_cron_step_order():
    repo = CAMPAIGN_OS.parent
    text = (repo / ".github" / "workflows" / "layer2-7-daily-cron.yml").read_text(encoding="utf-8")
    names = []
    for line in text.splitlines():
        if line.strip().startswith("- name: L5 —"):
            names.append(line.split("L5 —", 1)[1].strip())
    assert names.index("retry_failed_images") < names.index("draft_assets")
    assert names.index("draft_assets") < names.index("krea_poll_draft_images")
    assert names.index("krea_poll_draft_images") < names.index("asset_qc")


def test_poller_ignores_spend_cap(poll_env, monkeypatch):
    tmp_path = poll_env
    _seed_waiting(tmp_path, job_id="j1")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "0.001")
    _purge_modules()
    from _lib import llm_spend
    from _lib.jobs.layer5 import krea_poll_draft_images

    llm_spend.record(0.01, route="seed", kind="text")
    completed_payload = json.dumps({"status": "completed", "result": {"urls": ["https://x/y.png"]}})

    def fake_urlopen(url, timeout=30):  # noqa: ARG001
        mock = MagicMock()
        mock.read.return_value = PNG_1x1
        mock.__enter__ = lambda s: mock
        mock.__exit__ = lambda *a: None
        return mock

    with patch("_lib.krea_mcp.get_job", return_value={"content": [{"text": completed_payload}]}):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = krea_poll_draft_images.run(brand="swing-shack")
    assert result.get("completed") == 1
