"""Agents get the whole API with COS_JOB_TOKEN; pages and wrong tokens stay closed."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TOKEN = "test-job-token-not-a-secret"


@pytest.fixture()
def job_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", TOKEN)
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import app as app_module

    app_module.COS_JOB_TOKEN = TOKEN
    app_module._GIT_SYNC_DONE = True
    return app_module.app.test_client(cos_anon=True), app_module


def _auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_session_only_api_route_accepts_bearer(job_app):
    client, _ = job_app
    resp = client.get("/api/plan/v1/stick/list", headers=_auth())
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


def test_route_level_session_check_accepts_bearer(job_app):
    client, _ = job_app
    resp = client.get("/api/photos/review?brand_id=stick", headers=_auth())
    assert resp.status_code == 200


def test_anon_still_401(job_app):
    client, _ = job_app
    resp = client.get("/api/plan/v1/stick/list")
    assert resp.status_code == 401


def test_wrong_token_still_401(job_app):
    client, _ = job_app
    resp = client.get("/api/plan/v1/stick/list", headers=_auth("wrong"))
    assert resp.status_code == 401


def test_bearer_does_not_open_pages(job_app):
    client, _ = job_app
    resp = client.get("/app/daily", headers=_auth())
    assert resp.status_code in (301, 302, 303, 307, 308)


def test_no_token_configured_no_bearer(job_app):
    client, app_module = job_app
    app_module.COS_JOB_TOKEN = ""
    resp = client.get("/api/plan/v1/stick/list", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401
