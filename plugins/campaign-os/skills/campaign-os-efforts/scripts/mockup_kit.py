#!/usr/bin/env python3
"""Mockup kit for the monthly efforts packs: the helpers behind art-directed mockups on real photos.

Import it from a build script (see the recipes in SKILL.md), or make a review board from finished screens:

    python3 mockup_kit.py board --title "1 · Swing Shack: The Wedge Ladder" --note "MOCKUP · names are samples" \\
        --sub "What it is in one sentence." --screen story.png="Monday story" --screen feed.png="Feed post" \\
        --out boards/1-wedge-ladder.jpg

Pillow and numpy only. No model touches the pixels.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[5]
FONTS = ROOT / "data" / "brand-directory" / "stick" / "typography" / "fonts"


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Montserrat from the brand folder (Black, ExtraBold or Light)."""
    return ImageFont.truetype(str(FONTS / f"Montserrat-{weight}.ttf"), size)


# ── photos ──────────────────────────────────────────────────────────────

def grade(im, warmth=0.04, contrast=1.12, sat=1.08, recover=0.92):
    """A real grade, never a raw photo: compress highlights so lamps don't blow out, then contrast,
    a touch of warmth and a light sharpen."""
    a = np.asarray(im.convert("RGB")).astype(float) / 255
    a = np.where(a > 0.75, 0.75 + (a - 0.75) * recover, a)
    a[..., 0] *= 1 + warmth
    a[..., 2] *= 1 - warmth
    out = Image.fromarray((a.clip(0, 1) * 255).astype("uint8"))
    out = ImageEnhance.Contrast(out).enhance(contrast)
    out = ImageEnhance.Color(out).enhance(sat)
    return out.filter(ImageFilter.UnsharpMask(radius=1.4, percent=60, threshold=3))


def cover(im, w, h, fx=0.5, fy=0.5):
    """Scale to fill w x h and crop; fx/fy pick which part survives."""
    k = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    x, y = round((im.width - w) * fx), round((im.height - h) * fy)
    return im.crop((x, y, x + w, y + h))


def perspective_paste(base, src, quad):
    """Put art onto a real screen in a photo (a venue TV, a phone): quad is TL, TR, BR, BL in base pixels.
    Nothing outside the quad changes."""
    w, h = src.size
    srcpts = np.array([(0, 0), (w, 0), (w, h), (0, h)], float)
    rows = []
    for (x, y), (u, v) in zip(np.array(quad, float), srcpts):
        rows += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
    coeffs = np.linalg.solve(np.array(rows), srcpts.reshape(8))
    warped = src.convert(base.mode).transform(base.size, Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).polygon([tuple(p) for p in quad], fill=255)
    return Image.composite(warped, base, mask)


# ── light and texture ───────────────────────────────────────────────────

def glow(base, layer, radius=18, strength=1.0):
    """Bloom: `layer` is light drawn on black (neon type, a lightning bolt, a lit edge)."""
    bloom = layer.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        bloom = ImageEnhance.Brightness(bloom).enhance(strength)
    return ImageChops.screen(ImageChops.screen(base, bloom), layer)


def scanlines(im, every=6, dark=0.28):
    a = np.asarray(im).astype(float)
    a[::every] *= 1 - dark
    a[1::every] *= 1 - dark * 0.5
    return Image.fromarray(a.clip(0, 255).astype("uint8"))


def vignette(im, amount=0.55):
    w, h = im.size
    y, x = np.ogrid[:h, :w]
    d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    m = (1 - amount * np.clip(d - 0.35, 0, 1)).clip(0, 1)
    return Image.fromarray((np.asarray(im).astype(float) * m[..., None]).astype("uint8"))


def grain(im, amount=8, seed=3):
    rng = np.random.default_rng(seed)
    a = np.asarray(im.convert("RGB")).astype(float) + rng.normal(0, amount, (im.height, im.width, 1))
    return Image.fromarray(a.clip(0, 255).astype("uint8"))


