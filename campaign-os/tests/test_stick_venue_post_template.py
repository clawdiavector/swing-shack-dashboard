"""Stick venue-post template: canvases, plate, selection, goldens."""

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
PACK = STICK / "templates/venue-post"
BRAND = "stick"
NAVY = np.array([0x07, 0x46, 0x5F])
CASES = json.loads((PACK / "cases.json").read_text())


@pytest.fixture(scope="module")
def venue_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-venue-post")
    assert arch
    return arch


@pytest.fixture(scope="module")
def stand_in_photos() -> list[bytes]:
    out: list[bytes] = []
    for i in range(1, 4):
        path = PACK / f"photos/stand-in-0{i}.jpg"
        assert path.is_file(), path
        out.append(path.read_bytes())
    return out


def _fields(case_index: int = 0, **extra: str) -> dict[str, str]:
    base = {k: v for k, v in CASES[case_index].items() if k != "ref"}
    base.update(extra)
    return base


def _render(
    arch: dict,
    channels: list[str],
    photo_bytes: bytes,
    case_index: int = 0,
    **fields: str,
) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=_fields(case_index, **fields),
        photo_bytes=photo_bytes,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_archetype_spec_keys(venue_arch: dict):
    for key in ("canvas", "template_pack", "block_anchor", "channel_canvas", "zones"):
        assert key in venue_arch
    assert venue_arch["id"] == "stick-venue-post"
    assert venue_arch["template_pack"] == "templates/venue-post"
    assert venue_arch["block_anchor"] == "bottom"
    assert venue_arch["channel_canvas"]["facebook"] == "ig_post"
    assert "partner_logo" in venue_arch["zones"]
    assert venue_arch["zones"]["partner_logo"]["kind"] == "image"


def test_platform_canvases(venue_arch: dict, stand_in_photos: list[bytes]):
    out = _render(
        venue_arch,
        ["instagram", "instagram_story", "facebook"],
        stand_in_photos[0],
    )
    assert out["instagram"].size == (1080, 1350)
    assert out["instagram_story"].size == (1080, 1920)
    assert out["facebook"].size == (1080, 1350)


def test_navy_plate_bottom_right(venue_arch: dict, stand_in_photos: list[bytes]):
    img = np.asarray(_render(venue_arch, ["instagram"], stand_in_photos[0])["instagram"])
    h, w = img.shape[:2]
    plate = img[int(0.68 * h) :, int(0.50 * w) :]
    navy_mask = np.abs(plate.astype(int) - NAVY).sum(axis=2) < 55
    assert navy_mask.mean() > 0.35


def test_partner_asset_renders(venue_arch: dict, stand_in_photos: list[bytes]):
    img = _render(venue_arch, ["instagram"], stand_in_photos[1], case_index=1)["instagram"]
    assert img.size == (1080, 1350)


def test_deterministic_render(venue_arch: dict, stand_in_photos: list[bytes]):
    f = _fields(0)
    photo = stand_in_photos[0]
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=venue_arch,
        channels=["instagram"],
        fields=f,
        photo_bytes=photo,
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=venue_arch,
        channels=["instagram"],
        fields=f,
        photo_bytes=photo,
    )["instagram"]
    assert a == b


def test_pack_golden_files_exist():
    for name in (
        "ref-01-instagram.png",
        "compare-refs.jpg",
    ):
        path = PACK / "golden" / name
        assert path.is_file() and path.stat().st_size > 1000, f"missing {name}"


def test_golden_matches_compose(venue_arch: dict, stand_in_photos: list[bytes]):
    mp = compose_post_for_channels(
        brand_id=BRAND,
        archetype=venue_arch,
        channels=["instagram"],
        fields=_fields(0),
        photo_bytes=stand_in_photos[0],
    )["instagram"]
    golden = (PACK / "golden" / "ref-01-instagram.png").read_bytes()
    a = Image.open(io.BytesIO(mp)).convert("RGB")
    b = Image.open(io.BytesIO(golden)).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a, b)
    assert diff.getbbox() is None or max(diff.getextrema()[0]) <= 2


def _ctx(monkeypatch, *, post_type: str = "", subject: str = "") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": ["fitting"],
        "subject": subject,
        "post_type": post_type,
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-venue-1"


def test_subject_venue_selects_archetype(monkeypatch, venue_arch: dict):
    item = _ctx(monkeypatch, subject="venue")
    picked = arch_lib.select_archetype(BRAND, item)
    assert picked and picked.get("id") == "stick-venue-post"


def test_post_type_venue_post_selects_archetype(monkeypatch, venue_arch: dict):
    item = _ctx(monkeypatch, post_type="venue_post")
    picked = arch_lib.select_archetype(BRAND, item)
    assert picked and picked.get("id") == "stick-venue-post"
