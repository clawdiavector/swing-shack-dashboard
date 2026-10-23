#!/usr/bin/env python3
"""Render Swing Shack product posts from the three approved layouts.

    python campaign-os/scripts/render_product_post.py post.json out.jpg
    python campaign-os/scripts/render_product_post.py --goldens          # rebuild pack goldens
    python campaign-os/scripts/render_product_post.py --next type-hero one-hero   # which layout is due

post.json = {"layout","brand","headline":["LINE 1","LINE 2"],"models":[{"label","image"}],
             "accent"?,"tag"?,"cta"?,"sub"?}. Image paths may be relative to
data/brand-directory/swing-shack/images/Products or to any --images folder.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "campaign-os"))

from _lib import product_post_templates as pt  # noqa: E402

PRODUCTS = pt.brand_dir() / "images" / "Products"
PACKS = {"type-hero": "product-type-hero", "one-hero": "product-one-hero", "pick-yours": "product-pick-yours"}


def resolve(post: dict, images) -> dict:
    roots = [Path(i) for i in (images if isinstance(images, list) else [images])] + [PRODUCTS]
    out = dict(post)
    out["models"] = []
    for m in post["models"]:
        p = Path(m["image"])
        if not p.is_absolute():
            p = next((b / p for b in roots if (b / p).exists()), roots[0] / p)
        out["models"].append({**m, "image": str(p)})
    return out


def goldens(images) -> int:
    done = 0
    for layout, pack in PACKS.items():
        pdir = pt.brand_dir() / "templates" / pack
        cases = json.loads((pdir / "cases.json").read_text(encoding="utf-8"))
        (pdir / "golden").mkdir(exist_ok=True)
        for i, case in enumerate(cases, 1):
            img = pt.render(resolve({**case, "layout": layout}, images))
            img.save(pdir / "golden" / ("case-%02d.jpg" % i), quality=90)
            done += 1
    print("rendered", done, "goldens")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("post", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--images", action="append", default=[], help="extra folders to find images in (repeatable)")
    ap.add_argument("--goldens", action="store_true")
    ap.add_argument("--next", nargs="*", help="layouts of the previous product posts, oldest first")
    a = ap.parse_args()
    if a.next is not None:
        print(pt.next_layout(a.next))
        return 0
    if a.goldens:
        return goldens(a.images)
    if not (a.post and a.out):
        ap.error("post.json and out.jpg are required")
    post = resolve(json.loads(Path(a.post).read_text(encoding="utf-8")), a.images)
    pt.render(post).save(a.out, quality=92)
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
