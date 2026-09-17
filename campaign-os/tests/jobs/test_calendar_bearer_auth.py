"""Calendar scout bearer auth — explicit paths + safe prefixes only."""

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
    client = app_module.app.test_client(cos_anon=True)
    return client, app_module


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_scout_health_anon_401(job_app):
    client, _ = job_app
    resp = client.get("/api/calendar/scout-health")
    assert resp.status_code == 401
    assert resp.get_json().get("ok") is False


def test_scout_health_bearer_200(job_app):
    client, _ = job_app
    resp = client.get("/api/calendar/scout-health", headers=_auth())
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


def test_scout_health_session_ok(job_app):
    _, app_module = job_app
    session = app_module.app.test_client()
    resp = session.get("/api/calendar/scout-health")
    assert resp.status_code == 200


def test_context_bearer_200(job_app):
    client, _ = job_app
    resp = client.get("/api/calendar/context/stick", headers=_auth())
    assert resp.status_code != 401


def test_v2_upsert_bearer_not_401(job_app):
    client, _ = job_app
    resp = client.post("/api/calendar/v2/upsert", headers=_auth(), json={})
    assert resp.status_code != 401


def test_watchlist_due_bearer_not_401(job_app):
    client, _ = job_app
    resp = client.get("/api/calendar/v2/watchlist-due?brand_id=stick", headers=_auth())
    assert resp.status_code != 401


def test_v3_scout_discover_bearer_not_401(job_app):
    client, _ = job_app
    resp = client.post("/api/calendar/v3/scout/discover/stick", headers=_auth(), json={})
    assert resp.status_code != 401


def test_v3_scout_evaluate_bearer_not_401(job_app):
    client, _ = job_app
    resp = client.post("/api/calendar/v3/scout/evaluate", headers=_auth(), json={})
    assert resp.status_code != 401


def test_scout_simulate_unavailable_still_session_only(job_app):
    client, _ = job_app
    resp = client.post("/api/calendar/v3/scout-simulate-unavailable", headers=_auth(), json={})
    assert resp.status_code == 401


def test_calendar_simulate_unavailable_still_session_only(job_app):
    client, _ = job_app
    resp = client.post("/api/calendar/scout-simulate-unavailable", headers=_auth(), json={})
    assert resp.status_code == 401


def test_bad_token_401(job_app):
    client, _ = job_app
    resp = client.get(
        "/api/calendar/scout-health",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


def test_v1_candidates_still_session_only(job_app):
    client, _ = job_app
    resp = client.post("/api/calendar/candidates", headers=_auth(), json={})
    assert resp.status_code == 401


def test_bearer_not_widened_to_sibling_calendar(job_app):
    client, _ = job_app
    resp = client.get("/api/calendar/path-debug", headers=_auth())
    assert resp.status_code == 401
