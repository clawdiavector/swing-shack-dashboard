"""L2 watchdog heartbeat: POST /api/ops/watch/heartbeat + watch_verdict rollup."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def _auth():
    return {"Authorization": "Bearer test-cos-token"}


@pytest.fixture
def job_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-cos-token")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            sys.modules.pop(mod, None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import app as app_module  # noqa: E402

    app_module.COS_JOB_TOKEN = "test-cos-token"
    client = app_module.app.test_client()
    return client, app_module, tmp_path


def test_watch_heartbeat_bearer_ok(job_app):
    client, _, _ = job_app
    resp = client.post(
        "/api/ops/watch/heartbeat",
        headers=_auth(),
        json={"all_ok": True, "jobs_total": 10, "jobs_ok": 10},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["all_ok"] is True
    assert body["received_at"]


def test_watch_heartbeat_anon_401(job_app):
    client, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.post("/api/ops/watch/heartbeat", json={"all_ok": True})
    assert resp.status_code == 401


def test_layers_watch_verdict_from_heartbeat(job_app, tmp_path):
    client, _, tmp_path = job_app
    hb_dir = tmp_path / "ops"
    hb_dir.mkdir()
    recent = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    (hb_dir / "campaign-os-watch-heartbeat.json").write_text(
        json.dumps(
            {
                "schema": "campaign-os/watch-heartbeat/v1",
                "source": "campaign-os-watch",
                "all_ok": True,
                "jobs_total": 5,
                "jobs_ok": 5,
                "received_at": recent,
            }
        ),
        encoding="utf-8",
    )
    l2 = client.get("/api/ops/layers").get_json()["layers"]["L2"]
    assert l2["watch_verdict"] == "OK"
    assert l2["watch_age_s"] is not None
    assert l2["watch_age_s"] < 120


def test_layers_watch_verdict_failed_when_jobs_bad(job_app, tmp_path):
    client, _, tmp_path = job_app
    hb_dir = tmp_path / "ops"
    hb_dir.mkdir()
    recent = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    (hb_dir / "campaign-os-watch-heartbeat.json").write_text(
        json.dumps(
            {
                "all_ok": False,
                "jobs_total": 5,
                "jobs_ok": 3,
                "received_at": recent,
            }
        ),
        encoding="utf-8",
    )
    l2 = client.get("/api/ops/layers").get_json()["layers"]["L2"]
    assert l2["watch_verdict"] == "FAILED"


def test_derive_watch_verdict_stale():
    from _lib.ops_watch import derive_watch_verdict

    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).replace(microsecond=0)
    old_iso = old.isoformat().replace("+00:00", "Z")
    verdict, age = derive_watch_verdict({"received_at": old_iso, "all_ok": True})
    assert verdict == "LATE"
    assert age is not None
    assert age > 900
