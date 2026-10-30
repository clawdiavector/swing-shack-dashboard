"""The 07:15 asset check never overrules a person, and finds lodged images (2026-10-30).

On live, a Swing Shack post Christelle approved on 29 Oct (Callaway Quantum
Mini, due 30 Oct) was flipped to rejected by the next morning's asset_qc run,
so it never went out. Three Stick drafts were rejected the same way. The check
failed them for two things that say nothing about the post:

  - "missing fields: schema": posts lodged ready-made (render_batch,
    action compose_post) never write that label;
  - "image file missing or empty": the composed image is served from
    /brand-images/<brand>/<file> but lives in draft-assets/images/<brand>/,
    which the check never looked in.

Now: an approved post is never rejected by the check (its finding is kept on
the sidecar for a person to see), a lodged post's image is found where it
lives, and a lodged sidecar without the schema label is not a fault. Real
problems on a draft still reject it.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.jobs.test_layer5_create import _seed_brands, l5_app  # noqa: F401

BRAND = "swing-shack"
CAMPAIGN = "swing-shack-calendar"


def _seed_lodged(tmp_path: Path, asset_id: str, *, approval: str, caption: str = "Book a bay. DM us.",
                 png: bytes = b"\x89PNG not empty") -> None:
    img_dir = tmp_path / "draft-assets" / "images" / BRAND
    img_dir.mkdir(parents=True, exist_ok=True)
    fname = f"composed-{asset_id}-instagram.png"
    if png is not None:
        (img_dir / fname).write_bytes(png)
    url = f"/brand-images/{BRAND}/{fname}"
    sidecar = {  # what render_batch writes for a lodged post: no "schema", no cost
        "action": "compose_post",
        "asset_id": asset_id,
        "brand_id": BRAND,
        "campaign_id": CAMPAIGN,
        "channels": ["instagram"],
        "composed": {"instagram": url},
        "created_at": "2026-10-29T09:00:00Z",
        "created_by": "campaign-os/render_batch",
        "image_url": url,
        "source_inbox_item_id": f"calendar_candidate:{BRAND}:cal-{asset_id}",
    }
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data.setdefault("campaigns", {}).setdefault(CAMPAIGN, {"assets": {}})
    data["campaigns"][CAMPAIGN].setdefault("assets", {})[asset_id] = {
        "name": asset_id, "caption": caption, "approvalStatus": approval, "platform": "instagram",
        "image_url": url, "composed": {"instagram": url}, "updatedAt": "2026-10-29T09:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")


def _asset(tmp_path: Path, asset_id: str) -> dict:
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    return data["campaigns"][CAMPAIGN]["assets"][asset_id]


def _qc(tmp_path: Path, asset_id: str) -> dict:
    return json.loads((tmp_path / "draft-assets" / f"{asset_id}.json").read_text(encoding="utf-8"))["qc"]


def _run(tmp_path, monkeypatch):
    from _lib.jobs.layer5 import asset_qc

    monkeypatch.setenv("CAMPAIGN_OS_L6_ENQUEUE", "0")
    _seed_brands(tmp_path, brand=BRAND, campaign_id=CAMPAIGN)
    return asset_qc


def test_a_lodged_post_with_its_image_passes(l5_app, tmp_path, monkeypatch):
    asset_qc = _run(tmp_path, monkeypatch)
    _seed_lodged(tmp_path, "ss-callaway-mini", approval="draft")
    assert asset_qc.run()["ok"] is True
    assert _asset(tmp_path, "ss-callaway-mini")["approvalStatus"] == "draft"
    assert _qc(tmp_path, "ss-callaway-mini")["verdict"] == "pass"


def test_an_approved_post_is_never_rejected_by_the_check(l5_app, tmp_path, monkeypatch):
    asset_qc = _run(tmp_path, monkeypatch)
    _seed_lodged(tmp_path, "ss-approved-bad", approval="approved", caption="[LLM unavailable: x]")
    asset_qc.run()
    asset = _asset(tmp_path, "ss-approved-bad")
    assert asset["approvalStatus"] == "approved"
    assert "rejectionReason" not in asset
    qc = _qc(tmp_path, "ss-approved-bad")
    assert qc["verdict"] == "fail"
    assert qc["kept_because"] == "approved by a person"


def test_a_draft_with_a_real_problem_is_still_rejected(l5_app, tmp_path, monkeypatch):
    asset_qc = _run(tmp_path, monkeypatch)
    _seed_lodged(tmp_path, "ss-draft-bad", approval="draft", caption="[LLM unavailable: x]")
    asset_qc.run()
    asset = _asset(tmp_path, "ss-draft-bad")
    assert asset["approvalStatus"] == "rejected"
    assert "placeholder caption" in asset["rejectionReason"]


def test_a_lodged_draft_whose_image_really_is_missing_is_still_rejected(l5_app, tmp_path, monkeypatch):
    asset_qc = _run(tmp_path, monkeypatch)
    _seed_lodged(tmp_path, "ss-no-image", approval="draft", png=None)
    asset_qc.run()
    asset = _asset(tmp_path, "ss-no-image")
    assert asset["approvalStatus"] == "rejected"
    assert asset["rejectionReason"] == "image file missing or empty"
