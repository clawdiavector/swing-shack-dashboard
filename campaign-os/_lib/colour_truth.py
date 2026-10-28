"""Check an AI product image's colour against the maker's official listing (Christelle, 2026-10-28).

The target colour comes from the maker's own product page for the exact colourway
(Shopify `<page>.json`: colour option + front image), measured as a hex. Our shoot
photos are not the target: shop light tints them (Stick's blue-grey wall reads b -10).

Pillow only. Lab is CIE L*a*b* (D65); differences are CIEDE2000. The verdict is on hue and
chroma (lightness set equal): PASS up to 5, CHECK up to 10, FAIL above; a lightness gap over 20
turns a PASS into CHECK. Starting thresholds, tune on real batches.
"""

from __future__ import annotations

import io
import json
import math
import statistics
import urllib.request
from datetime import date
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from PIL import Image

PASS_MAX = 5.0
CHECK_MAX = 10.0
LIGHT_MAX = 20.0  # lightness gap (L*) that light alone can explain
_WHITE = (95.047, 100.0, 108.883)
_MAX_SAMPLES = 60_000


# --- colour maths --------------------------------------------------------

def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c: float) -> float:
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return min(1.0, max(0.0, c))


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_lin(v / 255) for v in rgb)
    xyz = (
        (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) * 100,
        (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) * 100,
        (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) * 100,
    )
    f = [t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116 for t in (v / w for v, w in zip(xyz, _WHITE))]
    L, a, b_ = 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])
    return (round(L, 4) + 0.0, round(a, 4) + 0.0, round(b_, 4) + 0.0)


def lab_to_rgb(lab: tuple[float, float, float]) -> tuple[int, int, int]:
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def inv(t: float) -> float:
        return t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)

    x, y, z = (inv(t) * w / 100 for t, w in zip((fx, fy, fz), _WHITE))
    rgb = (
        3.2404542 * x - 1.5371385 * y - 0.4985314 * z,
        -0.9692660 * x + 1.8760108 * y + 0.0415560 * z,
        0.0556434 * x - 0.2040259 * y + 1.0572252 * z,
    )
    return tuple(round(_gamma(v) * 255) for v in rgb)  # type: ignore[return-value]


def hex_to_lab(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return rgb_to_lab((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))


def lab_to_hex(lab: tuple[float, float, float]) -> str:
    return "#%02x%02x%02x" % lab_to_rgb(lab)


def delta_e2000(lab1: tuple[float, float, float], lab2: tuple[float, float, float], kL: float = 1.0) -> float:
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar ** 7 / (c_bar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))
    Lbp, Cbp = (L1 + L2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
    sc = 1 + 0.045 * Cbp
    sh = 1 + 0.015 * Cbp * t
    rt = (-2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
          * math.sin(math.radians(60 * math.exp(-(((hbp - 275) / 25) ** 2)))))
    return math.sqrt((dLp / (kL * sl)) ** 2 + (dCp / sc) ** 2 + (dHp / sh) ** 2 + rt * (dCp / sc) * (dHp / sh))


def verdict(delta_e: float) -> str:
    if delta_e <= PASS_MAX:
        return "PASS"
    return "CHECK" if delta_e <= CHECK_MAX else "FAIL"


# --- measuring an image --------------------------------------------------

def _median_lab(pixels: list[tuple[int, int, int]]) -> dict:
    if not pixels:
        raise ValueError("no pixels to measure")
    step = max(1, len(pixels) // _MAX_SAMPLES)
    labs = [rgb_to_lab(p) for p in pixels[::step]]
    lab = tuple(round(statistics.median(c), 2) for c in zip(*labs))
    return {"hex": lab_to_hex(lab), "lab": list(lab), "n": len(labs)}


def measure_box(img: Image.Image, box: tuple[int, int, int, int]) -> dict:
    """Median colour inside a box. Put the box on evenly lit fabric, away from seams and highlights."""
    crop = img.convert("RGB").crop(box)
    px = crop.load()
    return _median_lab([px[x, y] for y in range(crop.height) for x in range(crop.width)])


def measure_on_plain_background(img: Image.Image, bg_tolerance: float = 12.0, inset: float = 0.15) -> dict:
    """Official listing shots sit on a plain background: drop pixels close to the border colour,
    keep the inner part of what's left (away from the product's edges), take the median."""
    im = img.convert("RGB")
    im.thumbnail((600, 600))
    w, h = im.size
    px = im.load()
    border = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)] + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    bg = tuple(statistics.median(c) for c in zip(*(rgb_to_lab(p) for p in border[:: max(1, len(border) // 400)])))

    def is_product(p: tuple[int, int, int]) -> bool:
        L, a, b = rgb_to_lab(p)
        return math.dist((L, a, b), bg) > bg_tolerance

    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if is_product(px[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        raise ValueError("no product found against the background")
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    dx, dy = (x1 - x0) * inset, (y1 - y0) * inset
    inner = [px[x, y] for y in range(int(y0 + dy), int(y1 - dy) + 1) for x in range(int(x0 + dx), int(x1 - dx) + 1)
             if is_product(px[x, y])]
    return _median_lab(inner)


def compare(target_hex: str, measured_hex: str) -> dict:
    """Judge the fabric's colour (hue and chroma) apart from lighting: hard window light makes a
    black shirt dark grey without changing what it is. A lightness gap over LIGHT_MAX still needs a look."""
    t, m = hex_to_lab(target_hex), hex_to_lab(measured_hex)
    de = round(delta_e2000(t, m), 2)
    de_colour = round(delta_e2000(t, (t[0], m[1], m[2])), 2)
    dL = round(m[0] - t[0], 1)
    v = verdict(de_colour)
    if v == "PASS" and abs(dL) > LIGHT_MAX:
        v = "CHECK"
    return {"target": target_hex, "measured": measured_hex, "delta_e": de, "delta_e_colour": de_colour,
            "delta_L": dL, "verdict": v}


# --- the official listing (Shopify) ---------------------------------------

def product_json_url(page_url: str) -> str:
    s = urlsplit(page_url)
    path = s.path.rstrip("/")
    return urlunsplit((s.scheme, s.netloc, path if path.endswith(".json") else path + ".json", "", ""))


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (colour-truth)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def target_from_page(page_url: str, fetch: Callable[[str], bytes] = _fetch) -> dict:
    """Read one colourway's product page and measure its front image."""
    product = json.loads(fetch(product_json_url(page_url)))["product"]
    colours = [o for o in product.get("options", []) if str(o.get("name", "")).lower() in ("color", "colour")]
    if not colours or len(colours[0].get("values", [])) != 1:
        raise ValueError(f"{page_url}: not one exact colourway (colour option missing or several colours)")
    images = sorted(product.get("images", []), key=lambda i: i.get("position", 99))
    if not images:
        raise ValueError(f"{page_url}: no images")
    image_url = images[0]["src"]
    m = measure_on_plain_background(Image.open(io.BytesIO(fetch(image_url))))
    return {"page_url": page_url, "title": product.get("title", ""), "colour_name": colours[0]["values"][0],
            "image_url": image_url, "hex": m["hex"], "lab": m["lab"], "measured_on": date.today().isoformat()}
