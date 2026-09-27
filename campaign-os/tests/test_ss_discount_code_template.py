"""Swing Shack discount-code template: canvases, selection, optional expiry."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "swing-shack"
ORANGE_HOT = np.array([0xE9, 0x51, 0x05])
LIME = np.array([0x70, 0xFF, 0x0F])

FIELDS = {
    "caption_hook": "15% OFF",
    "offer_subject": "ALL FITTINGS",
    "offer_expiry": "UNTIL END OF MAY",
    "cta": "FITTING15",
}


@pytest.fixture(scope="module")
def discount() -> dict:
    arch = archetype_by_id(BRAND, "ss-discount-code")
    assert arch
    return arch


def _render(arch: dict, fields: dict, channels: list[str]) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=fields,
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(discount: dict):
    out = _render(discount, FIELDS, ["instagram", "instagram_story", "facebook"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


def test_accent_colours_present(discount: dict):
    img = np.asarray(_render(discount, FIELDS, ["instagram"])["instagram"]).astype(int)
    orange = np.abs(img - ORANGE_HOT).sum(axis=2) < 80
    lime = np.abs(img - LIME).sum(axis=2) < 120
    assert orange.any(), "headline orange missing"
    assert lime.any(), "CTA lime missing"


def test_optional_expiry_omits_tagline(discount: dict):
    fields = {k: v for k, v in FIELDS.items() if k != "offer_expiry"}
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=discount,
        channels=["instagram"],
        fields=fields,
        photo_bytes=None,
    )
    assert out["instagram"]


def _ctx(monkeypatch, post_type: str = "", template_id: str = "") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": ["ss-fitting"],
        "subject": "",
        "post_type": post_type,
        "template_id": template_id,
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-discount"


def test_post_type_discount_code_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="discount_code")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-discount-code"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(monkeypatch, post_type="tip", template_id="ss-discount-code")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-discount-code"
