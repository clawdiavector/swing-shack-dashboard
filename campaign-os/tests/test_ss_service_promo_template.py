"""Swing Shack ss-service-promo template: platforms, wrap, lockup, selection."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import _wrap_balanced, compose_post_for_channels
from _lib.archetypes import archetype_by_id
from _lib.brand_overlay import _load_brand_font

BRAND = "swing-shack"


@pytest.fixture(scope="module")
def promo() -> dict:
    arch = archetype_by_id(BRAND, "ss-service-promo")
    assert arch
    return arch


def _fields(headline: str, subhead: str, service: str, accent: str = "ss_blue") -> dict[str, str]:
    return {
        "caption_hook": headline,
        "cta": subhead,
        "service_label": service,
        "accent": accent,
    }


def _render(arch: dict, fields: dict[str, str], channels: list[str]) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=fields,
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(promo: dict):
    fields = _fields(
        "OFF-THE-RACK IS FOR GROCERIES",
        "GET EQUIPMENT BUILT FOR YOU",
        "CLUB FITTING",
    )
    out = _render(promo, fields, ["instagram", "instagram_story", "facebook"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


@pytest.mark.parametrize(
    ("headline", "lines"),
    [
        (
            "YOU WOULDN'T RUN A MARATHON IN SOMEONE ELSE'S SHOES",
            ["YOU WOULDN'T", "RUN A MARATHON", "IN SOMEONE", "ELSE'S SHOES"],
        ),
        (
            "OFF-THE-RACK IS FOR GROCERIES",
            ["OFF-THE-RACK", "IS", "FOR", "GROCERIES"],
        ),
    ],
)
def test_balanced_wrap_matches_reference_breaks(headline: str, lines: list[str]):
    font = _load_brand_font(BRAND, "display", 123)
    assert font is not None
    assert _wrap_balanced(headline.upper(), font, None, 4, set(), 0.0) == lines


def test_headline_not_clipped(promo: dict):
    fields = _fields(
        "YOU WOULDN'T RUN A MARATHON IN SOMEONE ELSE'S SHOES",
        "WHY PLAY WITH SOMEONE ELSE'S SPECS?",
        "CLUB FITTING",
        "ss_purple",
    )
    img = np.asarray(_render(promo, fields, ["instagram"])["instagram"]).astype(int)
    purple = np.abs(img - np.array([0x8F, 0x4B, 0xFA])).sum(axis=2) < 80
    cols = np.nonzero(purple.any(axis=0))[0]
    assert cols.min() > 60
    assert cols.max() < 1080 - 40


def test_lockup_near_canvas_centre(promo: dict):
    fields = _fields(
        "BUY FEWER GOLF BALLS",
        "INVEST IN A SWING THAT KEEPS THEM OUT OF THE WOODS.",
        "COACHING",
        "ss_green",
    )
    img = np.asarray(_render(promo, fields, ["instagram"])["instagram"])
    white_rows = np.where((img > 240).all(axis=2).any(axis=0))[0]
    assert white_rows.size > 0
    centre = int(white_rows.mean())
    assert abs(centre - 540) <= 80


def test_accent_is_deterministic(promo: dict):
    fields = _fields(
        "OFF-THE-RACK IS FOR GROCERIES",
        "GET EQUIPMENT BUILT FOR YOU",
        "CLUB FITTING",
        "ss_blue",
    )
    a = compose_post_for_channels(
        brand_id=BRAND, archetype=promo, channels=["instagram"], fields=fields, photo_bytes=None
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND, archetype=promo, channels=["instagram"], fields=fields, photo_bytes=None
    )["instagram"]
    assert a == b


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


def test_service_promo_post_type_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-fitting", post_type="service_promo")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-service-promo"


def test_fitting_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-service-frame"


def test_visual_copy_sets_service_label_for_fitting_promo(monkeypatch):
    from _lib.compose_visual_copy import visual_copy_for_archetype

    item = _ctx(monkeypatch, pillar_id="ss-fitting", post_type="service_promo")
    arch = arch_lib.select_archetype(BRAND, item)
    fields = visual_copy_for_archetype(
        brand_id=BRAND,
        moment_id=item,
        caption="Book a fitting this week.",
        archetype=arch,
    )
    assert fields.get("service_label") == "CLUB FITTING"
