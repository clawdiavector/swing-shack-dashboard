"""Stick service-start template: canvases, mint bar, selection, determinism."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import compose_post_for_channels
from _lib.archetypes import archetype_by_id
from _lib.compose_visual_copy import visual_copy_for_archetype

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "data/brand-directory/stick/templates/service-start"
BRAND = "stick"
MINT = np.array([0x24, 0xFF, 0xAF])
NAVY = np.array([0x07, 0x3C, 0x52])


@pytest.fixture(scope="module")
def start_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-service-start")
    assert arch
    return arch


def _fields(**extra: str) -> dict[str, str]:
    base = {"caption_hook": "COACHING", "cta": "@ stick", "photo_seed": "coaching"}
    base.update(extra)
    return base


def _render(arch: dict, channels: list[str], **fields: str) -> dict[str, Image.Image]:
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=_fields(**fields),
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def test_platform_canvases(start_arch: dict):
    out = _render(start_arch, ["instagram", "instagram_story", "facebook"])
    assert out["instagram"].size == (1080, 1350)
    assert out["instagram_story"].size == (1080, 1920)
    assert out["facebook"].size == (1080, 1350)


def test_mint_bar_pixels(start_arch: dict):
    img = np.asarray(_render(start_arch, ["instagram"])["instagram"])
    h, w = img.shape[:2]
    x0, y0 = int(0.051 * w), int(0.659 * h)
    x1, y1 = int(0.652 * w), int(0.680 * h)
    band = img[y0:y1, x0:x1]
    mint_mask = np.abs(band.astype(int) - MINT).sum(axis=2) < 80
    assert mint_mask.mean() > 0.5, "mint bar fill missing in measured rect"


def test_navy_text_in_service_and_lockup_zones(start_arch: dict):
    img = np.asarray(_render(start_arch, ["instagram"])["instagram"])
    h, w = img.shape[:2]
    svc = img[int(0.36 * h) : int(0.48 * h), int(0.1 * w) : int(0.92 * w)]
    lock = img[int(0.5 * h) : int(0.64 * h), int(0.12 * w) : int(0.88 * w)]
    navy_svc = np.abs(svc.astype(int) - NAVY).sum(axis=2) < 45
    navy_lock = np.abs(lock.astype(int) - NAVY).sum(axis=2) < 45
    assert navy_svc.sum() > 200, "service word navy glyphs expected"
    assert navy_lock.sum() > 100, "lockup navy glyphs expected"


def test_service_word_not_clipped_right(start_arch: dict):
    img = np.asarray(_render(start_arch, ["instagram"], caption_hook="EQUIPMENT")["instagram"])
    h, w = img.shape[:2]
    svc = img[int(0.36 * h) : int(0.48 * h), int(0.1 * w) : int(0.92 * w)]
    navy = np.abs(svc.astype(int) - NAVY).sum(axis=2) < 45
    cols = np.nonzero(navy.any(axis=0))[0]
    assert cols.size > 0
    assert cols.max() < svc.shape[1] - 8


def test_deterministic_render(start_arch: dict):
    f = _fields()
    a = compose_post_for_channels(
        brand_id=BRAND, archetype=start_arch, channels=["instagram"], fields=f, photo_bytes=None
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND, archetype=start_arch, channels=["instagram"], fields=f, photo_bytes=None
    )["instagram"]
    assert a == b


def test_visual_copy_service_start_lockup():
    arch = {"id": "stick-service-start", "applies_to": {"needs_photo": True}}
    fields = visual_copy_for_archetype(
        brand_id=BRAND,
        moment_id="proposal:stick:x",
        caption="TrackMan coaching session details",
        archetype=arch,
    )
    assert fields["caption_hook"] == "COACHING"
    assert fields["cta"] == "@ stick"


def _ctx(monkeypatch, *, post_type: str = "", pillar_id: str = "stick-coaching") -> str:
    ctx = {
        "has_product_item": False,
        "pillar_in": [pillar_id],
        "subject": "",
        "post_type": post_type,
        "template_id": "",
    }
    monkeypatch.setattr(arch_lib, "_moment_context", lambda _brand, _item: dict(ctx))
    return f"calendar_candidate:{BRAND}:cal-start-1"


def test_post_type_service_start_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="service_start", pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-start"


def test_fitting_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-frame"


def test_apparel_and_equipment_render_navy_glyphs(start_arch: dict):
    for word in ("APPAREL", "EQUIPMENT"):
        img = np.asarray(_render(start_arch, ["instagram"], caption_hook=word)["instagram"])
        h, w = img.shape[:2]
        svc = img[int(0.36 * h) : int(0.48 * h), int(0.1 * w) : int(0.92 * w)]
        navy = np.abs(svc.astype(int) - NAVY).sum(axis=2) < 45
        assert navy.sum() > 200, f"{word} navy glyphs expected in service zone"


def test_pack_cases_match_archetype(start_arch: dict):
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 4
    for case in cases:
        out = compose_post_for_channels(
            brand_id=BRAND,
            archetype=start_arch,
            channels=["instagram"],
            fields=case,
            photo_bytes=None,
        )
        assert out.get("instagram")
