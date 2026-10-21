"""Route engine for product posts: ideas x routes x backdrops, with a layout check.

A post is one *idea* (a line Christelle ticked Yes), one *route* (a way to
stage the product), one *backdrop* (a licence-safe texture) and a *seed*.
Nothing here is a fixed template: the same route lands differently for a
club, a putter, a ball box and a bag, and the rotation rules keep the feed
from repeating itself.

The product is always the real cut-out (never redrawn). The layout check
refuses a post whose hero word is hidden, whose caption runs into the product,
or whose background is crushed dark.

Pure PIL + numpy. Cut-outs are made elsewhere (rembg on the Mac).
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

CANVAS = (1080, 1350)
NAVY = (0, 61, 84)
GREY = (210, 210, 210)
WHITE = (255, 255, 255)
TEAL = (0, 179, 186)

# Christelle, 2026-10-20: "be careful of that spotlight, it's quite heavy".
# These are hard ceilings, not defaults: no preset may go past them.
LIGHT_CAPS = {
    "vignette": 0.28,       # how much the corners may darken (0 to 1)
    "pool_alpha": 38,       # strength of the soft light pool on turf (0 to 255)
    "rim_white": 0.22,
    "rim_colour": 0.16,
    "min_mean_luma": 38,    # whole post must not be crushed dark (0 to 255)
    "min_bg_luma": 30,      # the backdrop alone, before the product and words go on it
}
BLEED_MAX = 1.12  # a hero number may be at most 12 percent wider than the canvas
CHECKS = {
    "word_visible_min": {"crop_word": 0.80, "hero_number": 0.60},
    "caption_overlap_max": 0.03,
    "product_inside_min": {"crop_word": 0.80, "turf_shadow": 0.97, "hero_number": 0.90},
}

ROUTE_IDS = ("crop_word", "turf_shadow", "hero_number")
# Which product categories each route suits. A bag does not lie on turf.
ROUTE_CATEGORIES = {
    "crop_word": None,  # any
    "turf_shadow": {"irons", "wedges", "putters", "balls", "grips", "drivers", "other"},
    "hero_number": None,
}
ROUTE_TONES = {
    "crop_word": ("navy", "dark"),
    "turf_shadow": ("grass",),
    "hero_number": ("metal", "light", "grey"),
}
SATISFIABLE = {"in_stock", "tone_check"}  # facts the engine can vouch for (the rest need a person)


class LayoutFailed(Exception):
    pass


@dataclass
class Product:
    sku: str
    name: str                      # the brand word, e.g. "Takomo"
    cutout: Image.Image            # RGBA, cropped to the product
    category: str = "other"        # irons, putters, balls, grips, bags, apparel, gloves, drivers, other
    model_number: Optional[str] = None   # hero number for the number route, e.g. "101U"
    in_stock: bool = False
    stock_status: Optional[str] = None   # from the weekly stock list: new, back, low, heavy, still, stuck
    town: Optional[str] = None
    display_name: Optional[str] = None

    @property
    def shape(self) -> str:
        w, h = self.cutout.size
        if h / w > 1.6:
            return "tall"
        if w / h > 1.25:
            return "wide"
        return "square"


@dataclass
class Plan:
    idea: dict
    route: str
    backdrop_id: int
    seed: int


# ---------------------------------------------------------------- data

def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def brand_dir(brand: str) -> Path:
    return repo_root() / "data" / "brand-directory" / brand


def load_ideas(brand: str = "stick") -> List[dict]:
    p = brand_dir(brand) / "post-ideas.json"
    return json.loads(p.read_text(encoding="utf-8")).get("ideas", [])


def load_backdrops() -> List[dict]:
    p = repo_root() / "data" / "brand-directory" / "_system" / "backdrops.json"
    return json.loads(p.read_text(encoding="utf-8")).get("backdrops", [])


# ---------------------------------------------------------------- memory

class RouteMemory:
    """What was posted recently, so the next post does not repeat it."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self.items: List[dict] = []
        if self.path and self.path.exists():
            try:
                self.items = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.items = []

    def add(self, plan: Plan, sku: str) -> None:
        self.items.append({"idea_id": plan.idea["id"], "route": plan.route, "backdrop_id": plan.backdrop_id, "sku": sku})
        if self.path:
            self.path.write_text(json.dumps(self.items[-200:], indent=1), encoding="utf-8")

    def recent(self, key: str, n: int) -> List:
        return [i[key] for i in self.items[-n:]]


