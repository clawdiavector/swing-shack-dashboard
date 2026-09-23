"""L5 retry_failed_images — auto enqueue, retry reset, cap, holiday skip."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import _purge_modules, _seed_brands  # noqa: E402


@pytest.fixture()
def retry_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "1.00")
    _purge_modules()
    _seed_brands(tmp_path, brand="swing-shack", campaign_id="camp-ss")
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-09-24T00:00:00Z", "rows": []}),
        encoding="utf-8",
    )
    return tmp_path, cal_dir


def _write_moment(cal_dir: Path, record: dict) -> None:
    brand = record["brand_id"]
    path = cal_dir / f"{brand}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def test_retry_failed_images_registered(retry_env):
    tmp_path, _ = retry_env
    del tmp_path
    from _lib.jobs.registry import JOBS

    assert "retry_failed_images" in JOBS
    assert JOBS["draft_assets"].upstream == ("retry_failed_images",)


def test_skip_holiday_inject_moment(retry_env):
    tmp_path, cal_dir = retry_env
    fixed = date(2026, 9, 24)
    _write_moment(
        cal_dir,
        {
            "calendar_id": "cal-holiday-heritage",
            "brand_id": "swing-shack",
            "type": "moment",
            "status": "approved",
            "title": "Heritage Day",
            "event_date": "2026-09-24",
            "source_type": "deterministic",
            "created_by": "holiday_inject",
            "revision": 1,
        },
    )
    _write_moment(
        cal_dir,
        {
            "calendar_id": "cal-operator-fitting",
            "brand_id": "swing-shack",
            "type": "moment",
            "status": "approved",
            "title": "Book fitting",
            "event_date": "2026-09-24",
            "source_type": "operator",
            "primary_channel": "instagram",
            "revision": 1,
        },
    )
    from _lib.jobs.layer5 import retry_failed_images

    with patch.object(retry_failed_images, "_today_sast", return_value=fixed):
        result = retry_failed_images.run(brand="swing-shack")
    assert result.get("ok") is True
    assert result.get("enqueued") == 2
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    refs = {r.get("payload_ref") for r in queue.get("rows") or []}
    assert any("cal-operator-fitting" in (ref or "") for ref in refs)
    assert not any("cal-holiday-heritage" in (ref or "") for ref in refs)


def test_retry_empty_done_image_row(retry_env):
    tmp_path, cal_dir = retry_env
    fixed = date(2026, 9, 24)
    item_id = "calendar_candidate:swing-shack:cal-op-1"
    _write_moment(
        cal_dir,
        {
            "calendar_id": "cal-op-1",
            "brand_id": "swing-shack",
            "type": "moment",
            "status": "approved",
            "title": "Operator post",
            "event_date": "2026-09-24",
            "source_type": "operator",
            "primary_channel": "instagram",
            "revision": 1,
        },
    )
    queue = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-24T00:00:00Z",
        "rows": [
            {
                "id": "done-image-empty",
                "layer": "L5",
                "agent": "cos-image",
                "brand": "swing-shack",
                "action": "draft_image",
                "payload_ref": f"inbox/{item_id}",
                "status": "done",
            }
        ],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(queue), encoding="utf-8")
    from _lib.jobs.layer5 import retry_failed_images

    with patch.object(retry_failed_images, "_today_sast", return_value=fixed):
        result = retry_failed_images.run(brand="swing-shack")
    assert result.get("ok") is True
    assert result.get("reset_pending") == 1
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    img = next(r for r in rows if r.get("action") == "draft_image")
    assert img.get("status") == "pending"
    assert img.get("image_retry_count") == 1


def test_max_three_retries(retry_env):
    tmp_path, _ = retry_env
    item_id = "calendar_candidate:swing-shack:cal-max"
    queue = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-24T00:00:00Z",
        "rows": [
            {
                "id": "done-image-maxed",
                "layer": "L5",
                "agent": "cos-image",
                "brand": "swing-shack",
                "action": "draft_image",
                "payload_ref": f"inbox/{item_id}",
                "status": "done",
                "image_retry_count": 3,
            }
        ],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(queue), encoding="utf-8")
    from _lib.jobs.layer5 import retry_failed_images

    result = retry_failed_images.run(brand="swing-shack")
    assert result.get("reset_pending") == 0
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0].get("status") == "done"


def test_spend_cap_no_enqueue(retry_env, monkeypatch):
    tmp_path, cal_dir = retry_env
    fixed = date(2026, 9, 24)
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "0.001")
    _purge_modules()
    _write_moment(
        cal_dir,
        {
            "calendar_id": "cal-cap-block",
            "brand_id": "swing-shack",
            "type": "moment",
            "status": "approved",
            "title": "Cap blocked",
            "event_date": "2026-09-24",
            "source_type": "operator",
            "primary_channel": "instagram",
            "revision": 1,
        },
    )
    from _lib.jobs.layer5 import retry_failed_images

    with patch.object(retry_failed_images, "_today_sast", return_value=fixed):
        result = retry_failed_images.run(brand="swing-shack")
    assert result.get("ok") is True
    assert result.get("enqueued") == 0
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    assert queue.get("rows") == []
