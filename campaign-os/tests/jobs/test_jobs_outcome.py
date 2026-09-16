"""Outcome endpoint + result_summary ledger fields."""

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
    app_module._GIT_SYNC_DONE = True
    return app_module.app.test_client(), app_module, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_outcome_requires_job_param(job_app):
    client, _, _ = job_app
    resp = client.get("/api/jobs/outcome", headers=_auth())
    assert resp.status_code == 400


def test_outcome_after_run(job_app):
    client, _, tmp_path = job_app
    client.post("/api/jobs/run/freshness_scan", headers=_auth())
    resp = client.get("/api/jobs/outcome?job=freshness_scan", headers=_auth())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("ok") is True
    assert data.get("job") == "freshness_scan"
    assert isinstance(data.get("lines"), list)
    assert data.get("headline")

    ledger = tmp_path / "job-runs.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    finished = [r for r in rows if r.get("phase") == "finished"]
    assert finished
    assert "result_summary" in finished[-1]
