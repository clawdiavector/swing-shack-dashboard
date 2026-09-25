"""L5 Create — draft_assets, asset_qc, Create tab, enqueue hook."""

from __future__ import annotations

import json
import re
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


def _seed_brands(
    tmp_path: Path,
    brand: str = "stick",
    campaign_id: str = "camp-stick",
    *,
    campaign_ids: list[str] | None = None,
    publish_channels: list[str] | None = None,
) -> None:
    cids = campaign_ids if campaign_ids is not None else ([campaign_id] if campaign_id else [])
    entry: dict = {"id": brand, "campaign_ids": cids}
    if publish_channels is not None:
        entry["publish_channels"] = publish_channels
    elif brand == "stick":
        entry["publish_channels"] = ["instagram", "facebook"]
    elif brand == "swing-shack":
        entry["publish_channels"] = ["instagram", "facebook", "gbp"]
    elif brand == "bag-drop":
        entry["publish_channels"] = []
    (tmp_path / "brands.json").write_text(
        json.dumps({"brands": {brand: entry}}),
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

    assert "retry_failed_images" in JOBS
    assert "draft_assets" in JOBS
    assert "krea_poll_draft_images" in JOBS
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

    assert result.get("skipped_cap") or "cap" in str(result.get("reason") or result.get("error") or "").lower()


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
        "event_date": "2026-10-01",
        "primary_channel": "instagram",
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

    from _lib import unified_inbox

    unified_inbox.approve_item("calendar_candidate:stick:cal-enq", editor="test")
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    actions = {r.get("action") for r in pending}
    assert "draft_caption" in actions
    assert "draft_photo" in actions
    assert "compose_post" in actions


def test_enqueue_on_proposal_approve(l5_app, tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_OS_L5_ENQUEUE", "1")
    _purge_modules()

    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    row = {"id": "prop-e", "brand_id": "stick", "title": "Enqueue me", "status": "pending"}
    (tmp_path / "proposals" / "pending.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    from _lib import unified_inbox

    unified_inbox.approve_item(
        "proposal:stick:prop-e",
        editor="test",
        mode="lodge",
        event_date="2026-10-02",
        primary_channel="instagram",
    )
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    assert len(pending) == 3
    actions = {r["action"] for r in pending}
    assert actions == {"draft_caption", "draft_photo", "compose_post"}
    assert all(r["id"].startswith("manual-") for r in pending)

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

    _seed_brands(tmp_path)
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-09-17T10:00:00Z", "rows": []}),
        encoding="utf-8",
    )
    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    row = {"id": "prop-q", "brand_id": "stick", "title": "Queue", "status": "pending"}
    (tmp_path / "proposals" / "pending.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    unified_inbox.approve_item("proposal:stick:prop-q", editor="test")
    from _lib.l5_create_enqueue import enqueue_create_actions

    enqueue_create_actions(item_id="proposal:stick:prop-q", brand_id="stick", reason="proposal")

    agent_queue_writer.run()
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    assert any(str(r.get("id") or "").startswith("manual-") for r in pending)


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


def _seed_approved_calendar(tmp_path: Path, *, brand: str = "stick", cal_id: str = "cal-slot-1") -> str:
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": cal_id,
        "event_key": "evt-slot-1",
        "brand_id": brand,
        "pillar_id": "stick-retail",
        "status": "approved",
        "event_date": "2026-09-20",
        "title": "Approved slot day",
    }
    (cal_dir / f"{brand}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return f"calendar_candidate:{brand}:{cal_id}"


def _seed_fill_slot_row(tmp_path: Path, *, brand: str = "stick") -> None:
    row = {
        "id": f"stick-fill-slot-2026-09-20",
        "layer": "L3",
        "agent": "cos-scout",
        "brand": brand,
        "action": "fill_slot",
        "payload_ref": f"slot-planner.json#{brand}/2026-09-20/stick-retail",
        "status": "pending",
    }
    doc = {"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-09-17T10:00:00Z", "rows": [row]}
    (tmp_path / "agent-queue.json").write_text(json.dumps(doc), encoding="utf-8")


def test_fill_slot_produces_draft(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    _seed_approved_calendar(tmp_path)
    _seed_fill_slot_row(tmp_path)

    mock_result = {
        "ok": True,
        "survivors": [{"body": "Caption from fill_slot"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        result = draft_assets.run()

    assert result.get("ok") is True
    assert result.get("drafted") == 1
    sidecars = list((tmp_path / "draft-assets").glob("*.json"))
    assert sidecars
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    fill_rows = [r for r in queue["rows"] if r.get("action") == "fill_slot"]
    assert fill_rows[0]["status"] == "done"


def test_fill_slot_skips_invalid_brand(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    _seed_approved_calendar(tmp_path, brand="stick")
    doc = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-17T10:00:00Z",
        "rows": [
            {
                "id": "takomo-fill-slot",
                "layer": "L3",
                "agent": "cos-scout",
                "brand": "takomo",
                "action": "fill_slot",
                "payload_ref": "slot-planner.json#stick/2026-09-20/stick-retail",
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


def test_asset_qc_pass_enqueues_publish_sandbox(l5_app, tmp_path, monkeypatch):
    from _lib import publish_sandbox
    from _lib.jobs.layer5 import asset_qc

    monkeypatch.delenv("CAMPAIGN_OS_L6_ENQUEUE", raising=False)
    _seed_brands(tmp_path)
    publish_sandbox.ensure_sandbox_layout()

    asset_id = "draft-qc-pass"
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
        "name": "QC pass draft",
        "caption": "Clean caption for publish queue",
        "approvalStatus": "draft",
        "platform": "instagram",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = asset_qc.run()
        mock_urlopen.assert_not_called()

    assert result.get("ok") is True
    assert result.get("passed") == 1
    queue_rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
    assert queue_rows == []


def test_asset_qc_enqueue_idempotent(l5_app, tmp_path, monkeypatch):
    from _lib import publish_sandbox
    from _lib.jobs.layer5 import asset_qc

    monkeypatch.delenv("CAMPAIGN_OS_L6_ENQUEUE", raising=False)
    _seed_brands(tmp_path)
    publish_sandbox.ensure_sandbox_layout()

    asset_id = "draft-qc-idem"
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
        "name": "Idempotent QC draft",
        "caption": "Same caption daily",
        "approvalStatus": "draft",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    asset_qc.run()
    asset_qc.run()
    queue_rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
    assert len(queue_rows) == 0


def test_l5_enqueue_three_approvals_three_rows(l5_app, tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_OS_L5_ENQUEUE", "1")
    _purge_modules()

    _seed_brands(tmp_path)
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-09-17T10:00:00Z", "rows": []}),
        encoding="utf-8",
    )
    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    for pid in ("p-001", "p-002", "p-003"):
        row = {"id": pid, "brand_id": "stick", "title": f"Proposal {pid}", "status": "pending"}
        with (tmp_path / "proposals" / "pending.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    from _lib import unified_inbox

    for pid in ("p-001", "p-002", "p-003"):
        unified_inbox.approve_item(
            f"proposal:stick:{pid}",
            editor="test",
            mode="lodge",
            event_date="2026-10-03",
            primary_channel="instagram",
        )

    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    assert len(pending) == 9
    ids = {r["id"] for r in pending}
    assert len(ids) == 9
    payload_refs = {r["payload_ref"] for r in pending}
    assert len(payload_refs) == 3
    assert {r["action"] for r in pending} == {"draft_caption", "draft_photo", "compose_post"}


def _seed_calendar_candidate_jsonl(
    tmp_path: Path,
    *,
    brand: str = "swing-shack",
    cal_id: str = "cal-swing-shack-moment-1789713288-cec0c7a3",
    event_key: str = "moment-swing-shack-fixture",
    status: str = "candidate",
    revision: int = 1,
) -> None:
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": cal_id,
        "event_key": event_key,
        "brand_id": brand,
        "status": status,
        "revision": revision,
        "title": "Fixture moment",
        "event_date": "2026-09-25",
    }
    (cal_dir / f"{brand}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_canonical_equal_revision_last_write_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _purge_modules()
    from _lib.marketing_calendar import canonical_records

    cal_id = "cal-swing-shack-moment-1789713288-cec0c7a3"
    event_key = "moment-swing-shack-fixture"
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "calendar_id": cal_id,
        "event_key": event_key,
        "brand_id": "swing-shack",
        "revision": 1,
        "title": "Fixture moment",
    }
    line1 = {**base, "status": "candidate"}
    line2 = {**base, "status": "approved"}
    (cal_dir / "swing-shack.jsonl").write_text(
        json.dumps(line1) + "\n" + json.dumps(line2) + "\n",
        encoding="utf-8",
    )

    canon = canonical_records("swing-shack")
    match = next(r for r in canon if r.get("calendar_id") == cal_id)
    assert match["status"] == "approved"


def test_calendar_candidate_approve_canonical_and_enqueue(l5_app, tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_OS_L5_ENQUEUE", "1")
    _purge_modules()

    cal_id = "cal-swing-shack-moment-1789713288-cec0c7a3"
    _seed_calendar_candidate_jsonl(tmp_path, cal_id=cal_id)
    _seed_brands(tmp_path, brand="swing-shack", campaign_id="camp-swing-shack")

    from _lib import unified_inbox
    from _lib.marketing_calendar import canonical_records, list_records

    result = unified_inbox.approve_item(f"calendar_candidate:swing-shack:{cal_id}", editor="test")
    assert result.get("ok") is True

    canon = canonical_records("swing-shack")
    match = next(r for r in canon if r.get("calendar_id") == cal_id)
    assert match["status"] == "approved"

    appended = [r for r in list_records("swing-shack") if r.get("calendar_id") == cal_id]
    assert max(int(r.get("revision") or 1) for r in appended) == 2

    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    assert len(pending) == 4
    actions = {r["action"] for r in pending}
    assert actions == {"draft_caption", "draft_photo", "compose_post", "draft_gbp"}
    agents = {r["agent"] for r in pending}
    assert agents == {"cos-caption", "cos-image"}


def test_calendar_candidate_distinct_row_ids(l5_app, tmp_path, monkeypatch):
    """B3 regression: sha1 dedupe keys stay distinct under slug_id front-truncation."""
    monkeypatch.setenv("CAMPAIGN_OS_L5_ENQUEUE", "1")
    _purge_modules()

    _seed_brands(tmp_path, brand="swing-shack", campaign_id="camp-swing-shack")
    cal_specs = [
        (
            "cal-swing-shack-mom-1758123456-abc12345",
            "moment-swing-shack-mom-1758123456-abc12345",
        ),
        (
            "cal-swing-shack-mom-1758999999-zzz99999",
            "moment-swing-shack-mom-1758999999-zzz99999",
        ),
        (
            "cal-swing-shack-mom-1759000001-aaa11111",
            "moment-swing-shack-mom-1759000001-aaa11111",
        ),
        (
            "cal-swing-shack-mom-1759000002-bbb22222",
            "moment-swing-shack-mom-1759000002-bbb22222",
        ),
    ]
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for cal_id, event_key in cal_specs:
        lines.append(
            json.dumps(
                {
                    "calendar_id": cal_id,
                    "event_key": event_key,
                    "brand_id": "swing-shack",
                    "status": "candidate",
                    "revision": 1,
                    "title": f"Fixture {cal_id[-8:]}",
                    "event_date": "2026-09-25",
                }
            )
        )
    (cal_dir / "swing-shack.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    from _lib import unified_inbox

    for cal_id, _event_key in cal_specs:
        result = unified_inbox.approve_item(
            f"calendar_candidate:swing-shack:{cal_id}", editor="test"
        )
        assert result.get("ok") is True

    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    assert len(pending) == 16
    row_ids = {r["id"] for r in pending}
    assert len(row_ids) == 16
    actions = [r["action"] for r in pending]
    assert actions.count("draft_caption") == 4
    assert actions.count("draft_photo") == 4
    assert actions.count("compose_post") == 4
    assert actions.count("draft_gbp") == 4


def test_draft_assets_calendar_candidate_queue_row(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    cal_id = "cal-swing-shack-moment-1789713288-cec0c7a3"
    event_key = "moment-swing-shack-fixture"
    _seed_brands(tmp_path, brand="swing-shack", campaign_id="camp-swing-shack")
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    approved = {
        "calendar_id": cal_id,
        "event_key": event_key,
        "brand_id": "swing-shack",
        "status": "approved",
        "revision": 2,
        "title": "Approved moment",
        "event_date": "2026-09-25",
    }
    (cal_dir / "swing-shack.jsonl").write_text(json.dumps(approved) + "\n", encoding="utf-8")
    item_id = f"calendar_candidate:swing-shack:{event_key}"
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id, brand="swing-shack")

    mock_result = {
        "ok": True,
        "survivors": [{"body": "Caption from calendar candidate"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        result = draft_assets.run()

    assert result.get("ok") is True
    assert result.get("drafted") == 1


def test_l6_enqueue_flag_off(l5_app, tmp_path, monkeypatch):
    from _lib import publish_sandbox
    from _lib.jobs.layer5 import asset_qc

    monkeypatch.setenv("CAMPAIGN_OS_L6_ENQUEUE", "0")
    _seed_brands(tmp_path)
    publish_sandbox.ensure_sandbox_layout()

    asset_id = "draft-l6-off"
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
        "name": "Flag off draft",
        "caption": "No sandbox enqueue",
        "approvalStatus": "draft",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    asset_qc.run()
    queue_rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
    assert queue_rows == []


def test_draft_assets_error_carries_frame(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)

    with patch(
        "_lib.p11_context_engine.run_caption_pipeline",
        side_effect=AttributeError("boom"),
    ):
        result = draft_assets.run(brand="stick")

    assert result.get("ok") is False
    err = str(result.get("error") or "")
    assert re.search(r"AttributeError at \S+\.py:\d+", err)
    diag_path = tmp_path / "draft-assets" / "_diagnostics" / "last-error.json"
    assert diag_path.is_file()
    diag = json.loads(diag_path.read_text(encoding="utf-8"))
    assert diag.get("traceback")


def test_draft_assets_survives_malformed_calendar_line(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path, campaign_ids=[])
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    (cal_dir / "stick.jsonl").write_text("[\"not-a-dict\"]\n", encoding="utf-8")
    item_id = "calendar_candidate:stick:cal-bad"
    record = {
        "calendar_id": "cal-bad",
        "brand_id": "stick",
        "status": "approved",
        "title": "Bad line neighbour",
    }
    with (cal_dir / "stick.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)

    mock_result = {
        "ok": True,
        "survivors": [{"body": "Caption despite bad neighbour line"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        result = draft_assets.run(brand="stick")

    assert result.get("ok") is True
    assert result.get("skipped") >= 1


def test_approved_candidate_drafts_caption_and_image(l5_app, tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_OS_L5_ENQUEUE", "1")
    _purge_modules()

    cal_id = "cal-stick-visible"
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": cal_id,
        "brand_id": "stick",
        "status": "candidate",
        "title": "Stick school holidays",
        "event_date": "2026-09-25",
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    item_id = f"calendar_candidate:stick:{cal_id}"

    _seed_brands(tmp_path, campaign_ids=[])

    from _lib import unified_inbox

    approved = unified_inbox.approve_item(item_id, editor="test")
    assert approved.get("ok") is True
    with (cal_dir / "stick.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    **record,
                    "status": "approved",
                    "revision": 2,
                    "event_key": cal_id,
                }
            )
            + "\n"
        )

    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    assert {r["action"] for r in pending} == {"draft_caption", "draft_photo", "compose_post"}

    mock_result = {
        "ok": True,
        "survivors": [{"body": "Term 4 caption"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    img_dir = tmp_path / "draft-assets" / "images" / "stick" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_file = img_dir / "gen-test.png"
    png_body = b"\x89PNG\r\n\x1a\n" + b"x" * 32
    img_file.write_bytes(png_body)

    class _FakeGenResult:
        model = "test-model"
        provider = "openrouter"
        saved_path = str(img_file)
        bytes = png_body
        prompt_used = "composed prompt"
        provider_job_id = None

    qc_pass = {"verdict": "pass", "reasons": [], "ocr_available": True, "scores": {}}
    fake_png = png_body

    def _fake_compose(**_kwargs):
        return {"instagram": fake_png, "facebook": fake_png}

    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result), patch(
        "_lib.image_gen_router.generate_image_with_persistence", return_value=_FakeGenResult()
    ), patch("_lib.jobs.layer5.visual_qc.visual_check", return_value=qc_pass), patch(
        "_lib.archetype_compose.compose_post_for_channels", side_effect=_fake_compose
    ):
        from _lib.jobs.layer5 import draft_assets

        result = draft_assets.run(brand="stick")

    assert result.get("ok") is True
    assert result.get("drafted") >= 2
    sidecars = [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "draft-assets").glob("*.json")]
    assert any(s.get("photo_candidates") for s in sidecars)
    assert any(s.get("composed") for s in sidecars)
    queue2 = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    done_rows = [
        r
        for r in queue2.get("rows") or []
        if r.get("action") in ("draft_caption", "draft_photo", "compose_post", "draft_image") and r.get("status") == "done"
    ]
    assert len(done_rows) >= 2


def test_draft_asset_inbox_payload_exposes_caption_and_image(l5_app, tmp_path):
    from _lib import unified_inbox

    _seed_brands(tmp_path)
    long_caption = "x" * 420
    img_dir = tmp_path / "data" / "brand-directory" / "stick" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_file = img_dir / "gen-review.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"y" * 32)
    image_path = str(img_file)
    image_url = "/brand-images/stick/gen-review.png"
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"] = {
        "draft-caption": {
            "name": "Caption draft",
            "caption": long_caption,
            "approvalStatus": "draft",
            "platform": "instagram",
            "updatedAt": "2026-09-17T12:00:00Z",
        },
        "draft-image": {
            "name": "Image draft",
            "caption": "Image draft for stick",
            "approvalStatus": "draft",
            "platform": "instagram",
            "image_path": image_path,
            "image_url": image_url,
            "updatedAt": "2026-09-17T12:00:00Z",
        },
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    payload = unified_inbox.list_items(status="all", item_type="draft_asset", brand="stick")
    items = {i["meta"]["asset_id"]: i for i in payload.get("items") or []}
    assert items["draft-caption"]["meta"]["caption"] == long_caption
    assert items["draft-image"]["meta"]["image_url"].startswith("/brand-images/stick/")
    assert Path(items["draft-image"]["meta"]["image_path"]).name == "gen-review.png"


def test_publish_request_per_intended_channel(l5_app, tmp_path, monkeypatch):
    from _lib import publish_sandbox
    from _lib.jobs import publish_dispatch
    from _lib.jobs.layer5 import asset_qc

    monkeypatch.setenv("CAMPAIGN_OS_L6_ENQUEUE", "1")
    monkeypatch.setenv("PUBLISH_MODE", "sandbox")

    def _seed_qc_asset(*, brand: str, campaign_id: str, asset_id: str, caption: str) -> None:
        (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
        sidecar = {
            "schema": "campaign-os/draft-asset/v1",
            "asset_id": asset_id,
            "campaign_id": campaign_id,
            "brand_id": brand,
            "source_inbox_item_id": f"proposal:{brand}:x",
            "created_at": "2026-09-17T12:00:00Z",
            "action": "draft_caption",
            "cost_estimate_usd": 0.002,
        }
        (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
        data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
        data.setdefault("campaigns", {}).setdefault(campaign_id, {"assets": {}})
        data["campaigns"][campaign_id]["assets"][asset_id] = {
            "name": f"{brand} draft",
            "caption": caption,
            "approvalStatus": "draft",
            "updatedAt": "2026-09-17T12:00:00Z",
        }
        (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    (tmp_path / "brands.json").write_text(
        json.dumps(
            {
                "brands": {
                    "stick": {
                        "id": "stick",
                        "campaign_ids": ["camp-stick"],
                        "publish_channels": ["instagram", "facebook"],
                    },
                    "swing-shack": {
                        "id": "swing-shack",
                        "campaign_ids": ["camp-ss"],
                        "publish_channels": ["instagram", "facebook", "gbp"],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "campaign-data.json").write_text(
        json.dumps({"campaigns": {"camp-stick": {"assets": {}}, "camp-ss": {"assets": {}}}}),
        encoding="utf-8",
    )
    publish_sandbox.ensure_sandbox_layout()
    _seed_qc_asset(brand="stick", campaign_id="camp-stick", asset_id="draft-stick", caption="Stick caption")
    _seed_qc_asset(
        brand="swing-shack",
        campaign_id="camp-ss",
        asset_id="draft-ss",
        caption="Swing caption",
    )

    asset_qc.run()
    asset_qc.run()
    queue_rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
    assert queue_rows == []


def test_intended_publish_channels_matches_auth_matrix(l5_app, tmp_path):
    from _lib import publish_sandbox
    from _lib.connection_status import PUBLISHING_CHANNELS

    (tmp_path / "brands.json").write_text(
        json.dumps(
            {
                "brands": {
                    "swing-shack": {
                        "id": "swing-shack",
                        "publish_channels": ["instagram", "facebook", "gbp"],
                    },
                    "stick": {
                        "id": "stick",
                        "publish_channels": ["instagram", "facebook"],
                    },
                    "bag-drop": {"id": "bag-drop", "publish_channels": []},
                }
            }
        ),
        encoding="utf-8",
    )

    assert publish_sandbox.intended_publish_channels("swing-shack") == [
        "instagram",
        "facebook",
        "gbp",
    ]
    assert publish_sandbox.intended_publish_channels("stick") == ["instagram", "facebook"]
    assert publish_sandbox.intended_publish_channels("bag-drop") == []
    for brand in ("swing-shack", "stick", "bag-drop"):
        channels = publish_sandbox.intended_publish_channels(brand)
        assert not {"tiktok", "x", "linkedin"} & set(channels)
        assert set(channels).issubset(set(PUBLISHING_CHANNELS))


def _first_draft_asset_name(tmp_path: Path) -> str:
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    for campaign in (data.get("campaigns") or {}).values():
        for asset in (campaign.get("assets") or {}).values():
            if isinstance(asset, dict) and asset.get("name"):
                return str(asset["name"])
    raise AssertionError("no draft asset name in campaign-data")


def test_draft_caption_name_uses_calendar_title(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    cal_id = "cal-name-test"
    _seed_brands(tmp_path, brand="stick", campaign_id="camp-stick")
    item_id = _seed_approved_calendar(tmp_path, brand="stick", cal_id=cal_id)
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)

    mock_result = {
        "ok": True,
        "survivors": [{"body": "Caption body should not win when calendar has title"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        assert draft_assets.run().get("drafted") == 1

    assert _first_draft_asset_name(tmp_path) == "Approved slot day"
    sidecar = json.loads(next((tmp_path / "draft-assets").glob("*.json")).read_text(encoding="utf-8"))
    assert sidecar.get("title") == "Approved slot day"
    assert not re.match(r"^Draft [0-9a-f]{6}$", _first_draft_asset_name(tmp_path))


def test_draft_caption_name_uses_caption_when_no_calendar_title(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)
    mock_result = {
        "ok": True,
        "survivors": [{"body": "Opening line for the post\nMore detail below."}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        draft_assets.run()

    assert _first_draft_asset_name(tmp_path) == "Opening line for the post"
    assert not re.match(r"^Draft [0-9a-f]{6}$", _first_draft_asset_name(tmp_path))


def test_gbp_draft_name_from_post_body(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_gbp", item_id=item_id)

    with patch("_lib.gbp_daily_poster.build_daily_plan") as mock_plan:
        mock_plan.return_value = {
            "ok": True,
            "plan_id": "plan-test",
            "posts": [{"body": "GBP headline for the week"}],
            "publish": {"skipped": "publish=False (dry-run)"},
        }
        draft_assets.run()

    assert _first_draft_asset_name(tmp_path) == "GBP headline for the week"


def test_backfill_renames_legacy_draft_hex_names(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    asset_id = "draft-backfill01"
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    sidecar = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": asset_id,
        "campaign_id": "camp-stick",
        "brand_id": "stick",
        "source_inbox_item_id": "proposal:stick:prop-1",
        "action": "draft_caption",
        "created_at": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][asset_id] = {
        "name": "Draft bbffe7",
        "caption": "Backfilled from this caption",
        "approvalStatus": "draft",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-09-17T10:00:00Z", "rows": []}),
        encoding="utf-8",
    )

    draft_assets.run()

    saved = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert saved["campaigns"]["camp-stick"]["assets"][asset_id]["name"] == "Backfilled from this caption"


def test_unified_inbox_draft_hex_title_uses_caption(l5_app, tmp_path):
    from _lib import unified_inbox

    _seed_brands(tmp_path)
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"]["draft-hex"] = {
        "name": "Draft a1b2c3",
        "caption": "Unified inbox visible title",
        "approvalStatus": "draft",
        "platform": "instagram",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    inbox_row = {
        "campaignId": "camp-stick",
        "assetId": "draft-hex",
        "brand": "stick",
        "name": "Draft a1b2c3",
        "caption": "ignored",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    with patch(
        "_lib.intelligence.review_inbox",
        return_value={"pending": [inbox_row], "approved": [], "rejected": []},
    ):
        payload = unified_inbox.list_items(status="all", item_type="draft_asset", brand="stick")

    titles = [i["title"] for i in payload.get("items") or [] if i["meta"]["asset_id"] == "draft-hex"]
    assert titles == ["Unified inbox visible title"]


def test_draft_assets_diagnostics_path_allowed(l5_app):
    from _lib.jobs.output_file import is_path_allowed
    from _lib.jobs.registry import JOBS

    assert "draft_assets" in JOBS
    assert is_path_allowed("draft_assets", "draft-assets/_diagnostics/last-error.json") is True
