"""Serial complete-post — one moment's image before the next caption."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _purge_modules() -> None:
    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("_lib.jobs")
            or mod.startswith("_lib.")
            or mod == "_lib.unified_inbox"
            or mod == "_lib.intelligence"
            or mod == "_lib.llm_spend"
        ):
            del sys.modules[mod]


@pytest.fixture()
def l5_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "1.00")
    _purge_modules()
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    return app_module.app.test_client(), app_module, tmp_path


def _seed_brands(tmp_path: Path, brand: str = "stick", campaign_id: str = "camp-stick") -> None:
    (tmp_path / "brands.json").write_text(
        json.dumps(
            {
                "brands": {
                    brand: {
                        "id": brand,
                        "campaign_ids": [campaign_id],
                        "publish_channels": ["instagram", "facebook"],
                    }
                }
            }
        ),
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


def _seed_approved_proposal(tmp_path: Path, brand: str, pid: str) -> str:
    (tmp_path / "proposals").mkdir(parents=True, exist_ok=True)
    row = {
        "id": pid,
        "brand_id": brand,
        "title": f"Proposal {pid}",
        "status": "approved",
        "approved_at": "2026-09-17T10:00:00Z",
    }
    path = tmp_path / "proposals" / "pending.jsonl"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(existing + json.dumps(row) + "\n", encoding="utf-8")
    return f"proposal:{brand}:{pid}"


def _seed_queue_rows(tmp_path: Path, rows: list[dict]) -> None:
    doc = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-17T10:00:00Z",
        "rows": rows,
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(doc), encoding="utf-8")


def _image_mock(tmp_path: Path, name: str = "gen-a.png") -> MagicMock:
    img_dir = tmp_path / "draft-assets" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / name
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    mock_gen = MagicMock()
    mock_gen.model = "test-model"
    mock_gen.provider = "openrouter"
    mock_gen.saved_path = str(img_path)
    mock_gen.provider_job_id = None
    mock_gen.bytes = img_path.read_bytes()
    return mock_gen


def _sidecars_for_item(tmp_path: Path, item_id: str) -> list[dict]:
    out = []
    for path in (tmp_path / "draft-assets").glob("*.json"):
        sidecar = json.loads(path.read_text(encoding="utf-8"))
        if sidecar.get("source_inbox_item_id") == item_id:
            out.append(sidecar)
    return out


def test_one_tick_completes_moment_a_only(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_a = _seed_approved_proposal(tmp_path, "stick", "prop-a")
    item_b = _seed_approved_proposal(tmp_path, "stick", "prop-b")
    _seed_queue_rows(
        tmp_path,
        [
            {
                "id": "q-a-cap",
                "brand": "stick",
                "action": "draft_caption",
                "payload_ref": f"inbox/{item_a}",
                "status": "pending",
            },
            {
                "id": "q-a-img",
                "brand": "stick",
                "action": "draft_image",
                "payload_ref": f"inbox/{item_a}",
                "status": "pending",
            },
            {
                "id": "q-b-cap",
                "brand": "stick",
                "action": "draft_caption",
                "payload_ref": f"inbox/{item_b}",
                "status": "pending",
            },
            {
                "id": "q-b-img",
                "brand": "stick",
                "action": "draft_image",
                "payload_ref": f"inbox/{item_b}",
                "status": "pending",
            },
        ],
    )

    captions = {
        item_a: {"ok": True, "survivors": [{"body": "Caption A"}], "observability": {"provider": "openai"}},
        item_b: {"ok": True, "survivors": [{"body": "Caption B"}], "observability": {"provider": "openai"}},
    }

    def fake_caption(payload):
        brief = payload.get("user_brief") or ""
        if item_a in brief:
            return captions[item_a]
        if item_b in brief:
            return captions[item_b]
        return captions[item_a]

    mock_gen = _image_mock(tmp_path)

    with patch("_lib.p11_context_engine.run_caption_pipeline", side_effect=fake_caption), patch(
        "_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen
    ):
        result = draft_assets.run()

    assert result.get("ok") is True
    sidecars_a = _sidecars_for_item(tmp_path, item_a)
    actions_a = {s.get("action") for s in sidecars_a}
    assert "draft_caption" in actions_a
    assert "draft_image" in actions_a
    assert draft_assets._moment_has_image("stick", item_a)

    assert _sidecars_for_item(tmp_path, item_b) == []
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    b_rows = [r for r in queue["rows"] if item_b in str(r.get("payload_ref"))]
    assert all(r.get("status") == "pending" for r in b_rows)


def test_cap_mid_image_does_not_caption_moment_b(l5_app, tmp_path, monkeypatch):
    from _lib.jobs.layer5 import draft_assets

    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "0.05")
    _purge_modules()
    from _lib import llm_spend

    llm_spend.record(0.04, route="seed", kind="text")

    _seed_brands(tmp_path)
    item_a = _seed_approved_proposal(tmp_path, "stick", "prop-cap-a")
    item_b = _seed_approved_proposal(tmp_path, "stick", "prop-cap-b")
    _seed_queue_rows(
        tmp_path,
        [
            {
                "id": "cap-a-cap",
                "brand": "stick",
                "action": "draft_caption",
                "payload_ref": f"inbox/{item_a}",
                "status": "pending",
            },
            {
                "id": "cap-a-img",
                "brand": "stick",
                "action": "draft_image",
                "payload_ref": f"inbox/{item_a}",
                "status": "pending",
            },
            {
                "id": "cap-b-cap",
                "brand": "stick",
                "action": "draft_caption",
                "payload_ref": f"inbox/{item_b}",
                "status": "pending",
            },
        ],
    )

    mock_result = {
        "ok": True,
        "survivors": [{"body": "Caption before cap"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }

    def fake_check(kind, est):
        if kind == "image":
            return False, "daily LLM spend cap reached"
        return True, ""

    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result), patch(
        "_lib.llm_spend.check", side_effect=fake_check
    ):
        result = draft_assets.run()

    assert result.get("ok") is False
    assert result.get("error") == "daily LLM spend cap reached"
    assert _sidecars_for_item(tmp_path, item_b) == []
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    b_row = next(r for r in queue["rows"] if item_b in str(r.get("payload_ref")))
    assert b_row.get("status") == "pending"


def test_caption_only_pending_omitted_from_list_items(l5_app, tmp_path):
    from _lib import unified_inbox

    _seed_brands(tmp_path)
    asset_id = "draft-caption-only"
    sidecar = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": asset_id,
        "campaign_id": "camp-stick",
        "brand_id": "stick",
        "source_inbox_item_id": "proposal:stick:x",
        "created_at": "2026-09-17T12:00:00Z",
        "action": "draft_caption",
    }
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")

    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][asset_id] = {
        "name": "Caption only",
        "caption": "No image yet",
        "approvalStatus": "draft",
        "platform": "instagram",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    data["campaigns"]["camp-stick"]["assets"]["draft-with-image"] = {
        "name": "Complete draft",
        "caption": "Has pixels",
        "approvalStatus": "draft",
        "platform": "instagram",
        "image_url": "/brand-images/stick/complete.png",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    payload = unified_inbox.list_items(brand="stick", item_type="draft_asset", status="pending")
    asset_ids = [i.get("meta", {}).get("asset_id") for i in payload.get("items") or []]
    assert asset_id not in asset_ids
    assert "draft-with-image" in asset_ids


def test_gbp_draft_still_listed(l5_app, tmp_path):
    from _lib import unified_inbox
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    asset_id = "draft-gbp-only"
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][asset_id] = {
        "name": "GBP post",
        "caption": "Local update",
        "approvalStatus": "draft",
        "platform": "gbp",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    payload = unified_inbox.list_items(brand="stick", item_type="draft_asset", status="pending")
    asset_ids = [i.get("meta", {}).get("asset_id") for i in payload.get("items") or []]
    assert asset_id in asset_ids

    draft_assets.run()
    saved = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert saved["campaigns"]["camp-stick"]["assets"][asset_id]["approvalStatus"] == "draft"


def test_shelf_asset_with_image_not_rejected(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    asset_id = "shelf-takomo"
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][asset_id] = {
        "name": "Campaign file",
        "caption": "From file",
        "approvalStatus": "draft",
        "platform": "instagram",
        "visualUrl": "/media/takomo/hero.jpg",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    draft_assets.run()
    saved = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert saved["campaigns"]["camp-stick"]["assets"][asset_id]["approvalStatus"] == "draft"


def test_cleanup_is_idempotent(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    asset_id = "draft-reject-me"
    sidecar = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": asset_id,
        "campaign_id": "camp-stick",
        "brand_id": "stick",
        "source_inbox_item_id": "proposal:stick:orphan",
        "created_at": "2026-09-17T12:00:00Z",
        "action": "draft_caption",
    }
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][asset_id] = {
        "name": "Orphan caption",
        "caption": "No image",
        "approvalStatus": "draft",
        "platform": "instagram",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-09-17T10:00:00Z", "rows": []}),
        encoding="utf-8",
    )

    first = draft_assets.run()
    second = draft_assets.run()
    assert first.get("rejected") == 1
    assert second.get("rejected", 0) == 0
