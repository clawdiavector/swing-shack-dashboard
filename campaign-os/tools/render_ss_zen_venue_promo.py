#!/usr/bin/env python3
"""Render ss-zen-venue-promo goldens + reference comparison sheet."""

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

PACK = ROOT / "data/brand-directory/swing-shack/templates/zen-venue-promo"
FIELDS = {
    "caption_hook": "Zen Swing Stage?",
    "qualifier": "Slope changes everything",
    "accent": "ss_green",
}


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-zen-venue-promo")
    if not arch:
        print("ss-zen-venue-promo archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    out = compose_post_for_channels(
        brand_id="swing-shack",
        archetype=arch,
        channels=["instagram", "instagram_story"],
        fields=FIELDS,
        photo_bytes=None,
    )
    (golden / "render-instagram.png").write_bytes(out["instagram"])
    (golden / "render-story.png").write_bytes(out["instagram_story"])
    tw, th = 360, 450
    ref = Image.open(PACK / "references/ref-01.jpg").convert("RGB")
    ours = Image.open(io.BytesIO(out["instagram"])).convert("RGB")
    sheet = Image.new("RGB", (tw, 2 * th), "white")
    for row, im in enumerate((ref, ours)):
        im.thumbnail((tw - 6, th - 6))
        sheet.paste(im, (3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens + compare sheet under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
