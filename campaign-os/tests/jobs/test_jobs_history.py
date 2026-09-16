"""History endpoint + extended status fields for /ops/jobs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def job_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    return app_module.app.test_client(), app_module, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_jobs_history_requires_auth(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    assert anon.get("/api/jobs/history").status_code == 401


def test_jobs_history_returns_finished_runs(job_app):
    client, _, _ = job_app
    client.post("/api/jobs/run/golf_news", headers=_auth())
    resp = client.get("/api/jobs/history?limit=5", headers=_auth())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("ok") is True
    runs = data.get("jobs", {}).get("golf_news", [])
    assert len(runs) >= 1
    assert runs[0].get("run_id")
    assert runs[0].get("finished") or runs[0].get("started")


def test_jobs_status_includes_schedule_and_last_run(job_app):
    client, _, _ = job_app
    client.post("/api/jobs/run/freshness_scan", headers=_auth())
    st = client.get("/api/jobs/status", headers=_auth()).get_json()
    row = next(j for j in st["jobs"] if j["name"] == "freshness_scan")
    assert "schedule" in row
    assert row["schedule"].get("cron_sast")
    assert row.get("last_run_at")
    assert row.get("last_triggered_by")
