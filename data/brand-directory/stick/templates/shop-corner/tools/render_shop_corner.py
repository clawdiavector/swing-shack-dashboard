#!/usr/bin/env python3
"""Render stick-shop-corner goldens + reference comparison sheet for template QA."""

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
REFS = PACK / "references"


def main() -> int:
    arch = archetype_by_id("stick", "stick-shop-corner")
    if not arch:
        print("stick-shop-corner archetype missing", file=sys.stderr)
        return 1
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    tw, th = 360, 450
    sheet = Image.new("RGB", (len(cases) * tw, 2 * th), "white")
    for i, fields in enumerate(cases):
        ref_path = REFS / f"ref-0{i + 1}.jpg"
        photo_bytes = ref_path.read_bytes()
        out = compose_post_for_channels(
            brand_id="stick",
            archetype=arch,
            channels=["instagram"],
            fields=fields,
            photo_bytes=photo_bytes,
        )
        png = out.get("instagram")
        if not png:
            print(f"compose produced no instagram canvas for case {i}", file=sys.stderr)
            return 1
        if i == 0:
            (golden / "render-instagram.png").write_bytes(png)
        ref = Image.open(ref_path).convert("RGB")
        ours = Image.open(io.BytesIO(png)).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (i * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens + compare sheet under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
