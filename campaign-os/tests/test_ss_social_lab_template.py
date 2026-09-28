"""Swing Shack social-lab contest template: canvases, explicit body, CTA scrim, selection."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import _wrap_explicit, compose_post_for_channels
from _lib.archetypes import archetype_by_id
from _lib.compose_visual_copy import visual_copy_for_archetype

BRAND = "swing-shack"
ORANGE = np.array([0xE2, 0x71, 0x23])

FIELDS = {
    "caption_hook": "WIN A LAB OZ.1",
    "offer_subject": "PAR 3 CHALLENGE",
    "offer_expiry": "1 SEPTEMBER - 31 OCTOBER",
    "price": "R500",
    "caption_body": "R100 PER EXTRA ATTEMPT\nUNLIMITED ATTEMPTS ALLOWED",
    "cta": "DM US FOR MORE INFO",
}


@pytest.fixture(scope="module")
def social_lab() -> dict:
    arch = archetype_by_id(BRAND, "ss-social-lab")
    assert arch
    return arch


def _render(arch: dict, fields: dict | None = None, channels: list[str] | None = None) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels or ["instagram", "instagram_story", "facebook"],
        fields=fields or FIELDS,
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(social_lab: dict):
    out = _render(social_lab, channels=["instagram", "instagram_story", "facebook", "gbp"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


def test_body_wrap_is_explicit_not_reflowed():
    body = "R100 PER EXTRA ATTEMPT\nUNLIMITED ATTEMPTS ALLOWED"
    assert _wrap_explicit(body, 2) == [
        "R100 PER EXTRA ATTEMPT",
        "UNLIMITED ATTEMPTS ALLOWED",
    ]
    long_line = "A" * 80 + "\n" + "B" * 80
    assert len(_wrap_explicit(long_line, 2)) == 2


def test_compose_body_sidecar_passthrough(social_lab: dict):
    fields = visual_copy_for_archetype(
        brand_id=BRAND,
        archetype=social_lab,
        moment_id="proposal:swing-shack:social-lab",
        caption="Hook line\nignored",
        sidecar={
            "compose_headline": "Win a LAB OZ.1",
            "compose_subject": "Par 3 Challenge",
            "compose_expiry": "1 September – 31 October",
            "compose_price": "R500",
            "compose_body": "Line one\nLine two",
            "compose_cta": "DM us",
        },
    )
    assert fields["caption_body"] == "Line one\nLine two"
    assert fields["offer_subject"] == "Par 3 Challenge"


def test_no_clipping_at_max_chars(social_lab: dict):
    for ch in ("instagram", "instagram_story"):
        img = np.asarray(_render(social_lab, channels=[ch])[ch]).astype(int)
        orange = np.abs(img - ORANGE).sum(axis=2) < 90
        cols = np.nonzero(orange.any(axis=0))[0]
        assert cols.max() < (1080 if ch == "instagram" else 1080) - 24, f"{ch} orange text clipped right"
        assert cols.min() > 20, f"{ch} orange text clipped left"


def test_cta_legible_over_photo(social_lab: dict):
    arch = social_lab
    w, h = 1080, 1350
    zones = arch["zones"]
    cta = zones["cta"]["rect"]
    y0, y1 = int(cta["y0"] * h), int(cta["y1"] * h)
    x0, x1 = int(cta["x0"] * w), int(cta["x1"] * w)
    composed = np.asarray(_render(arch, channels=["instagram"])["instagram"]).astype(float)
    band = composed[y0:y1, x0:x1].mean()
    # CTA sits on the solid-black scrim band (feed), not bright grass-only pixels.
    assert band.mean() < 80, "CTA region too bright — likely on unscrimmed photo"


def _ctx(monkeypatch, post_type: str = "", template_id: str = "") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": ["ss-fitting"],
        "subject": "",
        "post_type": post_type,
        "template_id": template_id,
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-social-lab"


@pytest.mark.parametrize("post_type", ["contest", "giveaway", "challenge"])
def test_selection_via_post_type(monkeypatch, post_type: str):
    item = _ctx(monkeypatch, post_type=post_type)
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-social-lab"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(monkeypatch, post_type="tip", template_id="ss-social-lab")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-social-lab"
