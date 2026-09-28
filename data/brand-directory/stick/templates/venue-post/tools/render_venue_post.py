#!/usr/bin/env python3
"""Render stick-venue-post goldens and reference comparison sheet."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
CAMPAIGN = ROOT / "campaign-os"
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image  # noqa: E402

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402

PACK = Path(__file__).resolve().parents[1]
CASES = json.loads((PACK / "cases.json").read_text())


def _photo_for_index(i: int) -> bytes:
    path = PACK / "photos" / f"stand-in-0{i + 1}.jpg"
    return path.read_bytes()


def main() -> int:
    arch = archetype_by_id("stick", "stick-venue-post")
    if not arch:
        print("stick-venue-post archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    fields = dict(CASES[0])
    fields.pop("ref", None)
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram", "instagram_story", "facebook"],
        fields=fields,
        photo_bytes=_photo_for_index(0),
    )
    (golden / "ref-01-instagram.png").write_bytes(out["instagram"])
    (golden / "ref-01-story.png").write_bytes(out["instagram_story"])
    (golden / "ref-01-facebook.png").write_bytes(out["facebook"])
    tw, th = 360, 450
    sheet = Image.new("RGB", (len(CASES) * tw, 2 * th + 20), "white")
    for col, case in enumerate(CASES):
        fld = dict(case)
        ref_name = fld.pop("ref", f"ref-0{col + 1}.jpg")
        rendered = compose_post_for_channels(
            brand_id="stick",
            archetype=arch,
            channels=["instagram"],
            fields=fld,
            photo_bytes=_photo_for_index(col),
        )
        ref = Image.open(PACK / "references" / ref_name).convert("RGB")
        ours = Image.open(io.BytesIO(rendered["instagram"])).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (col * tw + 3, row * th + (17 if row else 3)))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
