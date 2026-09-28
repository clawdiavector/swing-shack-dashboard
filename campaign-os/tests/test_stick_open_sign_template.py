"""Stick open-sign template: photo bleed, gradient block, mint line, selection."""

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
PACK = ROOT / "data/brand-directory/stick/templates/open-sign"
BRAND = "stick"
MINT = np.array([0x24, 0xFF, 0xAF])
NAVY_ALT = np.array([0x05, 0x32, 0x5D])
NAVY_EDGE = np.array([0x07, 0x2A, 0x40])
WORDMARK = PACK / "assets/logo-wordmark-white.png"


@pytest.fixture(scope="module")
def open_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-open-sign")
    assert arch
    return arch


def _fields(**extra: str) -> dict[str, str]:
    base = {"caption_hook": "We are open", "photo_seed": "7"}
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


def test_needs_photo_and_background(open_arch: dict):
    applies = open_arch.get("applies_to") or {}
    assert applies.get("needs_photo") is True
    bg = open_arch.get("background") or {}
    assert bg.get("kind") == "photo_full_bleed"


def test_platform_canvases(open_arch: dict):
    out = _render(open_arch, ["instagram", "facebook"])
    assert out["instagram"].size == (1080, 1350)
    assert out["facebook"].size == (1080, 1350)


def test_block_gradient_endpoints(open_arch: dict):
    img = np.asarray(_render(open_arch, ["instagram"])["instagram"])
    h, w = img.shape[:2]
    x0, y0 = int(0.5005 * w), int(0.7128 * h)
    x1, y1 = int(1.0 * w), int(0.906 * h)
    left = img[y0 + (y1 - y0) // 2, x0]
    right = img[y0 + (y1 - y0) // 2, x1 - 1]
    assert np.abs(left.astype(int) - NAVY_ALT).sum() < 35
    assert np.abs(right.astype(int) - NAVY_EDGE).sum() < 35


def test_mint_headline_in_open_line_zone(open_arch: dict):
    img = np.asarray(_render(open_arch, ["instagram"])["instagram"])
    h, w = img.shape[:2]
    x0, y0 = int(0.5606 * w), int(0.8149 * h)
    x1, y1 = int(0.9528 * w), int(0.8453 * h)
    band = img[y0:y1, x0:x1]
    mint = np.abs(band.astype(int) - MINT).sum(axis=2) < 80
    assert mint.sum() > 200, "mint WE ARE OPEN glyphs expected in measured rect"


def test_open_line_one_line_not_clipped_right(open_arch: dict):
    img = np.asarray(_render(open_arch, ["instagram"])["instagram"])
    h, w = img.shape[:2]
    x0, y0 = int(0.5606 * w), int(0.8149 * h)
    x1, y1 = int(0.9528 * w), int(0.8453 * h)
    band = img[y0:y1, x0:x1]
    mint = np.abs(band.astype(int) - MINT).sum(axis=2) < 80
    cols = np.nonzero(mint.any(axis=0))[0]
    assert cols.size > 0
    assert cols.max() < band.shape[1] - 6


def test_wordmark_asset_present(open_arch: dict):
    assert WORDMARK.is_file()
    asset = Image.open(WORDMARK)
    assert asset.mode == "RGBA"


def test_flat_band_without_gradient_still_renders():
    """Regression: band zones without gradient key must stay flat fill."""
    start = archetype_by_id(BRAND, "stick-service-start")
    assert start
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=start,
        channels=["instagram"],
        fields={"caption_hook": "COACHING", "cta": "@ stick", "photo_seed": "coaching"},
        photo_bytes=None,
    )
    img = np.asarray(Image.open(io.BytesIO(out["instagram"])).convert("RGB"))
    h, w = img.shape[:2]
    x0, y0 = int(0.051 * w), int(0.659 * h)
    x1, y1 = int(0.652 * w), int(0.680 * h)
    band = img[y0:y1, x0:x1]
    mint_mask = np.abs(band.astype(int) - MINT).sum(axis=2) < 80
    assert mint_mask.mean() > 0.5


def _ctx(monkeypatch, *, post_type: str = "", pillar_id: str = "stick-coaching") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": [pillar_id],
        "subject": "",
        "post_type": post_type,
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-open-1"


def test_post_type_open_sign_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="open_sign", pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-open-sign"


def test_fitting_without_open_sign_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-frame"


def test_pack_cases_compose(open_arch: dict):
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 3
    for case in cases:
        out = compose_post_for_channels(
            brand_id=BRAND,
            archetype=open_arch,
            channels=["instagram"],
            fields=case,
            photo_bytes=None,
        )
        assert out.get("instagram")
