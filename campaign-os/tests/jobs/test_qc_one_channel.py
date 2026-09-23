"""QC pixel gate + one primary_channel sandbox enqueue."""

from __future__ import annotations

import json
from pathlib import Path

from tests.jobs.test_layer5_create import (  # noqa: E402
    _seed_brands,
    l5_app,
)


def _seed_calendar(
    tmp_path: Path,
    *,
    brand: str,
    cal_id: str,
    title: str,
    primary_channel: str,
    event_date: str = "2026-09-28",
) -> str:
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": cal_id,
        "event_key": cal_id,
        "status": "approved",
        "title": title,
        "event_date": event_date,
        "event_start": event_date,
        "primary_channel": primary_channel,
        "type": "moment",
    }
    (cal_dir / f"{brand}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return f"calendar_candidate:{brand}:{cal_id}"


def _seed_qc_image_asset(
    tmp_path: Path,
    *,
    brand: str,
    asset_id: str,
    campaign_id: str,
    inbox_item_id: str,
    caption: str,
    png_bytes: bytes,
    platform: str = "facebook",
    lodged_title: str = "",
) -> None:
    img_dir = tmp_path / "draft-assets" / "images" / brand / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / "gen-test.png"
    img_path.write_bytes(png_bytes)

    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    sidecar = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": asset_id,
        "campaign_id": campaign_id,
        "brand_id": brand,
        "source_inbox_item_id": inbox_item_id,
        "created_at": "2026-09-17T12:00:00Z",
        "action": "draft_image",
        "cost_estimate_usd": 0.04,
        "title": lodged_title or None,
    }
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")

    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data.setdefault("campaigns", {}).setdefault(campaign_id, {"assets": {}})
    data["campaigns"][campaign_id]["assets"][asset_id] = {
        "name": "Weekend fittings",
        "caption": caption,
        "approvalStatus": "draft",
        "platform": platform,
        "image_path": str(img_path),
        "image_url": f"/brand-images/{brand}/gen-test.png",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")


def test_asset_qc_skips_enqueue_when_png_empty(l5_app, tmp_path, monkeypatch):
    from _lib import publish_sandbox
    from _lib.jobs.layer5 import asset_qc

    monkeypatch.delenv("CAMPAIGN_OS_L6_ENQUEUE", raising=False)
    _seed_brands(tmp_path)
    publish_sandbox.ensure_sandbox_layout()

    inbox_id = _seed_calendar(
        tmp_path,
        brand="swing-shack",
        cal_id="cal-fb-1",
        title="Slots filling for weekend fittings",
        primary_channel="facebook",
    )
    asset_id = "draft-empty-png"
    _seed_qc_image_asset(
        tmp_path,
        brand="swing-shack",
        asset_id=asset_id,
        campaign_id="camp-ss",
        inbox_item_id=inbox_id,
        caption="Caption with empty PNG",
        png_bytes=b"",
    )

    result = asset_qc.run()
    assert result.get("ok") is True
    assert result.get("failed") == 1
    queue_rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
    assert queue_rows == []


def test_asset_qc_skips_enqueue_when_png_missing(l5_app, tmp_path, monkeypatch):
    from _lib import publish_sandbox
    from _lib.jobs.layer5 import asset_qc

    monkeypatch.delenv("CAMPAIGN_OS_L6_ENQUEUE", raising=False)
    _seed_brands(tmp_path)
    publish_sandbox.ensure_sandbox_layout()

    asset_id = "draft-missing-png"
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
        "name": "Caption only",
        "caption": "No image on disk",
        "approvalStatus": "draft",
        "updatedAt": "2026-09-17T12:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    asset_qc.run()
    queue_rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
    assert queue_rows == []


def test_facebook_lodge_one_sandbox_row_with_calendar_title(l5_app, tmp_path, monkeypatch):
    from _lib import publish_sandbox
    from _lib.jobs.layer5 import asset_qc

    monkeypatch.delenv("CAMPAIGN_OS_L6_ENQUEUE", raising=False)
    _seed_brands(tmp_path)
    publish_sandbox.ensure_sandbox_layout()

    cal_title = "Slots filling for weekend fittings"
    inbox_id = _seed_calendar(
        tmp_path,
        brand="swing-shack",
        cal_id="cal-fb-weekend",
        title=cal_title,
        primary_channel="facebook",
        event_date="2026-09-27",
    )
    asset_id = "draft-fb-one"
    _seed_qc_image_asset(
        tmp_path,
        brand="swing-shack",
        asset_id=asset_id,
        campaign_id="camp-ss",
        inbox_item_id=inbox_id,
        caption="Fitting season caption",
        png_bytes=b"\x89PNG\r\n\x1a\n" + b"x" * 64,
        platform="facebook",
        lodged_title=cal_title,
    )

    result = asset_qc.run()
    assert result.get("ok") is True
    assert result.get("passed") == 1
    queue_rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
    assert len(queue_rows) == 1
    row = queue_rows[0]
    assert row.get("platform") == "facebook"
    assert row.get("brand_id") == "swing-shack"
    assert row.get("lodged_title") == cal_title
    assert row.get("event_date") == "2026-09-27"
    assert row.get("idempotency_key") == f"qc-{asset_id}-facebook"


def test_generate_image_with_persistence_skips_empty_bytes(l5_app, tmp_path, monkeypatch):
    from _lib import image_gen_router

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    empty = image_gen_router.GenResult(
        bytes=b"",
        mime="image/png",
        model="krea/test",
        provider="krea",
        cost_estimate_usd=0.0,
        prompt_used="test",
        provider_job_id="job-empty-1",
    )

    def _fake_generate(*_args, **_kwargs):
        return empty

    monkeypatch.setattr(image_gen_router, "generate_image", _fake_generate)
    result = image_gen_router.generate_image_with_persistence(
        "prompt",
        brand_id="stick",
        output_base=str(tmp_path / "draft-assets" / "images"),
    )
    assert result.saved_path is None
    assert result.saved_sidecar_path
    sidecar = json.loads(Path(result.saved_sidecar_path).read_text(encoding="utf-8"))
    assert sidecar.get("bytes_size") == 0
    assert sidecar.get("provider_job_id") == "job-empty-1"
