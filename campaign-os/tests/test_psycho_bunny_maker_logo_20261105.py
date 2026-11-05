"""Psycho Bunny can go through the Stick product frame (G3, 2026-11-05).

Stick's Black Friday is Psycho Bunny, but live refused the product post with
"no vendor logo for 'Psycho Bunny'". Christelle cleared Psycho Bunny's image rights
on 5 Nov (Stick stocks it), so its logo joins the shared maker logos.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

BD = Path(__file__).resolve().parents[2] / "data" / "brand-directory"
LOGO = BD / "_shared" / "maker-logos" / "psycho-bunny.png"


def test_psycho_bunny_logo_is_a_transparent_png():
    assert LOGO.is_file()
    assert Image.open(LOGO).mode == "RGBA"


def test_psycho_bunny_logo_is_in_the_register():
    doc = json.loads((LOGO.parent / "logos.json").read_text(encoding="utf-8"))
    row = next((r for r in doc["logos"] if r["file"] == "psycho-bunny.png"), None)
    assert row and row["status"] == "official" and row["source"]


def test_psycho_bunny_rights_cleared():
    doc = json.loads((BD / "_system" / "image-sources.json").read_text(encoding="utf-8"))
    r = doc["brands"]["Psycho Bunny"]["rights"]
    assert r["status"] == "cleared" and r["basis"] and r["checked_on"] == "2026-11-05"


def test_stick_product_post_renders_psycho_bunny():
    arch = archetype_by_id("stick", "stick-product-post")
    buf = io.BytesIO()
    Image.new("RGBA", (600, 1100), (150, 150, 150, 255)).save(buf, format="PNG")
    fields = {"vendor_name": "Psycho Bunny", "product_name": "CLASSIC POLO", "cta": "DM US FOR DETAILS"}
    out = compose_post_for_channels(brand_id="stick", archetype=arch, channels=["instagram"],
                                    fields=fields, photo_bytes=buf.getvalue())
    assert out["instagram"]
