"""Swing Shack ss-event-poster: canvases, attach chain, selection."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "swing-shack"

FIELDS = {
    "caption_hook": "RYDER CUP",
    "offer_subject": "27 & 28 SEPTEMBER",
    "bio_1": "10 PLAYERS PER TEAM",
    "bio_2": "SATURDAY 27 SEPTEMBER",
    "bio_3": "SUNDAY 28 SEPTEMBER",
    "benefits": "ALTERNATE SHOT|SCRAMBLE",
    "caption_body": "INDIVIDUAL MATCHES",
    "price": "R250 ENTRY PER PLAYER",
    "cta": "DM US TO ENTER",
}


@pytest.fixture(scope="module")
def poster() -> dict:
    arch = archetype_by_id(BRAND, "ss-event-poster")
    assert arch
    return arch


def _render(arch: dict, channels: list[str]) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=dict(FIELDS),
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(poster: dict):
    out = _render(poster, ["instagram", "instagram_story", "facebook"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


def test_explicit_wrap_two_lines(poster: dict):
    out = _render(poster, ["instagram"])["instagram"]
    arr = np.asarray(out)
    red = np.array([0xD3, 0x20, 0x26])
    mask = np.abs(arr.astype(int) - red).sum(axis=2) < 80
    rows = np.where(mask.any(axis=1))[0]
    assert len(rows) > 50, "expected red schedule copy on canvas"


def test_compose_both_canvases_no_compose_error(poster: dict):
    _render(poster, ["instagram", "instagram_story"])


def test_post_type_event_poster_selects(poster: dict, monkeypatch):
    ctx = {
        "has_product_item": False,
        "pillar_in": ["ss-membership"],
        "subject": "",
        "post_type": "event_poster",
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _b, _i: dict(ctx))
    assert arch_lib.select_archetype(BRAND, "calendar_candidate:swing-shack:x")["id"] == "ss-event-poster"
