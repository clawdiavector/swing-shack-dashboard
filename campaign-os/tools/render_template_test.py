#!/usr/bin/env python3
"""Render stick-service-frame golden PNGs + compare sheet for template QA."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image  # noqa: E402

from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.archetype_compose import compose_post_for_channels  # noqa: E402

PACK = ROOT / "data/brand-directory/stick/templates/service-frame"
GOLDEN_FEED = PACK / "golden/render-instagram.png"
GOLDEN_STORY = PACK / "golden/render-instagram-story.png"
REFS = PACK / "references"


def _compose(arch: dict, *, channel: str, fields: dict) -> bytes:
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=[channel],
        fields=fields,
        photo_bytes=None,
    )
    key = "instagram" if channel == "instagram" else "instagram_story"
    png = out.get(key)
    if not png:
        raise RuntimeError(f"compose produced no {key} canvas")
    return png


def main() -> int:
    arch = archetype_by_id("stick", "stick-service-frame")
    if not arch:
        print("stick-service-frame archetype missing", file=sys.stderr)
        return 1
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    if len(cases) < 6:
        print("cases.json needs six entries (ref-01..ref-06)", file=sys.stderr)
        return 1

    feed_fields = cases[0]
    story_fields = cases[5]
    GOLDEN_FEED.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_FEED.write_bytes(_compose(arch, channel="instagram", fields=feed_fields))
    GOLDEN_STORY.write_bytes(_compose(arch, channel="instagram_story", fields=story_fields))
    print(f"wrote {GOLDEN_FEED} ({GOLDEN_FEED.stat().st_size} bytes)")
    print(f"wrote {GOLDEN_STORY} ({GOLDEN_STORY.stat().st_size} bytes)")

    feed_tw, feed_th = 540, 675
    story_tw, story_th = 540, 960
    feed_h = feed_th * 2
    story_h = story_th * 2
    sheet = Image.new("RGB", (4 * feed_tw, feed_h + story_h), "white")

    def _paste_pair(
        sheet_im: Image.Image,
        x0: int,
        y0: int,
        tw: int,
        th: int,
        ref_im: Image.Image,
        rend_im: Image.Image,
    ) -> None:
        for row, im in enumerate((ref_im, rend_im)):
            thumb = im.copy()
            thumb.thumbnail((tw - 6, th - 6), Image.LANCZOS)
            sheet_im.paste(thumb, (x0 + 3, y0 + row * th + 3))

    for i in range(4):
        ref = Image.open(REFS / f"ref-{i + 1:02d}.jpg").convert("RGB")
        rendered = Image.open(
            io.BytesIO(_compose(arch, channel="instagram", fields=cases[i]))
        ).convert("RGB")
        _paste_pair(sheet, i * feed_tw, 0, feed_tw, feed_th, ref, rendered)

    story_y = feed_h
    for j in range(2):
        idx = 4 + j
        ref = Image.open(REFS / f"ref-{idx + 1:02d}.jpg").convert("RGB")
        rendered = Image.open(
            io.BytesIO(_compose(arch, channel="instagram_story", fields=cases[idx]))
        ).convert("RGB")
        _paste_pair(sheet, j * story_tw, story_y, story_tw, story_th, ref, rendered)

    compare_path = PACK / "golden/compare-refs.jpg"
    sheet.save(compare_path, quality=85)
    print(f"wrote {compare_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
