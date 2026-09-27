"""Swing Shack ss-sale-offer template: canvases, compose, selection."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "swing-shack"
FIELDS = {
    "caption_hook": "10% OFF",
    "caption_body": "17 - 30 NOVEMBER",
    "cta": "DM US FOR MORE INFO",
}


@pytest.fixture(scope="module")
def sale_offer() -> dict:
    arch = archetype_by_id(BRAND, "ss-sale-offer")
    assert arch
    return arch


def _render(arch: dict, channels: list[str]) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=FIELDS,
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(sale_offer: dict):
    out = _render(sale_offer, ["instagram", "instagram_story", "facebook"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


def test_story_compose_is_deterministic(sale_offer: dict):
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=sale_offer,
        channels=["instagram_story"],
        fields=FIELDS,
        photo_bytes=None,
    )["instagram_story"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=sale_offer,
        channels=["instagram_story"],
        fields=FIELDS,
        photo_bytes=None,
    )["instagram_story"]
    assert a == b


def test_headline_region_has_text(sale_offer: dict):
    import numpy as np

    img = np.asarray(_render(sale_offer, ["instagram_story"])["instagram_story"])
    # measured headline band (1081×1920 → 1080×1920)
    band = img[246:660, 102:977].astype(int)
    bg = 58  # ss_charcoal on story canvas
    assert (np.abs(band - bg).sum(axis=2) > 40).sum() > 5000


def _ctx(monkeypatch, pillar_id: str, post_type: str = "", template_id: str = "") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": [pillar_id],
        "subject": "",
        "post_type": post_type,
        "template_id": template_id,
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-1"


def test_post_type_sale_offer_selects_template(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-membership", post_type="sale_offer")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-sale-offer"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-fitting", template_id="ss-sale-offer")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-sale-offer"


def test_sale_offer_pack_spec_exists():
    from pathlib import Path

    spec = (
        Path(__file__).resolve().parents[2]
        / "data/brand-directory/swing-shack/templates/sale-offer/spec.json"
    )
    assert spec.is_file()
    assert (spec.parent / "references/ref-01.jpg").is_file()
    assert (spec.parent / "golden/blackfriday-copy.jpg").is_file()