# ---------------------------------------------------------------- choosing

def eligible_ideas(ideas: List[dict], product: Product, facts: Optional[set] = None) -> List[dict]:
    have = set(SATISFIABLE if product.in_stock else {"tone_check"}) | set(facts or ())
    if product.stock_status == "new":
        have.add("status_new")
    if product.stock_status == "back":
        have.add("status_back")
    out = []
    for i in ideas:
        if i.get("status") != "yes" or i.get("pool") != "product":
            continue
        if i.get("multi"):
            continue  # a lineup or range idea needs several products in one post
        if i.get("brands") and product.name not in i["brands"]:
            continue  # the line names a brand
        if i.get("needs_number") and not product.model_number:
            continue
        pts = i.get("product_types") or []
        if pts and product.category not in pts:
            continue
        if set(i.get("requires") or []) - have:
            continue
        out.append(i)
    return out


def eligible_routes(product: Product) -> List[str]:
    out = []
    for r in ROUTE_IDS:
        cats = ROUTE_CATEGORIES[r]
        if cats is not None and product.category not in cats:
            continue
        if r == "hero_number" and not product.model_number:
            continue
        out.append(r)
    return out


def choose(product: Product, ideas: List[dict], backdrops: List[dict], memory: RouteMemory,
           seed: int, facts: Optional[set] = None, avoid_idea: int = 30, avoid_backdrop: int = 6) -> Plan:
    rng = random.Random(seed)
    pool = eligible_ideas(ideas, product, facts)
    if not pool:
        raise LayoutFailed("no eligible idea for %s (check stock status and ticked ideas)" % product.sku)
    recent_i = set(memory.recent("idea_id", avoid_idea))
    fresh = [i for i in pool if i["id"] not in recent_i] or pool
    idea = rng.choice(fresh)
    routes = eligible_routes(product)
    last = memory.recent("route", 1)
    routes_nl = [r for r in routes if r not in last] or routes
    counts = {r: memory.recent("route", 10).count(r) for r in routes_nl}
    low = min(counts.values())
    route = rng.choice([r for r in routes_nl if counts[r] == low])
    return Plan(idea, route, pick_backdrop(route, backdrops, memory, rng, avoid_backdrop), seed)


def pick_backdrop(route: str, backdrops: List[dict], memory: RouteMemory, rng: random.Random, avoid: int = 6) -> int:
    tones = ROUTE_TONES[route]
    pool = [b for b in backdrops if b["tone"] in tones]
    recent = set(memory.recent("backdrop_id", avoid))
    fresh = [b for b in pool if b["id"] not in recent] or pool
    return rng.choice(fresh)["id"]


# ---------------------------------------------------------------- fonts and text

def _font_candidates(brand: str):
    fonts = brand_dir(brand) / "typography" / "fonts"
    designer = sorted(fonts.glob("AllRoundGothic*Demi*Oblique*")) if fonts.exists() else []
    out = [(str(p), 0.0, False) for p in designer]
    out += [(p, 0.22, True) for p in (
        "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
        "C:/Windows/Fonts/ARLRDBD.TTF",
        str(fonts / "Montserrat-Black.ttf"),
    )]
    return out


def display_font(brand: str):
    """(path, shear, is_standin). The designer's All Round Gothic when its file is in the repo."""
    for path, shear, standin in _font_candidates(brand):
        if os.path.exists(path):
            return path, shear, standin
    raise LayoutFailed("no display font found")


def body_font(brand: str) -> str:
    p = brand_dir(brand) / "typography" / "fonts" / "Montserrat-Light.ttf"
    return str(p) if p.exists() else display_font(brand)[0]


def text_layer(t: str, size: int, colour, font_path: str, shear: float) -> Image.Image:
    f = ImageFont.truetype(font_path, size)
    b = f.getbbox(t)
    w, h = b[2] + int(size * 0.4), b[3] + int(size * 0.3)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), t, font=f, fill=tuple(colour) + (255,))
    if shear:
        im = im.transform(im.size, Image.AFFINE, (1, shear, -shear * h * 0.5, 0, 1, 0), Image.BICUBIC)
    return im


