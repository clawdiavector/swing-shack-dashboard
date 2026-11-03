"""Bag Drop weekly-deal story template, measured from the designer's six stories (3 Nov 2026).

Christelle sent the week's deal stories (30% off Srixon & Mizuno heads, 20% off selected
shafts, 20% off putters), each in two colourways: white top over a navy panel with a sage
bar, or navy top over a white panel with a navy bar. Deals rotate weekly, so the OS has to
draw next week's from typed text instead of a designer redrawing them. These checks hold
the render to the references: bands, logo, line positions, maker logos, the colours, and
that a long line shrinks rather than runs off the story.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import ComposeError, compose_post_for_channels
from _lib.archetypes import archetype_by_id

BRAND = "bag-drop"
REPO = Path(__file__).resolve().parents[2]
BAG_DROP = REPO / "data" / "brand-directory" / BRAND
REFS = BAG_DROP / "templates" / "weekly-deal" / "references"

NAVY = (0x29, 0x46, 0x64)
SAGE = (0x6C, 0x7C, 0x5F)
WHITE = (255, 255, 255)

MAKERS = {"vendor_name": "Srixon", "vendor_name_2": "Mizuno"}
SM = "SRIXON & MIZUNO|DRIVER & WOOD HEADS|THIS WEEK"

# ref, archetype, fields, text colour, panel colour
CASES = [
    ("ref-01.jpg", "bd-weekly-deal-makers", {"headline": "30% OFF", "deal_detail": SM, **MAKERS}, WHITE, NAVY),
    ("ref-02.jpg", "bd-weekly-deal-makers-navy", {"headline": "30% OFF", "deal_detail": SM, **MAKERS}, SAGE, WHITE),
    ("ref-03.jpg", "bd-weekly-deal", {"headline": "20% OFF", "deal_detail": "SELECTED SHAFTS|THIS WEEK"}, WHITE, NAVY),
    ("ref-04.jpg", "bd-weekly-deal-navy", {"headline": "20% OFF", "deal_detail": "SELECTED SHAFTS|THIS WEEK"}, SAGE, WHITE),
    ("ref-05.jpg", "bd-weekly-deal-navy", {"headline": "20% OFF", "deal_detail": "PUTTERS|THIS WEEK"}, SAGE, WHITE),
    ("ref-06.jpg", "bd-weekly-deal", {"headline": "20% OFF", "deal_detail": "PUTTERS|THIS WEEK"}, WHITE, NAVY),
]

# Measured on the references: top band 0-707, panel 709-1791, bottom bar 1793-1919.
TOP_Y, PANEL_Y, BAR_Y = 350, 1250, 1860


def _render(arch_id: str, fields: dict) -> Image.Image:
    arch = archetype_by_id(BRAND, arch_id)
    assert arch, arch_id
    out = compose_post_for_channels(
        brand_id=BRAND, archetype=arch, channels=["instagram_story"], fields=fields, photo_bytes=None
    )
    return Image.open(io.BytesIO(out["instagram_story"])).convert("RGB")


def _ref(name: str) -> Image.Image:
    return Image.open(REFS / name).convert("RGB").resize((1080, 1920), Image.LANCZOS)


def _text_rows(img: Image.Image, colour: tuple, y0: int = 1100, y1: int = 1791) -> list[tuple[int, int, int, int]]:
    """(top, bottom, left, right) of each line of text in the panel, in the given colour."""
    a = np.asarray(img).astype(int)
    m = np.abs(a - np.array(colour)).sum(2) < 120
    m[:y0] = False
    m[y1:] = False
    m[:, :20] = False
    m[:, -20:] = False
    rows = m.sum(1) > 0
    out, start = [], None
    for y, on in enumerate(rows):
        if on and start is None:
            start = y
        elif not on and start is not None:
            xs = np.where(m[start:y].any(0))[0]
            out.append((start, y - 1, int(xs[0]), int(xs[-1])))
            start = None
    return out


def _close(a: tuple, b: tuple, tol: int = 12) -> bool:
    return all(abs(int(x) - int(y)) <= tol for x, y in zip(a, b))


@pytest.mark.parametrize("ref,arch_id,fields,text,panel", CASES, ids=[c[0] for c in CASES])
def test_bands_match_reference(ref, arch_id, fields, text, panel):
    img = _render(arch_id, fields)
    assert img.size == (1080, 1920)
    want = _ref(ref)
    for y in (TOP_Y, PANEL_Y, BAR_Y):
        assert _close(img.getpixel((30, y)), want.getpixel((30, y)), 6), (ref, y)


@pytest.mark.parametrize("ref,arch_id,fields,text,panel", CASES, ids=[c[0] for c in CASES])
def test_text_lines_sit_where_the_designer_put_them(ref, arch_id, fields, text, panel):
    y0 = 1300 if "makers" in arch_id else 1100  # below the maker logos
    got = _text_rows(_render(arch_id, fields), text, y0)
    want = _text_rows(_ref(ref), text, y0)
    assert len(got) == len(want), (got, want)
    for g, w in zip(got, want):
        assert abs(g[0] - w[0]) <= 10 and abs(g[1] - w[1]) <= 10, (g, w)
        # Saira stands in for the designer's font, so widths get some slack.
        gw, ww = g[3] - g[2], w[3] - w[2]
        assert abs(gw - ww) <= 0.08 * ww, (g, w)
        assert abs((g[2] + g[3]) / 2 - 540) <= 8, g


@pytest.mark.parametrize("ref,arch_id,fields,text,panel", CASES, ids=[c[0] for c in CASES])
def test_render_is_close_to_reference(ref, arch_id, fields, text, panel):
    got = np.asarray(_render(arch_id, fields).convert("L")).astype(int)
    want = np.asarray(_ref(ref).convert("L")).astype(int)
    assert (np.abs(got - want) > 80).mean() < 0.03


@pytest.mark.parametrize("arch_id", ["bd-weekly-deal-makers", "bd-weekly-deal-makers-navy"])
def test_maker_logos_drawn_in_their_slots(arch_id):
    img = np.asarray(_render(arch_id, {"headline": "30% OFF", "deal_detail": SM, **MAKERS})).astype(int)
    panel = img[1250, 30]
    for y0, y1 in ((829, 970), (1065, 1251)):  # Srixon, Mizuno, measured on ref-01/02
        ink = (np.abs(img[y0:y1, 300:780] - panel).sum(2) > 60).mean()
        assert ink > 0.08, (arch_id, y0)


def test_maker_layout_needs_both_maker_logos():
    with pytest.raises(ComposeError):
        _render("bd-weekly-deal-makers", {"headline": "30% OFF", "deal_detail": SM, "vendor_name": "Srixon"})
    with pytest.raises(ComposeError):
        _render("bd-weekly-deal-makers", {"headline": "30% OFF", "deal_detail": SM, **MAKERS, "vendor_name_2": "Nobody Golf"})


def test_long_detail_line_shrinks_inside_the_story():
    img = _render("bd-weekly-deal", {"headline": "35% OFF", "deal_detail": "ALL CALLAWAY AND PING WEDGE HEADS|VOTING DAY ONLY"})
    rows = _text_rows(img, WHITE)
    assert len(rows) == 3
    for top, bottom, left, right in rows:
        assert left >= 54 and right <= 1026, (left, right)


def test_render_is_deterministic():
    fields = {"headline": "20% OFF", "deal_detail": "PUTTERS|THIS WEEK"}
    a = _render("bd-weekly-deal", fields)
    b = _render("bd-weekly-deal", fields)
    assert a.tobytes() == b.tobytes()


def test_palette_is_the_store_navy_and_sage():
    doc = json.loads((BAG_DROP / "palette" / "brand.json").read_text(encoding="utf-8"))
    tokens = {k: v.upper() for k, v in doc["tokens"].items()}
    assert tokens["bd_navy"] == "#294664"
    assert tokens["bd_sage"] == "#6C7C5F"
    assert doc["palette"]["primary"]["hex"].upper() == "#294664"
    assert "#F4A261" not in json.dumps(doc).upper()  # the old orange guess


def test_weekly_deal_post_type_selects_template(monkeypatch):
    ctx = {"has_product_item": False, "pillar_in": ["bags-retail"], "subject": "", "post_type": "weekly_deal", "template_id": ""}
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _b, _i: dict(ctx))
    assert arch_lib.select_archetype(BRAND, f"calendar_candidate:{BRAND}:cal-1")["id"] == "bd-weekly-deal"
