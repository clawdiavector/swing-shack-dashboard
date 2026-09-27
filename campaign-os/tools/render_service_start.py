#!/usr/bin/env python3
"""Render stick-service-start compare golden for template QA."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.archetype_compose import compose_post_for_channels  # noqa: E402

PACK = ROOT / "data/brand-directory/stick/templates/service-start"
GOLDEN = PACK / "golden/compare-refs.jpg"


def main() -> int:
    arch = archetype_by_id("stick", "stick-service-start")
    if not arch:
        print("stick-service-start archetype missing", file=sys.stderr)
        return 1
    cases_path = PACK / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    fields = cases[0]
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
    # store PNG render; compare sheet job writes JPG separately
    render_path = PACK / "golden/render-instagram.png"
    render_path.write_bytes(png)
    print(f"wrote {render_path} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
