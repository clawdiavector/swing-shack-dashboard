"""Stick shop-corner template: plate geometry, mint word, selection, goldens."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import ComposeError, compose_post_for_channels
from _lib.archetypes import archetype_by_id
from _lib.compose_visual_copy import visual_copy_for_archetype

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "data/brand-directory/stick/templates/shop-corner"
BRAND = "stick"
MINT = np.array([0x24, 0xFF, 0xAF])
NAVY_ALT = np.array([0x05, 0x32, 0x5D])
WHITE_LO = 220


@pytest.fixture(scope="module")
def corner_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-shop-corner")
    assert arch
    return arch


@pytest.fixture(scope="module")
def ref_photo() -> bytes:
    path = PACK / "references/ref-01.jpg"
    assert path.is_file()
    return path.read_bytes()


def _fields(**extra: str) -> dict[str, str]:
    base = {"caption_hook": "EQUIPMENT"}
    base.update(extra)
    return base


def _render(
    arch: dict,
    channels: list[str],
    photo_bytes: bytes,
    **fields: str,
) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=_fields(**fields),
        photo_bytes=photo_bytes,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_archetype_spec_keys(corner_arch: dict):
    assert corner_arch["id"] == "stick-shop-corner"
    zones = corner_arch.get("zones") or {}
    for key in ("photo", "plate", "service_word", "at_mark", "logo"):
        assert key in zones
    assert corner_arch["applies_to"]["needs_photo"] is True


def test_plate_half_width_bottom_corner(corner_arch: dict):
    plate = corner_arch["zones"]["plate"]["rect"]
    assert float(plate["x0"]) == 0.0
    assert float(plate["x1"]) == 0.5
    height = float(plate["y1"]) - float(plate["y0"])
    assert 0.18 <= height <= 0.20


def test_platform_canvases(corner_arch: dict, ref_photo: bytes):
    out = _render(corner_arch, ["instagram", "instagram_story", "facebook"], ref_photo)
    assert out["instagram"].size == (1080, 1350)
    assert out["instagram_story"].size == (1080, 1920)
    assert out["facebook"].size == (1080, 1350)


def test_missing_photo_raises(corner_arch: dict):
    with pytest.raises(ComposeError, match="missing background photo"):
        compose_post_for_channels(
            brand_id=BRAND,
            archetype=corner_arch,
            channels=["instagram"],
            fields=_fields(),
            photo_bytes=None,
        )


def test_service_word_uppercase_mint(corner_arch: dict, ref_photo: bytes):
    img = np.asarray(
        _render(corner_arch, ["instagram"], ref_photo, caption_hook="equipment")["instagram"]
    )
    h, w = img.shape[:2]
    sw = corner_arch["zones"]["service_word"]["rect"]
    band = img[
        int(float(sw["y0"]) * h) : int(float(sw["y1"]) * h),
        int(float(sw["x0"]) * w) : int(float(sw["x1"]) * w),
    ]
    mint_mask = np.abs(band.astype(int) - MINT).sum(axis=2) < 80
    assert mint_mask.sum() > 200, "mint service word glyphs expected"


def test_plate_navy_alt_fill(corner_arch: dict, ref_photo: bytes):
    img = np.asarray(_render(corner_arch, ["instagram"], ref_photo)["instagram"])
    h, w = img.shape[:2]
    plate = corner_arch["zones"]["plate"]["rect"]
    band = img[
        int(float(plate["y0"]) * h) : int(float(plate["y1"]) * h),
        int(float(plate["x0"]) * w) : int(float(plate["x1"]) * w),
    ]
    navy_mask = np.abs(band.astype(int) - NAVY_ALT).sum(axis=2) < 45
    assert navy_mask.mean() > 0.5


def test_at_mark_and_logo_present(corner_arch: dict, ref_photo: bytes):
    img = np.asarray(_render(corner_arch, ["instagram"], ref_photo)["instagram"])
    h, w = img.shape[:2]
    at_r = corner_arch["zones"]["at_mark"]["rect"]
    at_band = img[
        int(float(at_r["y0"]) * h) : int(float(at_r["y1"]) * h),
        int(float(at_r["x0"]) * w) : int(float(at_r["x1"]) * w),
    ]
    assert (at_band.max(axis=2) >= WHITE_LO).sum() > 30
    logo_r = corner_arch["zones"]["logo"]["rect"]
    logo_band = img[
        int(float(logo_r["y0"]) * h) : int(float(logo_r["y1"]) * h),
        int(float(logo_r["x0"]) * w) : int(float(logo_r["x1"]) * w),
    ]
    assert (logo_band.max(axis=2) >= WHITE_LO).sum() > 50


def test_deterministic_render(corner_arch: dict, ref_photo: bytes):
    f = _fields()
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=corner_arch,
        channels=["instagram"],
        fields=f,
        photo_bytes=ref_photo,
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=corner_arch,
        channels=["instagram"],
        fields=f,
        photo_bytes=ref_photo,
    )["instagram"]
    assert a == b


def test_visual_copy_shop_corner_routes_service_headline():
    arch = {"id": "stick-shop-corner", "applies_to": {"needs_photo": True}}
    fields = visual_copy_for_archetype(
        brand_id=BRAND,
        moment_id="proposal:stick:x",
        caption="New irons in store",
        archetype=arch,
        sidecar={"compose_headline": "EQUIPMENT"},
    )
    assert fields["caption_hook"] == "EQUIPMENT"
    assert fields["cta"] == "@ stick"


def _ctx(
    monkeypatch,
    *,
    post_type: str = "",
    pillar_id: str = "stick-fitting",
    template_id: str = "",
) -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": [pillar_id],
        "subject": "",
        "post_type": post_type,
        "template_id": template_id,
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-shop-1"


def test_post_type_shop_corner_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="shop_corner", pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-shop-corner"


def test_fitting_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-frame"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(
        monkeypatch,
        post_type="shop_corner",
        pillar_id="stick-equipment",
        template_id="stick-service-frame",
    )
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-frame"


def test_pack_cases_match_archetype(corner_arch: dict):
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 4
    for i, case in enumerate(cases):
        ref = (PACK / "references" / f"ref-0{i + 1}.jpg").read_bytes()
        out = compose_post_for_channels(
            brand_id=BRAND,
            archetype=corner_arch,
            channels=["instagram"],
            fields=case,
            photo_bytes=ref,
        )
        assert out.get("instagram")


def test_pack_golden_files_exist():
    compare = PACK / "golden/compare-refs.jpg"
    render = PACK / "golden/render-instagram.png"
    assert compare.is_file() and compare.stat().st_size > 5000
    assert render.is_file() and render.stat().st_size > 5000
