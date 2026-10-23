"""Swing Shack product post templates: three fixed layouts, any product.

Approved 2026-10-23 from the Srixon Z-Star Monday designs. The product is always
the real packshot, cut out of its white background and never redrawn. Only the
words, the models and the accent change between posts.

    type-hero   dark, huge headline, 1 to 3 boxes fanned along the bottom
    one-hero    charcoal and inset frame, one big product on the right
    pick-yours  light editorial, 1 to 3 products in numbered columns

Pure Pillow (the production image has no numpy or scipy).
How they were made and how to rebuild them: wiki CampaignOS/runbooks/swing-shack-product-post-templates-2026-10-23.md
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350
LAYOUTS = ("type-hero", "one-hero", "pick-yours")

GREEN = (116, 204, 70)
ORANGE = (226, 113, 36)
BLUE = (99, 163, 239)
PURPLE = (143, 75, 249)
NEAR = (12, 10, 11)
CHAR = (58, 58, 58)
ACCENTS = {"green": GREEN, "orange": ORANGE, "blue": BLUE, "purple": PURPLE}

BLK, EXB, LIT = "Montserrat-BlackItalic.ttf", "Montserrat-ExtraBoldItalic.ttf", "Montserrat-LightItalic.ttf"

# Words we never put in a product post: claims need a source link (Christelle, 21 Oct).
BANNED_CLAIMS = ("longest", "straightest", "best", "#1", "number one", "tour proven", "proven", "guaranteed")


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def brand_dir() -> Path:
    return _root() / "data" / "brand-directory" / "swing-shack"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(brand_dir() / "typography" / "fonts" / name), size)


# ── cut-out ─────────────────────────────────────────────────────────────

def cutout(path_or_img, thr: int = 14) -> Image.Image:
    """Cut a packshot off its white background. Flood fill from the border, so white
    inside the product (a white box, a white ball) is kept. Returns RGBA."""
    im = path_or_img if isinstance(path_or_img, Image.Image) else Image.open(path_or_img)
    if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 250:
        return im.copy()  # already a cut-out
    rgb = im.convert("RGB")
    r, g, b = rgb.split()
    lightest_gap = ImageChops.lighter(ImageChops.lighter(ImageChops.invert(r), ImageChops.invert(g)), ImageChops.invert(b))
    mask = lightest_gap.point(lambda v: 255 if v <= thr else 0)  # 255 = near white
    w, h = mask.size
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)):
        if mask.getpixel(seed) == 255:
            ImageDraw.floodfill(mask, seed, 128)
    fg = mask.point(lambda v: 0 if v == 128 else 255)
    fg = fg.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))  # drop specks
    fg = fg.filter(ImageFilter.GaussianBlur(1.2))
    out = rgb.convert("RGBA")
    out.putalpha(fg)
    return out


# ── drawing helpers ─────────────────────────────────────────────────────

def _logo(canvas: Image.Image, dark: bool, right: int, top: int, width: int) -> None:
    name = "swing-shack-logo-dark.png" if dark else "swing-shack-logo-white.png"
    lg = Image.open(brand_dir() / "logos" / name).convert("RGBA")
    lg.thumbnail((width, width))
    canvas.alpha_composite(lg, (right - lg.width, top))


def _shadow(canvas, im, x, y, strength=120, blur=28, dy=30):
    a = im.getchannel("A").point(lambda v: int(v * strength / 255))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.putalpha(a)
    pad = blur * 3
    big = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    big.alpha_composite(sh, (pad, pad))
    canvas.alpha_composite(big.filter(ImageFilter.GaussianBlur(blur)), (x - pad, y - pad + dy))


def _put(canvas, im, cx, cy, width, rot=0, shadow=True, **kw):
    h = int(im.height * width / im.width)
    r = im.resize((width, h), Image.LANCZOS)
    if rot:
        r = r.rotate(rot, expand=True, resample=Image.BICUBIC)
    x, y = int(cx - r.width / 2), int(cy - r.height / 2)
    if shadow:
        _shadow(canvas, r, x, y, **kw)
    canvas.alpha_composite(r, (x, y))
    return x, y, r.width, r.height


def _text(d, xy, s, f, fill, track=0):
    if not track:
        d.text(xy, s, font=f, fill=fill)
        return
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + track


def _fit(d, s, name, maxw, start, floor=40):
    size = start
    while size > floor and d.textlength(s, font=font(name, size)) > maxw:
        size -= 4
    return font(name, size)


def _pill(d, x, y, s, f, bg, fg):
    w = d.textlength(s, font=f)
    d.rounded_rectangle((x, y, x + w + 52, y + f.size + 24), radius=8, fill=bg)
    d.text((x + 26, y + 10), s, font=f, fill=fg)


# ── layouts ─────────────────────────────────────────────────────────────

def _type_hero(c: Image.Image, p: dict, acc, cuts: List[Image.Image]) -> None:
    d = ImageDraw.Draw(c)
    ghost = p["headline"][0].upper()
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    gf = _fit(ld, ghost, BLK, 1180, 300)
    ld.text((-30, 250), ghost, font=gf, fill=(34, 34, 34, 255))
    ld.text((-30, 520), ghost, font=gf, fill=(26, 26, 26, 255))
    c.alpha_composite(lay)
    d.rectangle((0, 0, 18, H), fill=acc)
    _logo(c, False, W - 70, 64, 230)
    d = ImageDraw.Draw(c)
    _pill(d, 80, 70, p.get("tag", "IN STOCK NOW").upper(), font(EXB, 28), acc, NEAR)
    _text(d, (76, 150), p["brand"].upper(), font(LIT, 44), (255, 255, 255), track=14)
    l1, l2 = p["headline"][0].upper(), p["headline"][1].upper()
    f1 = _fit(d, l1, BLK, 900, 168)
    f2 = _fit(d, l2, BLK, 900, 168)
    size = min(f1.size, f2.size)
    d.text((76, 205), l1, font=font(BLK, size), fill=(255, 255, 255))
    d.text((76, 205 + int(size * 0.98)), l2, font=font(BLK, size), fill=(255, 255, 255))
    n = len(cuts)
    xs = {1: [540], 2: [330, 750], 3: [205, 540, 875]}[n]
    ws = {1: [560], 2: [470, 470], 3: [400, 440, 400]}[n]
    rots = {1: [0], 2: [-3, 3], 3: [-5, 0, 5]}[n]
    order = [0, 2, 1] if n == 3 else list(range(n))  # centre product on top
    for i in order:
        _put(c, cuts[i], xs[i], 985 if (n == 3 and i == 1) or n < 3 else 960, ws[i], rot=rots[i], strength=200, blur=28, dy=38)
    d = ImageDraw.Draw(c)
    labels = "  ·  ".join(m["label"].upper() for m in p["models"])
    _text(d, (80, 1245), labels, _fit(d, labels, EXB, 900, 34, 22), (255, 255, 255), track=4)
    _text(d, (80, 1290), p.get("cta", "DM US TO ORDER").upper(), font(LIT, 26), ORANGE, track=3)


def _one_hero(c: Image.Image, p: dict, acc, cuts: List[Image.Image]) -> None:
    g = Image.linear_gradient("L").resize((W, H))  # black top to white bottom
    g = g.point(lambda v: int(255 * (v / 255) ** 1.3))
    c.paste(Image.composite(Image.new("RGBA", (W, H), NEAR + (255,)), c, g))
    d = ImageDraw.Draw(c)
    d.rectangle((33, 33, W - 33, H - 33), outline=(255, 255, 255, 120), width=4)
    _put(c, cuts[0], 780, 800, 780, strength=200, blur=40, dy=60)
    _logo(c, False, W - 90, 90, 200)
    d = ImageDraw.Draw(c)
    _text(d, (86, 110), p["brand"].upper(), font(LIT, 40), (255, 255, 255), track=12)
    l1, l2 = p["headline"][0].upper(), p["headline"][1].upper()
    size = min(_fit(d, l1, BLK, 560, 150).size, _fit(d, l2, BLK, 560, 150).size)
    d.text((86, 170), l1, font=font(BLK, size), fill=(255, 255, 255))
    d.text((86, 170 + int(size * 0.99)), l2, font=font(BLK, size), fill=acc)
    sub_y = 170 + int(size * 1.99) + 52
    for line in p.get("sub", [])[:2]:
        d.text((86, sub_y), line, font=font(LIT, 40), fill=(255, 255, 255))
        sub_y += 55
    labels = "  /  ".join(m["label"].upper() for m in p["models"])
    _text(d, (86, 1180), labels, _fit(d, labels, EXB, 880, 30, 20), (255, 255, 255), track=4)
    _text(d, (86, 1226), p.get("cta", "IN STOCK AT SWING SHACK. DM US.").upper(), font(LIT, 26), (200, 200, 200), track=3)


def _pick_yours(c: Image.Image, p: dict, acc, cuts: List[Image.Image]) -> None:
    d = ImageDraw.Draw(c)
    _logo(c, True, W - 70, 60, 210)
    d = ImageDraw.Draw(c)
    _text(d, (70, 70), p["brand"].upper(), font(LIT, 38), (64, 64, 64), track=14)
    l1, l2 = p["headline"][0].upper(), p["headline"][1].upper()
    size = min(_fit(d, l1, BLK, 900, 128).size, _fit(d, l2, BLK, 900, 128).size)
    d.text((66, 130), l1, font=font(BLK, size), fill=NEAR)
    d.text((66, 130 + int(size * 0.95)), l2, font=font(BLK, size), fill=NEAR)
    d.rectangle((70, 408, 240, 418), fill=acc)
    n = len(cuts)
    cw = (W - 140) // 3
    x_start = 70 + (3 - n) * cw // 2
    for i, im in enumerate(cuts):
        x0 = x_start + i * cw
        d.line((x0, 480, x0 + cw - 24, 480), fill=(220, 220, 220), width=3)
        _put(c, im, x0 + (cw - 24) // 2, 720, cw + 50, strength=70, blur=14, dy=18)
        d = ImageDraw.Draw(c)
        _text(d, (x0, 980), "0%d" % (i + 1), font(BLK, 64), acc)
        _text(d, (x0, 1060), p["models"][i]["label"].upper(), _fit(d, p["models"][i]["label"].upper(), EXB, cw - 10, 30, 18), NEAR)
    d.line((70, 1160, W - 70, 1160), fill=(220, 220, 220), width=3)
    _text(d, (70, 1195), p.get("tag", "IN STOCK NOW").upper(), font(EXB, 36), NEAR, track=3)
    _text(d, (70, 1250), p.get("cta", "DM US TO ORDER").upper(), font(LIT, 28), (64, 64, 64), track=3)


LAYOUT_FUNCS = {"type-hero": _type_hero, "one-hero": _one_hero, "pick-yours": _pick_yours}
LAYOUT_BG = {"type-hero": NEAR, "one-hero": CHAR, "pick-yours": (255, 255, 255)}


# ── public API ──────────────────────────────────────────────────────────

def check_post(post: dict) -> List[str]:
    """Reasons this post cannot be rendered; empty means fine."""
    bad: List[str] = []
    if post.get("layout") not in LAYOUTS:
        bad.append("layout must be one of %s" % ", ".join(LAYOUTS))
    models = post.get("models") or []
    if not models or len(models) > 3:
        bad.append("models: 1 to 3 products, each with label and image")
    if post.get("layout") == "one-hero" and len(models) != 1:
        bad.append("one-hero shows exactly one product")
    head = post.get("headline") or []
    if len(head) != 2:
        bad.append("headline: exactly two short lines")
    if not post.get("brand"):
        bad.append("brand: the product maker, e.g. SRIXON")
    text = " ".join([post.get("brand", ""), " ".join(head), post.get("tag", ""), post.get("cta", ""), " ".join(post.get("sub", []))]).lower()
    for w in BANNED_CLAIMS:
        if w in text:
            bad.append("claim '%s' needs a source link; leave it out" % w)
    for h in head:
        if len(h) > 14:
            bad.append("headline line '%s' is over 14 characters" % h)
    return bad


def render(post: dict) -> Image.Image:
    """post = {layout, brand, headline:[l1,l2], models:[{label,image}], accent?, tag?, cta?, sub?}"""
    problems = check_post(post)
    if problems:
        raise ValueError("; ".join(problems))
    layout = post["layout"]
    acc = ACCENTS.get(post.get("accent", "green" if layout != "one-hero" else "orange"), GREEN)
    cuts = [cutout(m["image"]) for m in post["models"]]
    canvas = Image.new("RGBA", (W, H), LAYOUT_BG[layout] + (255,))
    LAYOUT_FUNCS[layout](canvas, post, acc, cuts)
    return canvas.convert("RGB")


def next_layout(history: Sequence[str], min_gap: int = 2) -> str:
    """Pick the layout used longest ago, never one used in the last `min_gap` posts, so with three layouts
    a layout comes back at most every third product post.
    history = layouts of previous product posts, oldest first."""
    recent = list(history)[-min_gap:]
    pool = [l for l in LAYOUTS if l not in recent] or list(LAYOUTS)
    last_used = {l: (max((i for i, h in enumerate(history) if h == l), default=-1)) for l in pool}
    return min(pool, key=lambda l: last_used[l])


def layout_for(n_products: int, history: Sequence[str] = (), min_gap: int = 2) -> str:
    """Rotation that respects the product count: one product can use any layout,
    but only one-hero was designed for a single hero shot, so it leads for n == 1."""
    pick = next_layout(history, min_gap)
    if n_products > 1 and pick == "one-hero":
        alt = [l for l in LAYOUTS if l != "one-hero" and l not in list(history)[-1:]]
        return alt[0] if alt else "type-hero"
    return pick
