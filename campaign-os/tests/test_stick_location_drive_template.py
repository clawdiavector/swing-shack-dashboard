"""Stick location-drive template: styles, selection, goldens."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageChops

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

ROOT = Path(__file__).resolve().parents[2]
STICK = ROOT / "data" / "brand-directory" / "stick"
PACK = STICK / "templates/location-drive"
BRAND = "stick"
ACCENT = np.array([0x3E, 0xE0, 0x89])
NAVY = np.array([0x0B, 0x43, 0x72])


@pytest.fixture(scope="module")
def loc_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-location-drive")
    assert arch
    return arch


def _fields(style: str, **extra: str) -> dict[str, str]:
    base = {
        "style": style,
        "vendor_name": "FRANSCHHOEK" if style == "map-photo" else "GREEN POINT",
    }
    if style == "map-photo":
        base["caption_hook"] = (
            "25 MINUTE TRIP SO YOU CAN HIT A 9-IRON WHILE THEY SWEAT OVER A 5"
        )
    else:
        base["caption_kicker"] = "A 46 MINUTE TRIP"
        base["caption_hook"] = "TO MAKE THEM HIT THEIR SECOND SHOT FIRST ALL DAY"
    base.update(extra)
    return base


def _render(arch: dict, style: str, channels: list[str]) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=_fields(style),
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_archetype_spec_keys(loc_arch: dict):
    for key in (
        "canvas",
        "template_pack",
        "palette_tokens",
        "locked_headline",
        "accent_words",
        "zones_map_photo",
        "zones_route_line",
    ):
        assert key in loc_arch
    assert loc_arch["id"] == "stick-location-drive"
    assert loc_arch["template_pack"] == "templates/location-drive"


def test_platform_canvases(loc_arch: dict):
    mp = _render(loc_arch, "map-photo", ["instagram", "instagram_story", "facebook"])
    assert mp["instagram"].size == (1080, 1350)
    assert mp["instagram_story"].size == (1080, 1920)
    assert mp["facebook"].size == (1080, 1350)
    rl = _render(loc_arch, "route-line", ["instagram"])
    assert rl["instagram"].size == (1080, 1350)


def test_map_photo_accent_pills_and_headline(loc_arch: dict):
    img = np.asarray(_render(loc_arch, "map-photo", ["instagram"])["instagram"])
    green_mask = np.abs(img.astype(int) - ACCENT).sum(axis=2) < 80
    assert green_mask.sum() > 5000, "accent green pills missing"
    navy_mask = np.abs(img.astype(int) - NAVY).sum(axis=2) < 40
    assert navy_mask.mean() > 0.25


def test_route_line_green_stroke(loc_arch: dict):
    img = np.asarray(_render(loc_arch, "route-line", ["instagram"])["instagram"])
    green = np.abs(img.astype(int) - ACCENT).sum(axis=2) < 60
    assert green.sum() > 800, "route polyline not visible"


def test_deterministic_map_photo(loc_arch: dict):
    f = _fields("map-photo")
    a = compose_post_for_channels(
        brand_id=BRAND, archetype=loc_arch, channels=["instagram"], fields=f, photo_bytes=None
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND, archetype=loc_arch, channels=["instagram"], fields=f, photo_bytes=None
    )["instagram"]
    assert a == b


def test_pill_radius_in_spec(loc_arch: dict):
    pill = loc_arch["zones_map_photo"]["stick_logo_pill"]
    assert float(pill.get("radius") or 0) >= 0.03


def _ctx(monkeypatch, post_type: str = "", subject: str = "") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": ["fitting"],
        "subject": subject,
        "post_type": post_type,
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-loc-1"


def test_post_type_location_selects_archetype(monkeypatch, loc_arch: dict):
    item = _ctx(monkeypatch, post_type="location")
    picked = arch_lib.select_archetype(BRAND, item)
    assert picked and picked.get("id") == "stick-location-drive"


def test_pack_golden_files_exist():
    for name in ("franschoek.png", "greenpoint.png"):
        path = PACK / "golden" / name
        assert path.is_file() and path.stat().st_size > 1000, f"missing {name}"


def test_golden_matches_compose(loc_arch: dict):
    mp = compose_post_for_channels(
        brand_id=BRAND,
        archetype=loc_arch,
        channels=["instagram"],
        fields=_fields("map-photo"),
        photo_bytes=None,
    )["instagram"]
    golden = (PACK / "golden" / "franschoek.png").read_bytes()
    a = Image.open(io.BytesIO(mp)).convert("RGB")
    b = Image.open(io.BytesIO(golden)).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a, b)
    assert diff.getbbox() is None or max(diff.getextrema()[0]) <= 2
