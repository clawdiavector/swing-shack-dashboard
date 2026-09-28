#!/usr/bin/env python3
"""Render stick-hiring goldens + reference comparison sheet for template QA."""

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


def main() -> int:
    arch = archetype_by_id("stick", "stick-hiring")
    if not arch:
        print("stick-hiring archetype missing", file=sys.stderr)
        return 1
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    if not cases:
        print("cases.json empty", file=sys.stderr)
        return 1
    fields = cases[0]
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram"],
        fields=fields,
        photo_bytes=None,
    )
    (golden / "render-instagram.png").write_bytes(out["instagram"])
    tw, th = 360, 450
    sheet = Image.new("RGB", (tw, 2 * th), "white")
    ref = Image.open(PACK / "references/ref-01.jpg").convert("RGB")
    ours = Image.open(io.BytesIO(out["instagram"])).convert("RGB")
    for row, im in enumerate((ref, ours)):
        im.thumbnail((tw - 6, th - 6))
        sheet.paste(im, (3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens + compare sheet under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
