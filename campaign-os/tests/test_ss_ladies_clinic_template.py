"""Swing Shack ss-ladies-clinic: multi-page card, canvases, selection."""

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
    assert arch.get("multi_render") == ["page1", "page2"]
    return arch


def test_multi_page_outputs(clinic: dict):
    page1_fields = {
        "render_page": "page1",
        "headline": "LADIES CLINIC",
        "event_date": "FRIDAY, 12 SEPTEMBER - 18:00",
        "event_host": "HOSTED BY CATHERINE LAU",
    }
    page2_fields = {
        "render_page": "page2",
        "body_text": "IT'S THE PERFECT CHANCE TO\nLEARN, CONNECT, AND HAVE\nFUN ON THE RANGE.",
        "cta_lockup": "SPOTS ARE LIMITED.\nBOOK YOURS TODAY!",
        "booking_url": "BOOK ONLINE @\nSWINGSHACK.CO.ZA\nOR DM US",
    }
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=clinic,
        channels=["instagram"],
        fields=page1_fields,
        photo_bytes=None,
    )
    assert "instagram" in out and "instagram__page2" in out
    assert Image.open(io.BytesIO(out["instagram"])).size == (1080, 1350)
    out2 = compose_post_for_channels(
        brand_id=BRAND,
        archetype=clinic,
        channels=["instagram"],
        fields=page2_fields,
        photo_bytes=None,
    )
    assert out["instagram"] != out2["instagram"]


def test_page1_and_page2_differ(clinic: dict):
    p1 = compose_post_for_channels(
        brand_id=BRAND,
        archetype=clinic,
        channels=["instagram"],
        fields={
            "render_page": "page1",
            "headline": "LADIES CLINIC",
            "event_date": "FRIDAY, 12 SEPTEMBER - 18:00",
            "event_host": "HOSTED BY CATHERINE LAU",
        },
        photo_bytes=None,
    )["instagram"]
    both = compose_post_for_channels(
        brand_id=BRAND,
        archetype=clinic,
        channels=["instagram"],
        fields={
            "headline": "LADIES CLINIC",
            "event_date": "FRIDAY, 12 SEPTEMBER - 18:00",
            "event_host": "HOSTED BY CATHERINE LAU",
            "body_text": "FUN ON THE RANGE.",
            "cta_lockup": "BOOK TODAY!",
            "booking_url": "BOOK ONLINE @",
        },
        photo_bytes=None,
    )
    assert both["instagram"] == p1
    assert both["instagram__page2"] != p1


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