def pixel_text(text, cell, colour, font_px=11, weight="ExtraBold"):
    """Arcade lettering: render tiny, threshold to hard pixels, scale up block by block (NEAREST).
    Fit `cell` to the screen by measuring; never guess it."""
    f = font(weight, font_px)
    box = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)
    small = Image.new("L", (box[2] + 2, box[3] + 2), 0)
    ImageDraw.Draw(small).text((1, 1 - box[1]), text, font=f, fill=255)
    small = small.point(lambda v: 255 if v > 110 else 0)
    big = small.resize((small.width * cell, small.height * cell), Image.NEAREST)
    out = Image.new("RGBA", big.size, tuple(colour) + (0,))
    out.putalpha(big)
    return out


# ── cut-outs ────────────────────────────────────────────────────────────

def padded(piece, pad):
    """A transparent margin round a cut-out. Do this before any rim light or shadow: a figure that touches
    its own edge otherwise gets a glow that ends in a straight line (the December 'boxes' bug)."""
    out = Image.new("RGBA", (piece.width + 2 * pad, piece.height + 2 * pad), (0, 0, 0, 0))
    out.paste(piece, (pad, pad), piece)
    return out


def rim(piece, colour, width=10, blur=14):
    """A rim light: the piece's outline, spread and blurred, in one colour. Composite it under the piece."""
    al = piece.getchannel("A").filter(ImageFilter.MaxFilter(width | 1)).filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", piece.size, tuple(colour) + (0,))
    out.putalpha(al)
    return out


# ── review boards ───────────────────────────────────────────────────────

def phone(screen, label, width=420):
    """A plain phone frame around a 1080-wide screen, with a small label under it."""
    s = screen.convert("RGB").resize((width, round(screen.height * width / screen.width)), Image.LANCZOS)
    pad = 16
    fr = Image.new("RGBA", (s.width + 2 * pad, s.height + 2 * pad + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(fr)
    d.rounded_rectangle((0, 0, fr.width - 1, s.height + 2 * pad), radius=38, fill=(18, 18, 18))
    mask = Image.new("L", s.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s.width, s.height), radius=24, fill=255)
    fr.paste(s, (pad, pad), mask)
    d.text((fr.width // 2, s.height + 2 * pad + 10), label, font=font("Light", 18), fill=(60, 60, 60), anchor="mt")
    return fr


def _wrap(d, text, f, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textbbox((0, 0), t, font=f)[2] > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + [cur]


def board(title, note, sub, screens, out, bg=(245, 245, 243)):
    """One effort on one board: title, a red MOCKUP note, a wrapped description, the screens in phone frames."""
    frames = [phone(s, l) for s, l in screens]
    w = max(1300, sum(f.width for f in frames) + 60 * (len(frames) + 1))
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    sub_lines = _wrap(probe, sub, font("Light", 24), w - 120)
    top = 150 + 34 * len(sub_lines)
    h = top + max(f.height for f in frames) + 40
    b = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(b)
    d.text((60, 40), title, font=font("ExtraBold", 40), fill=(20, 20, 20))
    d.text((60, 100), note, font=font("Light", 20), fill=(200, 60, 60))
    for i, line in enumerate(sub_lines):
        d.text((60, 140 + 34 * i), line, font=font("Light", 24), fill=(70, 70, 70))
    x = (w - (sum(f.width for f in frames) + 60 * (len(frames) - 1))) // 2
    for f in frames:
        b.paste(f, (x, top + 10), f)
        x += f.width + 60
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    b.save(out, quality=90)
    return b


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    bp = sub.add_parser("board", help="lay finished screens out as one review board")
    bp.add_argument("--title", required=True)
    bp.add_argument("--note", default="MOCKUP")
    bp.add_argument("--sub", default="")
    bp.add_argument("--screen", action="append", required=True, help="path=label, in order")
    bp.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    screens = []
    for item in args.screen:
        path, _, label = item.partition("=")
        screens.append((Image.open(path), label or Path(path).stem))
    board(args.title, args.note, args.sub, screens, args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
