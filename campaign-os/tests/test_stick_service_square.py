"""Stick service-square template: canvas, variants, selection, goldens."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id, load_archetypes_doc

ROOT = Path(__file__).resolve().parents[2]
STICK = ROOT / "data" / "brand-directory" / "stick"
PACK = STICK / "templates/service-square"
GOLDEN_LAB = PACK / "golden/render-lab.png"
GOLDEN_AVODA = PACK / "golden/render-avoda.png"


@pytest.fixture(scope="module")
def square() -> dict:
    arch = archetype_by_id("stick", "stick-service-square")
    assert arch
    return arch


def test_archetype_and_canvas_present(square: dict):
    doc = load_archetypes_doc("stick")
    ids = {a["id"] for a in doc.get("archetypes") or [] if isinstance(a, dict)}
    assert "stick-service-square" in ids
    assert "ig_square" in (doc.get("canvases") or {})


def test_chevrons_asset_exists():
    path = PACK / "assets/chevrons.png"
    assert path.is_file() and path.stat().st_size > 500


def test_spec_json_matches_archetype(square: dict):
    spec = json.loads((PACK / "spec.json").read_text(encoding="utf-8"))
    assert spec["id"] == square["id"]
    assert spec["zones"].keys() == square["zones"].keys()


def _compose(caption_hook: str, variant: str) -> bytes:
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=archetype_by_id("stick", "stick-service-square"),
        channels=["instagram"],
        fields={"caption_hook": caption_hook, "variant": variant},
        photo_bytes=None,
    )
    return out["instagram"]


def test_lab_compose_dimensions(square: dict):
    png = _compose("Our lab builds clubs to your numbers and your swing.", "lab")
    im = Image.open(io.BytesIO(png))
    assert im.size == (1080, 1080)
    assert len(png) > 5000


def test_avoda_compose_dimensions(square: dict):
    png = _compose("COACHING stick", "avoda")
    im = Image.open(io.BytesIO(png))
    assert im.size == (1080, 1080)
    assert len(png) > 5000


def test_golden_lab_bytes_stable():
    png = _compose("Our lab builds clubs to your numbers and your swing.", "lab")
    if GOLDEN_LAB.is_file():
        assert GOLDEN_LAB.read_bytes() == png


def test_golden_avoda_bytes_stable():
    png = _compose("COACHING stick", "avoda")
    if GOLDEN_AVODA.is_file():
        assert GOLDEN_AVODA.read_bytes() == png


def test_service_category_picks_avoda_variant(square: dict):
    from _lib.archetype_compose import _compose_variant

    assert _compose_variant({"caption_hook": "LAB copy", "service_category": "AVODA"}) == "avoda"
    assert _compose_variant({"caption_hook": "LAB copy", "service_category": "LAB"}) == "lab"


def _ctx(monkeypatch, post_type: str = "", template_id: str = "") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": ["stick-coaching"],
        "subject": "",
        "post_type": post_type,
        "template_id": template_id,
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return "calendar_candidate:stick:cal-sq-1"


def test_post_type_service_square_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="service_square")
    assert arch_lib.select_archetype("stick", item)["id"] == "stick-service-square"


def test_coaching_pillar_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch)
    assert arch_lib.select_archetype("stick", item)["id"] == "stick-service-frame"
