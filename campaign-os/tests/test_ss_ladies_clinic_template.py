"""Swing Shack ss-ladies-clinic: variants, canvases, selection."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "swing-shack"


@pytest.fixture(scope="module")
def clinic() -> dict:
    arch = archetype_by_id(BRAND, "ss-ladies-clinic")
    assert arch
    return arch


def _render(arch: dict, fields: dict[str, str]) -> Image.Image:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=["instagram", "facebook"],
        fields=fields,
        photo_bytes=None,
    )
    return Image.open(io.BytesIO(out["instagram"])).convert("RGB")


def test_platform_canvases(clinic: dict):
    fields = {
        "variant": "invite",
        "caption_hook": "LADIES CLINIC",
        "qualifier": "FRIDAY, 12 SEPTEMBER - 18:00",
        "cta": "HOSTED BY CATHERINE LAU",
        "accent": "ss_clinic_magenta",
    }
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=clinic,
        channels=["instagram", "facebook"],
        fields=fields,
        photo_bytes=None,
    )
    assert {k: Image.open(io.BytesIO(v)).size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "facebook": (1080, 1350),
    }


def test_invite_and_detail_variants_differ(clinic: dict):
    invite = _render(
        clinic,
        {
            "variant": "invite",
            "caption_hook": "LADIES CLINIC",
            "qualifier": "FRIDAY, 12 SEPTEMBER - 18:00",
            "cta": "HOSTED BY CATHERINE LAU",
            "accent": "ss_clinic_magenta",
        },
    )
    detail = _render(
        clinic,
        {
            "variant": "detail",
            "caption_hook": "LEARN, CONNECT, AND HAVE FUN ON THE RANGE.",
            "qualifier": "SPOTS ARE LIMITED. BOOK YOURS TODAY!",
            "cta": "BOOK ONLINE @ SWINGSHACK.CO.ZA OR DM US",
        },
    )
    assert invite.tobytes() != detail.tobytes()


def test_clinic_invite_post_type_selects_archetype(monkeypatch):
    ctx = {
        "has_product_item": False,
        "pillar_in": ["ss-coaching"],
        "subject": "",
        "post_type": "clinic_invite",
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    assert arch_lib.select_archetype(BRAND, "calendar_candidate:swing-shack:cal-1")["id"] == "ss-ladies-clinic"
