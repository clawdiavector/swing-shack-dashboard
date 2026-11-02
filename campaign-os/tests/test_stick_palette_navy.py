"""Stick's navy is the darker #042840 its own graphics use, not the petrol #003D54 (Christelle, 2 Nov 2026)."""

from __future__ import annotations

import json
from pathlib import Path

PALETTE = Path(__file__).resolve().parents[2] / "data" / "brand-directory" / "stick" / "palette" / "brand.json"


def _palette() -> dict:
    return json.loads(PALETTE.read_text(encoding="utf-8"))


def test_stick_primary_is_dark_navy():
    assert _palette()["palette"]["primary"]["hex"].upper() == "#042840"


def test_stick_brand_navy_token_is_dark_navy():
    assert _palette()["tokens"]["brand_navy"].upper() == "#042840"


def test_petrol_navy_is_gone():
    assert "#003D54" not in PALETTE.read_text(encoding="utf-8").upper()
