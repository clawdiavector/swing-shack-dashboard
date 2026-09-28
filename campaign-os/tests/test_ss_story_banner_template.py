"""Swing Shack ss-story-banner: platforms, story logo zone, wrap, selection."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import _zones_for_canvas, compose_post_for_channels
from _lib.archetypes import archetype_by_id, load_archetypes_doc
from _lib.brand_overlay import _load_brand_font

BRAND = "swing-shack"
HEADLINE = "Book your club fitting today"
PHOTO_PATH = (
    arch_lib._bundled_brand_root()
    / BRAND
    / "templates/story-banner/photos/standin-sim-bay.jpg"
)


@pytest.fixture(scope="module")
def story_banner() -> dict:
    arch = archetype_by_id(BRAND, "ss-story-banner")
    assert arch
    return arch


@pytest.fixture(scope="module")
def photo_bytes() -> bytes:
    assert PHOTO_PATH.is_file(), f"missing {PHOTO_PATH}"
    return PHOTO_PATH.read_bytes()


def _render(
    arch: dict,
    headline: str,
    channels: list[str],
    photo_bytes: bytes,
) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields={"caption_hook": headline},
        photo_bytes=photo_bytes,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(story_banner: dict, photo_bytes: bytes):
    out = _render(
        story_banner,
        HEADLINE,
        ["instagram", "instagram_story", "facebook", "gbp"],
        photo_bytes,
    )
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1200, 630),
        "gbp": (1200, 900),
    }


def test_logo_visible_on_story(story_banner: dict):
    doc = load_archetypes_doc(BRAND)
    zones = _zones_for_canvas(story_banner, "ig_story", "ig_post", 1350, 1920)
    rect = zones["logo"]["rect"]
    assert 0 <= rect["y0"] < rect["y1"] <= 1.0
    story_safe = doc["canvases"]["ig_story"]["safe_zone"]
    assert rect["y1"] <= story_safe["y1"] + 1e-6


def test_headline_wrap_and_no_clipping(story_banner: dict, photo_bytes: bytes):
    long_hook = "Custom builds for every swing type"
    font = _load_brand_font(BRAND, "h1", 60)
    zone_w = int(0.8 * 1080)
    assert font.getlength(long_hook.upper()) <= zone_w * 2.05
    for channel in ("instagram", "instagram_story"):
        img = np.asarray(_render(story_banner, long_hook, [channel], photo_bytes)[channel]).astype(int)
        # Headline band ~ y 0.2–0.35 on ig_post; allow block_anchor shift on story.
        h = img.shape[0]
        band = img[int(0.12 * h) : int(0.42 * h), :, :]
        bright = (band.max(axis=2) > 200) & (band.min(axis=2) > 150)
        cols = np.nonzero(bright.any(axis=0))[0]
        assert cols.size > 0
        assert cols.min() > 40
        assert cols.max() < img.shape[1] - 24


def test_selection_via_post_type(monkeypatch, story_banner: dict):
    ctx = {
        "has_product_item": False,
        "pillar_in": ["ss-fitting"],
        "subject": "",
        "post_type": "story_banner",
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    item = f"calendar_candidate:{BRAND}:cal-1"
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-story-banner"


def test_pinned_template_id_wins(monkeypatch):
    ctx = {
        "has_product_item": False,
        "pillar_in": ["ss-fitting"],
        "subject": "",
        "post_type": "story_banner",
        "template_id": "ss-did-you-know",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    item = f"calendar_candidate:{BRAND}:cal-1"
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-did-you-know"
