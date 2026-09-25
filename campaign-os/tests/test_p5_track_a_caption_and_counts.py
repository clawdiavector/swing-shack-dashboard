"""P5 Track A — caption brief fidelity and uncapped approved draft counts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _purge() -> None:
    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]


def _seed_calendar(
    tmp_path: Path,
    *,
    brand: str,
    cal_id: str,
    **fields,
) -> str:
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": cal_id,
        "event_key": cal_id,
        "status": "approved",
        "title": "Member Appreciation Evening",
        "suggested_angles": ["Celebrate our regulars"],
        "pillars": ["community"],
        "event_start": "2026-10-01",
        "type": "content",
        **fields,
    }
    (cal_dir / f"{brand}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return f"calendar_candidate:{brand}:{cal_id}"


def _seed_brands_and_campaign(tmp_path: Path, brand: str, campaign_id: str, assets: dict) -> None:
    (tmp_path / "brands.json").write_text(
        json.dumps({"brands": {brand: {"id": brand, "campaign_ids": [campaign_id]}}}),
        encoding="utf-8",
    )
    (tmp_path / "campaign-data.json").write_text(
        json.dumps(
            {
                "campaigns": {
                    campaign_id: {
                        "identity": {"name": "Test camp", "brand": brand},
                        "assets": assets,
                    }
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def inbox_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _purge()
    yield tmp_path
    _purge()


def test_caption_brief_subject_not_draft_or_coaching(inbox_env, tmp_path):
    from _lib.jobs.layer5.draft_assets import _caption_pipeline_payload
    from _lib.jobs.layer5.image_draft_context import build_image_draft_context
    from _lib.p11_context_engine import _detect_brief_subject

    cases = [
        ("stick", "cal-stick-p5", {"title": "Trackman Demo Night"}),
        (
            "swing-shack",
            "cal-shack-p5",
            {"title": "Fall League Registration", "suggested_angles": ["Sign up today"]},
        ),
    ]
    for brand, cal_id, fields in cases:
        item_id = _seed_calendar(tmp_path, brand=brand, cal_id=cal_id, **fields)
        ctx = build_image_draft_context(brand, item_id)
        payload = _caption_pipeline_payload(brand_id=brand, item_id=item_id, ctx=ctx)
        subject = _detect_brief_subject(
            payload["user_brief"],
            payload.get("service"),
            payload.get("product_id"),
        )
        assert subject not in ("draft", "coaching"), (brand, subject, payload["user_brief"])
        assert payload["n_candidates"] >= 6
        assert "Draft from approved inbox item" not in payload["user_brief"]


def test_unified_inbox_approved_total_not_capped_by_shelf_slice(inbox_env, tmp_path):
    from _lib import intelligence
    from _lib.unified_inbox import list_items

    brand = "stick"
    campaign_id = "camp-stick"
    assets = {}
    for i in range(25):
        aid = f"approved-{i:02d}"
        assets[aid] = {
            "name": f"Piece {i}",
            "caption": "Long approved caption " + ("x" * 130) + f" #{i}",
            "approvalStatus": "approved",
            "platform": "instagram",
            "updatedAt": f"2026-09-{10 + (i % 10):02d}T12:00:00Z",
        }
    _seed_brands_and_campaign(tmp_path, brand, campaign_id, assets)
    intelligence.set_request_brand(brand)

    payload = list_items(status="approved", item_type="draft_asset", brand=brand)
    assert payload["counts"]["approved"] == 25
    assert len(payload["items"]) == 20
    first_summary = payload["items"][0]["summary"]
    assert len(first_summary) > 120
