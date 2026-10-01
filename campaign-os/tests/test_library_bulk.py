"""Library bulk archive/delete — drafts and sandbox queue rows."""

from __future__ import annotations

import json

import pytest

from _lib.library_shelf import apply_library_bulk, build_library_shelf


@pytest.fixture(autouse=True)
def _scratch_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "publish-sandbox").mkdir(parents=True, exist_ok=True)
    (tmp_path / "intelligence" / "marketing-calendar").mkdir(parents=True, exist_ok=True)
    yield


def test_bulk_sandbox_delete_removes_queue_row(tmp_path):
    brand = "swing-shack"
    qpath = tmp_path / "publish-sandbox" / "queue.jsonl"
    key = "qc-bulk-del-instagram"
    row = {
        "brand_id": brand,
        "queue_id": "q-bulk-1",
        "idempotency_key": key,
        "platform": "instagram",
        "status": "pending",
        "caption_preview": "Delete me",
        "human_approved": False,
    }
    qpath.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rpath = tmp_path / "publish-sandbox" / "receipts.jsonl"
    rpath.write_text("", encoding="utf-8")

    out = apply_library_bulk(brand, lane="sandbox", action="delete", ids=[key])
    assert out["applied_count"] == 1
    assert qpath.read_text(encoding="utf-8").strip() == ""
    payload = build_library_shelf(brand, view="sandbox")
    assert not any(_sandbox_key(r) == key for r in payload.get("sandbox") or [])


def test_bulk_sandbox_skips_receipt_only(tmp_path):
    brand = "stick"
    rpath = tmp_path / "publish-sandbox" / "receipts.jsonl"
    key = "qc-receipt-only-bulk"
    rec = {
        "brand_id": brand,
        "idempotency_key": key,
        "platform": "instagram",
        "sandbox_post_id": "sb-only",
        "dispatched_at": "2026-09-30T11:00:00Z",
        "caption_preview": "Receipt only",
    }
    rpath.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    (tmp_path / "publish-sandbox" / "queue.jsonl").write_text("", encoding="utf-8")

    out = apply_library_bulk(brand, lane="sandbox", action="delete", ids=[key])
    assert out["applied_count"] == 0
    assert out["skipped"][0]["reason"] == "receipt_only"
    assert rpath.read_text(encoding="utf-8").strip() != ""


def test_bulk_draft_archive(tmp_path):
    brand = "swing-shack"
    aid = "lib-bulk-archive"
    sidecar = {
        "asset_id": aid,
        "brand_id": brand,
        "campaign_id": "camp-bulk",
        "created_at": "2026-09-30T10:00:00Z",
    }
    (tmp_path / "draft-assets" / f"{aid}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    camp = {
        "campaigns": {
            "camp-bulk": {
                "assets": {
                    aid: {
                        "caption": "Archive me",
                        "approvalStatus": "pending",
                        "updatedAt": "2026-09-30T10:00:00Z",
                    }
                }
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")

    out = apply_library_bulk(brand, lane="drafts", action="archive", ids=[aid])
    assert out["applied_count"] == 1
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert data["campaigns"]["camp-bulk"]["assets"][aid]["approvalStatus"] == "archived"


def test_bulk_draft_delete_keeps_calendar_moment(tmp_path):
    brand = "swing-shack"
    cal_id = "cal-bulk-survive"
    cal_path = tmp_path / "intelligence" / "marketing-calendar" / f"{brand}.jsonl"
    moment = {
        "calendar_id": cal_id,
        "brand_id": brand,
        "type": "moment",
        "status": "candidate",
        "title": "Planning slot stays",
    }
    cal_path.write_text(json.dumps(moment) + "\n", encoding="utf-8")

    aid = "lib-bulk-delete"
    sidecar = {
        "asset_id": aid,
        "brand_id": brand,
        "campaign_id": "camp-del",
        "source_inbox_item_id": f"calendar_candidate:{brand}:{cal_id}",
        "created_at": "2026-09-30T10:00:00Z",
    }
    (tmp_path / "draft-assets" / f"{aid}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    camp = {
        "campaigns": {
            "camp-del": {
                "assets": {
                    aid: {
                        "caption": "Delete me",
                        "approvalStatus": "pending",
                        "updatedAt": "2026-09-30T10:00:00Z",
                    }
                }
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")

    out = apply_library_bulk(brand, lane="drafts", action="delete", ids=[aid])
    assert out["applied_count"] == 1
    assert not (tmp_path / "draft-assets" / f"{aid}.json").is_file()
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert aid not in data["campaigns"]["camp-del"]["assets"]
    cal_lines = cal_path.read_text(encoding="utf-8").strip().splitlines()
    assert any(json.loads(line).get("calendar_id") == cal_id for line in cal_lines)


def _sandbox_key(row: dict) -> str:
    return str(row.get("idempotency_key") or row.get("queue_id") or "")
