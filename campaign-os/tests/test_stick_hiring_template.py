"""Stick hiring template: bands, copy zones, selection, goldens."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "data/brand-directory/stick/templates/hiring"
BRAND = "stick"
TEAL = np.array([0x00, 0xB3, 0xBA])
NAVY = np.array([0x07, 0x3C, 0x52])
GREY = np.array([0xD1, 0xD1, 0xD1])
DIVIDER = np.array([0xE1, 0xE1, 0xE1])
WHITE_LO = 220

BAND_Y0 = (0.15914, 0.25907, 0.34419, 0.396, 0.9134)


@pytest.fixture(scope="module")
def hiring_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-hiring")
    assert arch
    return arch


def _fields(**extra: str) -> dict[str, str]:
    base = {
        "caption_hook": "WE'RE HIRING",
        "qualifier": "GOLF COACH & CUSTOM FITTER",
        "caption_body": (
            "Stick is looking for a PGA professional to join our team. "
            "If you love helping players improve their game and know your way "
            "around modern golf tech, we want to hear from you."
        ),
        "cta": "SWIPE FOR MORE DETAILS",
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


def test_archetype_spec_keys(hiring_arch: dict):
    assert hiring_arch["id"] == "stick-hiring"
    zones = hiring_arch.get("zones") or {}
    for key in (
        "header_band",
        "headline_band",
        "role_band",
        "divider_band",
        "brief_band",
        "wordmark",
        "headline",
        "role",
        "brief",
        "swipe",
        "chevron",
        "logo",
    ):
        assert key in zones, f"missing zone {key}"
    applies = hiring_arch.get("applies_to") or {}
    assert applies.get("needs_photo") is False
    assert hiring_arch.get("canvas") == "ig_post"
    cc = hiring_arch.get("channel_canvas") or {}
    assert cc.get("facebook") == "ig_post"


def test_platform_canvases(hiring_arch: dict):
    out = _render(hiring_arch, ["instagram", "facebook"])
    assert out["instagram"].size == (1080, 1350)
    assert out["facebook"].size == (1080, 1350)
    compose_post_for_channels(
        brand_id=BRAND,
        archetype=hiring_arch,
        channels=["instagram"],
        fields=_fields(),
        photo_bytes=None,
    )


def test_band_fractions(hiring_arch: dict):
    zones = hiring_arch["zones"]
    header = zones["header_band"]["rect"]
    assert abs(float(header["y1"]) - 0.15914) < 0.005
    assert zones["header_band"]["fill"] == "grey_light"
    for y0, fill_name in zip(BAND_Y0[:4], ("navy_deep", "teal", "#E1E1E1", "navy_deep")):
        for zname, z in zones.items():
            if z.get("kind") != "band":
                continue
            rect = z.get("rect") or {}
            if abs(float(rect.get("y0", -1)) - y0) < 0.005:
                assert z.get("fill") == fill_name
                break
        else:
            pytest.fail(f"no band at y0={y0}")
    assert abs(float(zones["brief_band"]["rect"]["y1"]) - 0.9134) < 0.005

    img = np.asarray(_render(hiring_arch, ["instagram"])["instagram"])
    h, w = img.shape[:2]
    assert _band_match(img, GREY, (0.05, 0.02, 0.95, 0.14)) > 0.85
    assert _band_match(img, NAVY, (0.02, 0.17, 0.08, 0.24)) > 0.85
    assert _band_match(img, TEAL, (0.02, 0.27, 0.08, 0.33)) > 0.85
    assert _band_match(img, DIVIDER, (0.05, 0.35, 0.95, 0.38)) > 0.85
    assert _band_match(img, NAVY, (0.05, 0.42, 0.95, 0.88)) > 0.75


def _band_match(arr: np.ndarray, colour: np.ndarray, rect_frac: tuple[float, float, float, float]) -> float:
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = rect_frac
    band = arr[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]
    return float((np.abs(band.astype(int) - colour).sum(axis=2) < 45).mean())


def test_headline_uppercase_teal(hiring_arch: dict):
    img = np.asarray(_render(hiring_arch, ["instagram"], caption_hook="we're hiring")["instagram"])
    h, w = img.shape[:2]
    patch = img[int(0.17 * h) : int(0.25 * h), int(0.15 * w) : int(0.85 * w)]
    teal = np.abs(patch.astype(int) - TEAL).sum(axis=2) < 12
    assert teal.sum() > 800, "headline should render in teal"


def test_role_uppercase_white(hiring_arch: dict):
    img = np.asarray(
        _render(hiring_arch, ["instagram"], qualifier="golf coach & custom fitter")["instagram"]
    )
    h, w = img.shape[:2]
    patch = img[int(0.27 * h) : int(0.32 * h), int(0.1 * w) : int(0.9 * w)]
    assert patch.min(axis=2).max() > WHITE_LO


def test_swipe_and_chevron_present(hiring_arch: dict):
    chev_path = PACK / "assets/chevron-swipe-navy.png"
    assert chev_path.is_file()
    asset = Image.open(chev_path)
    assert asset.mode == "RGBA"
    assert asset.size == (280, 100)
    img = np.asarray(_render(hiring_arch, ["instagram"])["instagram"])
    h, w = img.shape[:2]
    footer = img[int(0.915 * h) : int(0.99 * h), int(0.45 * w) : int(0.99 * w)]
    navy = np.abs(footer.astype(int) - NAVY).sum(axis=2) < 45
    assert navy.sum() > 400, "swipe text and chevron should show navy ink in footer"


def test_deterministic_render(hiring_arch: dict):
    f = _fields()
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=hiring_arch,
        channels=["instagram"],
        fields=f,
        photo_bytes=None,
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=hiring_arch,
        channels=["instagram"],
        fields=f,
        photo_bytes=None,
    )["instagram"]
    assert a == b


def _ctx(
    monkeypatch,
    *,
    post_type: str = "",
    pillar_id: str = "stick-coaching",
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
    return f"calendar_candidate:{BRAND}:cal-hiring-1"


def test_post_type_hiring_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="hiring")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-hiring"
    item2 = _ctx(monkeypatch, post_type="", pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item2)["id"] != "stick-hiring"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(monkeypatch, post_type="hiring", template_id="stick-brand-statement")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-brand-statement"


def test_pack_cases_match_archetype(hiring_arch: dict):
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    for case in cases:
        out = compose_post_for_channels(
            brand_id=BRAND,
            archetype=hiring_arch,
            channels=["instagram"],
            fields=case,
            photo_bytes=None,
        )
        assert out.get("instagram")


def test_pack_golden_files_exist():
    cmp_path = PACK / "golden/compare-refs.jpg"
    render_path = PACK / "golden/render-instagram.png"
    assert cmp_path.is_file() and cmp_path.stat().st_size > 1000
    assert render_path.is_file() and render_path.stat().st_size > 1000
    cmp_img = Image.open(cmp_path)
    assert cmp_img.size[0] >= 300 and cmp_img.size[1] >= 600
