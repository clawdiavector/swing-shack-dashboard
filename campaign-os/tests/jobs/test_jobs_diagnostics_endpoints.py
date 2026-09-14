"""t40 — /api/jobs/failures and /api/jobs/diagnostics/<run_id>."""

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
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    client = app_module.app.test_client()
    return client, app_module, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_failures_and_diagnostics_require_auth(job_app):
    client, _, _ = job_app
    assert client.get("/api/jobs/failures").status_code == 401
    assert client.get("/api/jobs/diagnostics/abc").status_code == 401


def test_failures_excludes_best_effort(job_app):
    client, app_module, tmp_path = job_app
    from _lib.jobs.registry import register
    from _lib.jobs.spec import JobSpec

    register(
        JobSpec(
            name="golf_news",
            fn=lambda: {"ok": False, "error": "rss down"},
            every_seconds=86400,
            best_effort=True,
            criticality="LOW",
            writes=("golf-news.json",),
        )
    )
    register(
        JobSpec(
            name="ga4_report",
            fn=lambda: {"ok": False, "error": "invalid_grant"},
            every_seconds=86400,
            best_effort=False,
            criticality="MEDIUM",
            credentials=("GA4_PROPERTY_ID",),
            writes=("ga4-report.json",),
        )
    )

    client.post("/api/jobs/run/golf_news", headers=_auth())
    client.post("/api/jobs/run/ga4_report", headers=_auth())

    resp = client.get("/api/jobs/failures", headers=_auth())
    assert resp.status_code == 200
    body = resp.get_json()
    jobs = {row["job"] for row in body.get("failures", body if isinstance(body, list) else [])}
    if isinstance(body, dict) and "failures" in body:
        rows = body["failures"]
    else:
        rows = body
    names = {r["job"] for r in rows}
    assert "golf_news" not in names
    assert "ga4_report" in names


def test_diagnostics_traversal_404(job_app):
    client, _, _ = job_app
    resp = client.get(
        "/api/jobs/diagnostics/..%2f..%2fetc%2fpasswd",
        headers=_auth(),
    )
    assert resp.status_code == 404


def test_diagnostics_unknown_404(job_app):
    client, _, _ = job_app
    resp = client.get("/api/jobs/diagnostics/nope-not-a-run", headers=_auth())
    assert resp.status_code == 404


def test_diagnostics_round_trip(job_app):
    client, _, tmp_path = job_app
    from _lib.jobs.registry import register
    from _lib.jobs.spec import JobSpec

    register(
        JobSpec(
            name="ga4_report",
            fn=lambda: {"ok": False, "error": "invalid_grant"},
            every_seconds=86400,
            credentials=("GA4_PROPERTY_ID",),
            writes=("ga4-report.json",),
        )
    )
    run = client.post("/api/jobs/run/ga4_report", headers=_auth()).get_json()
    run_id = run["run_id"]
    resp = client.get(f"/api/jobs/diagnostics/{run_id}", headers=_auth())
    assert resp.status_code == 200
    bundle = resp.get_json()
    assert bundle["schema"] == "campaign-os/diagnostic-bundle/v1"
    assert bundle["error_class"] == "auth"
    assert bundle["suggested_checks"]
