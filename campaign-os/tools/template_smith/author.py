#!/usr/bin/env python3
"""Turn measured.json into an archetype spec consumable by ``compose_to_canvas``.

Font sizes are solved from measured ink heights using the brand's vendored
fonts; tracking from measured line widths; origins from glyph bearings; zone
heights are pinned so the compose size-fit search lands on the measured size.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN = ROOT / "campaign-os"
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image  # noqa: E402

from _lib.brand_overlay import _load_brand_font  # noqa: E402

FRAME = ROOT / "data/brand-directory/stick/templates/service-frame"
BRAND = "stick"
W, H = 1080, 1350
LOGO_ASSET = "templates/service-frame/assets/logo-wordmark-white.png"
TAGLINE_ASSET = "templates/service-frame/assets/tagline-better-begins-here.png"


def _font(role: str, size: int):
    f = _load_brand_font(BRAND, role, size)
    if f is None:
        raise SystemExit(f"font role {role} unresolved")
    return f


def _ink_h(role: str, size: int, text: str) -> int:
    bb = _font(role, size).getbbox(text, anchor="ls")
    return bb[3] - bb[1]


def _solve_size(role: str, text: str, ink_h: float, lo: int = 12, hi: int = 200) -> int:
    best, err = lo, 1e9
    for s in range(lo, hi + 1):
        e = abs(_ink_h(role, s, text) - ink_h)
        if e < err:
            best, err = s, e
    return best


def _cap(font) -> int:
    bb = font.getbbox("H")
    return max(1, bb[3] - bb[1])


def _words_width(words: list[str], body, emph, emphasis: set[str], track: float) -> float:
    total = 0.0
    for i, wd in enumerate(words):
        f = emph if (emph and wd.upper() in emphasis) else body
        total += f.getlength(wd) + (track * (len(wd) - 1) if len(wd) > 1 else 0.0)
        if i < len(words) - 1:
            total += body.getlength(" ")
    return total


def _asset_rect(asset_rel: str, ink: dict, *, align: str) -> dict:
    """Rect for aspect_fit/bottom-aligned asset so its alpha ink lands on ``ink``."""
    img = Image.open(ROOT / "data/brand-directory" / BRAND / asset_rel).convert("RGBA")
    ax0, ay0, ax1, ay1 = img.getchannel("A").getbbox()
    s = (ink["x1"] - ink["x0"]) / (ax1 - ax0)
    tw, th = img.width * s, img.height * s
    left = ink["x0"] - ax0 * s
    bottom = ink["y1"] + (img.height - ay1) * s
    return {
        "x0": round(left / W, 4),
        "y0": round((bottom - th) / H, 4),
        "x1": round((left + tw) / W, 4),
        "y1": round(bottom / H, 4),
    }


def author(measured: dict, headline: list[str], cta: list[str], emphasis_word: str) -> dict:
    m = measured["primary"]
    band = m["teal_band"]

    # --- headline (display role, uppercase)
    hl = m["headline_lines"]
    sizes = [_solve_size("display", t, ln["y1"] - ln["y0"]) for t, ln in zip(headline, hl)]
    hs = round(sum(sizes) / len(sizes))
    hf = _font("display", hs)
    tops = [ln["y0"] - hf.getbbox(t, anchor="ls")[1] for t, ln in zip(headline, hl)]  # baselines
    pitch = (tops[-1] - tops[0]) / max(1, len(tops) - 1)
    h_lh = (pitch + 0.5) / hs
    h_cap = _cap(hf)
    h_y0 = tops[0] - h_cap
    h_origin = min(ln["x0"] - hf.getbbox(t, anchor="ls")[0] for t, ln in zip(headline, hl))
    h_block = (len(headline) - 1) * int(hs * h_lh) + h_cap
    h_widest = max(ln["x1"] for ln in hl)
    # zone must fit widest line but not the next word appended to line 1
    h_x1 = min(W - 1, h_widest + 30)

    # --- CTA (h2 light + cta_emphasis on the dense word)
    cl = m["cta_lines"]
    csizes = [_solve_size("h2", t, ln["y1"] - ln["y0"]) for t, ln in zip(cta, cl)]
    cs = round(sum(csizes) / len(csizes))
    body, emph = _font("h2", cs), _font("cta_emphasis", cs)
    emphasis = {emphasis_word.upper()}
    # tracking from the non-emphasis line (all-body glyphs)
    plain_i = next(i for i, t in enumerate(cta) if emphasis_word.upper() not in t.split())
    pw = cl[plain_i]["x1"] - cl[plain_i]["x0"]
    words = cta[plain_i].split()
    nat = _words_width(words, body, None, set(), 0.0)
    ntrack = sum(len(wd) - 1 for wd in words)
    track_px = (pw - nat) / max(1, ntrack)
    tracking_em = round(track_px / cs, 4)
    c_bl = [ln["y0"] - body.getbbox(t, anchor="ls")[1] for t, ln in zip(cta, cl)]
    c_pitch = (c_bl[-1] - c_bl[0]) / max(1, len(c_bl) - 1)
    c_lh = (c_pitch + 0.5) / cs
    c_cap = _cap(body)
    c_y0 = c_bl[0] - c_cap
    c_origin = min(ln["x0"] - body.getbbox(t, anchor="ls")[0] for t, ln in zip(cta, cl))
    c_block = (len(cta) - 1) * int(cs * c_lh) + c_cap
    c_widest = max(ln["x1"] for ln in cl)
    c_wrap_x1 = min(band["x1"] - 1, c_widest + 20)

    # footer
    ft = m["footer"]

    bg = m["background"]
    spec = {
        "id": "stick-service-frame-agent",
        "name": "Service frame (agent-authored, Track B)",
        "description": "Pixel-measured from references/ref-01.jpg by template_smith; see agent/template.md.",
        "canvas": "ig_post",
        "block_anchor": "center",
        "applies_to": {
            "channels": ["instagram", "instagram_story", "facebook", "gbp"],
            "record_types": ["moment", "evergreen"],
            "needs_photo": False,
        },
        "background": {
            "kind": "gradient",
            "gradient": {"direction": bg["direction"], "from": bg["from"], "to": bg["to"]},
        },
        "zones": {
            "headline": {
                "rect": {
                    "x0": round(h_origin / W, 4),
                    "y0": round(h_y0 / H, 4),
                    "x1": round(h_x1 / W, 4),
                    "y1": round((h_y0 + h_block + 1) / H, 4),
                },
                "kind": "text",
                "source": "caption_hook",
                "font_role": "display",
                "max_lines": len(headline),
                "max_chars_per_line": 24,
                "line_height": round(h_lh, 4),
                "text_transform": "uppercase",
                "text_origin_x": round(h_origin),
                "align": "left",
                "valign": "top",
                "colour": "white",
                "min_font_px": max(12, hs - 40),
            },
            "cta_band": {
                "rect": {
                    "x0": round(band["x0"] / W, 4),
                    "y0": round(band["y0"] / H, 4),
                    "x1": round(band["x1"] / W, 4),
                    "y1": round(band["y1"] / H, 4),
                },
                "kind": "band",
                "fill": band["colour"],
            },
            "cta": {
                "rect": {
                    "x0": round(c_origin / W, 4),
                    "y0": round(c_y0 / H, 4),
                    "x1": round(c_wrap_x1 / W, 4),
                    "y1": round((c_y0 + c_block + 1) / H, 4),
                },
                "kind": "text",
                "source": "cta",
                "font_role": "h2",
                "max_lines": len(cta),
                "max_chars_per_line": 24,
                "line_height": round(c_lh, 4),
                "text_transform": "uppercase",
                "emphasis_words": [emphasis_word.upper()],
                "emphasis_font_role": "cta_emphasis",
                "tracking_em": tracking_em,
                "text_origin_x": round(c_origin),
                "align": "left",
                "colour": "white",
                "min_font_px": max(12, cs - 30),
            },
            "logo": {
                "rect": _asset_rect(LOGO_ASSET, ft["logo"], align="left"),
                "kind": "image",
                "source": "asset",
                "asset": LOGO_ASSET,
                "fit": "aspect_fit",
                "align": "left",
                "valign": "bottom",
            },
            "tagline": {
                "rect": _asset_rect(TAGLINE_ASSET, ft["tagline"], align="right"),
                "kind": "image",
                "source": "asset",
                "asset": TAGLINE_ASSET,
                "fit": "aspect_fit",
                "align": "left",
                "valign": "bottom",
                "optional": True,
            },
        },
        "safe_zone": {"x0": 0.05, "y0": 0.04, "x1": 0.95, "y1": 0.96},
        "max_total_chars": 110,
        "_derivation": {
            "measured": "agent/measured.json",
            "headline_font_px": hs,
            "headline_sizes_per_line": sizes,
            "headline_pitch_px": round(pitch, 2),
            "cta_font_px": cs,
            "cta_sizes_per_line": csizes,
            "cta_pitch_px": round(c_pitch, 2),
            "cta_tracking_px": round(track_px, 3),
        },
    }
    return spec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--measured", type=Path, default=FRAME / "agent/measured.json")
    ap.add_argument("--out", type=Path, default=FRAME / "agent/spec.json")
    ap.add_argument("--headline", default="CONSISTENCY|STARTS WITH|DATA", help="reference headline lines, | separated")
    ap.add_argument("--cta", default="BOOK YOUR FREE|SWING ASSESSMENT", help="reference CTA lines, | separated")
    ap.add_argument("--emphasis", default="FREE")
    args = ap.parse_args()
    measured = json.loads(args.measured.read_text(encoding="utf-8"))
    spec = author(measured, args.headline.split("|"), args.cta.split("|"), args.emphasis)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(spec["_derivation"], indent=2))
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
