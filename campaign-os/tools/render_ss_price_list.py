#!/usr/bin/env python3
"""Render ss-price-list goldens + ICC-aware compare sheet."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image, ImageCms  # noqa: E402

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402

PACK = ROOT / "data/brand-directory/swing-shack/templates/price-list"
ARCH_ID = "ss-price-list"


def _ref_to_rgb(path: Path) -> Image.Image:
    im = Image.open(path)
    icc = im.info.get("icc_profile")
    if im.mode == "CMYK" and icc:
        return ImageCms.profileToProfile(
            im,
            ImageCms.ImageCmsProfile(io.BytesIO(icc)),
            ImageCms.createProfile("sRGB"),
            outputMode="RGB",
        )
    return im.convert("RGB")


def _channel_for_ref(path: Path) -> str:
    im = Image.open(path)
    return "instagram_story" if im.height > im.width * 1.4 else "instagram"


def main() -> int:
    arch = archetype_by_id("swing-shack", ARCH_ID)
    if not arch:
        print(f"{ARCH_ID} missing", file=sys.stderr)
        return 1
    cases_path = PACK / "cases.json"
    cases = json.loads(cases_path.read_text())
    refs = sorted(PACK.glob("references/ref-*.jpg"))
    if not refs:
        print("no references", file=sys.stderr)
        return 1

    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    tw, th = 360, 450
    sheet = Image.new("RGB", (len(refs) * tw, 2 * th), "white")

    fields0 = cases[0]
    out0 = compose_post_for_channels(
        brand_id="swing-shack",
        archetype=arch,
        channels=["instagram", "instagram_story"],
        fields=fields0,
        photo_bytes=None,
    )
    (golden / "render-instagram.png").write_bytes(out0["instagram"])
    (golden / "render-story.png").write_bytes(out0["instagram_story"])

    for i, ref_path in enumerate(refs):
        fields = cases[min(i, len(cases) - 1)]
        ch = _channel_for_ref(ref_path)
        out = compose_post_for_channels(
            brand_id="swing-shack",
            archetype=arch,
            channels=[ch],
            fields=fields,
            photo_bytes=None,
        )
        ref = _ref_to_rgb(ref_path)
        ours = Image.open(io.BytesIO(out[ch])).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (i * tw + 3, row * th + 3))

    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
