"""Classic ops-jobs brand-honest verdict chip + status payload."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
OPS_HTML = CAMPAIGN_OS / "ops-jobs.html"

if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _html() -> str:
    return OPS_HTML.read_text(encoding="utf-8")


def test_ops_html_defines_job_verdict_for_filter():
    text = _html()
    assert "function jobVerdictForFilter" in text
    assert re.search(r"function jobCard\([^)]*\)[\s\S]*jobVerdictForFilter\(j\)", text)
    assert re.search(r"function renderSummary\([^)]*\)[\s\S]*jobVerdictForFilter\(j\)", text)
    assert "const v = j.verdict" not in text
    assert "filterJobsForBrand" not in text
    assert "&all=1" not in text
    assert "jobMeta.brands" in text and "runNow" in text


@pytest.fixture()
def job_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "1.00")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import app as app_module
    from _lib.jobs import cooldown as cd

    cd.reset_for_tests()
    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    client = app_module.app.test_client()
    return client, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_status_payload_carries_per_brand_verdicts(job_app, monkeypatch):
    client, tmp_path = job_app
    from _lib.jobs import runner
    from _lib.jobs.registry import register
    from _lib.jobs.spec import JobSpec

    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(runner, "_utc_now", lambda: now)

    name = "brand_chip_probe"
    register(
        JobSpec(
            name=name,
            fn=lambda: {"ok": True},
            every_seconds=43200,
            timeout_seconds=60,
            brand_mode="per_brand",
            brands=("swing-shack", "stick"),
            writes=("brand-chip-probe.json",),
        )
    )
    stuck_started = (now - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok_finished = "2026-09-23T10:00:00Z"
    rows = [
        {
            "job": name,
            "brand": "swing-shack",
            "run_id": "ss-orphan",
            "phase": "started",
            "started": stuck_started,
            "triggered_by": "schedule",
        },
        {
            "job": name,
            "brand": "stick",
            "run_id": "stick-ok",
            "phase": "finished",
            "started": ok_finished,
            "finished": ok_finished,
            "status": "OK",
            "triggered_by": "schedule",
        },
    ]
    (tmp_path / "job-runs.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    st = client.get("/api/jobs/status", headers=_auth()).get_json()
    job = next(j for j in st["jobs"] if j["name"] == name)
    by_brand = {b["brand"]: b["verdict"] for b in job.get("brands") or []}
    assert by_brand.get("stick") == "OK"
    assert by_brand.get("swing-shack") == "STUCK"
    assert job["verdict"] == "STUCK"
