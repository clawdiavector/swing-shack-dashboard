#!/usr/bin/env python3
"""Render stick-open-sign golden PNGs for template QA."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
ROOT = PACK.parents[4]
CAMPAIGN = ROOT / "campaign-os"
sys.path.insert(0, str(CAMPAIGN))

from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.archetype_compose import compose_post_for_channels  # noqa: E402


def main() -> int:
    arch = archetype_by_id("stick", "stick-open-sign")
    if not arch:
        print("stick-open-sign archetype missing", file=sys.stderr)
        return 1
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    case = cases[0]
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram"],
        fields=case,
        photo_bytes=None,
    )
    png = out.get("instagram")
    if not png:
        print("compose produced no instagram feed PNG", file=sys.stderr)
        return 1
    path = golden / "render-open-sign.png"
    path.write_bytes(png)
    print(f"wrote {path} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
