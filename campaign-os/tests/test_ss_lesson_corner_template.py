"""Swing Shack lesson-corner template: platforms, wrap, clipping, accent, selection."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from _lib import archetypes as arch_lib
from _lib.archetype_compose import _wrap_balanced, compose_post_for_channels
from _lib.archetypes import archetype_by_id
from _lib.brand_overlay import _load_brand_font

BRAND = "swing-shack"
ORANGE = np.array([0xF5, 0x8E, 0x20])
BLUE = np.array([0x3B, 0x7F, 0xEE])
GREEN = np.array([0x74, 0xCB, 0x46])
PANEL_LEFT_PX = 288
RIGHT_INK_MAX = 1030


@pytest.fixture(scope="module")
def lesson() -> dict:
    arch = archetype_by_id(BRAND, "ss-lesson-corner")
    assert arch
    return arch


def _render(
    arch: dict,
    headline: str,
    channels: list[str],
    cta: str = "Book online or message us for more info",
    accent: str = "",
) -> dict[str, Image.Image]:
    fields: dict[str, str] = {"caption_hook": headline, "cta": cta}
    if accent:
        fields["accent"] = accent
    out = compose_post_for_channels(
        brand_id=BRAND,
        archetype=arch,
        channels=channels,
        fields=fields,
        photo_bytes=None,
    )
    return {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in out.items()}


def _accent_rows(img: np.ndarray) -> list[np.ndarray]:
    """Sample rows where service-line accent ink is expected (target canvas)."""
    ys = [1019, 1058, 1096]
    rows = []
    for y in ys:
        if y < img.shape[0]:
            rows.append(img[y])
    return rows


def _dominant_accent(row: np.ndarray) -> str | None:
    best = None
    best_n = 0
    for name, rgb in (("orange", ORANGE), ("blue", BLUE), ("green", GREEN)):
        n = int((np.abs(row.astype(int) - rgb).sum(axis=1) < 80).sum())
        if n > best_n:
            best_n = n
            best = name
    return best if best_n > 20 else None


def test_platform_canvases(lesson: dict):
    out = _render(lesson, "Beginner lessons", ["instagram", "facebook"])
    assert {k: v.size for k, v in out.items()} == {
        "instagram": (1080, 1350),
        "facebook": (1080, 1350),
    }


@pytest.mark.parametrize(
    ("headline", "lines"),
    [
        ("Beginner lessons", ["BEGINNER", "LESSONS"]),
        ("Junior lessons", ["JUNIOR", "LESSONS"]),
        ("Ladies lessons", ["LADIES", "LESSONS"]),
    ],
)
def test_headline_balanced_wrap(headline: str, lines: list[str]):
    font = _load_brand_font(BRAND, "display", 105)
    assert _wrap_balanced(headline.upper(), font, None, 2, set(), 0.0) == lines


def test_cta_balanced_wrap():
    font = _load_brand_font(BRAND, "display", 58)
    cta = "BOOK ONLINE OR MESSAGE US FOR MORE INFO"
    assert _wrap_balanced(cta, font, None, 3, set(), 0.0) == [
        "BOOK ONLINE",
        "OR MESSAGE US",
        "FOR MORE INFO",
    ]


def test_text_not_clipped(lesson: dict):
    img = np.asarray(_render(lesson, "Beginner lessons", ["instagram"])["instagram"]).astype(int)
    white = np.abs(img - 255).sum(axis=2) < 45
    cols = np.nonzero(white.any(axis=0))[0]
    assert cols.max() <= RIGHT_INK_MAX
    assert cols.min() >= PANEL_LEFT_PX - 20


def test_accent_same_across_service_zones(lesson: dict):
    img = np.asarray(_render(lesson, "Beginner lessons", ["instagram"], accent="ss_orange_bright")["instagram"])
    accents = {_dominant_accent(row) for row in _accent_rows(img)}
    accents.discard(None)
    assert len(accents) == 1


def test_accent_deterministic_from_headline(lesson: dict):
    a = compose_post_for_channels(
        brand_id=BRAND,
        archetype=lesson,
        channels=["instagram"],
        fields={"caption_hook": "Junior lessons", "cta": "Book online or message us for more info"},
        photo_bytes=None,
    )["instagram"]
    b = compose_post_for_channels(
        brand_id=BRAND,
        archetype=lesson,
        channels=["instagram"],
        fields={"caption_hook": "Junior lessons", "cta": "Book online or message us for more info"},
        photo_bytes=None,
    )["instagram"]
    assert a == b


def test_accent_rotates_by_headline(lesson: dict):
    beginner = np.asarray(_render(lesson, "Beginner lessons", ["instagram"])["instagram"])
    junior = np.asarray(_render(lesson, "Junior lessons", ["instagram"])["instagram"])
    b_acc = _dominant_accent(_accent_rows(beginner)[0])
    j_acc = _dominant_accent(_accent_rows(junior)[0])
    assert b_acc and j_acc and b_acc != j_acc


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


def test_post_type_lesson_selects_lesson_corner(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-coaching", post_type="lesson")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-lesson-corner"


def test_coaching_without_post_type_keeps_service_frame(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-coaching")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-service-frame"


def test_pinned_template_id_wins(monkeypatch):
    item = _ctx(monkeypatch, pillar_id="ss-membership", template_id="ss-lesson-corner")
    assert arch_lib.select_archetype(BRAND, item)["id"] == "ss-lesson-corner"
