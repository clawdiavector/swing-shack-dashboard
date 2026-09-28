#!/usr/bin/env python3
"""Render stick-brand-statement golden PNGs for template QA."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402

PACK = ROOT / "data/brand-directory/stick/templates/brand-statement"
HOOK = "FITTINGS\nCOACHING\nEQUIPMENT\nAPPAREL"


def main() -> int:
    arch = archetype_by_id("stick", "stick-brand-statement")
    if not arch:
        print("stick-brand-statement archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram", "instagram_story", "facebook"],
        fields={"caption_hook": HOOK},
        photo_bytes=None,
    )
    (golden / "instagram.png").write_bytes(out["instagram"])
    (golden / "instagram_story.png").write_bytes(out["instagram_story"])
    (golden / "facebook.png").write_bytes(out["facebook"])
    print(f"wrote goldens under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
