"""Swing Shack fitting-headline template: platforms, lockup, clipping, selection."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "swing-shack"
FIT_BLUE = np.array([0x15, 0x78, 0xDD])
FIT_ORANGE = np.array([0xEA, 0x86, 0x24])
WHITE_LO = 220


@pytest.fixture(scope="module")
def fitting_headline() -> dict:
    arch = archetype_by_id(BRAND, "ss-fitting-headline")
    assert arch
    return arch


def _fields(kicker: str, lockup: str, accent: str = "ss_fit_blue") -> dict[str, str]:
    return {"caption_hook": kicker, "service_lockup": lockup, "accent": accent}


def _render(arch: dict, fields: dict[str, str], channels: list[str]) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=fields,
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(fitting_headline: dict):
    out = _render(
        fitting_headline,
        _fields("DROP MORE PUTTS WITH A", "PUTTER FITTING", "ss_fit_orange"),
        ["instagram", "instagram_story", "facebook", "gbp"],
    )
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


def test_lockup_stays_on_one_line(fitting_headline: dict):
    img = _render(
        fitting_headline,
        _fields("DROP MORE PUTTS WITH A", "PUTTER FITTING", "ss_fit_orange"),
        ["instagram"],
    )["instagram"]
    arr = np.asarray(img).astype(int)
    orange = np.abs(arr - FIT_ORANGE).sum(axis=2) < 80
    rows = np.nonzero(orange.any(axis=1))[0]
    assert rows.max() - rows.min() < 130, "lockup wrapped to multiple rows"


def test_no_clipping(fitting_headline: dict):
    img = np.asarray(
        _render(
            fitting_headline,
            _fields("DROP MORE PUTTS WITH A", "PUTTER FITTING", "ss_fit_orange"),
            ["instagram"],
        )["instagram"]
    ).astype(int)
    orange = np.abs(img - FIT_ORANGE).sum(axis=2) < 80
    cols = np.nonzero(orange.any(axis=0))[0]
    assert cols.min() > 37
    assert cols.max() < 1080 - 37
    assert cols.max() > 950, "final G missing from FITTING"


def test_kicker_sits_18px_above_headline(fitting_headline: dict):
    img = np.asarray(
        _render(
            fitting_headline,
            _fields("HIT MORE GREENS WITH AN", "IRON FITTING", "ss_fit_blue"),
            ["instagram"],
        )["instagram"]
    ).astype(int)
    white = img.min(axis=2) > WHITE_LO
    blue = np.abs(img - FIT_BLUE).sum(axis=2) < 80
    kicker_rows = np.nonzero(white.any(axis=1))[0]
    lockup_rows = np.nonzero(blue.any(axis=1))[0]
    kicker_bottom = int(kicker_rows.max())
    lockup_top = int(lockup_rows.min())
    gap = lockup_top - kicker_bottom
    assert 12 <= gap <= 28, f"expected ~18px gap, got {gap}"


def test_accent_is_deterministic_without_override(fitting_headline: dict):
    fields = _fields("HIT MORE GREENS WITH AN", "IRON FITTING")
    a = compose_post_for_channels(
        brand_id=BRAND, archetype=fitting_headline, channels=["instagram"], fields=fields, photo_bytes=None
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND, archetype=fitting_headline, channels=["instagram"], fields=fields, photo_bytes=None
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


def test_post_type_fitting_headline_selects_template(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-fitting", post_type="fitting_headline")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-fitting-headline"


def test_fitting_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-service-frame"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-membership", template_id="ss-fitting-headline")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-fitting-headline"
