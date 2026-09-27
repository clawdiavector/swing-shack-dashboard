"""Swing Shack did-you-know template: platforms, wrap, clipping, selection."""

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
GREEN = np.array([0x74, 0xCB, 0x46])


@pytest.fixture(scope="module")
def dyk() -> dict:
    arch = archetype_by_id(BRAND, "ss-did-you-know")
    assert arch
    return arch


def _render(arch: dict, headline: str, channels: list[str], accent: str = "ss_green") -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields={"caption_hook": headline, "accent": accent},
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(dyk: dict):
    out = _render(dyk, "Wrong flex hurts control?", ["instagram", "instagram_story", "facebook", "gbp"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


@pytest.mark.parametrize(
    ("headline", "lines"),
    [
        ("Golf can feel simpler?", ["GOLF", "CAN", "FEEL", "SIMPLER?"]),
        ("Your grip might be wrong?", ["YOUR", "GRIP", "MIGHT BE", "WRONG?"]),
        ("Set makeup can fix mishits?", ["SET", "MAKEUP", "CAN FIX", "MISHITS?"]),
        ("Your putter might be too long?", ["YOUR", "PUTTER", "MIGHT BE", "TOO LONG?"]),
    ],
)
def test_balanced_wrap_matches_reference_breaks(headline: str, lines: list[str]):
    font = _load_brand_font(BRAND, "display", 181)
    assert _wrap_balanced(headline.upper(), font, None, 4, set(), 0.0) == lines


def test_long_line_is_not_clipped(dyk: dict):
    img = np.asarray(_render(dyk, "Wrong flex hurts control?", ["instagram"])["instagram"]).astype(int)
    green = np.abs(img - GREEN).sum(axis=2) < 60
    cols = np.nonzero(green.any(axis=0))[0]
    assert cols.min() > 60
    assert cols.max() < 1080 - 36, "headline ran into the frame"
    assert cols.max() > 900, "question mark missing from CONTROL?"


def test_accent_is_deterministic_without_override(dyk: dict):
    a = compose_post_for_channels(
        brand_id=BRAND, archetype=dyk, channels=["instagram"], fields={"caption_hook": "Bounce saves shots?"}, photo_bytes=None
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND, archetype=dyk, channels=["instagram"], fields={"caption_hook": "Bounce saves shots?"}, photo_bytes=None
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


def test_post_type_rule_matching():
    when = {"post_type_in": ["tip", "did_you_know"]}
    assert arch_lib._rule_matches(when, {"post_type": "tip"})
    assert not arch_lib._rule_matches(when, {"post_type": ""})
    assert not arch_lib._rule_matches(when, {"post_type": "price_package"})


def test_post_type_tip_selects_did_you_know(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-fitting", post_type="tip")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-did-you-know"


def test_fitting_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-service-frame"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-membership", template_id="ss-did-you-know")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-did-you-know"
