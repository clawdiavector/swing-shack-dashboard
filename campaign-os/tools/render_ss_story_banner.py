#!/usr/bin/env python3
"""Render ss-story-banner goldens and a four-up compare sheet (no reference JPGs)."""

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

PACK = ROOT / "data/brand-directory/swing-shack/templates/story-banner"
PHOTO = PACK / "photos/standin-sim-bay.jpg"

CHANNELS = [
    ("instagram", "render-instagram.png"),
    ("instagram_story", "render-story.png"),
    ("facebook", "render-facebook.png"),
    ("gbp", "render-gbp.png"),
]


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-story-banner")
    if not arch:
        print("ss-story-banner archetype missing", file=sys.stderr)
        return 1
    if not PHOTO.is_file():
        print(f"missing stand-in photo: {PHOTO}", file=sys.stderr)
        return 1
    photo_bytes = PHOTO.read_bytes()
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    fields = {"caption_hook": "Book your fitting this week"}
    blobs: list[tuple[str, bytes]] = []
    for channel, fname in CHANNELS:
        out = compose_post_for_channels(
            brand_id="swing-shack",
            archetype=arch,
            channels=[channel],
            fields=fields,
            photo_bytes=photo_bytes,
        )
        blob = out[channel]
        (golden / fname).write_bytes(blob)
        blobs.append((channel, blob))
        print(f"wrote {golden / fname}")

    thumbs: list[Image.Image] = []
    for _ch, blob in blobs:
        im = Image.open(io.BytesIO(blob)).convert("RGB")
        im.thumbnail((360, 640))
        thumbs.append(im)
    pad = 8
    cols = 2
    rows = 2
    cell_w = max(t.width for t in thumbs) + pad * 2
    cell_h = max(t.height for t in thumbs) + pad * 2
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    for i, thumb in enumerate(thumbs):
        r, c = divmod(i, cols)
        ox = c * cell_w + pad + (cell_w - pad * 2 - thumb.width) // 2
        oy = r * cell_h + pad + (cell_h - pad * 2 - thumb.height) // 2
        sheet.paste(thumb, (ox, oy))
    out_path = golden / "compare-sheet.jpg"
    sheet.save(out_path, quality=88)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
