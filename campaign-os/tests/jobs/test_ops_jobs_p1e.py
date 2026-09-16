"""t42 /ops/jobs session gate; t44 manual cooldown; t47 init once; t50 spend cap."""

from __future__ import annotations

import json
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
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "1.00")
    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("_lib.jobs")
            or mod == "_lib.llm_spend"
            or mod.startswith("_lib.llm_spend")
        ):
            del sys.modules[mod]
    import app as app_module
    from _lib.jobs import cooldown as cd

    cd.reset_for_tests()
    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True  # already ran at import; keep stable for spies
    client = app_module.app.test_client()
    return client, app_module, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_ops_jobs_page_requires_session(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/ops/jobs", follow_redirects=False)
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        loc = resp.headers.get("Location") or ""
        assert "/login" in loc


def test_ops_jobs_bearer_does_not_open_page(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/ops/jobs", headers=_auth(), follow_redirects=False)
    assert resp.status_code == 302


def test_ops_jobs_page_ok_with_session(job_app):
    client, _, _ = job_app
    resp = client.get("/ops/jobs")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Jobs" in body
    assert "/api/jobs/status" in body
    assert "/api/jobs/history" in body
    assert "Schedule at a glance" in body
    assert "script src=" not in body.lower()
    assert "<link rel=\"stylesheet\"" not in body.lower()


def test_ops_jobs_not_in_public_prefixes(job_app):
    _, app_module, _ = job_app
    pubs = getattr(app_module, "PUBLIC_ROUTE_PREFIXES", ())
    assert not any(p.startswith("/ops") for p in pubs)


def test_manual_run_sets_triggered_by_and_duration(job_app):
    client, app_module, tmp_path = job_app
    from _lib.jobs.registry import register
    from _lib.jobs.spec import JobSpec

    register(
        JobSpec(
            name="probe_manual",
            fn=lambda: {"ok": True},
            every_seconds=3600,
            criticality="LOW",
            writes=("probe-manual.json",),
        )
    )
    resp = client.post("/api/jobs/run/probe_manual?reason=manual", headers=_auth())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("triggered_by") == "manual"
    assert body.get("duration_s") is not None

    st = client.get("/api/jobs/status", headers=_auth()).get_json()
    row = next(j for j in st["jobs"] if j["name"] == "probe_manual")
    assert row.get("last_duration_s") is not None
    assert row.get("last_run_id")


def test_manual_cooldown_per_job(job_app):
    client, _, _ = job_app
    from _lib.jobs.registry import register
    from _lib.jobs.spec import JobSpec
    from _lib.jobs import cooldown as cd

    cd.reset_for_tests()
    register(
        JobSpec(
            name="cool_a",
            fn=lambda: {"ok": True},
            every_seconds=3600,
            criticality="LOW",
            writes=("cool-a.json",),
        )
    )
    register(
        JobSpec(
            name="cool_b",
            fn=lambda: {"ok": True},
            every_seconds=3600,
            criticality="LOW",
            writes=("cool-b.json",),
        )
    )
    assert client.post("/api/jobs/run/cool_a?reason=manual", headers=_auth()).status_code == 200
    r2 = client.post("/api/jobs/run/cool_a?reason=manual", headers=_auth())
    assert r2.status_code == 429
    assert r2.headers.get("Retry-After")
    # Different job not locked
    assert client.post("/api/jobs/run/cool_b?reason=manual", headers=_auth()).status_code == 200


def test_init_repo_not_on_request_path(job_app, monkeypatch):
    client, app_module, _ = job_app
    calls = {"n": 0}

    def fake():
        calls["n"] += 1

    monkeypatch.setattr(app_module, "init_repo", fake)
    app_module._GIT_SYNC_DONE = True  # already done at import
    client.get("/api/ops/llm-spend")
    client.get("/api/health")
    assert calls["n"] == 0
    app_module._GIT_SYNC_DONE = False
    app_module._boot_git_sync()
    assert calls["n"] == 1
    app_module._boot_git_sync()
    assert calls["n"] == 1


def test_llm_spend_gate_requires_approval_and_cap(job_app):
    client, app_module, tmp_path = job_app
    from _lib import llm_spend

    resp = client.post(
        "/api/image/generate",
        json={"prompt": "test golf ball on tee", "brand_id": "swing-shack", "save": False},
    )
    assert resp.status_code == 403
    assert resp.get_json().get("code") == "approval_required"

    llm_spend.record(1.00, route="test", model="fixture")
    resp = client.post(
        "/api/image/generate",
        json={
            "prompt": "test golf ball on tee",
            "brand_id": "swing-shack",
            "save": False,
            "human_approved": True,
            "max_cost_usd": 0.50,
        },
    )
    assert resp.status_code == 402
    body = resp.get_json()
    assert body.get("code") == "spend_cap"


def test_llm_spend_fails_closed_on_corrupt(job_app, tmp_path):
    client, _, tmp_path = job_app
    day_dir = tmp_path / "llm-spend"
    day_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (day_dir / f"{day}.json").write_text("NOT-JSON{{{", encoding="utf-8")
    resp = client.post(
        "/api/image/generate",
        json={
            "prompt": "x",
            "brand_id": "swing-shack",
            "save": False,
            "human_approved": True,
        },
    )
    assert resp.status_code == 402


def test_llm_spend_endpoint_session(job_app):
    client, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    assert anon.get("/api/ops/llm-spend").status_code == 401
    resp = client.get("/api/ops/llm-spend")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "spent_usd" in body
    assert "cap_usd" in body


def test_runbook_includes_llm_spend(job_app):
    client, _, _ = job_app
    resp = client.get("/api/ops/runbook")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "llm_spend" in body
    assert body.get("ops_jobs_url") == "/ops/jobs"
