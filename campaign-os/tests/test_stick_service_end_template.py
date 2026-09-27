"""Stick service-end template: story canvas, mint panel, static END, selection."""

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
PACK = ROOT / "data/brand-directory/stick/templates/service-end"
BRAND = "stick"
MINT = np.array([0x24, 0xFF, 0xAF])
NAVY = np.array([0x07, 0x3C, 0x52])


@pytest.fixture(scope="module")
def end_arch() -> dict:
    arch = archetype_by_id(BRAND, "stick-service-end")
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


def test_platform_canvases(end_arch: dict):
    out = _render(end_arch, ["instagram_story", "facebook"])
    assert out["instagram_story"].size == (1080, 1920)
    assert out["facebook"].size == (1080, 1920)


def test_mint_panel_pixels(end_arch: dict):
    img = np.asarray(_render(end_arch, ["instagram_story"])["instagram_story"])
    h, w = img.shape[:2]
    x0, y0 = int(0.0 * w), int(0.518 * h)
    x1, y1 = int(0.914 * w), int(0.834 * h)
    band = img[y0:y1, x0:x1]
    mint_mask = np.abs(band.astype(int) - MINT).sum(axis=2) < 80
    assert mint_mask.mean() > 0.45, "mint panel fill missing in measured rect"


def test_navy_text_in_service_lockup_and_end(end_arch: dict):
    img = np.asarray(_render(end_arch, ["instagram_story"])["instagram_story"])
    h, w = img.shape[:2]
    svc = img[int(0.22 * h) : int(0.32 * h), int(0.08 * w) : int(0.92 * w)]
    lock = img[int(0.34 * h) : int(0.46 * h), int(0.1 * w) : int(0.92 * w)]
    end = img[int(0.58 * h) : int(0.78 * h), int(0.12 * w) : int(0.82 * w)]
    navy_svc = np.abs(svc.astype(int) - NAVY).sum(axis=2) < 45
    navy_lock = np.abs(lock.astype(int) - NAVY).sum(axis=2) < 45
    navy_end = np.abs(end.astype(int) - NAVY).sum(axis=2) < 45
    assert navy_svc.sum() > 200, "service word navy glyphs expected"
    assert navy_lock.sum() > 100, "lockup navy glyphs expected"
    assert navy_end.sum() > 400, "static END navy glyphs expected"


def test_static_end_when_caption_hook_empty(end_arch: dict):
    img = np.asarray(
        _render(end_arch, ["instagram_story"], caption_hook="", cta="@ stick")["instagram_story"]
    )
    h, w = img.shape[:2]
    end = img[int(0.58 * h) : int(0.78 * h), int(0.12 * w) : int(0.82 * w)]
    navy_end = np.abs(end.astype(int) - NAVY).sum(axis=2) < 45
    assert navy_end.sum() > 400, "END must render without caption_hook"


def test_deterministic_render(end_arch: dict):
    f = _fields()
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=end_arch,
        channels=["instagram_story"],
        fields=f,
        photo_bytes=None,
    )["instagram_story"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=end_arch,
        channels=["instagram_story"],
        fields=f,
        photo_bytes=None,
    )["instagram_story"]
    assert a == b


def test_visual_copy_service_end_lockup():
    arch = {"id": "stick-service-end", "applies_to": {"needs_photo": True}}
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
    return f"calendar_candidate:{BRAND}:cal-end-1"


def test_post_type_service_end_selects_archetype(monkeypatch):
    item = _ctx(monkeypatch, post_type="service_end", pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-end"


def test_fitting_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="stick-fitting")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "stick-service-frame"


def test_pack_cases_match_archetype(end_arch: dict):
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 2
    for case in cases[:2]:
        out = compose_post_for_channels(
            brand_id=BRAND,
            archetype=end_arch,
            channels=["instagram_story"],
            fields=case,
            photo_bytes=None,
        )
        assert out.get("instagram_story")