def fit_size(t: str, maxw: int, font_path: str, shear: float, start: int = 900, floor: int = 24) -> int:
    """Largest size (up to start) whose text layer fits maxw. Measures once, scales, then trims."""
    f100 = ImageFont.truetype(font_path, 100)
    w100 = f100.getbbox(t)[2] + 40 + abs(shear) * 100
    s = int(min(start, max(floor, 100 * maxw / max(w100, 1))))
    while s > floor and text_layer(t, s, WHITE, font_path, shear).width > maxw:
        s -= 4
    return max(s, floor)


def wrap(text: str, font_path: str, size: int, maxw: int) -> List[str]:
    f = ImageFont.truetype(font_path, size)
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if f.getlength(trial) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_text(d, xy, text, font, fill) -> None:
    """Text with a soft dark under-stroke so it stays readable on grass and metal."""
    x, y = xy
    for dx, dy in ((2, 2), (-1, 2), (2, -1)):
        d.text((x + dx, y + dy), text, font=font, fill=(0, 20, 30, 150))
    d.text((x, y), text, font=font, fill=tuple(fill) + (255,))


def split_headline(text: str) -> List[str]:
    """Break an idea into at most two display lines, at a sentence boundary when it has one."""
    parts = [p.strip() for p in text.replace("? ", "?|").replace(". ", ".|").split("|") if p.strip()]
    if len(parts) == 2:
        return parts
    if len(parts) > 2:
        mid = len(parts) // 2
        return [" ".join(parts[:mid]), " ".join(parts[mid:])]
    words = text.split()
    if len(words) <= 3:
        return [text]
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


# ---------------------------------------------------------------- pixels

def put(canvas: Image.Image, im: Image.Image, pos: Tuple[int, int]) -> None:
    tmp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    tmp.paste(im, pos, im)
    canvas.alpha_composite(tmp)


def mask_of(im: Image.Image, pos: Tuple[int, int], size=CANVAS) -> Image.Image:
    m = Image.new("L", size, 0)
    m.paste(im.split()[3], pos)
    return m


def covered(mask_a: Image.Image, mask_b: Image.Image, rect=None) -> float:
    a = np.asarray(mask_a) > 40
    b = np.asarray(mask_b) > 40
    if rect:
        x0, y0, x1, y1 = [int(v) for v in rect]
        a, b = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
    total = a.sum()
    return 0.0 if total == 0 else float((a & b).sum()) / float(total)


def rect_cover(mask: Image.Image, rect) -> float:
    x0, y0, x1, y1 = [max(0, int(v)) for v in rect]
    sub = np.asarray(mask)[y0:y1, x0:x1] > 40
    return float(sub.mean()) if sub.size else 0.0


def mean_luma(im: Image.Image, rect=None) -> float:
    g = np.asarray(im.convert("L"), dtype=float)
    if rect:
        x0, y0, x1, y1 = [int(v) for v in rect]
        g = g[y0:y1, x0:x1]
    return float(g.mean())


def product_luma(cut: Image.Image) -> float:
    a = np.asarray(cut.split()[3]) > 128
    g = np.asarray(cut.convert("L"), dtype=float)
    return float(g[a].mean()) if a.any() else 128.0


def soft_vignette(img: Image.Image, strength: float) -> Image.Image:
    strength = min(strength, LIGHT_CAPS["vignette"])
    w, h = img.size
    y, x = np.ogrid[:h, :w]
    d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    m = np.clip(1 - strength * np.clip(d - 0.5, 0, 1) ** 1.5, 0, 1)[..., None]
    return Image.fromarray((np.asarray(img.convert("RGB")).astype(float) * m).clip(0, 255).astype("uint8"))


def grain(img: Image.Image, amount: float = 5.0, seed: int = 7) -> Image.Image:
    n = np.random.default_rng(seed).normal(0, amount, (img.height, img.width, 1))
    return Image.fromarray((np.asarray(img.convert("RGB")).astype(float) + n).clip(0, 255).astype("uint8"))


def shadow(canvas, cut, pos, dx, dy, steps, blur, alpha):
    base = mask_of(cut, pos, canvas.size)
    acc = Image.new("L", canvas.size, 0)
    for i in range(steps + 1):
        acc = ImageChops.lighter(acc, ImageChops.offset(base, int(dx * i / max(steps, 1)), int(dy * i / max(steps, 1))))
    acc = acc.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    lay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    lay.putalpha(acc)
    canvas.alpha_composite(lay)


