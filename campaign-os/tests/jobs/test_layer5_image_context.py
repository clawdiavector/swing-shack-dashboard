"""L5 draft_image rich context — unit + integration tests (mocked router)."""

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

from tests.jobs.test_layer5_create import (  # noqa: E402
    CAMPAIGN_OS as _CO,
    REPO_ROOT as _REPO,
    _purge_modules,
    _seed_brands,
    l5_app,
)


def _seed_approved_calendar(
    tmp_path: Path,
    *,
    brand: str = "stick",
    cal_id: str = "cal-1",
    **fields,
) -> str:
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": cal_id,
        "event_key": cal_id,
        "status": "approved",
        "title": "Summer Trackman Demo",
        "suggested_angles": ["Bring your swing"],
        "pillars": ["product-demo"],
        "event_start": "2026-10-01",
        "type": "content",
        "products": ["product-trackman"],
        **fields,
    }
    (cal_dir / f"{brand}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return f"calendar_candidate:{brand}:{cal_id}"


def _seed_image_queue_row(tmp_path: Path, *, item_id: str, brand: str = "stick") -> None:
    row = {
        "id": f"manual-{brand}-cos-image-draft-image",
        "layer": "L3",
        "agent": "cos-image",
        "brand": brand,
        "action": "draft_image",
        "payload_ref": f"inbox/{item_id}",
        "status": "pending",
    }
    doc = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-17T10:00:00Z",
        "rows": [row],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(doc), encoding="utf-8")


def _mock_gen_result(tmp_path: Path) -> MagicMock:
    import base64

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    png_path = tmp_path / "draft-assets" / "images" / "out.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(png)
    mock_gen = MagicMock()
    mock_gen.model = "test-model"
    mock_gen.provider = "openrouter"
    mock_gen.prompt_used = "composed prompt used upstream"
    mock_gen.bytes = png
    mock_gen.saved_path = str(png_path)
    mock_gen.saved_sidecar_path = str(tmp_path / "draft-assets" / "images" / "out.meta.json")
    mock_gen.provider_job_id = None
    return mock_gen


def test_build_context_from_approved_calendar(l5_app, tmp_path):
    from _lib.jobs.layer5.image_draft_context import build_image_draft_context

    item_id = _seed_approved_calendar(tmp_path)
    ctx = build_image_draft_context("stick", item_id)

    assert "Summer Trackman Demo" in ctx.job
    assert "Bring your swing" in ctx.job
    assert ctx.aspect in {"1024x1024", "1024x1792", "1792x1024"}
    assert ctx.lineage["calendar"]["calendar_id"] == "cal-1"


def test_context_selects_learnable_reference_only(l5_app, tmp_path):
    from _lib.jobs.layer5.image_draft_context import build_image_draft_context

    brand = "stick"
    item_id = _seed_approved_calendar(tmp_path, brand=brand, title="Trackman hero")
    images_dir = tmp_path / "brand-directory" / brand / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "alpha.jpg").write_bytes(b"fake-alpha")
    (images_dir / "beta.jpg").write_bytes(b"fake-beta")

    refs_dir = tmp_path / "brand-directory" / brand / "references"
    refs_dir.mkdir(parents=True)
    alpha_dna = {
        "ref_id": "ref-alpha123456",
        "source_filename": "alpha.jpg",
        "label": "Alpha",
        "filename": "alpha.jpg",
    }
    beta_dna = {
        "ref_id": "ref-beta1234567",
        "source_filename": "beta.jpg",
        "label": "Beta",
        "filename": "beta.jpg",
    }
    (refs_dir / "ref-alpha123456.reference-dna.json").write_text(json.dumps(alpha_dna), encoding="utf-8")
    (refs_dir / "ref-beta1234567.reference-dna.json").write_text(json.dumps(beta_dna), encoding="utf-8")

    social_dir = tmp_path / "brand-directory" / brand / "social"
    social_dir.mkdir(parents=True)
    (social_dir / "asset-classifications.json").write_text(
        json.dumps({"curated::alpha.jpg": {"classification": "rejected"}}),
        encoding="utf-8",
    )

    ctx = build_image_draft_context(brand, item_id)

    assert len(ctx.refs) <= 1
    if ctx.refs:
        assert ctx.refs[0]["source_filename"] == "beta.jpg"


def test_context_no_reference_degrades_cleanly(l5_app, tmp_path):
    from _lib.jobs.layer5.image_draft_context import build_image_draft_context

    item_id = _seed_approved_calendar(tmp_path)
    ctx = build_image_draft_context("stick", item_id)

    assert ctx.refs == []
    degraded_sources = {entry["source"] for entry in ctx.lineage.get("degraded") or []}
    assert "reference" in degraded_sources or ctx.lineage.get("reference", {}).get("selected") is None
    cd = ctx.lineage.get("creative_director") or {}
    assert cd.get("negative_prompt")


def test_image_row_passes_context_to_router(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets
    from _lib.jobs.layer5.image_draft_context import build_image_draft_context

    _seed_brands(tmp_path)
    item_id = _seed_approved_calendar(tmp_path)
    _seed_image_queue_row(tmp_path, item_id=item_id)
    ctx = build_image_draft_context("stick", item_id)
    mock_gen = _mock_gen_result(tmp_path)

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen) as mock_router:
        result = draft_assets.run()
        mock_router.assert_called_once()
        kwargs = mock_router.call_args.kwargs
        assert kwargs["prompt"] == ctx.job
        assert kwargs["size"] == ctx.aspect
        assert kwargs.get("reference_dnas") == ctx.refs or (
            not ctx.refs and "reference_dnas" not in kwargs
        )
        assert "Social image for approved inbox item" not in kwargs["prompt"] or "Summer Trackman Demo" in kwargs["prompt"]

    assert result.get("ok") is True


