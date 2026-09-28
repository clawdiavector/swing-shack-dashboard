#!/usr/bin/env python3
"""Render ss-fitting-headline goldens + a reference comparison sheet for template QA."""

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

PACK = ROOT / "data/brand-directory/swing-shack/templates/fitting-headline"
REF_CASES = [
    ("HIT MORE GREENS WITH AN", "IRON FITTING", "ss_fit_blue"),
    ("DROP MORE PUTTS WITH A", "PUTTER FITTING", "ss_fit_orange"),
]


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-fitting-headline")
    if not arch:
        print("ss-fitting-headline archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    tw, th = 360, 450
    sheet = Image.new("RGB", (len(REF_CASES) * tw, 2 * th), "white")
    for i, (kicker, lockup, accent) in enumerate(REF_CASES):
        out = compose_post_for_channels(
            brand_id="swing-shack",
            archetype=arch,
            channels=["instagram", "instagram_story"],
            fields={"caption_hook": kicker, "service_lockup": lockup, "accent": accent},
            photo_bytes=None,
        )
        if i == 0:
            (golden / "render-instagram.png").write_bytes(out["instagram"])
            (golden / "render-story.png").write_bytes(out["instagram_story"])
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
