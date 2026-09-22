"""L2 ops ribbon: /ops shell, GET /api/ops/layers, Health tab, session gate."""

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


def test_ops_page_requires_session(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/ops", follow_redirects=False)
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert "/login" in (resp.headers.get("Location") or "")


def test_ops_bearer_does_not_open_page(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/ops", headers=_auth(), follow_redirects=False)
    assert resp.status_code == 302


def test_ops_page_ok_with_session(job_app):
    client, _, _ = job_app
    resp = client.get("/ops")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "ops-ribbon" in body or 'id="ops-ribbon"' in body
    assert "/ops?layer=jobs" in body
    assert "/ops?layer=health" in body
    assert "script src=" not in body.lower()
    assert '<link rel="stylesheet"' not in body.lower()


def test_ops_default_and_jobs_layer(job_app):
    client, _, _ = job_app
    for path in ("/ops", "/ops?layer=jobs"):
        resp = client.get(path)
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Schedule at a glance" in body
        assert "data-jobs-view" in body


def test_ops_health_layer(job_app):
    client, _, _ = job_app
    resp = client.get("/ops?layer=health")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="layer-health"' in body
    assert "Linux watchdog" in body


def test_ops_unknown_layer_falls_back_to_jobs(job_app):
    client, _, _ = job_app
    resp = client.get("/ops?layer=nonsense")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Schedule at a glance" in body


def test_ops_not_in_public_prefixes(job_app):
    _, app_module, _ = job_app
    pubs = getattr(app_module, "PUBLIC_ROUTE_PREFIXES", ())
    assert not any(p.startswith("/ops") for p in pubs)


def test_layers_api_anon_401_json(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/api/ops/layers")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body.get("ok") is False


def test_layers_api_bearer_ok(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/api/ops/layers", headers=_auth())
    assert resp.status_code == 200


def test_layers_api_session_ok(job_app):
    client, _, _ = job_app
    resp = client.get("/api/ops/layers")
    assert resp.status_code == 200


def test_layers_api_schema(job_app):
    client, _, _ = job_app
    resp = client.get("/api/ops/layers")
    body = resp.get_json()
    assert body.get("schema") == "campaign-os/ops-layers/v1"
    assert body.get("generated_at")
    layers = body.get("layers") or {}
    assert set(layers) == {f"L{i}" for i in range(1, 8)}
    valid = {"OK", "LATE", "STUCK", "FAILED", "NEVER"}
    for key, layer in layers.items():
        assert "label" in layer
        assert "verdict" in layer
        assert "href" in layer
        assert layer["verdict"] in valid
        if key == "L7":
            assert "recipes" in layer
            assert "winners" in layer
            assert "samples" in layer
        if key == "L5":
            assert "drafts_today" in layer
            assert "spent_usd" in layer
        if key == "L4":
            assert "pending" in layer
            assert "stale" in layer
            assert "approved_today" in layer
        if key == "L3":
            assert layer["verdict"] == "NEVER"
            assert layer.get("agents", 0) >= 1


def test_layers_api_bearer_not_widened_to_other_ops(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)
    for path in ("/api/ops/errors", "/api/ops/runbook", "/api/ops/llm-spend"):
        assert anon.get(path, headers=_auth()).status_code == 401


def test_layers_l2_watch_and_queue_empty(job_app):
    client, _, _ = job_app
    body = client.get("/api/ops/layers").get_json()
    l2 = body["layers"]["L2"]
    assert l2.get("watch_verdict") == "NEVER"
    assert l2.get("watch_age_s") is None
    assert l2.get("queue_depth") == 0


def test_layers_queue_depth_from_file(job_app, tmp_path):
    client, app_module, tmp_path = job_app
    queue = {
        "rows": [
            {"id": "a", "status": "pending"},
            {"id": "b", "status": "pending"},
            {"id": "c", "status": "approved"},
        ]
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(queue), encoding="utf-8")
    body = client.get("/api/ops/layers").get_json()
    assert body["layers"]["L2"]["queue_depth"] == 2


def test_layers_freshness_counts(job_app, tmp_path):
    client, app_module, tmp_path = job_app
    freshness = {
        "generated": "2026-09-17T07:00:00Z",
        "by_staleness": {"fresh": 10, "stale": 3, "rotten": 1},
    }
    (tmp_path / "freshness.json").write_text(json.dumps(freshness), encoding="utf-8")
    body = client.get("/api/ops/layers").get_json()
    l2 = body["layers"]["L2"]
    assert l2["rotten"] == 1
    assert l2["stale"] == 3


def test_build_layers_pure_function():
    from datetime import datetime, timezone

    from _lib.ops_layers import build_layers, worst_verdict

    recent = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = build_layers(
        {"jobs": [
            {"verdict": "OK"},
            {"verdict": "LATE"},
            {"verdict": "FAILED"},
        ]},
        freshness={"rotten": 0, "stale": 2},
        queue={"rows": [{"id": "x", "status": "pending"}]},
        watch={"received_at": recent, "all_ok": True},
    )
    assert payload["schema"] == "campaign-os/ops-layers/v1"
    assert payload["layers"]["L1"]["verdict"] == "FAILED"
    assert payload["layers"]["L1"]["ok"] == 1
    assert payload["layers"]["L2"]["queue_depth"] == 1
    assert payload["layers"]["L2"]["watch_verdict"] == "OK"
    assert payload["layers"]["L2"]["watch_age_s"] is not None
    assert worst_verdict(["OK", "LATE", "STUCK"]) == "STUCK"


def test_disabled_job_does_not_mask_failed():
    from _lib.ops_layers import build_layers, worst_verdict

    payload = build_layers({"jobs": [
        {"verdict": "OK"}, {"verdict": "DISABLED"}, {"verdict": "FAILED"},
    ]})
    assert payload["layers"]["L1"]["verdict"] == "FAILED"
    assert payload["layers"]["L2"]["verdict"] == "FAILED"
    assert payload["layers"]["L1"]["disabled"] == 1
    assert payload["layers"]["L1"]["never"] == 0
    assert worst_verdict(["OK", "DISABLED"]) == "OK"
    assert worst_verdict(["OK", "SKIPPED"]) == "OK"


def test_all_disabled_reads_disabled_not_never():
    from _lib.ops_layers import build_layers

    payload = build_layers({"jobs": [{"verdict": "DISABLED"}]})
    assert payload["layers"]["L1"]["verdict"] == "DISABLED"


def test_roster_verdict_excludes_disabled():
    from _lib.ops_agents import roster_verdict

    agents = [
        {"last_heartbeat_at": "2026-09-21T07:00:00Z", "last_status": "OK"},
        {"last_heartbeat_at": "2026-09-21T07:00:00Z", "last_status": "DISABLED"},
        {"last_heartbeat_at": "2026-09-21T07:00:00Z", "last_status": "FAILED"},
    ]
    assert roster_verdict(agents) == "FAILED"


def test_e2e_gate_flow(job_app):
    _, app_module, _ = job_app
    anon = app_module.app.test_client(cos_anon=True)

    r1 = anon.get("/ops", follow_redirects=False)
    assert r1.status_code == 302
    assert "/login" in (r1.headers.get("Location") or "")

    anon.post("/login", data={"password": app_module.SHARED_PASSWORD})

    r2 = anon.get("/ops")
    assert r2.status_code == 200
    body = r2.get_data(as_text=True)
    assert 'id="ops-ribbon"' in body
    for slug in ("jobs", "health", "agents", "approve", "create", "publish", "learn"):
        assert f"/ops?layer={slug}" in body

    assert anon.get("/ops?layer=health").status_code == 200
    assert "layer-health" in anon.get("/ops?layer=health").get_data(as_text=True)

    layers = anon.get("/api/ops/layers").get_json()
    assert set(layers.get("layers", {})) == {f"L{i}" for i in range(1, 8)}

    assert anon.get("/ops/jobs").status_code == 200
    assert "Schedule at a glance" in anon.get("/ops/jobs").get_data(as_text=True)

    bearer_only = app_module.app.test_client(cos_anon=True)
    assert bearer_only.get("/api/ops/layers", headers=_auth()).status_code == 200
    assert bearer_only.get("/ops", headers=_auth(), follow_redirects=False).status_code == 302
