#!/usr/bin/env python3
"""Render agent/spec.json through compose_post_for_channels."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "campaign-os"))

from PIL import Image  # noqa: E402

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402

FRAME = ROOT / "data/brand-directory/stick/templates/service-frame"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", type=Path, default=FRAME / "agent/spec.json")
    ap.add_argument("--out", type=Path, default=FRAME / "agent/render-instagram.png")
    ap.add_argument("--headline", default="Consistency starts with data")
    ap.add_argument("--cta", default="Book your free swing assessment")
    args = ap.parse_args()
    arch = json.loads(args.spec.read_text(encoding="utf-8"))
    out = compose_post_for_channels(
        brand_id="stick",
        archetype=arch,
        channels=["instagram"],
        fields={"caption_hook": args.headline, "cta": args.cta},
        photo_bytes=None,
    )
    png = out.get("instagram")
    if not png:
        print("compose produced no instagram canvas", file=sys.stderr)
        return 1
    size = Image.open(io.BytesIO(png)).size
    if size != (1080, 1350):
        print(f"unexpected canvas {size}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(png)
    print(f"wrote {args.out} {size[0]}x{size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