def rim(canvas, cut, pos, colour, radius, alpha):
    alpha = min(alpha, LIGHT_CAPS["rim_white"] if tuple(colour) == WHITE else LIGHT_CAPS["rim_colour"])
    a = mask_of(cut, pos, canvas.size).filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(v * alpha))
    lay = Image.new("RGBA", canvas.size, tuple(colour) + (0,))
    lay.putalpha(a)
    canvas.alpha_composite(lay)


def scaled(cut: Image.Image, long_side: float, rot: float) -> Image.Image:
    r = long_side / max(cut.size)
    im = cut.resize((max(1, int(cut.width * r)), max(1, int(cut.height * r))), Image.LANCZOS)
    return im.rotate(rot, expand=True, resample=Image.BICUBIC)


def fit_cover(im: Image.Image) -> Image.Image:
    return ImageOps.fit(im.convert("RGB"), CANVAS, Image.LANCZOS)


# ---------------------------------------------------------------- brand marks

def logo_for(canvas: Image.Image, brand: str, rect) -> Tuple[Image.Image, bool]:
    """Pick the navy or white wordmark by the brightness under it, so it is always legible."""
    dark_logo = mean_luma(canvas, rect) > 140
    name = "stick-logo-navy.png" if dark_logo else "stick-logo-white.png"
    p = brand_dir(brand) / "logos" / name
    if not p.exists():
        raise LayoutFailed("logo file missing: %s" % p)
    l = Image.open(p).convert("RGBA")
    w = 230
    return l.resize((w, int(l.height * w / l.width)), Image.LANCZOS), dark_logo


LOGO_RECT = (64, 56, 64 + 230, 56 + 80)


def caption_for(product: Product) -> str:
    nm = product.display_name or product.name
    if product.in_stock and product.town:
        return "%s. In store, %s." % (nm, product.town)
    return "%s." % nm


# ---------------------------------------------------------------- routes

def _place_checked(canvas_bg, product, long_side, rot, cx, cy, protected, word_mask, word_min, inside_min, steps=14):
    """Place the product, then shrink and nudge until the text stays clear and the hero word stays readable."""
    L = long_side
    x = cx
    for _ in range(steps):
        ir = scaled(product.cutout, L, rot)
        pos = (int(CANVAS[0] * x - ir.width / 2), int(CANVAS[1] * cy - ir.height / 2))
        pm = mask_of(ir, pos)
        in_canvas = float((np.asarray(pm) > 40).sum()) / max(float((np.asarray(mask_of(ir, (0, 0, ), (ir.width, ir.height))) > 40).sum()), 1.0)
        word_vis = 1.0 - covered(word_mask, pm) if word_mask is not None else 1.0
        worst = max([rect_cover(pm, r) for r in protected] or [0.0])
        if word_vis >= word_min and worst <= CHECKS["caption_overlap_max"] and in_canvas >= inside_min:
            return ir, pos, {"word_visible": round(word_vis, 3), "text_overlap": round(worst, 3), "product_inside": round(in_canvas, 3)}
        L *= 0.94
        x -= 0.012
    raise LayoutFailed("could not keep the text clear of the product")


