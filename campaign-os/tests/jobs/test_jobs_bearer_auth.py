"""t31 — bearer COS_JOB_TOKEN auth on POST /api/jobs/run/<name> (amendment t25_scope).

Session-cookie auth is covered elsewhere; this pins the bearer path.
"""

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
    # cos_anon: P1a conftest auto-logs in test_client(); dual-auth job
    # endpoints accept session OR bearer, so rejection cases need anon.
    client = app_module.app.test_client(cos_anon=True)
    return client, app_module


def _stub_golf(app_module):
    from _lib.jobs.registry import register
    from _lib.jobs.spec import JobSpec

    def _fn():
        return {"ok": True, "rows": 3}

    register(
        JobSpec(
            name="golf_news",
            fn=_fn,
            every_seconds=86400,
            best_effort=True,
            criticality="LOW",
            writes=("golf-news.json",),
        )
    )


def test_jobs_run_bearer_ok(job_app):
    client, app_module = job_app
    _stub_golf(app_module)
    resp = client.post(
        "/api/jobs/run/golf_news",
        headers={"Authorization": "Bearer test-job-token-not-a-secret"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("job") == "golf_news"
    assert body.get("status") == "OK"
    assert body.get("rows") == 3


def test_jobs_run_bearer_rejects_bad_token(job_app):
    client, _ = job_app
    resp = client.post(
        "/api/jobs/run/golf_news",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401
    assert resp.get_json().get("ok") is False


def test_jobs_run_unauthenticated_rejected(job_app):
    client, _ = job_app
    resp = client.post("/api/jobs/run/golf_news")
    assert resp.status_code == 401
