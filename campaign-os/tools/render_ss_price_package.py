#!/usr/bin/env python3
"""Render ss-price-package / ss-price-list goldens + compare sheets."""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image  # noqa: E402

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402

PACKAGE_CASES = [
    {
        "caption_hook": "I Am Golf",
        "qualifier": "Weekly lesson & unlimited practice",
        "price": "R 2 850",
        "price_period": "Per month",
        "cta": "Book online or DM us",
        "accent": "ss_green",
    },
    {
        "caption_hook": "I Dabble",
        "qualifier": "Unlimited practice",
        "price": "R 1 800",
        "price_period": "Per month",
        "cta": "Book online or DM us",
        "accent": "ss_purple",
    },
    {
        "caption_hook": "Birdie Hunter",
        "qualifier": "1 lesson & unlimited practice",
        "price": "R 2 300",
        "price_period": "Per month",
        "cta": "Book online or DM us",
        "accent": "ss_orange",
    },
]

def _sheet(*, pack: Path, arch_id: str, cases: list[dict], ref_count: int) -> None:
    arch = archetype_by_id("swing-shack", arch_id)
    if not arch:
        print(f"{arch_id} missing", file=sys.stderr)
        raise SystemExit(1)
    golden = pack / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    tw, th = 360, 450
    sheet = Image.new("RGB", (ref_count * tw, 2 * th), "white")
    for i in range(ref_count):
        fields = cases[min(i, len(cases) - 1)]
        out = compose_post_for_channels(
            brand_id="swing-shack",
            archetype=arch,
            channels=["instagram", "instagram_story"],
            fields=fields,
            photo_bytes=None,
        )
        if i == 0:
            (golden / "render-instagram.png").write_bytes(out["instagram"])
            (golden / "render-story.png").write_bytes(out["instagram_story"])
        ref = Image.open(pack / f"references/ref-{i + 1:02d}.jpg").convert("RGB")
        ours = Image.open(io.BytesIO(out["instagram"])).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (i * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote {golden}")


def main() -> int:
    _sheet(
        pack=ROOT / "data/brand-directory/swing-shack/templates/price-package",
        arch_id="ss-price-package",
        cases=PACKAGE_CASES,
        ref_count=3,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