def render_route(route: str, product: Product, plan: Plan, brand: str, backdrops_dir: Path) -> Tuple[Image.Image, dict]:
    path, shear, standin = display_font(brand)
    light = body_font(brand)
    bd_file = None
    for b in load_backdrops():
        if b["id"] == plan.backdrop_id:
            bd_file = Path(backdrops_dir) / b["file"]
    if not bd_file or not bd_file.exists():
        raise LayoutFailed("backdrop file missing for id %s" % plan.backdrop_id)
    bg_src = fit_cover(Image.open(bd_file))
    line = plan.idea["line"]
    caption = caption_for(product)
    W, H = CANVAS
    checks: dict = {}

    def check_bg(img):
        l = mean_luma(img)
        if l < LIGHT_CAPS["min_bg_luma"]:
            raise LayoutFailed("backdrop is too dark (mean luma %.0f)" % l)
        checks["bg_luma"] = round(l, 1)

    if route == "crop_word":
        bg = Image.blend(bg_src, Image.new("RGB", CANVAS, NAVY), 0.35)
        bg = soft_vignette(bg, 0.22).convert("RGBA")
        check_bg(bg)
        word = (product.display_name or product.name).upper()
        s = fit_size(word, H - 260, path, shear, 900)
        wl = text_layer(word, s, WHITE, path, shear).rotate(90, expand=True, resample=Image.BICUBIC)
        wpos = (W - wl.width + 10, 120)
        wmask = mask_of(wl, wpos)
        cap_lines = wrap(line, light, 40, 560)
        cap_rect = (60, H - 130 - 48 * (len(cap_lines) - 1), 640, H - 60)
        pill_rect = (60, 160, 330, 240)
        base_long = {"tall": 1200, "wide": 920, "square": 980}[product.shape]
        rot = -12 if product.shape == "tall" else -8
        ir, pos, c = _place_checked(bg, product, base_long, rot, 0.40, 0.58, [cap_rect, pill_rect, LOGO_RECT], wmask,
                                    CHECKS["word_visible_min"]["crop_word"], CHECKS["product_inside_min"]["crop_word"])
        checks.update(c)
        put(bg, wl, wpos)
        shadow(bg, ir, pos, 40, 60, 6, 38, 0.45)
        rim(bg, ir, pos, WHITE, 10, 0.22)
        rim(bg, ir, pos, TEAL, 36, 0.16)
        put(bg, ir, pos)
        kicker = "NEW IN" if product.stock_status == "new" else None  # only what the stock list backs up
        _kicker_and_caption(bg, kicker, cap_lines, light, path, 40, WHITE, H)

    elif route == "turf_shadow":
        bg = Image.blend(bg_src, Image.new("RGB", CANVAS, (12, 40, 34)), 0.3)
        bg = soft_vignette(bg, 0.2).convert("RGBA")
        check_bg(bg)
        top = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        d = ImageDraw.Draw(top)
        for y in range(700):
            d.line([(0, y), (W, y)], fill=NAVY + (int(225 * (1 - y / 700) ** 1.1),))
        bg.alpha_composite(top)
        lines = split_headline(line)
        size = min(96, min(fit_size(l, W - 130, path, shear, 120, 40) for l in lines))
        head_rect = (50, 190, W - 50, 190 + int(size * 1.15 * len(lines)) + 20)
        cap_rect = (60, H - 130, W - 60, H - 60)
        rot, base_long, cy = {"tall": (52, 980, 0.70), "wide": (10, 640, 0.64), "square": (8, 700, 0.66)}[product.shape]
        ir, pos, c = _place_checked(bg, product, base_long, rot, 0.55, cy, [head_rect, cap_rect, LOGO_RECT], None,
                                    0.0, CHECKS["product_inside_min"]["turf_shadow"])
        checks.update(c)
        pool = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        ImageDraw.Draw(pool).ellipse([pos[0] - 80, pos[1] - 40, pos[0] + ir.width + 80, pos[1] + ir.height + 80],
                                     fill=(255, 255, 235, LIGHT_CAPS["pool_alpha"]))
        bg.alpha_composite(pool.filter(ImageFilter.GaussianBlur(90)))
        shadow(bg, ir, pos, 150, 190, 30, 22, 0.5)
        shadow(bg, ir, pos, 14, 20, 3, 9, 0.7)
        put(bg, ir, pos)
        y = 200
        for l in lines:
            put(bg, text_layer(l, size, WHITE, path, shear), (60, y))
            y += int(size * 1.12)
        draw_text(ImageDraw.Draw(bg), (64, H - 110), caption, ImageFont.truetype(light, 38), WHITE)

    elif route == "hero_number":
        dark = product_luma(product.cutout) > 170
        if dark:
            bg = Image.blend(bg_src, Image.new("RGB", CANVAS, NAVY), 0.55)
        else:
            bg = Image.blend(Image.new("RGB", CANVAS, GREY), bg_src, 0.42)
        bg = soft_vignette(bg, 0.2).convert("RGBA")
        check_bg(bg)
        col = WHITE if dark else NAVY
        num = product.model_number
        s = fit_size(num, int(W * BLEED_MAX), path, shear, 1300)  # may bleed off the edge a little, never lose a character
        nl = text_layer(num, s, col, path, shear)
        npos = (-int(nl.width * 0.04), LOGO_RECT[3] + 40)  # below the logo, never under it
        nmask = mask_of(nl, npos)
        txt_lines = wrap(line, light, 42, 600)[:2]
        cap_rect = (60, H - 60 - 52 * (len(txt_lines) + 1) - 10, 700, H - 50)
        base_long, rot, cx, cy = {"tall": (1080, -8, 0.72, 0.62), "wide": (820, -6, 0.62, 0.66), "square": (900, -6, 0.64, 0.64)}[product.shape]
        ir, pos, c = _place_checked(bg, product, base_long, rot, cx, cy, [cap_rect, LOGO_RECT], nmask,
                                    CHECKS["word_visible_min"]["hero_number"], CHECKS["product_inside_min"]["hero_number"])
        checks.update(c)
        put(bg, nl, npos)
        shadow(bg, ir, pos, 36, 56, 6, 34, 0.4)
        put(bg, ir, pos)
        f2 = ImageFont.truetype(light, 42)
        d2 = ImageDraw.Draw(bg)
        y2 = H - 60 - 52 * (len(txt_lines) + 1)
        for tl in txt_lines + [caption]:
            draw_text(d2, (64, y2), tl, f2, col)
            y2 += 52
    else:
        raise LayoutFailed("unknown route %s" % route)

    lg, dark_logo = logo_for(bg, brand, LOGO_RECT)
    put(bg, lg, (64, 56))
    out = grain(bg)
    luma = mean_luma(out)
    if luma < LIGHT_CAPS["min_mean_luma"]:
        raise LayoutFailed("post is too dark (mean luma %.0f)" % luma)
    checks["mean_luma"] = round(luma, 1)
    meta = {
        "sku": product.sku, "route": route, "backdrop_id": plan.backdrop_id, "seed": plan.seed,
        "idea_id": plan.idea["id"], "idea_line": line, "caption": caption,
        "standin_font": standin, "logo": "navy" if dark_logo else "white",
        "checks": checks,
        "confirm_before_posting": sorted(set(plan.idea.get("requires") or []) | ({"in_stock"} if product.in_stock else set())),
    }
    return out, meta


