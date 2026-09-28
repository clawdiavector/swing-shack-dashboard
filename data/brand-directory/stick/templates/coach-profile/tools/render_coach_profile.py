#!/usr/bin/env python3
"""Render stick-coach-profile goldens + reference comparison sheet for template QA."""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
CAMPAIGN = ROOT / "campaign-os"
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image  # noqa: E402

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402

PACK = Path(__file__).resolve().parents[1]
PHOTO = PACK / "photos/stand-in.jpg"

# Compare-only copy transcribed from ref ink (not compose defaults).
FIELDS = {
    "caption_hook": "DAVE LAMPRECHT",
    "bio_1": "AVAILABLE FOR",
    "bio_2": "COACHING, FITTINGS",
    "bio_3": "AND ASSESSMENTS",
}


def main() -> int:
    arch = archetype_by_id("stick", "stick-coach-profile")
    if not arch:
        print("stick-coach-profile archetype missing", file=sys.stderr)
        return 1
    photo_bytes = PHOTO.read_bytes()
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram", "instagram_story"],
        fields=FIELDS,
        photo_bytes=photo_bytes,
    )
    (golden / "render-instagram.png").write_bytes(out["instagram"])
    (golden / "render-story.png").write_bytes(out["instagram_story"])
    tw, th = 360, 450
    sheet = Image.new("RGB", (2 * tw, 2 * th), "white")
    for col, ref_name in enumerate(("ref-01.jpg", "ref-02.jpg")):
        channel = "instagram" if col == 0 else "instagram_story"
        ref = Image.open(PACK / "references" / ref_name).convert("RGB")
        ours = Image.open(io.BytesIO(out[channel])).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (col * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens + compare sheet under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
