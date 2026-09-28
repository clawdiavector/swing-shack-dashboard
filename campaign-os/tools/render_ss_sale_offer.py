#!/usr/bin/env python3
"""Render ss-sale-offer goldens + reference comparison sheet for template QA."""

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

PACK = ROOT / "data/brand-directory/swing-shack/templates/sale-offer"
CASES = [
    ("10% OFF", "17 - 30 NOVEMBER", "DM US FOR MORE INFO", 2),
    ("20% OFF", "SELECTED ITEMS", "DM US FOR MORE INFO", 1),
]


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-sale-offer")
    if not arch:
        print("ss-sale-offer archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    tw, th = 360, 640
    sheet = Image.new("RGB", (len(CASES) * tw, 2 * th), "white")
    for i, (headline, subline, cta, ref_idx) in enumerate(CASES):
        fields = {
            "caption_hook": headline,
            "caption_body": subline,
            "cta": cta,
        }
        out = compose_post_for_channels(
            brand_id="swing-shack",
            archetype=arch,
            channels=["instagram_story", "instagram"],
            fields=fields,
            photo_bytes=None,
        )
        if i == 0:
            (golden / "render-story.png").write_bytes(out["instagram_story"])
            (golden / "render-instagram.png").write_bytes(out["instagram"])
        ref = Image.open(PACK / f"references/ref-0{ref_idx}.jpg").convert("RGB")
        ours = Image.open(io.BytesIO(out["instagram_story"])).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (i * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens + compare sheet under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
