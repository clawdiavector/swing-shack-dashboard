#!/usr/bin/env python3
"""Group a dump of post images into template candidates by filename stem and platform size.

Writes <out>/<stem-group>/<platform>/<file> symlinks, a _sheet.jpg per group,
_overview.jpg (one example per group) and groups.json.

  python3 group_images.py --src "<Content Bank>/Swing Shack/Services" --out /tmp/review/ss
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def stem_key(path: Path) -> str:
    """'coaching_post2' -> 'coaching_post', 'cf5 copy' -> 'cf', 'blackfriday copy 3' -> 'blackfriday'."""
    s = path.stem.lower()
    s = re.sub(r"( copy( \d+)?|[-_ ]?\d+)+$", "", s).strip()
    s = re.sub(r"[-_ ](post|story|feed|static)$", "", s)
    return s or path.stem.lower()


def platform(w: int, h: int) -> str:
    a = h / w
    if a > 1.6:
        return "instagram-story_1080x1920"
    if 1.2 <= a <= 1.3:
        return "instagram-post_1080x1350"
    if 1.05 < a < 1.2:
        return "instagram-post-oldcrop_1080x1200"
    if 0.95 <= a <= 1.05:
        return "square_1080x1080"
    return "facebook-gbp-landscape"


def sheet(files: list[Path], out: Path, cols: int = 8, tw: int = 170) -> None:
    th = int(tw * 1.78)
    rows = max(1, (len(files) + cols - 1) // cols)
    canvas = Image.new("RGB", (cols * tw, rows * (th + 14)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        w, h = im.size
        im.thumbnail((tw - 4, th - 4))
        x, y = (i % cols) * tw, (i // cols) * (th + 14)
        canvas.paste(im, (x + 2, y + 2))
        draw.text((x + 2, y + th - 2), f"{f.stem[:20]} {w}x{h}", fill="black", font=font)
    canvas.save(out, quality=80)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, action="append", help="source dir (repeatable, recursive)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--clean", action="store_true", help="delete --out first")
    args = ap.parse_args()
    out = Path(args.out)
    if args.clean and out.exists():
        shutil.rmtree(out)
    groups: dict[str, list[tuple[Path, int, int]]] = defaultdict(list)
    for src in args.src:
        for p in sorted(Path(src).rglob("*")):
            if p.suffix.lower() in SUFFIXES and p.is_file():
                with Image.open(p) as im:
                    groups[stem_key(p)].append((p.resolve(), *im.size))
    summary = {}
    for key, items in sorted(groups.items()):
        for p, w, h in items:
            d = out / key / platform(w, h)
            d.mkdir(parents=True, exist_ok=True)
            link = d / p.name
            if not link.exists():
                link.symlink_to(p)
        files = sorted((out / key).glob("*/*"))
        sheet(files, out / key / "_sheet.jpg")
        counts: dict[str, int] = defaultdict(int)
        for _, w, h in items:
            counts[platform(w, h).split("_")[0]] += 1
        summary[key] = {"count": len(items), "platforms": dict(counts), "files": [p.name for p, _, _ in items]}
    firsts = [sorted((out / k).glob("*/*"))[0] for k in summary]
    sheet(firsts, out / "_overview.jpg", cols=7, tw=220)
    (out / "groups.json").write_text(json.dumps(summary, indent=1))
    for k, v in summary.items():
        print(f"{k:28} {v['count']:3}  {v['platforms']}")
    print(f"\n{len(summary)} groups -> {out} (open _overview.jpg; merge groups that share a look)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
