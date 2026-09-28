#!/usr/bin/env python3
"""Render stick-brand-statement golden PNGs + compare sheet for template QA."""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image  # noqa: E402

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402

PACK = ROOT / "data/brand-directory/stick/templates/brand-statement"
HOOK_CATEGORY = "FITTINGS\nCOACHING\nEQUIPMENT\nAPPAREL"
HOOK_SENTENCE = (
    "WE FIT THE EQUIPMENT TO THE PLAYER.\nNEVER THE OTHER WAY AROUND."
)
COMPARE_CASES = [
    (HOOK_CATEGORY, "ref-01.jpg"),
    (HOOK_SENTENCE, "ref-02.jpg"),
]


def main() -> int:
    arch = archetype_by_id("stick", "stick-brand-statement")
    if not arch:
        print("stick-brand-statement archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram", "instagram_story", "facebook"],
        fields={"caption_hook": HOOK_CATEGORY},
        photo_bytes=None,
    )
    (golden / "instagram.png").write_bytes(out["instagram"])
    (golden / "instagram_story.png").write_bytes(out["instagram_story"])
    (golden / "facebook.png").write_bytes(out["facebook"])

    tw, th = 540, 675
    sheet = Image.new("RGB", (len(COMPARE_CASES) * tw, 2 * th), "white")
    for i, (hook, ref_name) in enumerate(COMPARE_CASES):
        rendered = compose_post_for_channels(
            brand_id="stick",
            archetype=arch,
            channels=["instagram"],
            fields={"caption_hook": hook},
            photo_bytes=None,
        )["instagram"]
        ref = Image.open(PACK / "references" / ref_name).convert("RGB")
        ours = Image.open(io.BytesIO(rendered)).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (i * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)

    print(f"wrote goldens + compare-refs.jpg under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
