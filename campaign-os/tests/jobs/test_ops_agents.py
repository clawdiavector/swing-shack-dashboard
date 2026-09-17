"""L3 ops agents: heartbeat, roster GET, enqueue, auth, persistence."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
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
            or mod == "_lib.ops_layers"
            or mod == "_lib.ops_agents"
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


def _heartbeat_body(**overrides):
    body = {
        "id": "cos-scout",
        "profile": "cos-scout",
        "kind": "hermes",
        "layer": "L3",
        "status": "OK",
        "action": "upserted 3 candidates for stick",
        "writes": ["calendar/stick"],
        "skill": "campaign-calendar-scout",
    }
    body.update(overrides)
    return body


def test_agents_get_anon_401(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/api/ops/agents")
    assert resp.status_code == 401
    assert resp.get_json().get("ok") is False


def test_heartbeat_anon_401(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.post("/api/ops/agents/heartbeat", json=_heartbeat_body())
    assert resp.status_code == 401


def test_enqueue_anon_401(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.post(
        "/api/ops/agents/enqueue",
        json={"agent": "cos-scout", "brand": "stick", "reason": "manual"},
    )
    assert resp.status_code == 401


def test_agents_bearer_ok(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/api/ops/agents", headers=_auth())
    assert resp.status_code == 200


def test_heartbeat_bearer_ok(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.post("/api/ops/agents/heartbeat", headers=_auth(), json=_heartbeat_body())
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


def test_enqueue_bearer_ok(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "stick", "reason": "manual"},
    )
    assert resp.status_code == 200


def test_agents_session_ok(job_app):
    client, _, _ = job_app
    resp = client.get("/api/ops/agents")
    assert resp.status_code == 200


def test_bearer_not_widened(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    for path in ("/api/ops/errors", "/api/ops/runbook", "/api/ops/llm-spend"):
        assert anon.get(path, headers=_auth()).status_code == 401


def test_ops_page_still_session_only(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/ops", headers=_auth(), follow_redirects=False)
    assert resp.status_code == 302


def test_heartbeat_roundtrip(job_app):
    client, _, _ = job_app
    client.post("/api/ops/agents/heartbeat", json=_heartbeat_body())
    body = client.get("/api/ops/agents").get_json()
    scout = next(a for a in body["agents"] if a["id"] == "cos-scout")
    assert scout["last_action"] == "upserted 3 candidates for stick"
    assert scout["last_writes"] == ["calendar/stick"]
    assert scout["last_status"] == "OK"
    assert scout["last_heartbeat_at"]


def test_heartbeat_writes_expected_file(job_app, tmp_path):
    client, _, tmp_path = job_app
    client.post("/api/ops/agents/heartbeat", json=_heartbeat_body())
    path = tmp_path / "ops-agents" / "cos-scout.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == "cos-scout"


def test_heartbeat_is_idempotent_overwrite(job_app, tmp_path):
    client, _, tmp_path = job_app
    client.post("/api/ops/agents/heartbeat", json=_heartbeat_body(action="first"))
    client.post("/api/ops/agents/heartbeat", json=_heartbeat_body(action="second"))
    files = list((tmp_path / "ops-agents").glob("cos-scout.json"))
    assert len(files) == 1
    scout = next(
        a for a in client.get("/api/ops/agents").get_json()["agents"] if a["id"] == "cos-scout"
    )
    assert scout["last_action"] == "second"


def test_roster_seeds_never_agents(job_app):
    client, _, _ = job_app
    body = client.get("/api/ops/agents").get_json()
    ids = {a["id"] for a in body["agents"]}
    assert "cos-scout" in ids
    assert "cos-foreman" in ids
    for agent in body["agents"]:
        assert agent["last_status"] == "NEVER"
        assert agent["last_heartbeat_at"] is None


@pytest.mark.parametrize("bad_id", ["../etc/passwd", "a/b", "", "a" * 200])
def test_unknown_agent_id_rejected(job_app, tmp_path, bad_id):
    client, _, tmp_path = job_app
    resp = client.post("/api/ops/agents/heartbeat", json=_heartbeat_body(id=bad_id))
    assert resp.status_code == 400
    assert not any(tmp_path.rglob("*.json"))


def test_unknown_agent_still_listed(job_app):
    client, _, _ = job_app
    client.post(
        "/api/ops/agents/heartbeat",
        json=_heartbeat_body(id="cos-unknown-test", kind="hermes"),
    )
    body = client.get("/api/ops/agents").get_json()
    row = next(a for a in body["agents"] if a["id"] == "cos-unknown-test")
    assert row["kind"] == "hermes"


def test_late_derivation(job_app, tmp_path):
    from _lib import ops_agents as ops_agents_mod

    roster_dir = tmp_path / "ops-agents"
    roster_dir.mkdir()
    old = (datetime.now(timezone.utc) - timedelta(days=3)).replace(microsecond=0)
    old_iso = old.isoformat().replace("+00:00", "Z")
    (roster_dir / "cos-reactive.json").write_text(
        json.dumps(
            {
                "schema": ops_agents_mod.SCHEMA,
                "id": "cos-reactive",
                "profile": "cos-reactive",
                "kind": "hermes",
                "layer": "L3",
                "status": "OK",
                "action": "watch",
                "writes": [],
                "skill": "",
                "enabled": False,
                "last_heartbeat_at": old_iso,
                "received_at": old_iso,
            }
        ),
        encoding="utf-8",
    )
    row = next(a for a in ops_agents_mod.read_roster(roster_dir) if a["id"] == "cos-reactive")
    assert row["last_status"] == "LATE"


def test_oneshot_never_late(job_app, tmp_path):
    from _lib import ops_agents as ops_agents_mod

    roster_dir = tmp_path / "ops-agents"
    roster_dir.mkdir()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).replace(microsecond=0)
    old_iso = old.isoformat().replace("+00:00", "Z")
    (roster_dir / "pi-score.json").write_text(
        json.dumps(
            {
                "schema": ops_agents_mod.SCHEMA,
                "id": "pi-score",
                "profile": "pi-score",
                "kind": "pi",
                "layer": "L3",
                "status": "OK",
                "action": "scored",
                "writes": [],
                "skill": "",
                "enabled": False,
                "last_heartbeat_at": old_iso,
                "received_at": old_iso,
            }
        ),
        encoding="utf-8",
    )
    row = next(a for a in ops_agents_mod.read_roster(roster_dir) if a["id"] == "pi-score")
    assert row["last_status"] != "LATE"


def test_enqueue_appends_queue_row(job_app, tmp_path):
    client, _, tmp_path = job_app
    client.post(
        "/api/ops/agents/enqueue",
        json={"agent": "cos-scout", "brand": "stick", "reason": "manual"},
    )
    doc = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    manual = [r for r in doc["rows"] if str(r["id"]).startswith("manual-")]
    assert len(manual) == 1
    assert set(manual[0].keys()) == {
        "id",
        "layer",
        "agent",
        "brand",
        "action",
        "payload_ref",
        "status",
    }
    assert manual[0]["status"] == "pending"


def test_enqueue_row_survives_queue_writer(job_app, tmp_path):
    client, _, tmp_path = job_app
    client.post(
        "/api/ops/agents/enqueue",
        json={"agent": "cos-scout", "brand": "stick", "reason": "manual"},
    )
    from _lib.jobs.layer2 import agent_queue_writer

    agent_queue_writer.run()
    doc = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    manual = [r for r in doc["rows"] if str(r["id"]).startswith("manual-")]
    assert len(manual) == 1


def test_enqueue_moves_queue_depth(job_app):
    client, _, _ = job_app
    before = client.get("/api/ops/layers").get_json()["layers"]["L2"]["queue_depth"]
    client.post(
        "/api/ops/agents/enqueue",
        json={"agent": "cos-scout", "brand": "stick", "reason": "manual"},
    )
    after = client.get("/api/ops/layers").get_json()["layers"]["L2"]["queue_depth"]
    assert after == before + 1


def test_layers_l3_reflects_roster(job_app):
    client, _, _ = job_app
    empty = client.get("/api/ops/layers").get_json()["layers"]["L3"]
    assert empty["verdict"] == "NEVER"
    client.post("/api/ops/agents/heartbeat", json=_heartbeat_body())
    ok = client.get("/api/ops/layers").get_json()["layers"]["L3"]
    assert ok["verdict"] == "OK"
    assert ok.get("reporting", 0) >= 1


def test_ops_agents_layer_renders(job_app):
    client, _, _ = job_app
    resp = client.get("/ops?layer=agents")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="layer-agents"' in body
    assert 'id="agents-list"' in body


def test_ops_page_has_no_external_assets(job_app):
    client, _, _ = job_app
    body = client.get("/ops?layer=agents").get_data(as_text=True)
    assert "script src=" not in body.lower()
    assert '<link rel="stylesheet"' not in body.lower()


def test_agents_stub_copy_gone(job_app):
    client, _, _ = job_app
    body = client.get("/ops?layer=agents").get_data(as_text=True)
    assert "L3 not built" not in body
