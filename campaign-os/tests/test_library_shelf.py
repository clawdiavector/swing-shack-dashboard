"""Library shelf — read-only drafts, sandbox, templates aggregate."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from _lib.library_shelf import build_library_shelf, caption_present


@pytest.fixture(autouse=True)
def _scratch_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "publish-sandbox").mkdir(parents=True, exist_ok=True)
    yield


def test_caption_present_predicate():
    assert caption_present("  hello  ") is True
    assert caption_present("") is False
    assert caption_present(None) is False


def test_swing_shack_templates_lane_count():
    payload = build_library_shelf("swing-shack")
    assert payload["brand_id"] == "swing-shack"
    templates = payload.get("templates") or []
    assert len(templates) == 9


def test_stick_service_frame_undeclared_refs():
    payload = build_library_shelf("stick")
    templates = {t["template_id"]: t for t in payload.get("templates") or []}
    frame = templates.get("stick-service-frame")
    assert frame is not None
    assert frame.get("references_undeclared") is True
    disk = [r for r in frame.get("reference_images") or [] if r.get("provenance") == "disk"]
    assert len(disk) >= 1


def test_bag_drop_empty_templates_ok():
    payload = build_library_shelf("bag-drop")
    assert payload["counts"]["templates"]["total"] == 0


def test_invalid_brand_raises():
    with pytest.raises(ValueError):
        build_library_shelf("not-a-brand-id-xyz")


def test_sandbox_dispatched_row(tmp_path):
    brand = "swing-shack"
    qpath = tmp_path / "publish-sandbox" / "queue.jsonl"
    rpath = tmp_path / "publish-sandbox" / "receipts.jsonl"
    row = {
        "brand_id": brand,
        "queue_id": "q-dispatch-1",
        "idempotency_key": "qc-libtest-asset-instagram",
        "platform": "instagram",
        "status": "dispatched",
        "caption_preview": "Sandbox caption for library test",
        "sandbox_post_id": "sb-post-libtest",
        "dispatched_at": "2026-09-30T12:00:00Z",
        "human_approved": True,
    }
    qpath.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rec = dict(row)
    rpath.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    payload = build_library_shelf(brand, view="sandbox")
    sandbox = payload.get("sandbox") or []
    assert any(r.get("status") == "dispatched" and r.get("sandbox_post_id") for r in sandbox)


def test_receipt_only_row(tmp_path):
    brand = "stick"
    rpath = tmp_path / "publish-sandbox" / "receipts.jsonl"
    rec = {
        "brand_id": brand,
        "idempotency_key": "qc-orphan-receipt-only-instagram",
        "platform": "instagram",
        "sandbox_post_id": "sb-post-receipt-only",
        "dispatched_at": "2026-09-30T11:00:00Z",
        "caption_preview": "Receipt without queue",
    }
    rpath.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    payload = build_library_shelf(brand, view="sandbox")
    sandbox = payload.get("sandbox") or []
    assert any(r.get("receipt_only") is True for r in sandbox)


def test_caption_only_draft_in_lane(tmp_path, monkeypatch):
    brand = "swing-shack"
    aid = "lib-caption-only-test"
    sidecar = {
        "asset_id": aid,
        "brand_id": brand,
        "campaign_id": "camp-test",
        "action": "draft_caption",
        "source_inbox_item_id": "calendar_candidate:swing-shack:cal-lib-1",
        "created_at": "2026-09-30T10:00:00Z",
    }
    (tmp_path / "draft-assets" / f"{aid}.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )
    camp = {
        "campaigns": {
            "camp-test": {
                "assets": {
                    aid: {
                        "caption": "Caption only draft body",
                        "approvalStatus": "draft",
                        "updatedAt": "2026-09-30T10:00:00Z",
                    }
                }
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")
    payload = build_library_shelf(brand, view="drafts")
    drafts = payload.get("drafts") or []
    match = [d for d in drafts if d.get("asset_id") == aid]
    assert len(match) == 1
    assert match[0].get("caption_present") is True
    assert match[0].get("image_present") is False


def test_counts_caption_balance():
    payload = build_library_shelf("stick")
    for lane in ("drafts", "sandbox"):
        c = payload["counts"][lane]
        assert c["with_caption"] + c["without_caption"] == c["returned"]
