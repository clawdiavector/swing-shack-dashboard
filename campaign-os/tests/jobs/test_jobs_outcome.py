"""Outcome endpoint + descriptions on status."""

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


def test_jobs_outcome_requires_auth(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    assert anon.get("/api/jobs/outcome?job=golf_news").status_code == 401


def test_jobs_outcome_after_run(job_app):
    client, _, tmp_path = job_app
    run = client.post("/api/jobs/run/freshness_scan", headers=_auth()).get_json()
    resp = client.get(
        f"/api/jobs/outcome?job=freshness_scan&run_id={run['run_id']}",
        headers=_auth(),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("ok") is True
    assert data.get("run_id") == run["run_id"]
    assert isinstance(data.get("lines"), list)
    assert data.get("headline")


def test_status_includes_info(job_app):
    client, _, _ = job_app
    st = client.get("/api/jobs/status", headers=_auth()).get_json()
    row = next(j for j in st["jobs"] if j["name"] == "meta_refresh")
    assert row["info"].get("title")
    assert row["info"].get("summary")
