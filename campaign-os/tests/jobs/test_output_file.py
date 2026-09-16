"""Job output JSON read API (ops/jobs viewer)."""

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

    client = app_module.app.test_client()
    return client, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_output_requires_allowed_path(job_app):
    client, tmp_path = job_app
    (tmp_path / "secret.json").write_text('{"x":1}', encoding="utf-8")
    resp = client.get(
        "/api/jobs/output?job=ga4_report&path=secret.json",
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is False
    assert "not allowed" in (body.get("error") or "")


def test_output_reads_job_json(job_app):
    client, tmp_path = job_app
    (tmp_path / "ga4-metrics.json").write_text(
        json.dumps({"sessions": 42, "users": 10}),
        encoding="utf-8",
    )
    resp = client.get(
        "/api/jobs/output?job=ga4_report&path=ga4-metrics.json",
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    assert body.get("data", {}).get("sessions") == 42


def test_outputs_list_ga4(job_app):
    client, _ = job_app
    resp = client.get("/api/jobs/outputs?job=ga4_report", headers=_auth())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    paths = [f["path"] for f in body.get("files", [])]
    assert "ga4-metrics.json" in paths
