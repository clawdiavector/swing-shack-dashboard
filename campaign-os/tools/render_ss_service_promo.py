#!/usr/bin/env python3
"""Render ss-service-promo goldens + reference comparison sheet."""

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

PACK = ROOT / "data/brand-directory/swing-shack/templates/service-promo"
CASES = [
    ("OFF-THE-RACK IS FOR GROCERIES", "GET EQUIPMENT BUILT FOR YOU", "CLUB FITTING", "ss_blue"),
    (
        "YOU WOULDN'T RUN A MARATHON IN SOMEONE ELSE'S SHOES",
        "WHY PLAY WITH SOMEONE ELSE'S SPECS?",
        "CLUB FITTING",
        "ss_purple",
    ),
    (
        "YOUTUBE CAN'T SEE WHAT YOU'RE DOING WRONG",
        "STOP THE ENDLESS CYCLE OF SELF-DIAGNOSING.",
        "COACHING",
        "ss_orange",
    ),
    (
        "BUY FEWER GOLF BALLS",
        "INVEST IN A SWING THAT KEEPS THEM OUT OF THE WOODS.",
        "COACHING",
        "ss_green",
    ),
]


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-service-promo")
    if not arch:
        print("ss-service-promo archetype missing", file=sys.stderr)
        return 1
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    tw, th = 360, 450
    sheet = Image.new("RGB", (len(CASES) * tw, 2 * th), "white")
    for i, (headline, subhead, service, accent) in enumerate(CASES):
        fields = {
            "caption_hook": headline,
            "cta": subhead,
            "service_label": service,
            "accent": accent,
        }
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
        ref = Image.open(PACK / f"references/ref-0{i + 1}.jpg").convert("RGB")
        ours = Image.open(io.BytesIO(out["instagram"])).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (i * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens + compare sheet under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
