"""Stick retail templates: product-post (maker stack) and venue-post (partner plate).

Both take a maker logo from stick/logos/vendors/<slug>.png via fields["vendor_name"],
and product-post fits a transparent cut-out into its photo zone without stretching it
or turning the transparent part black.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from _lib.archetype_compose import ComposeError, compose_post_for_channels, vendor_slug
from _lib.archetypes import archetype_by_id

ROOT = Path(__file__).resolve().parents[2]
VENDORS = ROOT / "data" / "brand-directory" / "stick" / "logos" / "vendors"
BRAND = "stick"


def _cutout(w: int = 400, h: int = 900) -> bytes:
    """A grey product on a transparent background, with a faint shadow strip."""
    im = Image.new("RGBA", (w + 200, h + 200), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (w, h), (150, 150, 150, 255)), (100, 100))
    im.paste(Image.new("RGBA", (w + 200, 40), (0, 0, 0, 30)), (0, h + 150))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _photo(w: int = 1600, h: int = 2000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 90, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def _render(arch_id: str, fields: dict[str, str], photo: bytes) -> Image.Image:
    arch = archetype_by_id(BRAND, arch_id)
    assert arch, arch_id
    out = compose_post_for_channels(
        brand_id=BRAND, archetype=arch, channels=["instagram"], fields=fields, photo_bytes=photo
    )
    return Image.open(io.BytesIO(out["instagram"])).convert("RGB")


def _rect(im: Image.Image, r: dict[str, float]) -> np.ndarray:
    w, h = im.size
    return np.asarray(im)[int(r["y0"] * h) : int(r["y1"] * h), int(r["x0"] * w) : int(r["x1"] * w)]


@pytest.mark.parametrize(
    "name,slug",
    [("RIPIT", "ripit"), ("Takomo", "takomo"), ("L.A.B. Golf", "lab-golf"), ("Vice", "vice"), ("Callaway", "callaway")],
)
def test_vendor_slug(name: str, slug: str):
    assert vendor_slug(name) == slug


@pytest.mark.parametrize("slug", ["ripit", "takomo", "vice", "callaway"])
def test_vendor_logos_present(slug: str):
    p = VENDORS / f"{slug}.png"
    assert p.is_file()
    assert Image.open(p).mode == "RGBA"


@pytest.mark.parametrize("arch_id", ["stick-product-post", "stick-venue-post"])
def test_archetypes_vetted_with_pack(arch_id: str):
    arch = archetype_by_id(BRAND, arch_id)
    assert arch["vetted"] is True
    assert (ROOT / "data" / "brand-directory" / BRAND / arch["template_pack"] / "spec.json").is_file()


def test_product_post_keeps_cutout_transparency_and_draws_logo():
    arch = archetype_by_id(BRAND, "stick-product-post")
    im = _render(
        "stick-product-post",
        {"vendor_name": "Takomo", "product_name": "101U DRIVING IRON", "cta": "DM US FOR DETAILS"},
        _cutout(),
    )
    assert im.size == (1080, 1350)
    photo = _rect(im, arch["zones"]["photo"]["rect"])
    # The corners of the photo zone show the gradient, not black from a lost alpha channel.
    for corner in (photo[5, 5], photo[5, -5], photo[-5, 5], photo[-5, -5]):
        assert corner.mean() > 60
    # The product is not stretched to the zone: its grey sits in the middle, the sides stay gradient.
    mid_row = photo[photo.shape[0] // 2]
    grey = np.where((np.abs(mid_row.astype(int) - 150) < 6).all(axis=1))[0]
    assert 0 < len(grey) < photo.shape[1] * 0.6
    # The maker logo is drawn white in the vendor lockup.
    lock = _rect(im, arch["zones"]["vendor_lockup"]["rect"])
    assert (lock > 230).all(axis=2).sum() > 200


def test_product_post_needs_a_vendor_logo():
    with pytest.raises(ComposeError, match="no vendor logo"):
        _render(
            "stick-product-post",
            {"vendor_name": "Nobody Golf", "product_name": "X", "cta": "DM US FOR DETAILS"},
            _cutout(),
        )


def test_venue_post_plate_shows_vendor_logo_not_stick_logo_twice():
    arch = archetype_by_id(BRAND, "stick-venue-post")
    im = _render("stick-venue-post", {"vendor_name": "RIPIT"}, _photo())
    plate = _rect(im, arch["zones"]["plate"]["rect"])
    assert (plate > 230).all(axis=2).sum() > 500
    logo_zone = _rect(im, arch["zones"]["partner_logo"]["rect"])
    assert (logo_zone > 230).all(axis=2).sum() > 200
