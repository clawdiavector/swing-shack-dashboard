"""Stick service-frame compose: fonts, transforms, assets, golden render."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFont

ROOT = Path(__file__).resolve().parents[2]
STICK = ROOT / "data" / "brand-directory" / "stick"
GOLDEN = (
    STICK / "templates/service-frame/golden/render-instagram.png"
)
REF = STICK / "images/Services/swingasses.jpg"


@pytest.fixture(scope="module")
def golden_png() -> bytes:
    from _lib.archetypes import archetype_by_id
    from _lib.archetype_compose import compose_post_for_channels

    arch = archetype_by_id("stick", "stick-service-frame")
    assert arch
    return compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram"],
        fields={
            "caption_hook": "Consistency starts with data",
            "cta": "Book your free swing assessment",
        },
        photo_bytes=None,
    )["instagram"]


def test_brand_fonts_are_truetype(golden_png: bytes):
    from _lib.brand_overlay import _load_brand_font

    for role, suffix, size in (
        ("display", "Montserrat-Black.ttf", 113),
        ("h2", "Montserrat-Light.ttf", 75),
        ("cta_emphasis", "Montserrat-ExtraBold.ttf", 75),
    ):
        font = _load_brand_font("stick", role, size)
        assert isinstance(font, ImageFont.FreeTypeFont)
        assert font.path.endswith(suffix)
        assert font.size == size


def test_compose_uses_freetype_not_bitmap_default(golden_png: bytes):
    from _lib.archetype_compose import _fit_font_size
    from _lib.archetypes import archetype_by_id

    arch = archetype_by_id("stick", "stick-service-frame")
    hz = arch["zones"]["headline"]
    w, h = 1080, 1350
    x0 = int(hz["rect"]["x0"] * w)
    x1 = int(hz["rect"]["x1"] * w)
    y0 = int(hz["rect"]["y0"] * h)
    y1 = int(hz["rect"]["y1"] * h)
    size, _, body, _ = _fit_font_size(
        brand_id="stick",
        role="display",
        zone=hz,
        text="CONSISTENCY STARTS WITH DATA",
        zone_w=x1 - x0,
        zone_h=y1 - y0,
        min_px=56,
    )
    assert size == 113
    assert isinstance(body, ImageFont.FreeTypeFont)
    assert body.path.endswith("Montserrat-Black.ttf")
    bitmap = ImageFont.load_default()
    assert getattr(bitmap, "size", 0) != 113


def test_uppercase_transform(golden_png: bytes):
    from _lib.archetype_compose import _apply_text_transform

    zone = {"text_transform": "uppercase"}
    assert _apply_text_transform("Hello", zone) == "HELLO"


def test_emphasis_word_uses_heavier_stem(golden_png: bytes):
    from _lib.brand_overlay import _load_brand_font

    body = _load_brand_font("stick", "h2", 75)
    emph = _load_brand_font("stick", "cta_emphasis", 75)
    assert body and emph
    assert emph.getlength("FREE") > body.getlength("FREE")
    assert emph.getlength("F") > body.getlength("F")


def test_logo_and_tagline_assets():
    logo = STICK / "logo.png"
    tag = STICK / "images/tagline-light.png"
    assert logo.stat().st_size > 10_000
    assert tag.stat().st_size > 10_000
    assert Image.open(logo).size != (64, 64)
    assert Image.open(tag).mode == "RGBA"


def test_golden_render_dimensions_and_not_blank(golden_png: bytes):
    im = Image.open(io.BytesIO(golden_png))
    assert im.size == (1080, 1350)
    arr = np.array(im.convert("RGB"))
    assert arr.std() > 10
    assert not np.all(arr == 255)
    assert tuple(arr[0, 0]) == (7, 61, 85)
    assert tuple(arr[0, -1]) == (6, 52, 67)


def test_golden_file_matches_compose(golden_png: bytes):
    if GOLDEN.is_file():
        on_disk = GOLDEN.read_bytes()
        assert on_disk == golden_png
