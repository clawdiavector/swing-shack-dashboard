"""Studio-set posts: Krea builds an empty set, the real product goes in, then a design layer.

The set (a plinth, a block, a wall with window light...) is generated once with no product and
no text, and kept in a small library (data/brand-directory/_system/studio-sets.json). A post is
the real cut-out placed in a set with its own shadow, then graphic design on top: a giant word
behind the product (tone-on-tone, solid or outline), a headline, a caption, crop marks with a
spec line and, only when the stock list backs it up, a badge.

Rules this module enforces (Christelle, 2026-10-20 and 21):
- the product pixels are never repainted or tinted, only shadowed;
- text colour comes from the pixels behind it, and a soft scrim guarantees contrast;
- the giant word stays readable, headlines stay off the product and the word;
- light is soft, never a heavy spotlight; a post that comes out too dark is refused.

Pure Pillow, like post_routes.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from _lib import post_routes as pr

CW, CH = pr.CANVAS
NAVY_INK = (14, 40, 58)
WHITE_INK = (255, 255, 255)
TEAL = (0, 179, 186)
NAVY = (0, 61, 84)

# product height (px at 1350 high), rotation, float above the surface, by category
CATEGORY_LAYOUT = {
    "irons": (500, -16, 70), "wedges": (540, -12, 60), "drivers": (520, -12, 60), "putters": (430, 0, 40),
    "balls": (470, 0, 0), "grips": (470, 62, 40), "bags": (780, 0, 0), "apparel": (640, 0, 0),
    "gloves": (360, 0, 30), "other": (420, 0, 40),
}
WORD_VISIBLE_MIN = 0.78
CONTRAST_MIN = 70          # between the text colour and the pixels behind it, after the scrim
HEADLINE_OVERLAP_MAX = 0.03


# ---------------------------------------------------------------- sets

def load_sets() -> List[dict]:
    p = pr.repo_root() / "data" / "brand-directory" / "_system" / "studio-sets.json"
    return json.loads(p.read_text(encoding="utf-8")).get("sets", [])


def eligible_sets(product: pr.Product, sets: Optional[List[dict]] = None) -> List[dict]:
    sets = sets if sets is not None else load_sets()
    return [s for s in sets if product.category in s.get("suits", [])]


def pick_set(product: pr.Product, memory: pr.RouteMemory, rng: random.Random, sets: Optional[List[dict]] = None,
             avoid: int = 6, exclude: Optional[set] = None) -> dict:
    pool = [s for s in eligible_sets(product, sets) if s["id"] not in (exclude or set())]
    if not pool:
        raise pr.LayoutFailed("no studio set suits category %s" % product.category)
    recent = set(memory.recent("backdrop_id", avoid))
    fresh = [s for s in pool if s["id"] not in recent] or pool
    return rng.choice(fresh)


# ---------------------------------------------------------------- pixels

def _stats(img: Image.Image, rect) -> Tuple[float, float]:
    g = img.convert("L").crop(tuple(int(v) for v in rect))
    st = ImageStat.Stat(g)
    return st.mean[0], st.stddev[0]


def ink_for(img: Image.Image, rect) -> Tuple[int, int, int]:
    return WHITE_INK if _stats(img, rect)[0] < 135 else NAVY_INK


def _scene(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGB")
    im = ImageOps.fit(im, pr.CANVAS, Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 40, 2))
    return im.convert("RGBA")


def _soft_ellipse(canvas, cx, cy, w, h, alpha, blur):
    m = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(m).ellipse([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], fill=int(255 * alpha))
    m = m.filter(ImageFilter.GaussianBlur(blur))
    lay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    lay.putalpha(m)
    canvas.alpha_composite(lay)


def _scrim(canvas, rect, ink, alpha=0.30):
    """Soft pad in the opposite colour behind text, so it reads on any surface."""
    x0, y0, x1, y1 = [int(v) for v in rect]
    pad = 26
    col = NAVY if ink == WHITE_INK else (255, 255, 255)
    m = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([x0 - pad, y0 - pad, x1 + pad, y1 + pad], radius=40, fill=int(255 * alpha))
    m = m.filter(ImageFilter.GaussianBlur(28))
    lay = Image.new("RGBA", canvas.size, col + (0,))
    lay.putalpha(m)
    canvas.alpha_composite(lay)


# ---------------------------------------------------------------- design elements

def giant_word(canvas, word: str, style: str, y: int, width: int, colour, font_path: str, shear: float) -> Image.Image:
    """A huge word behind the product. style: tone (low contrast), solid, outline. Returns its mask."""
    probe = ImageFont.truetype(font_path, 900)
    size = int(900 * width / max(probe.getbbox(word)[2], 1))
    ff = ImageFont.truetype(font_path, size)
    lay = Image.new("RGBA", (int(width * 1.2), int(size * 1.4)), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    if style == "outline":
        d.text((10, 0), word, font=ff, fill=(0, 0, 0, 0), stroke_width=5, stroke_fill=tuple(colour) + (235,))
    else:
        d.text((10, 0), word, font=ff, fill=tuple(colour) + ((84 if style == "tone" else 255),))
    if shear:
        lay = lay.transform(lay.size, Image.AFFINE, (1, shear, -shear * lay.height * 0.5, 0, 1, 0), Image.BICUBIC)
    pos = (int((CW - lay.width) / 2), int(y))
    pr.put(canvas, lay, pos)
    m = Image.new("L", canvas.size, 0)
    m.paste(lay.split()[3].point(lambda v: 255 if v > 30 else 0), pos)
    return m


def _badge(canvas, text, cx, cy, font_path, d=190, rot=-12):
    b = Image.new("RGBA", (d + 40, d + 40), (0, 0, 0, 0))
    dr = ImageDraw.Draw(b)
    dr.ellipse([20, 20, d + 20, d + 20], fill=TEAL + (255,))
    f = ImageFont.truetype(font_path, int(d * 0.24))
    lines = text.split("\n")
    y = d / 2 + 20 - len(lines) * f.size * 0.6
    for ln in lines:
        w = dr.textbbox((0, 0), ln, font=f)[2]
        dr.text(((d + 40 - w) / 2, y), ln, font=f, fill=NAVY + (255,))
        y += f.size * 1.15
    b = b.rotate(rot, expand=True, resample=Image.BICUBIC)
    pr.put(canvas, b, (int(cx - b.width / 2), int(cy - b.height / 2)))


def _marks(canvas, ink, spec: str, body_font: str):
    """Crop marks in the corners and a small vertical spec line down the left edge."""
    d = ImageDraw.Draw(canvas)
    c = tuple(ink) + (190,)
    L = 34
    for x, y, sx, sy in ((40, 40, 1, 1), (CW - 40, 40, -1, 1), (40, CH - 40, 1, -1), (CW - 40, CH - 40, -1, -1)):
        d.line([(x, y), (x + sx * L, y)], fill=c, width=3)
        d.line([(x, y), (x, y + sy * L)], fill=c, width=3)
    t = Image.new("RGBA", (760, 40), (0, 0, 0, 0))
    ImageDraw.Draw(t).text((0, 0), spec, font=ImageFont.truetype(body_font, 26), fill=tuple(ink) + (210,))
    pr.put(canvas, t.rotate(90, expand=True), (52, 400))


def _text_with_shadow(canvas, t: str, xy, size: int, ink, font_path: str):
    f = ImageFont.truetype(font_path, size)
    d = ImageDraw.Draw(canvas)
    d.text((xy[0] + 2, xy[1] + 2), t, font=f, fill=(0, 20, 30, 120))
    d.text(xy, t, font=f, fill=tuple(ink) + (255,))


# ---------------------------------------------------------------- layout helpers

def _fit_headline(lines: List[str], maxw: int, font_path: str, shear: float) -> int:
    best = 92
    for l in lines:
        best = min(best, pr.fit_size(l, maxw, font_path, shear, 92, 44))
    return best


def _bbox_rect(mask):
    b = mask.getbbox()
    return b if b else (0, 0, 0, 0)


def _rect_overlap(a, b) -> float:
    """Share of rect a that lies inside rect b."""
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    area = max((a[2] - a[0]) * (a[3] - a[1]), 1)
    return max(0, x1 - x0) * max(0, y1 - y0) / area


def _headline_zone(bg, lines, size, font_path, shear, pmask, wmask):
    block_h = int(len(lines) * size * 1.1)
    w = max(pr.text_layer(l, size, pr.WHITE, font_path, shear).width for l in lines)
    options = {"top": 175, "upper": 330, "bottom": CH - 150 - block_h - 70}
    wbox = _bbox_rect(wmask) if wmask is not None else None
    best = None
    for name, y in options.items():
        rect = (100, y, 100 + w + 10, y + block_h)
        _, tex = _stats(bg, rect)
        over_word = _rect_overlap(rect, wbox) if wbox else 0.0
        score = 14 * pr.rect_cover(pmask, rect) + 14 * over_word + tex / 30.0 + (0.15 if name == "upper" else 0)
        if best is None or score < best[0]:
            best = (score, name, y, rect, max(pr.rect_cover(pmask, rect), over_word))
    return best


def _spec_line(product: pr.Product) -> str:
    parts = [product.name.upper(), (product.model_number or product.category).upper()]
    return "  /  ".join(parts)   # the caption already says it is in store


# ---------------------------------------------------------------- the render

def render_studio(product: pr.Product, idea: dict, set_meta: dict, scenes_dir: Path, brand: str, seed: int,
                  word_style: Optional[str] = None) -> Tuple[Image.Image, dict]:
    rng = random.Random(seed)
    path = Path(scenes_dir) / set_meta["file"]
    if not path.exists():
        raise pr.LayoutFailed("studio scene missing: %s" % path)
    disp, shear, standin = pr.display_font(brand)
    body = pr.body_font(brand)
    base_bg = _scene(path)
    base_bg = pr.grain(base_bg, 2.2).convert("RGBA")   # grain on the set only, the product stays exact
    bg_luma = pr.mean_luma(base_bg)
    if bg_luma < pr.LIGHT_CAPS["min_bg_luma"]:
        raise pr.LayoutFailed("studio scene is too dark (mean luma %.0f)" % bg_luma)

    style = word_style or rng.choice(["tone", "solid", "outline"])
    candidates = [w for w in (product.model_number, product.display_name and product.name or product.name) if w]
    word = rng.choice(candidates).upper()
    word_y = 150 + rng.randint(0, 120)
    word_w = 1000
    wrect = (0, word_y, CW, word_y + 300)
    wcol = NAVY_INK if _stats(base_bg, wrect)[0] >= 135 else WHITE_INK

    height, rot, lift = CATEGORY_LAYOUT.get(product.category, CATEGORY_LAYOUT["other"])
    h = height
    c_x = set_meta["cx"]
    b_y = set_meta["base"] * CH
    cut = product.cutout
    wm = pm = None
    placed = None
    lines = pr.split_headline(idea["line"])
    hsize = _fit_headline(lines, CW - 220, disp, shear)
    for _ in range(10):
        r = h / cut.height
        im = cut.resize((max(1, int(cut.width * r)), max(1, int(h))), Image.LANCZOS)
        if rot:
            im = im.rotate(rot, expand=True, resample=Image.BICUBIC)
        px = int(c_x * CW - im.width / 2)
        py = int(b_y - im.height - lift)
        pm = pr.mask_of(im, (px, py))
        probe = base_bg.copy()
        wm = giant_word(probe, word, style, word_y, word_w, wcol, disp, shear)
        visible = 1.0 - pr.covered(wm, pm)
        inside = pr._share(pr._on(pm)) * CW * CH / max(pr._share(pr._on(im.split()[3])) * im.width * im.height, 1.0)
        hz = _headline_zone(base_bg, lines, hsize, disp, shear, pm, wm)
        if visible >= WORD_VISIBLE_MIN and inside >= 0.9 and hz[4] <= HEADLINE_OVERLAP_MAX:
            placed = (im, px, py, visible, inside)
            break
        h *= 0.93   # make room: a slightly smaller product beats a skipped post
    if not placed:
        raise pr.LayoutFailed("could not keep the word and the headline clear of the product")
    im, px, py, visible, inside = placed

    bg = base_bg.copy()
    wm = giant_word(bg, word, style, word_y, word_w, wcol, disp, shear)
    dx = 60 if set_meta["light"] == "left" else -60
    _soft_ellipse(bg, c_x * CW + dx * 0.2, b_y + 6, im.width * 0.5 + 60, 34 + lift * 0.1, 0.55 if not lift else 0.40, 16)
    _soft_ellipse(bg, c_x * CW + dx * 0.9, b_y + 10, im.width * 0.8 + 120, 46, 0.22, 34)
    pr.put(bg, im, (px, py))                       # the real pixels, untouched

    # logo: top-left unless that corner is blocked or busy
    lw = 230
    lg_n = Image.open(pr.brand_dir(brand) / "logos" / "stick-logo-navy.png").convert("RGBA")
    lh = int(lg_n.height * lw / lg_n.width)
    corners = {"tl": (64, 56), "tr": (CW - 64 - lw, 56)}

    def busy(k):
        rect = (corners[k][0], corners[k][1], corners[k][0] + lw, corners[k][1] + lh)
        return pr.rect_cover(pm, rect) * 10 + _stats(bg, rect)[1] / 30

    corner = "tl" if busy("tl") < 1.0 else min(corners, key=busy)
    lx, ly = corners[corner]
    lrect = (lx, ly, lx + lw, ly + lh)
    lcol = ink_for(bg, lrect)
    name = "stick-logo-white.png" if lcol == WHITE_INK else "stick-logo-navy.png"
    logo = Image.open(pr.brand_dir(brand) / "logos" / name).convert("RGBA").resize((lw, lh), Image.LANCZOS)
    pr.put(bg, logo, (lx, ly))

    checks = {"word_visible": round(visible, 3), "product_inside": round(inside, 3), "bg_luma": round(bg_luma, 1)}

    # headline
    size = hsize
    score, zone, zy, zrect, overlap = _headline_zone(bg, lines, size, disp, shear, pm, wm)
    if overlap > HEADLINE_OVERLAP_MAX:
        raise pr.LayoutFailed("no calm zone for the headline (overlap %.2f)" % overlap)
    hcol = ink_for(bg, zrect)
    _scrim(bg, zrect, hcol)
    yy = zy
    for ln in lines:
        lay = pr.text_layer(ln, size, hcol, disp, shear)
        sh = Image.new("RGBA", lay.size, (0, 0, 0, 0))
        sh.putalpha(lay.split()[3].point(lambda v: int(v * 0.35)))
        pr.put(bg, sh.filter(ImageFilter.GaussianBlur(4)), (112, yy + 4))
        pr.put(bg, lay, (110, yy))
        yy += int(size * 1.1)
    contrast = abs(_stats(bg, zrect)[0] - (255 if hcol == WHITE_INK else 14))
    if contrast < CONTRAST_MIN:
        raise pr.LayoutFailed("headline would not be readable (contrast %.0f)" % contrast)
    checks.update({"headline_zone": zone, "headline_overlap": round(overlap, 3), "headline_contrast": round(contrast, 0)})

    # caption
    caption = pr.caption_for(product)
    crect = (100, CH - 108, CW - 100, CH - 52)
    ccol = ink_for(bg, crect)
    _scrim(bg, crect, ccol, 0.24)
    _text_with_shadow(bg, caption, (110, CH - 100), 38, ccol, body)

    # crop marks + spec line, badge
    _marks(bg, ink_for(bg, (40, 400, 90, 900)), _spec_line(product), body)
    badge_text = None
    if product.stock_status == "new":
        badge_text = "NEW\nIN"
    elif product.in_stock and rng.random() < 0.15:
        badge_text = "IN\nSTORE"
    if badge_text:
        spots = [(850, 430), (230, 520), (860, 800)]
        free = [s for s in spots if pr.rect_cover(pm, (s[0] - 100, s[1] - 100, s[0] + 100, s[1] + 100)) < 0.02
                and pr.rect_cover(wm, (s[0] - 100, s[1] - 100, s[0] + 100, s[1] + 100)) < 0.3]
        if free:
            _badge(bg, badge_text, free[0][0], free[0][1], disp)
        else:
            badge_text = None

    out = bg.convert("RGB")
    luma = pr.mean_luma(out)
    if luma < pr.LIGHT_CAPS["min_mean_luma"]:
        raise pr.LayoutFailed("post is too dark (mean luma %.0f)" % luma)
    checks["mean_luma"] = round(luma, 1)
    meta = {
        "sku": product.sku, "route": "studio_set", "backdrop_id": set_meta["id"], "set_file": set_meta["file"], "seed": seed,
        "idea_id": idea["id"], "idea_line": idea["line"], "caption": caption, "word": word, "word_style": style,
        "badge": (badge_text or "").replace("\n", " "), "logo_corner": corner, "standin_font": standin,
        "checks": checks,
        "confirm_before_posting": sorted(set(idea.get("requires") or []) | ({"in_stock"} if product.in_stock else set())),
    }
    return out, meta
