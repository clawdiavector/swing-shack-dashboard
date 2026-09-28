#!/usr/bin/env python3
"""Render ss-discount-code golden PNGs for template QA."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.archetype_compose import compose_post_for_channels  # noqa: E402

GOLDEN_DIR = (
    ROOT
    / "data/brand-directory/swing-shack/templates/discount-code/golden"
)

FIELDS = {
    "caption_hook": "15% OFF",
    "offer_subject": "ALL FITTINGS",
    "offer_expiry": "UNTIL END OF MAY",
    "cta": "FITTING15",
}


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-discount-code")
    if not arch:
        print("ss-discount-code archetype missing", file=sys.stderr)
        return 1
    out = compose_post_for_channels(
        brand_id="swing-shack",
        archetype=arch,
        channels=["instagram", "instagram_story"],
        fields=FIELDS,
        photo_bytes=None,
    )
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for channel, png in out.items():
        name = channel.replace("_", "-")
        path = GOLDEN_DIR / f"render-{name}.png"
        path.write_bytes(png)
        print(f"wrote {path} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
