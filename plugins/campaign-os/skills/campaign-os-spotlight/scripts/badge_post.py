#!/usr/bin/env python3
"""Turn a real close-up photo of a badge or logo into a finished post.

The badge is found, straightened (rotated to its most left-right symmetrical
angle) and centred; a white-on-black-outline label ("PSYCHO BUNNY @ stick")
sits centred under it. No plate, no AI on the pixels. Outputs an Instagram /
Facebook 4:5 (1080x1350) and a Google Business 4:3 (1200x900: the 4:5 post
centred on a blurred copy of itself, because portrait photos can't be cropped
to landscape without the label hitting the badge).

    python3 badge_post.py --photo 004.jpg --photo 007.jpg --label "PSYCHO BUNNY" \\
        --brand-dir data/brand-directory/stick --out out/

Needs Pillow and rembg (`pip install "rembg[cpu]"`, first run downloads the
birefnet model, about 220 MB). Put rembg in its own virtualenv if the main one
must stay lean. Check every result by eye: a badge cut off by the photo edge
can't be centred.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

IG = (1080, 1350)
GBP = (1200, 900)


def badge_mask(im: Image.Image) -> Image.Image:
    try:
        from rembg import new_session, remove
    except ImportError:
        sys.exit('rembg is not installed: pip install "rembg[cpu]"')
    small = im.copy()
    small.thumbnail((1200, 1200))
    session = new_session("birefnet-general-lite")
    return remove(small, session=session, only_mask=True, post_process_mask=True).resize(im.size)


def centroid(mask: Image.Image) -> tuple[float, float]:
    s = mask.resize((max(1, mask.width // 8), max(1, mask.height // 8)))
    px = s.load()
    tx = ty = n = 0
    for y in range(s.height):
        for x in range(s.width):
            if px[x, y] > 127:
                tx += x
                ty += y
                n += 1
    if not n:
        sys.exit("no badge found in the photo")
    return tx / n * 8, ty / n * 8


def symmetry_angle(mask: Image.Image, cx: float, cy: float) -> float:
    """The rotation (-12..12 deg, half-degree steps) where the badge mirrors best."""
    def score(a: float) -> int:
        r = mask.rotate(a, center=(cx, cy), resample=Image.BILINEAR)
        c = r.crop((int(cx - 500), int(cy - 600), int(cx + 500), int(cy + 600))).resize((250, 300))
        d = ImageChops.difference(c, ImageOps.mirror(c))
        return sum(i * v for i, v in enumerate(d.histogram()))
    return min((score(a / 2), a / 2) for a in range(-24, 25))[1]


def outlined_logo(logo: Image.Image, width: int, stroke: int) -> Image.Image:
    a = logo.split()[3].resize((width, round(logo.height * width / logo.width)), Image.LANCZOS)
    pad = stroke * 2
    alpha = Image.new("L", (a.width + 2 * pad, a.height + 2 * pad), 0)
    alpha.paste(a, (pad, pad))
    grown = alpha.filter(ImageFilter.MaxFilter(stroke * 2 + 1))
    out = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", alpha.size, (0, 0, 0, 255)), (0, 0), grown)
    out.paste(Image.new("RGBA", alpha.size, (255, 255, 255, 255)), (0, 0), alpha)
    return out


def label(canvas: Image.Image, text: str, fonts: Path, logo: Image.Image) -> None:
    w, h = canvas.size
    d = ImageDraw.Draw(canvas)

    def say(xy, t, font, sw):
        d.text(xy, t, font=font, fill=(255, 255, 255), stroke_width=sw, stroke_fill=(0, 0, 0))

    big = ImageFont.truetype(str(fonts / "Montserrat-Black.ttf"), int(h * 0.040))
    small = ImageFont.truetype(str(fonts / "Montserrat-ExtraBold.ttf"), int(h * 0.024))
    y = int(h * 0.80)
    say(((w - d.textlength(text, font=big)) / 2, y), text, big, max(2, int(h * 0.004)))
    y2 = y + int(h * 0.056)
    say(((w - d.textlength("@", font=small)) / 2, y2), "@", small, max(2, int(h * 0.003)))
    lg = outlined_logo(logo, int(h * 0.135), max(2, int(h * 0.003)))
    canvas.paste(lg, ((w - lg.width) // 2, y2 + int(h * 0.036)), lg)


def make(photo: Path, text: str, brand_dir: Path, out: Path, fill: float) -> list[Path]:
    im = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    mask = badge_mask(im).convert("L")
    cx, cy = centroid(mask)
    ang = symmetry_angle(mask, cx, cy)
    im = im.rotate(ang, center=(cx, cy), resample=Image.BICUBIC)
    mask = mask.rotate(ang, center=(cx, cy))
    x0, y0, x1, y1 = mask.getbbox()
    bx, by, bh = (x0 + x1) / 2, (y0 + y1) / 2, y1 - y0
    w, h = im.size
    margin = int(w * math.sin(math.radians(abs(ang))) * 1.2) + 10
    ch = bh / fill
    cw = ch * IG[0] / IG[1]
    if cw > w - 2 * margin:
        cw = w - 2 * margin
        ch = cw * IG[1] / IG[0]
    if ch > h - 2 * margin:
        ch = h - 2 * margin
        cw = ch * IG[0] / IG[1]
    X = min(max(bx - cw / 2, margin), w - margin - cw)
    Y = min(max(by - 0.40 * ch, margin), h - margin - ch)
    post = im.crop((int(X), int(Y), int(X + cw), int(Y + ch))).resize(IG, Image.LANCZOS)
    logo = Image.open(brand_dir / "logos" / "stick-logo-navy.png").convert("RGBA")
    label(post, text, brand_dir / "typography" / "fonts", logo)

    r = max(GBP[0] / post.width, GBP[1] / post.height)
    bg = post.resize((round(post.width * r), round(post.height * r)), Image.LANCZOS)
    left, top = (bg.width - GBP[0]) // 2, (bg.height - GBP[1]) // 2
    bg = bg.crop((left, top, left + GBP[0], top + GBP[1])).filter(ImageFilter.GaussianBlur(28))
    bg = ImageEnhance.Brightness(bg).enhance(0.85)
    fg = post.resize((GBP[1] * IG[0] // IG[1], GBP[1]), Image.LANCZOS)
    bg.paste(fg, ((GBP[0] - fg.width) // 2, 0))

    out.mkdir(parents=True, exist_ok=True)
    paths = [out / f"{photo.stem}__instagram.jpg", out / f"{photo.stem}__gbp.jpg"]
    post.save(paths[0], quality=93)
    bg.save(paths[1], quality=93)
    print(f"ok  {photo.name}  straightened {ang:+.1f} deg  -> {paths[0].name}, {paths[1].name}")
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photo", action="append", required=True, help="close-up photo (repeatable)")
    ap.add_argument("--label", default="PSYCHO BUNNY", help="brand line above '@ stick'")
    ap.add_argument("--brand-dir", default="data/brand-directory/stick",
                    help="brand folder holding logos/ and typography/fonts/")
    ap.add_argument("--fill", type=float, default=0.44, help="badge height as a share of the post height")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    for p in a.photo:
        make(Path(p), a.label, Path(a.brand_dir), Path(a.out), a.fill)
    return 0


if __name__ == "__main__":
    sys.exit(main())
