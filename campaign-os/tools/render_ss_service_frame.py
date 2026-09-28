#!/usr/bin/env python3
"""Render ss-service-frame goldens (no refs — synthetic compare sheet)."""

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

PACK = ROOT / "data/brand-directory/swing-shack/templates/service-frame"
PHOTO = PACK / "photos/standin-sim-bay.jpg"


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-service-frame")
    if not arch:
        print("ss-service-frame archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    fields = {"caption_hook": "Book your club fitting today"}
    no_photo = compose_post_for_channels(
        brand_id="swing-shack",
        archetype=arch,
        channels=["instagram"],
        fields=fields,
        photo_bytes=None,
    )["instagram"]
    photo_bytes = PHOTO.read_bytes() if PHOTO.is_file() else None
    with_photo = compose_post_for_channels(
        brand_id="swing-shack",
        archetype=arch,
        channels=["instagram"],
        fields=fields,
        photo_bytes=photo_bytes,
    )["instagram"]
    (golden / "render-instagram-no-photo.png").write_bytes(no_photo)
    (golden / "render-instagram-with-photo.png").write_bytes(with_photo)
    tw, th = 540, 675
    sheet = Image.new("RGB", (tw * 2 + 12, th + 8), "white")
    for col, blob in enumerate((no_photo, with_photo)):
        im = Image.open(io.BytesIO(blob)).convert("RGB")
        im.thumbnail((tw, th))
        sheet.paste(im, (col * (tw + 4) + 4, 4))
    sheet.save(golden / "compare-synthetic.jpg", quality=85)
    print(f"wrote goldens under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