def _kicker_and_caption(bg, kicker, cap_lines, light, path, size, colour, H):
    d = ImageDraw.Draw(bg)
    if kicker:
        f = ImageFont.truetype(path, 40)
        b = d.textbbox((0, 0), kicker, font=f)
        w, h = b[2] + 56, b[3] + 34
        d.rounded_rectangle([64, 170, 64 + w, 170 + h], radius=h // 2, fill=TEAL + (255,))
        d.text((92, 182), kicker, font=f, fill=NAVY + (255,))
    f = ImageFont.truetype(light, size)
    y = H - 120 - 48 * (len(cap_lines) - 1)
    for l in cap_lines:
        draw_text(d, (64, y), l, f, colour)
        y += 48


def render_post(product: Product, ideas: List[dict], backdrops: List[dict], memory: RouteMemory,
                seed: int, brand: str, backdrops_dir: Path, facts: Optional[set] = None) -> Tuple[Image.Image, dict]:
    """Choose a plan and render it; if the layout check fails, fall through to the other routes."""
    plan = choose(product, ideas, backdrops, memory, seed, facts)
    tried = []
    order = [plan.route] + [r for r in eligible_routes(product) if r != plan.route]
    rng = random.Random(seed + 1)
    for r in order:
        base_id = plan.backdrop_id if r == plan.route else pick_backdrop(r, backdrops, memory, rng)
        pool = [b["id"] for b in backdrops if b["tone"] in ROUTE_TONES[r] and b["id"] != base_id]
        rng.shuffle(pool)
        for bid in [base_id] + pool[:3]:  # a backdrop that is too dark gets swapped, not fatal
            try:
                use = Plan(plan.idea, r, bid, seed)
                img, meta = render_route(r, product, use, brand, backdrops_dir)
                meta["tried_first"] = tried
                memory.add(use, product.sku)
                return img, meta
            except LayoutFailed as e:
                tried.append({"route": r, "backdrop": bid, "why": str(e)})
    raise LayoutFailed("no route passed the layout check for %s: %s" % (product.sku, tried))
