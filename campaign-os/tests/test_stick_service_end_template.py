"""Stick service-end template v2: gradient, tagline panel, lockup asset, selection."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import _wrap_text, compose_post_for_channels
from _lib.archetypes import archetype_by_id
from _lib.brand_overlay import _load_brand_font
from _lib.compose_visual_copy import visual_copy_for_archetype

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "data/brand-directory/stick/templates/service-end"
BRAND = "stick"
MINT = np.array([0x24, 0xFF, 0xAF])
NAVY_ALT = np.array([0x05, 0x32, 0x5D])
NAVY_DEEP = np.array([0x07, 0x3C, 0x52])
GRAD_TOP = np.array([0xD4, 0xDE, 0xDD])
LOCKUP = PACK / "assets/lockup-at-stick.png"

TAGLINE_WIDTH_PX = int(round((0.8677 - 0.1323) * 1080))


@pytest.fixture(scope="module")
def end_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-service-end")
    assert arch
    return arch


def _fields(**extra: str) -> dict[str, str]:
    base = {
        "caption_hook": "COACHING",
        "qualifier": "Coaching sessions that guide players toward better, more enjoyable golf.",
    }
    base.update(extra)
    return base


def _render(arch: dict, channels: list[str], **fields: str) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=_fields(**fields),
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_needs_photo_false(end_arch: dict):
    applies = end_arch.get("applies_to") or {}
    assert applies.get("needs_photo") is False
    bg = end_arch.get("background") or {}
    assert bg.get("kind") == "gradient"


def test_platform_canvases(end_arch: dict):
    out = _render(end_arch, ["instagram_story", "facebook"])
    assert out["instagram_story"].size == (1080, 1920)
    assert out["facebook"].size == (1080, 1920)


def test_mint_panel_pixels(end_arch: dict):
    img = np.asarray(_render(end_arch, ["instagram_story"])["instagram_story"])
    h, w = img.shape[:2]
    x0, y0 = int(0.0 * w), int(0.5182 * h)
    x1, y1 = int(0.9139 * w), int(0.8344 * h)
    band = img[y0:y1, x0:x1]
    mint_mask = np.abs(band.astype(int) - MINT).sum(axis=2) < 80
    assert mint_mask.mean() > 0.45, "mint panel fill missing in measured rect"


def test_gradient_background(end_arch: dict):
    img = np.asarray(_render(end_arch, ["instagram_story"])["instagram_story"])
    top = img[0, w // 2] if (w := img.shape[1]) else img[0, 540]
    bot = img[-1, img.shape[1] // 2]
    assert np.abs(top.astype(int) - GRAD_TOP).sum() < 35
    assert bot.min() > 245


def test_no_navy_deep_on_canvas(end_arch: dict):
    img = np.asarray(_render(end_arch, ["instagram_story"])["instagram_story"])
    r, g, b = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    deep = (np.abs(r - 7) < 4) & (np.abs(g - 60) < 4) & (np.abs(b - 82) < 4)
    assert deep.sum() == 0, "navy_deep #073C52 must not appear on service-end"


def test_navy_alt_in_service_and_tagline(end_arch: dict):
    img = np.asarray(_render(end_arch, ["instagram_story"])["instagram_story"])
    h, w = img.shape[:2]
    svc = img[int(0.21 * h) : int(0.30 * h), int(0.08 * w) : int(0.93 * w)]
    tag = img[int(0.52 * h) : int(0.82 * h), int(0.13 * w) : int(0.87 * w)]
    navy_svc = np.abs(svc.astype(int) - NAVY_ALT).sum(axis=2) < 45
    navy_tag = np.abs(tag.astype(int) - NAVY_ALT).sum(axis=2) < 45
    assert navy_svc.sum() > 200, "service word navy_alt glyphs expected"
    assert navy_tag.sum() > 400, "tagline navy_alt glyphs expected"


def test_lockup_asset_present_and_in_rect(end_arch: dict):
    assert LOCKUP.is_file()
    asset = Image.open(LOCKUP)
    assert asset.mode == "RGBA"
    assert asset.size == (538, 334)
    img = np.asarray(_render(end_arch, ["instagram_story"])["instagram_story"])
    h, w = img.shape[:2]
    x0, y0 = int(0.4172 * w), int(0.2724 * h)
    x1, y1 = int(0.914 * w), int(0.4458 * h)
    crop = img[y0:y1, x0:x1]
    white = crop.min(axis=2) > 240
    navy = np.abs(crop.astype(int) - NAVY_ALT).sum(axis=2) < 50
    assert white.sum() > 100 and navy.sum() > 100, "lockup asset should show white @ and navy wordmark"


def test_deterministic_render(end_arch: dict):
    f = _fields()
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=end_arch,
        channels=["instagram_story"],
        fields=f,
        photo_bytes=None,
    )["instagram_story"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=end_arch,
        channels=["instagram_story"],
        fields=f,
        photo_bytes=None,
    )["instagram_story"]
    assert a == b


@pytest.mark.parametrize(
    ("qualifier", "lines"),
    [
        (
            "Coaching sessions that guide players toward better, more enjoyable golf.",
            [
                "Coaching sessions",
                "that guide players",
                "toward better, more",
                "enjoyable golf.",
            ],
        ),
        (
            "Brand-agnostic fittings guided by data and science.",
            ["Brand-agnostic", "fittings guided by", "data and science."],
        ),
        (
            "Curated brands selected for quality, value, and relevance.",
            ["Curated brands", "selected for quality,", "value, and relevance."],
        ),
        ("Style that belongs.", ["Style that belongs."]),
    ],
)
def test_tagline_wrap_matches_reference_breaks(qualifier: str, lines: list[str]):
    font = _load_brand_font(BRAND, "display", 66)
    got = _wrap_text(qualifier, font, font, TAGLINE_WIDTH_PX, 4, 24, set(), 0.0)
    assert got == lines


def test_service_word_equipment_shrinks_vs_apparel(end_arch: dict):
    eq = np.asarray(
        _render(end_arch, ["instagram_story"], caption_hook="EQUIPMENT", qualifier="x.")["instagram_story"]
    )
    ap = np.asarray(
        _render(end_arch, ["instagram_story"], caption_hook="APPAREL", qualifier="y.")["instagram_story"]
    )
    h, w = eq.shape[:2]
    y0, y1 = int(0.21 * h), int(0.30 * h)
    x0, x1 = int(0.08 * w), int(0.93 * w)

    def ink_rows(img: np.ndarray) -> int:
        band = img[y0:y1, x0:x1]
        navy = np.abs(band.astype(int) - NAVY_ALT).sum(axis=2) < 45
        rows = np.where(navy.any(axis=1))[0]
        return int(rows[-1] - rows[0] + 1) if len(rows) else 0

    assert ink_rows(eq) < ink_rows(ap), "EQUIPMENT should render with smaller cap than APPAREL"


def test_visual_copy_populates_qualifier():
    arch = {"id": "stick-service-end", "applies_to": {"needs_photo": False}}
    fields = visual_copy_for_archetype(
        brand_id=BRAND,
        moment_id="proposal:stick:x",
        caption="TrackMan coaching session details",
        archetype=arch,
    )
    assert fields["caption_hook"] == "COACHING"
    assert "Coaching sessions" in fields["qualifier"]


def _ctx(monkeypatch, *, post_type: str = "", pillar_id: str = "stick-coaching") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": [pillar_id],
        "subject": "",
        "post_type": post_type,
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-end-1"


def test_post_type_service_end_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="service_end", pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-end"


def test_fitting_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-frame"


def test_pack_cases_compose(end_arch: dict):
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 4
    for case in cases:
        out = compose_post_for_channels(
            brand_id=BRAND,
            archetype=end_arch,
            channels=["instagram_story"],
            fields=case,
            photo_bytes=None,
        )
        assert out.get("instagram_story")
