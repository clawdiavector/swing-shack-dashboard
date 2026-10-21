"""Studio-set posts: Krea builds an empty set, the real product goes in, then a light design layer.

The set (a plinth, a block, a wall with window light...) is generated once with no product and
no text, and kept in a small library (data/brand-directory/_system/studio-sets.json). A post is
the real cut-out placed in a set, grounded or levitating on purpose, with a floor shadow and a
contact shadow, then at most three pieces of text: a giant word behind the product, a headline
and a short caption. A badge appears only when the stock list backs it up.

Hard rules (Christelle, 2026-10-20 and 21), enforced by post_qa.check_post and by this module:
- the product pixels are never repainted or tinted; they are only defringed, very slightly
  softened to sit in the scene's photographic softness, shadowed and occluded;
- a product either rests on its surface (shadow touching it) or levitates clearly (a real gap and
  a soft shadow below). Never an ambiguous hover;
- the product's name appears once at most as text; text budget three, flourishes never stack;
- the giant word is never cropped by the canvas edge, and stays readable;
- text colour comes from the pixels behind it, and a soft scrim guarantees contrast;
- light is soft; a post that comes out too dark is refused.

Pure Pillow, like post_routes.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from _lib import post_routes as pr
from _lib import post_qa as qa

CW, CH = pr.CANVAS
NAVY_INK = (14, 40, 58)
WHITE_INK = (255, 255, 255)
TEAL = (0, 179, 186)
NAVY = (0, 61, 84)

GROUNDED = {"balls", "bags", "other"}            # rest on the surface
LEVITATE = {"irons", "wedges", "drivers", "putters", "gloves", "grips"}   # float, clearly
WALL_HUNG = {"apparel"}                          # hang on the wall, shadow on the wall
# product height (px at 1350 high), rotation, lift above the surface (0 grounded, clear gap if levitating)
CATEGORY_LAYOUT = {
    "irons": (520, -16, 120), "wedges": (560, -12, 120), "drivers": (540, -12, 120), "putters": (430, 0, 110),
    "balls": (470, 0, 0), "grips": (480, 62, 110), "bags": (780, 0, 0), "apparel": (640, 0, 0),
    "gloves": (380, 0, 110), "other": (420, 0, 0),
}
LIFT_MIN = qa.LIFT_MIN


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
    # a grounded product needs a straight-on set (its photo is straight-on): prefer those
    if product.category in GROUNDED:
        straight = [s for s in pool if s.get("view") in ("front", "floor")]
        pool = straight or pool
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
    im = ImageOps.fit(im, pr.CANVAS, Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.0, 30, 2))
    return im.convert("RGBA")


def _soft_ellipse(canvas, cx, cy, w, h, alpha, blur):
    m = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(m).ellipse([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], fill=int(255 * alpha))
    m = m.filter(ImageFilter.GaussianBlur(blur))
    lay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    lay.putalpha(m)
    canvas.alpha_composite(lay)


def _scrim(canvas, rect, ink, alpha=0.30):
    x0, y0, x1, y1 = [int(v) for v in rect]
    pad = 26
    col = NAVY if ink == WHITE_INK else (255, 255, 255)
    m = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([x0 - pad, y0 - pad, x1 + pad, y1 + pad], radius=40, fill=int(255 * alpha))
    m = m.filter(ImageFilter.GaussianBlur(28))
    lay = Image.new("RGBA", canvas.size, col + (0,))
    lay.putalpha(m)
    canvas.alpha_composite(lay)


def _defringe(im: Image.Image) -> Image.Image:
    """Pull in the cut-out edge one pixel and soften it slightly, so no halo of the old background shows."""
    a = im.split()[3].filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    out = im.copy()
    out.putalpha(a)
    return out


def _soften(im: Image.Image, radius: float = 0.55) -> Image.Image:
    """The set is a photograph with natural softness; a razor-sharp cut-out reads as pasted."""
    rgb = im.convert("RGB").filter(ImageFilter.GaussianBlur(radius)).convert("RGBA")
    rgb.putalpha(im.split()[3])
    return rgb


def _base_width(im: Image.Image) -> int:
    """Width of the product's lowest few percent: the footprint that touches the surface."""
    a = im.split()[3].point(lambda v: 255 if v > 80 else 0)
    box = a.getbbox()
    if not box:
        return im.width
    h = box[3] - box[1]
    strip = a.crop((0, int(box[3] - max(8, h * 0.06)), a.width, box[3]))
    sb = strip.getbbox()
    return (sb[2] - sb[0]) if sb else im.width


