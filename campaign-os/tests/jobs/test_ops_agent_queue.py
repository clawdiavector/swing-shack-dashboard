"""Agent queue lifecycle — GET rows + POST mark-done with bearer auth."""

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
            or mod == "_lib.ops_agents"
            or mod == "_lib.ops_layers"
        ):
            del sys.modules[mod]
    import app as app_module
    from _lib.jobs import cooldown as cd

    cd.reset_for_tests()
    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    client = app_module.app.test_client()
    return client, app_module, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_queue_get_anon_401(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/api/ops/agent-queue")
    assert resp.status_code == 401


def test_queue_get_bearer_ok_empty(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/api/ops/agent-queue", headers=_auth())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    assert body.get("rows") == []
    assert body.get("counts", {}).get("pending") == 0


def test_queue_get_session_ok(job_app):
    client, _, _ = job_app
    resp = client.get("/api/ops/agent-queue")
    assert resp.status_code == 200


def test_queue_roundtrip(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    enq = anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "manual"},
    )
    assert enq.status_code == 200
    row_id = enq.get_json()["id"]

    listed = anon.get("/api/ops/agent-queue", headers=_auth()).get_json()
    row = next(r for r in listed["rows"] if r["id"] == row_id)
    assert row["status"] == "pending"

    done = anon.post(
        "/api/ops/agent-queue/mark-done",
        headers=_auth(),
        json={"id": row_id, "agent": "cos-scout"},
    )
    assert done.status_code == 200
    assert done.get_json().get("status") == "done"
    assert done.get_json().get("pending") == 0

    after = anon.get("/api/ops/agent-queue", headers=_auth()).get_json()
    row_after = next(r for r in after["rows"] if r["id"] == row_id)
    assert row_after["status"] == "done"


def test_queue_filter_by_agent(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "a"},
    )
    anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-triage", "brand": "stick", "reason": "b"},
    )
    body = anon.get("/api/ops/agent-queue?agent=cos-scout", headers=_auth()).get_json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["agent"] == "cos-scout"


def test_queue_filter_by_status(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    enq = anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "filter"},
    )
    row_id = enq.get_json()["id"]
    anon.post(
        "/api/ops/agent-queue/mark-done",
        headers=_auth(),
        json={"id": row_id, "agent": "cos-scout"},
    )
    pending = anon.get("/api/ops/agent-queue?status=pending", headers=_auth()).get_json()
    assert all(r["status"] == "pending" for r in pending["rows"])
    assert not any(r["id"] == row_id for r in pending["rows"])


def test_mark_done_idempotent(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    row_id = anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "idem"},
    ).get_json()["id"]
    first = anon.post(
        "/api/ops/agent-queue/mark-done",
        headers=_auth(),
        json={"id": row_id},
    )
    second = anon.post(
        "/api/ops/agent-queue/mark-done",
        headers=_auth(),
        json={"id": row_id},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json().get("status") == "done"
    assert second.get_json().get("pending") == 0


def test_mark_done_unknown_id_404(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.post(
        "/api/ops/agent-queue/mark-done",
        headers=_auth(),
        json={"id": "missing-row-id"},
    )
    assert resp.status_code == 404
    assert resp.get_json().get("ok") is False


def test_mark_done_agent_mismatch_403(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    row_id = anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "owner"},
    ).get_json()["id"]
    resp = anon.post(
        "/api/ops/agent-queue/mark-done",
        headers=_auth(),
        json={"id": row_id, "agent": "cos-triage"},
    )
    assert resp.status_code == 403


def test_mark_done_anon_401(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.post(
        "/api/ops/agent-queue/mark-done",
        json={"id": "any"},
    )
    assert resp.status_code == 401


def test_row_keys_exact(job_app):
    from _lib import ops_agents as ops_agents_mod

    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "keys"},
    )
    body = anon.get("/api/ops/agent-queue", headers=_auth()).get_json()
    for row in body["rows"]:
        assert set(row.keys()) == ops_agents_mod.QUEUE_ROW_KEYS


def test_done_row_survives_queue_writer(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    row_id = anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "survive"},
    ).get_json()["id"]
    anon.post(
        "/api/ops/agent-queue/mark-done",
        headers=_auth(),
        json={"id": row_id},
    )
    from _lib.jobs.layer2 import agent_queue_writer

    agent_queue_writer.run()
    body = anon.get("/api/ops/agent-queue", headers=_auth()).get_json()
    row = next(r for r in body["rows"] if r["id"] == row_id)
    assert row["status"] == "done"


def test_done_retention_cap(job_app, tmp_path):
    from _lib import ops_agents as ops_agents_mod

    rows = []
    for idx in range(ops_agents_mod.DONE_RETENTION_MAX + 5):
        rows.append(
            {
                "id": f"manual-stick-cos-scout-retention-{idx:04d}",
                "layer": "L3",
                "agent": "cos-scout",
                "brand": "stick",
                "action": "enqueue",
                "payload_ref": "ops-agents/enqueue#retention",
                "status": "done",
            }
        )
    rows.append(
        {
            "id": "manual-stick-cos-scout-retention-pending",
            "layer": "L3",
            "agent": "cos-scout",
            "brand": "stick",
            "action": "enqueue",
            "payload_ref": "ops-agents/enqueue#retention",
            "status": "pending",
        }
    )
    doc = {
        "schema": ops_agents_mod.QUEUE_SCHEMA,
        "generated_at": "2026-09-17T10:00:00Z",
        "rows": rows,
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(doc), encoding="utf-8")

    ops_agents_mod.mark_row_done(tmp_path, "manual-stick-cos-scout-retention-pending")
    after = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    done_rows = [r for r in after["rows"] if r.get("status") == "done"]
    assert len(done_rows) <= ops_agents_mod.DONE_RETENTION_MAX


def test_queue_depth_unchanged_by_mark_done_semantics(job_app):
    client, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    before = client.get("/api/ops/layers").get_json()["layers"]["L2"]["queue_depth"]
    row_id = anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "depth"},
    ).get_json()["id"]
    mid = client.get("/api/ops/layers").get_json()["layers"]["L2"]["queue_depth"]
    assert mid == before + 1
    anon.post(
        "/api/ops/agent-queue/mark-done",
        headers=_auth(),
        json={"id": row_id},
    )
    after = client.get("/api/ops/layers").get_json()["layers"]["L2"]["queue_depth"]
    assert after == before
