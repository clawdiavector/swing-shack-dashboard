#!/usr/bin/env python3
"""Render stick-service-frame golden PNG for template QA."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.archetype_compose import compose_post_for_channels  # noqa: E402

GOLDEN = (
    ROOT
    / "data/brand-directory/stick/templates/service-frame/golden/render-instagram.png"
)


def main() -> int:
    arch = archetype_by_id("stick", "stick-service-frame")
    if not arch:
        print("stick-service-frame archetype missing", file=sys.stderr)
        return 1
    fields = {
        "caption_hook": "Consistency starts with data",
        "cta": "Book your free swing assessment",
    }
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram"],
        fields=fields,
        photo_bytes=None,
    )
    png = out.get("instagram")
    if not png:
        print("compose produced no instagram canvas", file=sys.stderr)
        return 1
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_bytes(png)
    print(f"wrote {GOLDEN} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
