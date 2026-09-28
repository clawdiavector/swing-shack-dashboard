#!/usr/bin/env python3
"""Render ss-lesson-corner goldens + a reference comparison sheet for template QA."""

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

PACK = ROOT / "data/brand-directory/swing-shack/templates/lesson-corner"
CASES = [
    ("Beginner lessons", "Book online or message us for more info", "ss_orange_bright"),
    ("Junior lessons", "Book online or message us for more info", "ss_blue_bright"),
    ("Ladies lessons", "Book online or message us for more info", "ss_green"),
]


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-lesson-corner")
    if not arch:
        print("ss-lesson-corner archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    tw, th = 360, 450
    sheet = Image.new("RGB", (len(CASES) * tw, 2 * th), "white")
    for i, (headline, cta, accent) in enumerate(CASES):
        fields = {"caption_hook": headline, "cta": cta, "accent": accent}
        out = compose_post_for_channels(
            brand_id="swing-shack",
            archetype=arch,
            channels=["instagram"],
            fields=fields,
            photo_bytes=None,
        )
        if i == 0:
            (golden / "render-instagram.png").write_bytes(out["instagram"])
        ref = Image.open(PACK / f"references/ref-0{i + 1}.jpg").convert("RGB")
        ours = Image.open(io.BytesIO(out["instagram"])).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (i * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens + compare sheet under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
