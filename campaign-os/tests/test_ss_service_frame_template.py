"""Swing Shack ss-service-frame pack: stub compose, selection, template_pack."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "swing-shack"
ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "data/brand-directory/swing-shack/templates/service-frame"


@pytest.fixture(scope="module")
def frame_arch() -> dict:
    arch = archetype_by_id(BRAND, "ss-service-frame")
    assert arch
    return arch


def _render(arch: dict, headline: str, *, photo_bytes: bytes | None) -> Image.Image:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=["instagram"],
        fields={"caption_hook": headline},
        photo_bytes=photo_bytes,
    )
    return Image.open(io.BytesIO(out["instagram"])).convert("RGB")


def test_template_pack_and_zones(frame_arch: dict):
    assert frame_arch["template_pack"] == "templates/service-frame"
    zones = frame_arch["zones"]
    assert zones["photo"].get("optional") is True
    assert zones["headline"]["source"] == "caption_hook"


def test_ig_post_canvas_no_photo(frame_arch: dict):
    im = _render(frame_arch, "Fitting slots open this week", photo_bytes=None)
    assert im.size == (1080, 1350)
    arr = np.asarray(im)
    assert arr.std() > 5


def test_optional_photo_zone(frame_arch: dict):
    photo = (PACK / "photos/standin-sim-bay.jpg").read_bytes()
    plain = np.asarray(_render(frame_arch, "Coaching intro offer", photo_bytes=None))
    with_photo = np.asarray(_render(frame_arch, "Coaching intro offer", photo_bytes=photo))
    assert not np.array_equal(plain, with_photo)


def test_golden_files_match_compose(frame_arch: dict):
    golden_no = PACK / "golden/render-instagram-no-photo.png"
    golden_yes = PACK / "golden/render-instagram-with-photo.png"
    assert golden_no.is_file() and golden_yes.is_file()
    fields = {"caption_hook": "Book your club fitting today"}
    live_no = compose_post_for_channels(
        brand_id=BRAND,
        archetype=frame_arch,
        channels=["instagram"],
        fields=fields,
        photo_bytes=None,
    )["instagram"]
    photo = (PACK / "photos/standin-sim-bay.jpg").read_bytes()
    live_yes = compose_post_for_channels(
        brand_id=BRAND,
        archetype=frame_arch,
        channels=["instagram"],
        fields=fields,
        photo_bytes=photo,
    )["instagram"]
    assert golden_no.read_bytes() == live_no
    assert golden_yes.read_bytes() == live_yes


def test_fitting_pillar_selection_rule():
    s = arch_lib.suggest_template_for_record(
        BRAND,
        {"pillar_id": "ss-coaching", "has_product_item": False},
    )
    assert s["template_id"] == "ss-service-frame"
    assert s["resolution"] == "rule"


def test_validate_template_id_brand_scoped():
    assert arch_lib.validate_template_id(BRAND, "ss-service-frame")
    assert not arch_lib.validate_template_id(BRAND, "stick-service-frame")
