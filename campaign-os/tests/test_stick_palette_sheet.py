"""Stick's colours are the two on its official sheet (colour_font.pdf): navy #003D54 and grey #D2D2D2 (Christelle, 3 Nov 2026)."""

from __future__ import annotations

import json
from pathlib import Path

PALETTE = Path(__file__).resolve().parents[2] / "data" / "brand-directory" / "stick" / "palette" / "brand.json"


def _palette() -> dict:
    return json.loads(PALETTE.read_text(encoding="utf-8"))


def test_stick_primary_is_sheet_navy():
    assert _palette()["palette"]["primary"]["hex"].upper() == "#003D54"


def test_stick_brand_navy_token_is_sheet_navy():
    assert _palette()["tokens"]["brand_navy"].upper() == "#003D54"


def test_stick_grey_is_sheet_grey():
    assert _palette()["tokens"]["brand_grey"].upper() == "#D2D2D2"
