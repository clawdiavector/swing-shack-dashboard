#!/usr/bin/env python3
"""Render stick-service-square golden PNGs for template QA."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.archetype_compose import compose_post_for_channels  # noqa: E402

GOLDEN_DIR = ROOT / "data/brand-directory/stick/templates/service-square/golden"


def _render(variant: str, caption_hook: str, name: str) -> int:
    arch = archetype_by_id("stick", "stick-service-square")
    if not arch:
        print("stick-service-square archetype missing", file=sys.stderr)
        return 1
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram"],
        fields={"caption_hook": caption_hook, "variant": variant},
        photo_bytes=None,
    )
    png = out.get("instagram")
    if not png:
        print(f"compose produced no instagram canvas for {name}", file=sys.stderr)
        return 1
    path = GOLDEN_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    print(f"wrote {path} ({len(png)} bytes)")
    return 0


def main() -> int:
    rc = _render(
        "lab",
        "Our lab builds clubs to your numbers and your swing.",
        "render-lab.png",
    )
    if rc:
        return rc
    return _render("avoda", "COACHING stick", "render-avoda.png")


if __name__ == "__main__":
    raise SystemExit(main())
