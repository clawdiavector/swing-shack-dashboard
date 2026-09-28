#!/usr/bin/env python3
"""Render ss-event-poster goldens and compare sheet."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image  # noqa: E402

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402

PACK = ROOT / "data/brand-directory/swing-shack/templates/event-poster"


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-event-poster")
    if not arch:
        print("ss-event-poster missing", file=sys.stderr)
        return 1
    cases = json.loads((PACK / "cases.json").read_text())
    fields = cases[0]
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    out = compose_post_for_channels(
        brand_id="swing-shack",
        archetype=arch,
        channels=["instagram", "instagram_story"],
        fields=fields,
        photo_bytes=None,
    )
    (golden / "ss-event-poster-ig_post.jpg").write_bytes(out["instagram"])
    (golden / "ss-event-poster-ig_story.jpg").write_bytes(out["instagram_story"])

    tw, th = 360, 450
    refs = [
        (PACK / "references/ref-01.jpg", out["instagram"], "ig_post"),
        (PACK / "references/ref-02.jpg", out["instagram_story"], "ig_story"),
    ]
    sheet = Image.new("RGB", (tw * 2, th * 2), "white")
    for col, (ref_path, png_bytes, _label) in enumerate(refs):
        ref = Image.open(ref_path).convert("RGB")
        ours = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (col * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
