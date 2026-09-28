#!/usr/bin/env python3
"""Render stick-service-end golden PNGs for template QA."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
ROOT = PACK.parents[4]
CAMPAIGN = ROOT / "campaign-os"
sys.path.insert(0, str(CAMPAIGN))

from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.archetype_compose import compose_post_for_channels  # noqa: E402


def _slug(hook: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", hook.lower()).strip("-") or "case"


def main() -> int:
    arch = archetype_by_id("stick", "stick-service-end")
    if not arch:
        print("stick-service-end archetype missing", file=sys.stderr)
        return 1
    cases = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    for case in cases:
        hook = str(case.get("caption_hook") or "case")
        out = compose_post_for_channels(
            brand_id="stick",
            archetype=arch,
            channels=["instagram_story"],
            fields=case,
            photo_bytes=None,
        )
        png = out.get("instagram_story")
        if not png:
            print(f"compose produced no instagram_story for {hook}", file=sys.stderr)
            return 1
        if case is cases[0]:
            (golden / "render-instagram-story.png").write_bytes(png)
        path = golden / f"render-{_slug(hook)}.png"
        path.write_bytes(png)
        print(f"wrote {path} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
