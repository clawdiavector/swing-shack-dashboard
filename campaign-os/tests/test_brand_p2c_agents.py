"""P2c agent pipeline brand contract tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

LEARN_BRAND = "stick"


@pytest.fixture()
def job_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib."):
            del sys.modules[mod]
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    return app_module.app.test_client(), tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_enqueue_missing_brand_returns_400(job_env):
    client, _ = job_env
    resp = client.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "reason": "manual"},
    )
    assert resp.status_code == 400
    assert "brand_id required" in resp.get_json().get("error", "")


def test_enqueue_invalid_brand_returns_400(job_env):
    client, _ = job_env
    resp = client.post(
        "/api/ops/agents/enqueue",
        headers=_auth(),
        json={"agent": "cos-scout", "brand": "takomo", "reason": "manual"},
    )
    assert resp.status_code == 400
    assert "invalid brand_id" in resp.get_json().get("error", "")


def test_agent_queue_filter_invalid_brand_returns_400(job_env):
    client, _ = job_env
    resp = client.get("/api/ops/agent-queue?brand=invalid-lane", headers=_auth())
    assert resp.status_code == 400


def test_publish_sandbox_enqueue_invalid_brand_returns_400(job_env):
    client, _ = job_env
    resp = client.post(
        "/api/publish/sandbox/enqueue",
        headers=_auth(),
        json={"brand_id": "takomo", "caption_preview": "x"},
    )
    assert resp.status_code == 400


def test_agent_queue_writer_skips_unknown_reco_owner(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod.startswith("_lib.jobs.layer2") or mod == "_lib.jobs.layer1._io":
            del sys.modules[mod]
    from _lib.jobs.layer2 import agent_queue_writer

    (tmp_path / "slot-planner.json").write_text(json.dumps({"empty_slots": []}), encoding="utf-8")
    (tmp_path / "freshness.json").write_text(json.dumps({"rotten_files": []}), encoding="utf-8")
    brand_root = tmp_path / "brands" / "stick"
    brand_root.mkdir(parents=True, exist_ok=True)
    (brand_root / "recommendation-scores.json").write_text(
        json.dumps(
            {
                "do_first": [
                    {"item": {"hook_id": "orphan-hook", "owner": "unknown-brand", "type": "post"}}
                ]
            }
        ),
        encoding="utf-8",
    )
    result = agent_queue_writer.run()
    assert result["ok"] is True, result.get("error")
    doc = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    brands = {row["brand"] for row in doc["rows"]}
    assert "swing-shack" not in brands
    assert "unknown-brand" not in brands


def test_post_outcomes_skips_receipt_without_brand_id(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    fixtures = Path(__file__).resolve().parent / "jobs" / "fixtures" / "layer7"
    brand_root = tmp_path / "brands" / LEARN_BRAND
    brand_root.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy(fixtures / "ig-business-analytics.min.json", brand_root / "ig-business-analytics.json")
    shutil.copy(fixtures / "post-conversion-score.min.json", brand_root / "post-conversion-score.json")
    sandbox = tmp_path / "publish-sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "receipts.jsonl").write_text(
        json.dumps(
            {
                "schema": "campaign-os/publish-receipt/v1",
                "brand_id": "",
                "idempotency_key": "bad-receipt",
                "caption_preview": "Too many swing thoughts? Lets lessen that Book your coaching session @swingshack",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    from _lib.jobs.layer7 import post_outcomes

    result = post_outcomes.run(brand=LEARN_BRAND)
    assert result["ok"] is True
    doc = json.loads((brand_root / "post-outcomes.json").read_text(encoding="utf-8"))
    assert doc.get("receipts_skipped_no_brand") == 1
    assert doc.get("brand_id") == LEARN_BRAND


def test_postiz_stick_does_not_use_global_key(monkeypatch):
    from _lib import postiz_client as pc

    monkeypatch.delenv("POSTIZ_API_KEY_STICK", raising=False)
    monkeypatch.setenv("POSTIZ_API_KEY", "global-key-should-not-leak")
    assert pc._read_api_key(brand_id="stick") is None


def test_no_default_brand_in_post_outcomes_source():
    source = (CAMPAIGN_OS / "_lib" / "jobs" / "layer7" / "post_outcomes.py").read_text(encoding="utf-8")
    assert "DEFAULT_BRAND" not in source
