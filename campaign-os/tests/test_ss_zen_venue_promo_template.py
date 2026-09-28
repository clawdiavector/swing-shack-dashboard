"""Swing Shack zen-venue-promo template: platforms, stack, clipping, selection."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "swing-shack"
GREEN = np.array([0x74, 0xCB, 0x46])
WHITE_LO = 220


@pytest.fixture(scope="module")
def zen_promo() -> dict:
    arch = archetype_by_id(BRAND, "ss-zen-venue-promo")
    assert arch
    return arch


def _fields(headline: str = "Zen Swing Stage?", qualifier: str = "Slope changes everything") -> dict[str, str]:
    return {"caption_hook": headline, "qualifier": qualifier, "accent": "ss_green"}


def _render(arch: dict, fields: dict[str, str], channels: list[str]) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=fields,
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(zen_promo: dict):
    out = _render(zen_promo, _fields(), ["instagram", "instagram_story", "facebook", "gbp"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


def _headline_row(arr: np.ndarray) -> np.ndarray:
    band = arr[150:380].astype(int)
    green = np.abs(band - GREEN).sum(axis=2) < 60
    rows = np.nonzero(green.any(axis=1))[0]
    assert len(rows), "headline accent not found in expected band"
    # pick the scanline with the widest green run (headline accent, not UI specks)
    best = rows[0]
    best_span = 0
    for r in rows:
        cols = np.nonzero(green[r])[0]
        span = int(cols.max() - cols.min()) if len(cols) else 0
        if span > best_span:
            best_span = span
            best = r
    return band[best]


def test_headline_stays_one_line(zen_promo: dict):
    arr = np.asarray(_render(zen_promo, _fields(), ["instagram"])["instagram"])
    band = arr[150:380].astype(int)
    green = np.abs(band - GREEN).sum(axis=2) < 60
    rows = np.nonzero(green.any(axis=1))[0]
    assert rows.max() - rows.min() < 90, "headline wrapped to multiple rows"


def test_no_clipping(zen_promo: dict):
    row = _headline_row(np.asarray(_render(zen_promo, _fields(), ["instagram"])["instagram"]))
    green = np.abs(row - GREEN).sum(axis=1) < 60
    cols = np.nonzero(green)[0]
    assert cols.min() > 15
    assert cols.max() < 1040, "headline ink ran into frame"
    assert cols.max() > 950, "question mark missing from STAGE?"


def test_three_line_stack_order(zen_promo: dict):
    arr = np.asarray(_render(zen_promo, _fields(), ["instagram"])["instagram"]).astype(int)
    white = arr.min(axis=2) > WHITE_LO
    band = arr[150:380]
    green = np.abs(band - GREEN).sum(axis=2) < 60
    headline_top = 150 + int(np.nonzero(green.any(axis=1))[0].min())
    headline_bottom = 150 + int(np.nonzero(green.any(axis=1))[0].max())
    white_rows = np.nonzero(white.any(axis=1))[0]
    kicker_rows = white_rows[white_rows < headline_top]
    subline_rows = white_rows[white_rows > headline_bottom]
    assert len(kicker_rows) > 0, "expected kicker above headline"
    assert len(subline_rows) > 0, "expected subline below headline"
    assert kicker_rows.max() < headline_top - 10


def test_optional_subline_dropped_without_qualifier(zen_promo: dict):
    with_qual = np.asarray(_render(zen_promo, _fields(), ["instagram"])["instagram"]).astype(int)
    without = np.asarray(
        _render(zen_promo, {"caption_hook": "Zen Swing Stage?", "accent": "ss_green"}, ["instagram"])["instagram"]
    ).astype(int)
    assert not np.array_equal(with_qual, without)
    band = slice(280, 360)
    wq = with_qual[band].min(axis=2) > WHITE_LO
    wo = without[band].min(axis=2) > WHITE_LO
    assert wq.sum() > wo.sum(), "subline white text should drop when qualifier omitted"


def test_story_no_ig_post_scaled_headline(zen_promo: dict):
    """AC10: no second headline stack at ig_post y-fractions scaled onto 1920."""
    arr = np.asarray(_render(zen_promo, _fields(), ["instagram_story"])["instagram_story"]).astype(int)
    green = np.abs(arr - GREEN).sum(axis=2) < 60
    for y in range(240, 450):
        if np.count_nonzero(green[y]) > 400:
            pytest.fail(f"unexpected headline-width green band at y={y} (scaled ig_post duplicate)")


def test_kicker_thinner_than_headline(zen_promo: dict):
    """AC9: h3 kicker must not match display headline stroke mass."""
    arr = np.asarray(_render(zen_promo, _fields(), ["instagram"])["instagram"]).astype(int)
    white = arr.min(axis=2) > WHITE_LO
    kicker_h = int(np.count_nonzero(white[95:135].any(axis=1)))
    green_head = np.abs(arr[175:275] - GREEN).sum(axis=2) < 60
    headline_h = int(np.count_nonzero(green_head.any(axis=1)))
    assert kicker_h < headline_h, "kicker vertical ink span should be thinner than display headline"


def test_story_single_headline_band(zen_promo: dict):
    """Headline accent on story must appear once in the ig_story override band only."""
    arr = np.asarray(_render(zen_promo, _fields(), ["instagram_story"])["instagram_story"]).astype(int)
    green = np.abs(arr - GREEN).sum(axis=2) < 60
    wide_bands: list[tuple[int, int]] = []
    in_band = False
    start = 0
    for y in range(580, 780):
        cols = np.nonzero(green[y])[0]
        if len(cols) > 400:
            if not in_band:
                start = y
                in_band = True
        elif in_band:
            wide_bands.append((start, y - 1))
            in_band = False
    if in_band:
        wide_bands.append((start, 779))
    assert len(wide_bands) == 1, f"expected one story headline band, got {wide_bands}"


def test_accent_is_deterministic_without_override(zen_promo: dict):
    fields = _fields()
    a = compose_post_for_channels(
        brand_id=BRAND, archetype=zen_promo, channels=["instagram"], fields=fields, photo_bytes=None
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND, archetype=zen_promo, channels=["instagram"], fields=fields, photo_bytes=None
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


def test_post_type_venue_promo_selects_template(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-fitting", post_type="venue_promo")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-zen-venue-promo"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-membership", template_id="ss-zen-venue-promo")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-zen-venue-promo"
