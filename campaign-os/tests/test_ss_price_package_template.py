"""Swing Shack price-package + price-list templates."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import _wrap_explicit, compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "swing-shack"
GREEN = np.array([0x74, 0xCB, 0x46])


PACKAGE_FIELDS = {
    "caption_hook": "Birdie Hunter",
    "qualifier": "1 lesson & unlimited practice",
    "price": "R 2 300",
    "price_period": "Per month",
    "cta": "Book online or DM us",
    "accent": "ss_orange",
}

LIST_FIELDS = {
    "caption_hook": "Coaching packages",
    "price_labels": "1x session|3x sessions|5x sessions|10x sessions",
    "price_values": "R 820|R 2350|R 3850|R 7200",
    "cta": "DM us for details",
    "accent": "ss_blue",
}


@pytest.fixture(scope="module")
def pkg() -> dict:
    arch = archetype_by_id(BRAND, "ss-price-package")
    assert arch
    return arch


@pytest.fixture(scope="module")
def rate_list() -> dict:
    arch = archetype_by_id(BRAND, "ss-price-list")
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


def test_price_package_platform_canvases(pkg: dict):
    out = _render(pkg, PACKAGE_FIELDS, ["instagram", "instagram_story", "facebook"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


def test_price_list_explicit_wrap_row_count():
    lines = _wrap_explicit(LIST_FIELDS["price_labels"], 4)
    assert lines == ["1x session", "3x sessions", "5x sessions", "10x sessions"]


def test_long_package_name_not_clipped(pkg: dict):
    fields = {**PACKAGE_FIELDS, "caption_hook": "Birdie Hunter"}
    img = np.asarray(_render(pkg, fields, ["instagram"])["instagram"]).astype(int)
    orange = np.array([0xE2, 0x71, 0x23])
    mask = np.abs(img - orange).sum(axis=2) < 80
    cols = np.nonzero(mask.any(axis=0))[0]
    assert cols.min() > 60
    assert cols.max() < 1080 - 36
    assert cols.max() > 850


def test_accent_is_deterministic_with_override(pkg: dict):
    a = compose_post_for_channels(
        brand_id=BRAND, archetype=pkg, channels=["instagram"], fields=PACKAGE_FIELDS, photo_bytes=None
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND, archetype=pkg, channels=["instagram"], fields=PACKAGE_FIELDS, photo_bytes=None
    )["instagram"]
    assert a == b


def test_rate_list_renders(rate_list: dict):
    out = _render(rate_list, LIST_FIELDS, ["instagram"])
    assert out["instagram"].size == (1080, 1350)


def _ctx(monkeypatch, *, pillar_id: str, post_type: str = "", template_id: str = "") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": [pillar_id],
        "subject": "",
        "post_type": post_type,
        "template_id": template_id,
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-1"


def test_post_type_price_package_beats_coaching_pillar(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="coaching", post_type="price_package")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-price-package"


def test_post_type_price_list_selects_rate_card(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-coaching", post_type="price_list")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-price-list"


def test_pinned_template_id_wins_over_post_type(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="coaching", post_type="price_package", template_id="ss-did-you-know")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-did-you-know"
