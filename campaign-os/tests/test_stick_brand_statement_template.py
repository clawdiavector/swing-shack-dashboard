"""Stick brand-statement template: platforms, mint body, selection, determinism."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id

from pathlib import Path

BRAND = "stick"
NAVY = np.array([7, 60, 82])
MINT = np.array([36, 255, 175])
ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data/brand-directory/stick/templates/brand-statement/golden/instagram.png"
ARCH_ID = "stick-brand-statement"

CATEGORY_HOOK = "FITTINGS\nCOACHING\nEQUIPMENT\nAPPAREL"
SENTENCE_HOOK = (
    "WE FIT THE EQUIPMENT TO THE PLAYER.\nNEVER THE OTHER WAY AROUND."
)


@pytest.fixture(scope="module")
def arch() -> dict:
    row = archetype_by_id(BRAND, ARCH_ID)
    assert row
    return row


def _render(arch: dict, caption_hook: str, channels: list[str]) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields={"caption_hook": caption_hook},
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def _mint_mask(img: np.ndarray) -> np.ndarray:
    return np.abs(img.astype(int) - MINT).sum(axis=2) < 60


def _zone_has_content(img: np.ndarray, rect: dict[str, float], w: int, h: int) -> bool:
    x0 = int(rect["x0"] * w)
    y0 = int(rect["y0"] * h)
    x1 = int(rect["x1"] * w)
    y1 = int(rect["y1"] * h)
    crop = img[y0:y1, x0:x1]
    return crop.std() > 8


@pytest.mark.parametrize("caption_hook", [CATEGORY_HOOK, SENTENCE_HOOK])
def test_platform_canvases(arch: dict, caption_hook: str):
    out = _render(
        arch,
        caption_hook,
        ["instagram", "instagram_story", "facebook"],
    )
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "instagram_story": (1080, 1920),
        "facebook": (1080, 1350),
    }


@pytest.mark.parametrize("caption_hook", [CATEGORY_HOOK, SENTENCE_HOOK])
def test_navy_field_and_mint_body(arch: dict, caption_hook: str):
    img = np.asarray(_render(arch, caption_hook, ["instagram"])["instagram"])
    assert np.abs(img[0, 0].astype(int) - NAVY).max() <= 3
    assert _mint_mask(img).any()


@pytest.mark.parametrize("caption_hook", [CATEGORY_HOOK, SENTENCE_HOOK])
def test_logo_and_tagline_present(arch: dict, caption_hook: str):
    img = np.asarray(_render(arch, caption_hook, ["instagram"])["instagram"])
    zones = arch["zones"]
    assert _zone_has_content(img, zones["logo"]["rect"], 1080, 1350)
    assert _zone_has_content(img, zones["tagline"]["rect"], 1080, 1350)


def test_no_right_edge_clipping(arch: dict):
    img = np.asarray(_render(arch, CATEGORY_HOOK, ["instagram"])["instagram"])
    mint_cols = np.nonzero(_mint_mask(img).any(axis=0))[0]
    assert mint_cols.size > 0
    assert int(mint_cols.max()) < 1080 - 32


def test_compose_is_deterministic(arch: dict):
    fields = {"caption_hook": CATEGORY_HOOK}
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=["instagram"],
        fields=fields,
        photo_bytes=None,
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=["instagram"],
        fields=fields,
        photo_bytes=None,
    )["instagram"]
    assert a == b


def _ctx(monkeypatch, post_type: str = "", template_id: str = "") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": ["service"],
        "subject": "",
        "post_type": post_type,
        "template_id": template_id,
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return "calendar_candidate:stick:cal-brand-statement"


def test_brand_statement_post_type_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="brand_statement")
    assert arch_lib.select_archetype(BRAND, item)["id"] == ARCH_ID


def test_golden_instagram_matches_compose(arch: dict):
    png = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=["instagram"],
        fields={"caption_hook": CATEGORY_HOOK},
        photo_bytes=None,
    )["instagram"]
    if GOLDEN.is_file():
        assert GOLDEN.read_bytes() == png
