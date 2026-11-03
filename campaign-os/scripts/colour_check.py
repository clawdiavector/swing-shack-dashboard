#!/usr/bin/env python3
"""Check an AI product image's colour against the maker's official listing.

The target is the maker's own product page for the exact colourway (Shopify stores:
Psycho Bunny, Vessel, Herschel; see data/brand-directory/_system/image-sources.json).

    # 1. the official colour, measured from the listing's front image
    python3 campaign-os/scripts/colour_check.py target \\
        https://psychobunny.com/products/mens-classic-polo-b6k001arpc-001-black

    # 2. an AI image against it (box on evenly lit fabric: x0,y0,x1,y1 in pixels)
    python3 campaign-os/scripts/colour_check.py check post.jpg --box 420,520,560,700 \\
        --page https://psychobunny.com/products/mens-classic-polo-b6k001arpc-001-black

    # or against a hex you already have
    python3 campaign-os/scripts/colour_check.py check post.jpg --box 420,520,560,700 --hex "#151517"

Prints JSON. Verdict: PASS (difference up to 5), CHECK (up to 10, look by eye), FAIL (bounce).
No listing for the product? The check is "estimated": say so in the QA log.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from _lib import colour_truth as ct  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("target", help="measure the official colour from a product page")
    t.add_argument("page")
    c = sub.add_parser("check", help="compare an image's fabric with the official colour")
    c.add_argument("image")
    c.add_argument("--box", required=True, help="x0,y0,x1,y1 on evenly lit fabric")
    src = c.add_mutually_exclusive_group(required=True)
    src.add_argument("--page", help="official product page for the exact colourway")
    src.add_argument("--hex", help="official colour already measured")
    a = ap.parse_args(argv)

    if a.cmd == "target":
        print(json.dumps(ct.target_from_page(a.page), indent=2))
        return 0
    box = tuple(int(v) for v in a.box.split(","))
    measured = ct.measure_box(Image.open(a.image), box)  # type: ignore[arg-type]
    target = ct.target_from_page(a.page) if a.page else {"hex": a.hex}
    out = {**ct.compare(target["hex"], measured["hex"]), "image": a.image, "box": list(box)}
    if a.page:
        out.update(page_url=a.page, colour_name=target["colour_name"], official_image=target["image_url"])
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
