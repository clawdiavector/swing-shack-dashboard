#!/usr/bin/env python3
"""Render stick-service-end golden PNG for template QA."""

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
    arch = archetype_by_id("stick", "stick-service-end")
    if not arch:
        print("stick-service-end archetype missing", file=sys.stderr)
        return 1
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    fields = cases[0]
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram_story"],
        fields=fields,
        photo_bytes=None,
    )
    png = out.get("instagram_story")
    if not png:
        print("compose produced no instagram_story canvas", file=sys.stderr)
        return 1
    render_path = PACK / "golden/render-instagram-story.png"
    render_path.parent.mkdir(parents=True, exist_ok=True)
    render_path.write_bytes(png)
    print(f"wrote {render_path} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
