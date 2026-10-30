#!/usr/bin/env python3
"""Mockup kit for the monthly efforts packs: the helpers behind art-directed mockups on real photos.

Import it from a build script (see the recipes in SKILL.md), or make a review board from finished screens:

    python3 mockup_kit.py board --title "1 · Swing Shack: The Wedge Ladder" --note "MOCKUP · names are samples" \\
        --sub "What it is in one sentence." --screen story.png="Monday story" --screen feed.png="Feed post" \\
        --out boards/1-wedge-ladder.jpg

Pillow only (no numpy, so it runs wherever the tests run). No model touches the pixels.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    knee = 0.75 * 255

    def lut(gain):
        out = []
        for v in range(256):
            x = knee + (v - knee) * recover if v > knee else v
            out.append(max(0, min(255, round(x * gain))))
        return out

    out = im.convert("RGB").point(lut(1 + warmth) + lut(1.0) + lut(1 - warmth))
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
    srcpts = [(0, 0), (w, 0), (w, h), (0, h)]
    rows, rhs = [], []
    for (x, y), (u, v) in zip(quad, srcpts):
        rows += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        rhs += [u, v]
    coeffs = _solve(rows, rhs)
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
    """Darken every `every`-th row (and half as much on the row after), like a CRT."""
    mask = Image.new("L", im.size, 255)
    d = ImageDraw.Draw(mask)
    for y in range(0, im.height, every):
        d.line((0, y, im.width, y), fill=round(255 * (1 - dark)))
        d.line((0, y + 1, im.width, y + 1), fill=round(255 * (1 - dark / 2)))
    return ImageChops.multiply(im.convert("RGB"), Image.merge("RGB", (mask, mask, mask)))


def vignette(im, amount=0.55):
    """Darken towards the corners."""
    g = Image.radial_gradient("L")                     # 0 at the centre, 255 at the middle of each edge
    m = g.point(lambda v: round(255 * (1 - amount * max(0.0, v / 255 - 0.35)))).resize(im.size, Image.BILINEAR)
    return ImageChops.multiply(im.convert("RGB"), Image.merge("RGB", (m, m, m)))


def grain(im, amount=8, seed=3):
    """Film grain: a fixed noise field (Pillow's effect_noise) added and subtracted around mid-grey."""
    noise = Image.effect_noise(im.size, amount)        # mid-grey 128 with Gaussian noise
    up = noise.point(lambda v: max(0, v - 128))
    down = noise.point(lambda v: max(0, 128 - v))
    rgb = im.convert("RGB")
    rgb = ImageChops.add(rgb, Image.merge("RGB", (up, up, up)))
    return ImageChops.subtract(rgb, Image.merge("RGB", (down, down, down)))


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


def _solve(a, b):
    """Solve a small linear system (Gaussian elimination with partial pivoting)."""
    n = len(b)
    m = [list(map(float, row)) + [float(v)] for row, v in zip(a, b)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


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
