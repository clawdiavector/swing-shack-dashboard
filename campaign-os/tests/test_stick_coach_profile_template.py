"""Stick coach-profile template: canvases, bands, selection, determinism."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id
from _lib.compose_visual_copy import visual_copy_for_archetype

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "data/brand-directory/stick/templates/coach-profile"
BRAND = "stick"
TEAL = np.array([0x00, 0xB3, 0xBA])
NAVY = np.array([0x07, 0x3C, 0x52])
FOOTER = np.array([0xF9, 0xF9, 0xF9])
WHITE_LO = 220


@pytest.fixture(scope="module")
def coach_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-coach-profile")
    assert arch
    return arch


@pytest.fixture(scope="module")
def stand_in_photo() -> bytes:
    path = PACK / "photos/stand-in.jpg"
    assert path.is_file()
    return path.read_bytes()


def _fields(**extra: str) -> dict[str, str]:
    base = {
        "caption_hook": "ALEX MORGAN",
        "bio_1": "AVAILABLE FOR",
        "bio_2": "COACHING, FITTINGS",
        "bio_3": "AND ASSESSMENTS",
    }
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


def test_platform_canvases(coach_arch: dict, stand_in_photo: bytes):
    out = _render(coach_arch, ["instagram", "instagram_story", "facebook"], stand_in_photo)
    assert out["instagram"].size == (1080, 1350)
    assert out["instagram_story"].size == (1080, 1920)
    assert out["facebook"].size == (1080, 1350)


def _band_match(arr: np.ndarray, colour: np.ndarray, rect_frac: tuple[float, float, float, float]) -> float:
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = rect_frac
    band = arr[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]
    return float((np.abs(band.astype(int) - colour).sum(axis=2) < 45).mean())


def test_teal_name_band_and_navy_footer(coach_arch: dict, stand_in_photo: bytes):
    img = np.asarray(_render(coach_arch, ["instagram"], stand_in_photo)["instagram"])
    assert _band_match(img, TEAL, (0.05, 0.23, 0.95, 0.5)) > 0.8
    assert _band_match(img, NAVY, (0.0, 0.518, 1.0, 0.778)) > 0.85
    assert _band_match(img, FOOTER, (0.0, 0.782, 1.0, 1.0)) > 0.85


def test_white_glyphs_in_text_zones(coach_arch: dict, stand_in_photo: bytes):
    img = np.asarray(_render(coach_arch, ["instagram"], stand_in_photo)["instagram"])
    h, w = img.shape[:2]
    zones = (
        (0.06, 0.24, 0.99, 0.48),
        (0.115, 0.556, 0.9, 0.594),
        (0.115, 0.621, 0.9, 0.667),
    )
    for rect in zones:
        x0, y0, x1, y1 = rect
        patch = img[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]
        assert patch.min(axis=2).max() > WHITE_LO, f"expected white ink in {rect}"


def test_story_overrides_shift_photo(coach_arch: dict, stand_in_photo: bytes):
    post = _render(coach_arch, ["instagram"], stand_in_photo)["instagram"]
    story = _render(coach_arch, ["instagram_story"], stand_in_photo)["instagram_story"]
    assert story.size == (1080, 1920)
    post_arr = np.asarray(post)
    story_arr = np.asarray(story)
    post_photo = post_arr[int(0.006 * 1350) : int(0.36 * 1350), :]
    story_photo = story_arr[int(0.004 * 1920) : int(0.379 * 1920), :]
    assert story_photo.shape[0] > post_photo.shape[0]


def test_deterministic_render(coach_arch: dict, stand_in_photo: bytes):
    f = _fields()
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=coach_arch,
        channels=["instagram"],
        fields=f,
        photo_bytes=stand_in_photo,
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=coach_arch,
        channels=["instagram"],
        fields=f,
        photo_bytes=stand_in_photo,
    )["instagram"]
    assert a == b


def test_visual_copy_splits_body_lines():
    arch = {"id": "stick-coach-profile", "applies_to": {"needs_photo": True}}
    fields = visual_copy_for_archetype(
        brand_id=BRAND,
        moment_id="proposal:stick:x",
        caption="Coach intro",
        archetype=arch,
        sidecar={
            "compose_headline": "ALEX MORGAN",
            "compose_body": "AVAILABLE FOR\nCOACHING, FITTINGS\nAND ASSESSMENTS",
        },
    )
    assert fields["caption_hook"] == "ALEX MORGAN"
    assert fields["kicker"] == "AVAILABLE FOR"
    assert fields["bio_1"] == "COACHING, FITTINGS"
    assert fields["bio_2"] == "AND ASSESSMENTS"


def _ctx(monkeypatch, *, post_type: str = "", pillar_id: str = "stick-coaching") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": [pillar_id],
        "subject": "",
        "post_type": post_type,
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-coach-1"


def test_post_type_staff_profile_selects_template(monkeypatch):
    item = _ctx(monkeypatch, post_type="staff_profile")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-coach-profile"


def test_coaching_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="stick-coaching")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-frame"