def floor_shadow(canvas, im, pos, base_y, light, length=1.0):
    """Cast the product's silhouette onto the floor: flattened, sheared away from the light, soft."""
    a = im.split()[3]
    flat_h = max(8, int(a.height * 0.16))
    flat = a.resize((a.width, flat_h), Image.BICUBIC)
    shear = 0.9 * length * (1 if light == "left" else -1)
    flat = flat.transform((a.width + int(abs(shear) * flat_h), flat_h), Image.AFFINE,
                          (1, shear, 0 if shear > 0 else abs(shear) * flat_h, 0, 1, 0), Image.BICUBIC)
    m = Image.new("L", canvas.size, 0)
    m.paste(flat, (pos[0], int(base_y - flat_h * 0.55)))
    m = m.filter(ImageFilter.GaussianBlur(11)).point(lambda v: int(v * 0.42))
    lay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    lay.putalpha(m)
    canvas.alpha_composite(lay)


# ---------------------------------------------------------------- design elements

def giant_word(canvas, word: str, style: str, y: int, width: int, colour, font_path: str, shear: float):
    """A huge word behind the product. Never wider than the canvas. Returns (mask, bbox)."""
    probe = ImageFont.truetype(font_path, 900)
    size = int(900 * width / max(probe.getbbox(word)[2], 1))
    for _ in range(4):
        ff = ImageFont.truetype(font_path, size)
        lay = Image.new("RGBA", (int(size * len(word) * 0.95) + 120, int(size * 1.4)), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        if style == "outline":
            d.text((30, 0), word, font=ff, fill=(0, 0, 0, 0), stroke_width=max(8, size // 38), stroke_fill=tuple(colour) + (255,))
        else:
            d.text((30, 0), word, font=ff, fill=tuple(colour) + ((90 if style == "tone" else 255),))
        if shear:
            lay = lay.transform(lay.size, Image.AFFINE, (1, shear, -shear * lay.height * 0.5, 0, 1, 0), Image.BICUBIC)
        box = lay.split()[3].point(lambda v: 255 if v > 30 else 0).getbbox()
        if not box:
            break
        bw = box[2] - box[0]
        if bw <= CW - 80:
            break
        size = int(size * (CW - 90) / bw)
    lay = lay.crop(box)
    pos = (int((CW - lay.width) / 2), int(y))
    pr.put(canvas, lay, pos)
    m = Image.new("L", canvas.size, 0)
    m.paste(lay.split()[3].point(lambda v: 255 if v > 30 else 0), pos)
    return m, (pos[0], pos[1], pos[0] + lay.width, pos[1] + lay.height)


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
    return (int(cx - d / 2), int(cy - d / 2), int(cx + d / 2), int(cy + d / 2))


def _marks(canvas, ink):
    """Quiet crop marks in the four corners (only on some posts, and never with a badge)."""
    d = ImageDraw.Draw(canvas)
    c = tuple(ink) + (170,)
    L = 30
    for x, y, sx, sy in ((40, 40, 1, 1), (CW - 40, 40, -1, 1), (40, CH - 40, 1, -1), (CW - 40, CH - 40, -1, -1)):
        d.line([(x, y), (x + sx * L, y)], fill=c, width=3)
        d.line([(x, y), (x, y + sy * L)], fill=c, width=3)


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


def _rect_overlap(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    area = max((a[2] - a[0]) * (a[3] - a[1]), 1)
    return max(0, x1 - x0) * max(0, y1 - y0) / area


def _headline_zone(bg, lines, size, font_path, shear, pmask, wbox, avoid=(), base_y=None):
    block_h = int(len(lines) * size * 1.1)
    w = max(pr.text_layer(l, size, pr.WHITE, font_path, shear).width for l in lines)
    options = {"top": 175, "upper": 330, "bottom": CH - 150 - block_h - 70}
    if base_y is not None and base_y + 50 + block_h <= CH - 120:
        options["below"] = int(base_y + 50)       # on the front of the plinth or the floor, under the product
    best = None
    for name, y in options.items():
        rect = (100, y, 100 + w + 10, y + block_h)
        _, tex = _stats(bg, rect)
        over_word = _rect_overlap(rect, wbox) if wbox else 0.0
        over_other = max([_rect_overlap(rect, a) for a in avoid] or [0.0])
        score = 14 * pr.rect_cover(pmask, rect) + 14 * over_word + 14 * over_other + tex / 30.0 + (0.15 if name == "upper" else 0)
        if best is None or score < best[0]:
            best = (score, name, y, rect, max(pr.rect_cover(pmask, rect), over_word, over_other))
    return best


def _best_headline(bg, lines, size, font_path, shear, pmask, wbox, base_y):
    """Try the full size, then smaller: a smaller headline in a calm zone beats a skipped post."""
    last = None
    for k in (1.0, 0.85, 0.72):
        sz = max(52, int(size * k))
        z = _headline_zone(bg, lines, sz, font_path, shear, pmask, wbox, base_y=base_y)
        last = (sz,) + z
        if z[4] <= qa.HEADLINE_OVERLAP_MAX:
            return last
    return last


def choose_word(product: pr.Product, idea: dict, rng: random.Random) -> Optional[str]:
    """One giant word, never one the headline already says, and never the product name twice."""
    line = idea["line"].lower()
    cands = [w for w in (product.model_number, product.name) if w and w.lower() not in line]
    if idea.get("brands"):
        cands = [c for c in cands if c.lower() not in [b.lower() for b in idea["brands"]]]
    if not cands or rng.random() > 0.85:
        return None
    return rng.choice(cands).upper()


def choose_caption(product: pr.Product, word: Optional[str], idea: dict) -> str:
    """The caption says where it is, not what it is again, when the giant word already names it."""
    where = "In store, %s." % product.town if product.in_stock and product.town else ""
    name = (product.display_name or product.name)
    if word and word.lower() in name.lower() and where:
        return where
    if name.lower() in idea["line"].lower() and where:
        return where
    return pr.caption_for(product)


# ---------------------------------------------------------------- the render

def render_studio(product: pr.Product, idea: dict, set_meta: dict, scenes_dir: Path, brand: str, seed: int,
                  word_style: Optional[str] = None) -> Tuple[Image.Image, dict]:
    rng = random.Random(seed)
    path = Path(scenes_dir) / set_meta["file"]
    if not path.exists():
        raise pr.LayoutFailed("studio scene missing: %s" % path)
    disp, shear, standin = pr.display_font(brand)
    body = pr.body_font(brand)
    base_bg = pr.grain(_scene(path), 1.6).convert("RGBA")   # one fine grain over the set; the product stays exact
    bg_luma = pr.mean_luma(base_bg)
    if bg_luma < pr.LIGHT_CAPS["min_bg_luma"]:
        raise pr.LayoutFailed("studio scene is too dark (mean luma %.0f)" % bg_luma)

    style = word_style or rng.choice(["tone", "solid", "solid", "outline"])
    word = choose_word(product, idea, rng)
    word_y = 150 + rng.randint(0, 110)
    wrect = (0, word_y, CW, word_y + 300)
    wcol = NAVY_INK if _stats(base_bg, wrect)[0] >= 135 else WHITE_INK

    height, rot, lift = CATEGORY_LAYOUT.get(product.category, CATEGORY_LAYOUT["other"])
    if lift and lift < LIFT_MIN:
        lift = LIFT_MIN
    h = height
    c_x = set_meta["cx"]
    b_y = set_meta["base"] * CH
    cut = _soften(_defringe(product.cutout))
    lines = pr.split_headline(idea["line"])
    hsize = _fit_headline(lines, CW - 220, disp, shear)
    placed = None
    for _ in range(10):
        r = h / cut.height
        im = cut.resize((max(1, int(cut.width * r)), max(1, int(h))), Image.LANCZOS)
        if rot:
            im = im.rotate(rot, expand=True, resample=Image.BICUBIC)
        px = int(c_x * CW - im.width / 2)
        py = int(b_y - im.height - lift)
        pm = pr.mask_of(im, (px, py))
        probe = base_bg.copy()
        wm, wbox = (giant_word(probe, word, style, word_y, int(CW * 0.9), wcol, disp, shear) if word else (None, None))
        visible = 1.0 - pr.covered(wm, pm) if wm is not None else 1.0
        inside = pr._share(pr._on(pm)) * CW * CH / max(pr._share(pr._on(im.split()[3])) * im.width * im.height, 1.0)
        hz = _best_headline(base_bg, lines, hsize, disp, shear, pm, wbox, b_y)
        if visible >= qa.WORD_VISIBLE_MIN and inside >= 0.9 and hz[5] <= qa.HEADLINE_OVERLAP_MAX:
            placed = (im, px, py, visible, inside)
            break
        h *= 0.93
    if not placed:
        raise pr.LayoutFailed("could not keep the word and the headline clear of the product")
    im, px, py, visible, inside = placed

    bg = base_bg.copy()
    wm, wbox = (giant_word(bg, word, style, word_y, int(CW * 0.9), wcol, disp, shear) if word else (None, None))
    foot_w = _base_width(im)
    foot_cx = px + im.width / 2
    if product.category in WALL_HUNG:
        # hangs on the wall: soft shadow thrown onto the wall behind it
        dx = 30 if set_meta["light"] == "left" else -30
        pr.shadow(bg, im, (px, py), dx, 40, 4, 24, 0.36)
    elif lift:
        # levitates: a clear gap, a soft pool of shadow on the surface below
        _soft_ellipse(bg, foot_cx, b_y + 6, max(foot_w, im.width * 0.45) * 1.15 + 60, 40, 0.42, 22)
        _soft_ellipse(bg, foot_cx, b_y + 10, max(foot_w, im.width * 0.45) * 1.8 + 120, 62, 0.18, 36)
    else:
        # rests on the surface: cast shadow along the floor, occlusion where it touches
        floor_shadow(bg, im, (px, py), b_y, set_meta["light"])
        _soft_ellipse(bg, foot_cx, b_y + 2, foot_w * 1.04, 16, 0.78, 5)
        _soft_ellipse(bg, foot_cx, b_y + 4, foot_w * 1.3, 30, 0.38, 14)
    pr.put(bg, im, (px, py))

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
    lcol = ink_for(bg, (lx, ly, lx + lw, ly + lh))
    name = "stick-logo-white.png" if lcol == WHITE_INK else "stick-logo-navy.png"
    logo = Image.open(pr.brand_dir(brand) / "logos" / name).convert("RGBA").resize((lw, lh), Image.LANCZOS)
    pr.put(bg, logo, (lx, ly))

    checks = {"word_visible": round(visible, 3), "product_inside": round(inside, 3), "bg_luma": round(bg_luma, 1),
              "lift": lift, "grounded": lift == 0}
    text_items = 1 if word else 0

    # headline
    size, score, zone, zy, zrect, overlap = _best_headline(bg, lines, hsize, disp, shear, pm, wbox, b_y)
    if overlap > qa.HEADLINE_OVERLAP_MAX:
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
    text_items += 1
    contrast = abs(_stats(bg, zrect)[0] - (255 if hcol == WHITE_INK else 14))
    checks.update({"headline_zone": zone, "headline_overlap": round(overlap, 3), "headline_contrast": round(contrast, 0)})

    # caption
    caption = choose_caption(product, word, idea)
    if caption:
        crect = (100, CH - 108, CW - 100, CH - 52)
        if _rect_overlap(crect, zrect) < 0.05:
            ccol = ink_for(bg, crect)
            _scrim(bg, crect, ccol, 0.24)
            _text_with_shadow(bg, caption, (110, CH - 100), 38, ccol, body)
            text_items += 1
        else:
            caption = ""

    # one flourish at most: a badge (only if the stock list says new), else quiet crop marks on some posts
    badge_text = "NEW\nIN" if product.stock_status == "new" else None
    badge_box = None
    if badge_text:
        spots = [(850, 430), (230, 520), (860, 800)]
        for s in spots:
            box = (s[0] - 100, s[1] - 100, s[0] + 100, s[1] + 100)
            if (pr.rect_cover(pm, box) < 0.02 and (wbox is None or _rect_overlap(box, wbox) < 0.3)
                    and _rect_overlap(box, zrect) < 0.05):
                badge_box = _badge(bg, badge_text, s[0], s[1], disp)
                break
        if not badge_box:
            badge_text = None
    elif rng.random() < 0.25:
        _marks(bg, ink_for(bg, (30, 30, 400, 400)))

    out = bg.convert("RGB")
    luma = pr.mean_luma(out)
    checks["mean_luma"] = round(luma, 1)
    checks["text_items"] = text_items
    meta = {
        "sku": product.sku, "route": "studio_set", "backdrop_id": set_meta["id"], "set_file": set_meta["file"], "seed": seed,
        "idea_id": idea["id"], "idea_line": idea["line"], "caption": caption, "word": word, "word_style": style if word else None,
        "badge": (badge_text or "").replace("\n", " "), "logo_corner": corner, "standin_font": standin,
        "category": product.category, "checks": checks,
        "confirm_before_posting": sorted(set(idea.get("requires") or []) | ({"in_stock"} if product.in_stock else set())),
    }
    problems = qa.check_post(meta, product_name=(product.display_name or product.name), texts=[idea["line"], caption, word or ""])
    meta["qa"] = {"passed": not problems, "problems": problems}
    if problems:
        raise pr.LayoutFailed("visual QA: " + "; ".join(problems))
    return out, meta
