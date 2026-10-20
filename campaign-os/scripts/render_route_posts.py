#!/usr/bin/env python3
"""Render product posts with the route engine (ideas x routes x backdrops).

Needs cut-out PNGs (made by cutout_products.py, on the Mac) and the backdrop
folder (not in git; ROUTE_BACKDROPS_DIR or --backdrops).

  python campaign-os/scripts/render_route_posts.py --brand stick \
      --products route-products.json --cutouts out/birefnet --backdrops backdrops \
      --out out/posts --count 6 --seed 20261020

Each post gets a .jpg and a .json with the idea, route, backdrop, layout checks and what
must be confirmed before it goes out. Nothing is published from here.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from _lib import post_routes as pr  # noqa: E402


def load_cutout(cut_dir: Path, name: str) -> Image.Image:
    p = Path(name)
    cands = [cut_dir / name, cut_dir / (name + ".png"), cut_dir / (p.stem + ".png")]
    for c in cands:
        if c.exists():
            im = Image.open(c).convert("RGBA")
            a = im.split()[3].point(lambda v: 0 if v < 60 else v)
            im.putalpha(a)
            return im.crop(im.getbbox())
    raise SystemExit("cut-out not found for %s in %s" % (name, cut_dir))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--products", required=True, help="JSON list of products (see data/brand-directory/stick/route-products.example.json)")
    ap.add_argument("--cutouts", required=True)
    ap.add_argument("--backdrops", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--memory", default=None, help="memory file so runs do not repeat each other (default: OUT/route-memory.json)")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    products = json.loads(Path(a.products).read_text(encoding="utf-8"))
    ideas = pr.load_ideas(a.brand)
    backdrops = pr.load_backdrops()
    memory = pr.RouteMemory(Path(a.memory) if a.memory else out / "route-memory.json")
    made = 0
    for n in range(a.count):
        spec = products[n % len(products)]
        prod = pr.Product(
            sku=spec["sku"], name=spec["name"], cutout=load_cutout(Path(a.cutouts), spec["cutout"]),
            category=spec.get("category", "other"), model_number=spec.get("model_number"),
            in_stock=bool(spec.get("in_stock")), town=spec.get("town"), display_name=spec.get("display_name"),
        )
        try:
            img, meta = pr.render_post(prod, ideas, backdrops, memory, a.seed + n, a.brand, Path(a.backdrops))
        except pr.LayoutFailed as e:
            print("SKIP %s: %s" % (spec["sku"], e))
            continue
        stem = "%s-%02d-%s-%s" % (spec["sku"], n + 1, meta["route"], meta["idea_id"])
        img.save(out / (stem + ".jpg"), quality=90)
        (out / (stem + ".json")).write_text(json.dumps(meta, indent=1), encoding="utf-8")
        print("made", stem, meta["checks"])
        made += 1
    print("done: %d posts in %s" % (made, out))


if __name__ == "__main__":
    main()
