"""L5 Create — draft_assets, asset_qc, Create tab, enqueue hook."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _purge_modules() -> None:
    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("_lib.jobs")
            or mod.startswith("_lib.")
            or mod == "_lib.ops_layers"
            or mod == "_lib.unified_inbox"
            or mod == "_lib.intelligence"
            or mod == "_lib.marketing_calendar"
            or mod == "_lib.llm_spend"
        ):
            del sys.modules[mod]


@pytest.fixture()
def l5_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "1.00")
    monkeypatch.delenv("CAMPAIGN_OS_L5_ENQUEUE", raising=False)
    _purge_modules()
    import app as app_module
    from _lib.jobs import cooldown as cd

    cd.reset_for_tests()
    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    client = app_module.app.test_client()
    return client, app_module, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def _seed_brands(tmp_path: Path, brand: str = "stick", campaign_id: str = "camp-stick") -> None:
    (tmp_path / "brands.json").write_text(
        json.dumps({"brands": {brand: {"id": brand, "campaign_ids": [campaign_id]}}}),
        encoding="utf-8",
    )
    (tmp_path / "campaign-data.json").write_text(
        json.dumps(
            {
                "campaigns": {
                    campaign_id: {
                        "identity": {"name": "Stick drafts", "brand": brand},
                        "assets": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _seed_approved_proposal(tmp_path: Path, brand: str = "stick", pid: str = "prop-1") -> str:
    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    row = {
        "id": pid,
        "brand_id": brand,
        "title": "Test proposal",
        "status": "approved",
        "approved_at": "2026-09-17T10:00:00Z",
    }
    (tmp_path / "proposals" / "pending.jsonl").write_text(
        json.dumps(row) + "\n",
        encoding="utf-8",
    )
    return f"proposal:{brand}:{pid}"


def _seed_queue_row(tmp_path: Path, *, action: str, item_id: str, brand: str = "stick") -> None:
    row = {
        "id": f"manual-{brand}-cos-caption-{action}",
        "layer": "L3",
        "agent": "cos-caption",
        "brand": brand,
        "action": action,
        "payload_ref": f"inbox/{item_id}",
        "status": "pending",
    }
    doc = {"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-09-17T10:00:00Z", "rows": [row]}
    (tmp_path / "agent-queue.json").write_text(json.dumps(doc), encoding="utf-8")


def test_layer5_specs_registered(l5_app):
    from _lib.jobs.registry import JOBS

    assert "draft_assets" in JOBS
    assert "asset_qc" in JOBS
    assert JOBS["draft_assets"].best_effort is True
    assert JOBS["asset_qc"].best_effort is False
    assert JOBS["draft_assets"].retries == 0
    assert JOBS["asset_qc"].retries == 0


def test_draft_assets_missing_llm_is_late(l5_app, tmp_path):
    from _lib.jobs.errors import classify
    from _lib.jobs.layer5 import draft_assets
    from _lib.jobs.registry import JOBS
    from _lib.jobs.runner import verdict_for

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)

    mock_result = {
        "ok": True,
        "survivors": [{"body": "[LLM unavailable — route=x, brand=stick]"}],
        "observability": {"provider": "none", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        result = draft_assets.run()

    assert result.get("ok") is False
    assert "missing OPENAI_API_KEY" in str(result.get("error"))
    err_class, _ = classify(message=result.get("error"))
    assert err_class == "auth"
    assert JOBS["draft_assets"].best_effort is True
    assert (
        verdict_for(
            "draft_assets",
            [{"phase": "finished", "status": "FAILED", "finished": "2026-09-17T10:00:00Z"}],
        )
        == "LATE"
    )


def test_draft_assets_respects_cap(l5_app, tmp_path, monkeypatch):
    from _lib.jobs.layer5 import draft_assets

    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "0.01")
    _purge_modules()
    from _lib import llm_spend

    llm_spend.record(0.01, route="seed", kind="text")

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)

    with patch("_lib.p11_context_engine.run_caption_pipeline") as mock_cap:
        result = draft_assets.run()
        mock_cap.assert_not_called()

    assert result.get("ok") is False
    err = str(result.get("error") or "")
    assert "daily LLM spend cap reached" in err
    assert "quota" not in err.lower()
    assert "rate limit" not in err.lower()


def test_draft_assets_skips_invalid_brand_row(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    doc = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-17T10:00:00Z",
        "rows": [
            {
                "id": "manual-takomo-cos-scout-manual",
                "layer": "L3",
                "agent": "cos-scout",
                "brand": "takomo",
                "action": "draft_caption",
                "payload_ref": f"inbox/{item_id}",
                "status": "pending",
            }
        ],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(doc), encoding="utf-8")

    with patch("_lib.p11_context_engine.run_caption_pipeline") as mock_pipe:
        result = draft_assets.run()
        mock_pipe.assert_not_called()

    assert result.get("ok") is True
    assert result.get("drafted") == 0
    assert result.get("skipped") >= 1


def test_draft_assets_only_approved(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    pending = {"id": "prop-p", "brand_id": "stick", "title": "Pending", "status": "pending"}
    (tmp_path / "proposals" / "pending.jsonl").write_text(json.dumps(pending) + "\n", encoding="utf-8")
    item_id = "proposal:stick:prop-p"
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)

    with patch("_lib.p11_context_engine.run_caption_pipeline") as mock_pipe:
        result = draft_assets.run()
        mock_pipe.assert_not_called()

    assert result.get("ok") is True
    assert result.get("drafted") == 0
    assert result.get("skipped") >= 1


def test_draft_lands_in_unified_inbox(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)

    mock_result = {
        "ok": True,
        "survivors": [{"body": "Fresh caption for stick"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        out = draft_assets.run()
    assert out.get("ok") is True
    assert out.get("drafted") == 1

    client, _, _ = l5_app
    resp = client.get("/api/inbox/unified?brand=stick&status=all")
    body = resp.get_json()
    ids = [i["id"] for i in body.get("items") or [] if i.get("type") == "draft_asset"]
    assert any(i.startswith("draft_asset:camp-stick:") for i in ids)


def test_draft_writes_sidecar_and_records_spend(l5_app, tmp_path):
    from _lib import llm_spend
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)
    before = llm_spend.status().get("calls") or 0

    mock_result = {
        "ok": True,
        "survivors": [{"body": "Sidecar caption"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        draft_assets.run()

    sidecars = list((tmp_path / "draft-assets").glob("*.json"))
    assert sidecars
    sidecar = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert sidecar.get("source_inbox_item_id") == item_id
    assert sidecar.get("cost_estimate_usd") is not None
    assert (llm_spend.status().get("calls") or 0) > before
    assert list((tmp_path / "receipts").glob("llm-generate-*.json"))


def test_no_repo_writes(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    repo_brand_dir = REPO_ROOT / "data" / "brand-directory"
    before = set(repo_brand_dir.rglob("*")) if repo_brand_dir.is_dir() else set()

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_image", item_id=item_id)

    mock_gen = MagicMock()
    mock_gen.model = "test-model"
    mock_gen.provider = "openrouter"
    mock_gen.saved_path = str(tmp_path / "draft-assets" / "images" / "out.png")

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    after = set(repo_brand_dir.rglob("*")) if repo_brand_dir.is_dir() else set()
    assert before == after


def test_asset_qc_flags_banned_words(l5_app, tmp_path):
    from _lib.jobs.layer5 import asset_qc

    _seed_brands(tmp_path)
    banned_patch = patch(
        "_lib.p11_context_engine._extract_banned_terms",
        return_value=["forbiddenword", "\u2014"],
    )
    asset_id = "draft-bad"
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    sidecar = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": asset_id,
        "campaign_id": "camp-stick",
        "brand_id": "stick",
        "source_inbox_item_id": "proposal:stick:x",
        "created_at": "2026-09-17T12:00:00Z",
        "action": "draft_caption",
        "cost_estimate_usd": 0.002,
    }
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")

    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][asset_id] = {
        "name": "Bad draft",
        "caption": "This uses forbiddenword in the caption",
        "approvalStatus": "draft",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    clean_id = "draft-good"
    sidecar2 = dict(sidecar, asset_id=clean_id)
    (tmp_path / "draft-assets" / f"{clean_id}.json").write_text(json.dumps(sidecar2), encoding="utf-8")
    data["campaigns"]["camp-stick"]["assets"][clean_id] = {
        "name": "Good draft",
        "caption": "Clean caption for stick",
        "approvalStatus": "draft",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    with banned_patch:
        result = asset_qc.run()
    assert result.get("ok") is True
    assert result.get("failed") >= 1

    saved = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert saved["campaigns"]["camp-stick"]["assets"][asset_id]["approvalStatus"] == "rejected"
    assert saved["campaigns"]["camp-stick"]["assets"][clean_id]["approvalStatus"] == "draft"


def test_gbp_draft_is_dry_run(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_gbp", item_id=item_id)

    with patch("_lib.gbp_daily_poster.build_daily_plan") as mock_plan:
        mock_plan.return_value = {
            "ok": True,
            "plan_id": "plan-test",
            "posts": [{"body": "GBP dry run post"}],
            "publish": {"skipped": "publish=False (dry-run)"},
        }
        result = draft_assets.run()

    assert result.get("ok") is True
    mock_plan.assert_called_once()
    _, kwargs = mock_plan.call_args
    assert kwargs.get("publish") is False


def test_enqueue_on_calendar_approve(l5_app, tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_OS_L5_ENQUEUE", "1")
    _purge_modules()

    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": "cal-enq",
        "event_key": "cal-enq",
        "status": "candidate",
        "title": "Enqueue calendar",
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

    from _lib import unified_inbox

    unified_inbox.approve_item("calendar_candidate:stick:cal-enq", editor="test")
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    actions = {r.get("action") for r in pending}
    assert "draft_caption" in actions
    assert "draft_image" in actions


def test_enqueue_on_proposal_approve(l5_app, tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_OS_L5_ENQUEUE", "1")
    _purge_modules()

    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    row = {"id": "prop-e", "brand_id": "stick", "title": "Enqueue me", "status": "pending"}
    (tmp_path / "proposals" / "pending.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    from _lib import unified_inbox

    unified_inbox.approve_item("proposal:stick:prop-e", editor="test")
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    assert len(pending) == 1
    assert pending[0]["id"].startswith("manual-")
    assert pending[0]["action"] == "draft_caption"

    _seed_brands(tmp_path)
    (tmp_path / "campaign-data.json").write_text(
        json.dumps(
            {
                "campaigns": {
                    "camp-stick": {
                        "identity": {"brand": "stick"},
                        "assets": {
                            "asset-d": {
                                "name": "Draft",
                                "caption": "x",
                                "approvalStatus": "draft",
                                "updatedAt": "2026-09-17T10:00:00Z",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    before = len(pending)
    unified_inbox.approve_item("draft_asset:camp-stick:asset-d", editor="test")
    queue2 = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending2 = [r for r in queue2.get("rows") or [] if r.get("status") == "pending"]
    assert len(pending2) == before


def test_enqueue_survives_queue_writer(l5_app, tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_OS_L5_ENQUEUE", "1")
    _purge_modules()

    from _lib import unified_inbox
    from _lib.jobs.layer2 import agent_queue_writer

    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    row = {"id": "prop-q", "brand_id": "stick", "title": "Queue", "status": "pending"}
    (tmp_path / "proposals" / "pending.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    unified_inbox.approve_item("proposal:stick:prop-q", editor="test")

    agent_queue_writer.run()
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    assert any(r.get("action") == "draft_caption" for r in pending)


def test_enqueue_flag_off_default(l5_app, tmp_path):
    from _lib import unified_inbox

    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    row = {"id": "prop-off", "brand_id": "stick", "title": "No enqueue", "status": "pending"}
    (tmp_path / "proposals" / "pending.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    unified_inbox.approve_item("proposal:stick:prop-off", editor="test")
    assert not (tmp_path / "agent-queue.json").exists()


def test_layers_l5_create_counts(l5_app, tmp_path):
    from datetime import datetime, timezone

    for mod in list(sys.modules):
        if mod == "_lib.ops_layers":
            del sys.modules[mod]
    from _lib.ops_layers import build_layers, load_create_stats

    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sidecar = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": "d1",
        "campaign_id": "camp-stick",
        "brand_id": "stick",
        "source_inbox_item_id": "proposal:stick:x",
        "created_at": today,
        "action": "draft_caption",
        "cost_estimate_usd": 0.002,
    }
    (tmp_path / "draft-assets" / "d1.json").write_text(json.dumps(sidecar), encoding="utf-8")

    stats = load_create_stats()
    assert stats.get("drafts_today") >= 1
    payload = build_layers({"jobs": []})
    l5 = payload["layers"]["L5"]
    assert "drafts_today" in l5
    assert "spent_usd" in l5
    assert l5["verdict"] in ("OK", "LATE", "NEVER")


def test_ops_create_tab_anon_401(l5_app):
    _, app_module, _ = l5_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/ops", follow_redirects=False)
    assert resp.status_code in (302, 401)
    spend = anon.get("/api/ops/llm-spend")
    assert spend.status_code == 401
