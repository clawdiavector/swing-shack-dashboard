"""Retail campaign captions: caption_lint import path and hook_max compliance."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

from _lib import retail_campaign as rc  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.stock_pulse import _ball_idea  # noqa: E402

REPO = CAMPAIGN_OS.parent
SWING_SHACK_ARCH = REPO / "data" / "brand-directory" / "swing-shack" / "visual-spec" / "archetypes.json"


def test_caption_hard_fails_uses_scripts_caption_lint():
    fails = rc.caption_hard_fails(
        "swing-shack",
        "Fresh stock on the shelf.\nDM us to order or book a ball fitting.",
    )
    assert fails == []


@pytest.mark.parametrize("product_name", ["Titleist Pro V1", "Callaway Chrome Soft"])
def test_build_caption_fits_swing_shack_hook_max_from_stock_idea(product_name: str):
    idea = _ball_idea(product_name)
    caption = rc.build_caption("swing-shack", product_name, idea, "heavy")
    hook = caption.split("\n", 1)[0]
    assert len(hook) <= 100
    assert rc.caption_hard_fails("swing-shack", caption) == []


def test_swing_shack_product_post_archetypes_in_extension():
    doc = json.loads(SWING_SHACK_ARCH.read_text(encoding="utf-8"))
    extras = doc.get("product_post_archetypes") or []
    assert len(extras) == 3
    assert {a["id"] for a in extras} == set(rc.LAYOUT_TO_ARCHETYPE.values())
    for layout, arch_id in rc.LAYOUT_TO_ARCHETYPE.items():
        arch = archetype_by_id("swing-shack", arch_id)
        assert arch is not None, arch_id
        assert arch.get("renderer") == "product_post"
        assert arch.get("product_layout") == layout