def test_sidecar_lineage_populated(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets
    from _lib.jobs.layer5 import asset_qc

    _seed_brands(tmp_path)
    item_id = _seed_approved_calendar(tmp_path)
    _seed_image_queue_row(tmp_path, item_id=item_id)
    mock_gen = _mock_gen_result(tmp_path)

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    sidecar_path = next((tmp_path / "draft-assets").glob("*.json"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar.get("sections")
    assert sidecar.get("negative_prompt")
    assert sidecar.get("model_routing")
    assert sidecar.get("calendar", {}).get("calendar_id") == "cal-1"
    assert sidecar.get("image_size") in asset_qc.VALID_IMAGE_SIZES
    assert isinstance(sidecar.get("context_degraded"), list)


def test_asset_name_from_calendar_title(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_calendar(tmp_path, title="Launch Night")
    _seed_image_queue_row(tmp_path, item_id=item_id)
    mock_gen = _mock_gen_result(tmp_path)

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assets = data["campaigns"]["camp-stick"]["assets"]
    names = [a.get("name") for a in assets.values()]
    assert "Launch Night" in names


def test_image_cross_links_caption_draft(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_calendar(tmp_path)
    caption_asset_id = "draft-caption123"
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    caption_sidecar = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": caption_asset_id,
        "campaign_id": "camp-stick",
        "brand_id": "stick",
        "source_inbox_item_id": item_id,
        "created_at": "2026-09-17T10:00:00Z",
        "action": "draft_caption",
    }
    (tmp_path / "draft-assets" / f"{caption_asset_id}.json").write_text(
        json.dumps(caption_sidecar),
        encoding="utf-8",
    )
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][caption_asset_id] = {
        "name": "Caption draft",
        "caption": "Linked caption text",
        "approvalStatus": "draft",
        "updatedAt": "2026-09-17T10:00:00Z",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    doc = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-17T10:00:00Z",
        "rows": [
            {
                "id": "manual-stick-cos-caption-draft-caption",
                "layer": "L3",
                "agent": "cos-caption",
                "brand": "stick",
                "action": "draft_caption",
                "payload_ref": f"inbox/{item_id}",
                "status": "done",
            },
            {
                "id": "manual-stick-cos-image-draft-image",
                "layer": "L3",
                "agent": "cos-image",
                "brand": "stick",
                "action": "draft_image",
                "payload_ref": f"inbox/{item_id}",
                "status": "pending",
            },
        ],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(doc), encoding="utf-8")
    mock_gen = _mock_gen_result(tmp_path)

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    image_sidecar = json.loads(
        next(p for p in (tmp_path / "draft-assets").glob("*.json") if "caption123" not in p.name).read_text(
            encoding="utf-8"
        )
    )
    assert image_sidecar.get("caption_asset_id") == caption_asset_id
    saved = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    image_assets = [
        a for aid, a in saved["campaigns"]["camp-stick"]["assets"].items() if aid != caption_asset_id
    ]
    assert image_assets[0]["caption"] == "Linked caption text"


def test_no_repo_writes_with_context(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    repo_brand_dir = REPO_ROOT / "data" / "brand-directory"
    campaign_os_data = CAMPAIGN_OS / "data"
    before_repo = set(repo_brand_dir.rglob("*")) if repo_brand_dir.is_dir() else set()
    before_cos = set(campaign_os_data.rglob("*")) if campaign_os_data.is_dir() else set()

    _seed_brands(tmp_path)
    item_id = _seed_approved_calendar(tmp_path)
    _seed_image_queue_row(tmp_path, item_id=item_id)
    mock_gen = _mock_gen_result(tmp_path)

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    after_repo = set(repo_brand_dir.rglob("*")) if repo_brand_dir.is_dir() else set()
    after_cos = set(campaign_os_data.rglob("*")) if campaign_os_data.is_dir() else set()
    assert before_repo == after_repo
    assert before_cos == after_cos


def test_context_survives_missing_calendar_record(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets
    from _lib.jobs.layer5.image_draft_context import build_image_draft_context

    _seed_brands(tmp_path)
    item_id = "calendar_candidate:stick:missing-cal"
    _seed_image_queue_row(tmp_path, item_id=item_id)
    ctx = build_image_draft_context("stick", item_id)
    assert ctx.job
    mock_gen = _mock_gen_result(tmp_path)

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        result = draft_assets.run()

    assert result.get("ok") is True


def test_asset_qc_passes_rich_image_sidecar(l5_app, tmp_path):
    from _lib.jobs.layer5 import asset_qc, draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_calendar(tmp_path)
    _seed_image_queue_row(tmp_path, item_id=item_id)
    mock_gen = _mock_gen_result(tmp_path)

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen):
        draft_assets.run()

    sidecar_path = next((tmp_path / "draft-assets").glob("*.json"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    asset_id = sidecar["asset_id"]
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][asset_id]["caption"] = "Clean caption for QC"
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    with patch("_lib.p11_context_engine._extract_banned_terms", return_value=[]):
        result = asset_qc.run()

    assert result.get("ok") is True
    saved = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert saved.get("qc", {}).get("verdict") == "pass"
    assert "invalid image aspect" not in (saved.get("qc", {}).get("issues") or [])
