"""
image_dissector.py — Visual DNA Engine for Campaign OS brand directories.

Given an image (local path), extract structured visual intelligence:
- Layer 1: Basic metadata (path, name, size, dimensions, format)
- Layer 6: OCR text recognition (tesseract)
- Layer 7: Typography detection (font, weight, size, colour from OCR results)
- Layer 8: Brand Bible Compliance (score against canonical brand-bible.json)
- Layer 9: Colour palette extraction (dominant + brand-match %)
- Layer 10: Composition analysis (rule-of-thirds, safe zones, balance)
- Layer 17: Visual Recipe schema (how the image was made, where reusable)

Outputs:
- Per-image .visual-dna.json alongside the source file
- Cross-image index at data/brand-directory/{brand}/visual-dna-index.json

Uses:
- Pillow (already in venv)
- pytesseract (TBD — installs with `pip install pytesseract`; brew install tesseract)
- colour quantization via Pillow's quantize + median cut
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat, ImageFilter

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


def hex_from_rgb(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{c:02x}" for c in rgb)


def parse_hex(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))


def color_distance(a: tuple, b: tuple) -> float:
    """Euclidean distance in RGB. Cheap, good enough for brand-match."""
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: Basic metadata
# ─────────────────────────────────────────────────────────────────────────────

def layer1_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with Image.open(path) as im:
        w, h = im.size
        fmt = im.format
        mode = im.mode
        exif = {}
        try:
            raw = im.getexif()
            for k, v in raw.items():
                if isinstance(v, (str, int, float)):
                    exif[str(k)] = v
        except Exception:
            pass
    return {
        "filename": path.name,
        "format": fmt,
        "mode": mode,
        "width_px": w,
        "height_px": h,
        "aspect_ratio": round(w / h, 4) if h else None,
        "orientation": "landscape" if w > h else ("portrait" if w < h else "square"),
        "file_size_bytes": stat.st_size,
        "modified": stat.st_mtime,
        "exif": exif,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Layer 9: Colour palette extraction
# ─────────────────────────────────────────────────────────────────────────────

def layer9_palette(im: Image.Image, n_colors: int = 8) -> dict[str, Any]:
    """Extract dominant colours via median-cut quantization."""
    rgb = im.convert("RGB")
    small = rgb.resize((200, 200))
    quant = small.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
    palette = quant.getpalette()
    counts = Counter(quant.getdata())
    total = sum(counts.values())

    colors = []
    for idx, freq in counts.most_common(n_colors):
        r, g, b = palette[idx*3:idx*3+3]
        colors.append({
            "hex": hex_from_rgb((r, g, b)),
            "rgb": [r, g, b],
            "share": round(freq / total, 4),
        })

    # Quick stats
    stat = ImageStat.Stat(rgb)
    mean_brightness = sum(stat.mean) / 3

    return {
        "dominant_colors": colors,
        "mean_brightness": round(mean_brightness, 1),
        "luminance_category": (
            "dark" if mean_brightness < 60
            else "mid" if mean_brightness < 160
            else "light"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Layer 10: Composition analysis
# ─────────────────────────────────────────────────────────────────────────────

def layer10_composition(im: Image.Image) -> dict[str, Any]:
    """Aspect, brightness gradient (top vs bottom), edge density map."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    grey = rgb.convert("L")

    # Top vs bottom brightness — gradient direction
    top_band = grey.crop((0, 0, w, h // 3))
    bot_band = grey.crop((0, 2 * h // 3, w, h))
    top_b = ImageStat.Stat(top_band).mean[0]
    bot_b = ImageStat.Stat(bot_band).mean[0]
    gradient = "top-to-bottom darkening" if top_b > bot_b else "top-to-bottom lightening"

    # Edge density in 3x3 grid (proxy for rule-of-thirds subject presence)
    edges = grey.filter(ImageFilter.FIND_EDGES)
    edge_grid = []
    for row in range(3):
        row_edges = []
        for col in range(3):
            cell = edges.crop((col * w // 3, row * h // 3, (col+1) * w // 3, (row+1) * h // 3))
            density = ImageStat.Stat(cell).mean[0]
            row_edges.append(round(density, 2))
        edge_grid.append(row_edges)

    # Find the cell with highest edge density — likely subject
    flat = [(r, c, edge_grid[r][c]) for r in range(3) for c in range(3)]
    subject_cell = max(flat, key=lambda x: x[2])
    thirds_positions = ["top-left", "top", "top-right",
                        "left", "centre", "right",
                        "bottom-left", "bottom", "bottom-right"]
    subject_position = thirds_positions[subject_cell[0]*3 + subject_cell[1]]

    return {
        "aspect_ratio": round(w / h, 3),
        "gradient": gradient,
        "brightness_top": round(top_b, 1),
        "brightness_bottom": round(bot_b, 1),
        "edge_density_grid": edge_grid,
        "subject_estimate_position": subject_position,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Layer 6 + 7: OCR + Typography
# ─────────────────────────────────────────────────────────────────────────────

def layer6_ocr(im: Image.Image) -> dict[str, Any]:
    """OCR via tesseract. Returns text blocks with bounding boxes + confidence."""
    if not HAS_TESSERACT:
        return {"available": False, "text": "", "blocks": []}
    try:
        # Get word-level data for typography
        data = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT)
        blocks = []
        for i in range(len(data["text"])):
            txt = data["text"][i].strip()
            if not txt:
                continue
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1
            blocks.append({
                "text": txt,
                "conf": conf,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
                "block": data["block_num"][i],
                "line": data["line_num"][i],
            })
        full_text = " ".join(b["text"] for b in blocks)
        return {
            "available": True,
            "text": full_text,
            "word_count": len(blocks),
            "blocks": blocks,
        }
    except Exception as e:
        return {"available": False, "error": str(e), "text": "", "blocks": []}


def layer7_typography(ocr_data: dict, im: Image.Image) -> dict[str, Any]:
    """Estimate typography from OCR blocks: detected caps, dominant size, colours."""
    if not ocr_data.get("available") or not ocr_data["blocks"]:
        return {"detected": False}

    # Most blocks per line give a rough "body" size; tallest block is likely heading
    # Filter out very-low-confidence blocks (often logo glyphs misread as text)
    blocks = [b for b in ocr_data["blocks"] if b.get("conf", -1) >= 50]
    heights = [b["height"] for b in blocks if b["height"] > 0]
    if not heights:
        return {"detected": False}

    median_h = sorted(heights)[len(heights) // 2]
    max_h = max(heights)
    largest_blocks = [b for b in blocks if b["height"] >= max_h * 0.8]

    # Check all-caps — strip non-alphabetic, then check the rest is upper
    def _is_caps(t: str) -> bool:
        cleaned = "".join(c for c in t if c.isalpha())
        # If block has no letters at all (logo glyphs etc.), don't count it as failing
        return not cleaned or cleaned.isupper()

    is_all_caps = all(_is_caps(b["text"]) for b in largest_blocks if b["text"])

    # Sample pixel colour at each text bounding box (mid-pixel)
    rgb = im.convert("RGB")
    text_colors = []
    for b in largest_blocks[:5]:
        cx = b["left"] + b["width"] // 2
        cy = b["top"] + b["height"] // 2
        if 0 <= cx < rgb.width and 0 <= cy < rgb.height:
            text_colors.append(rgb.getpixel((cx, cy)))

    text_colour_hex = hex_from_rgb(text_colors[0]) if text_colors else None

    return {
        "detected": True,
        "max_text_height_px": max_h,
        "median_text_height_px": median_h,
        "likely_heading_text": " ".join(b["text"] for b in largest_blocks[:3]),
        "is_all_caps": is_all_caps,
        "sample_text_colour": text_colour_hex,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Layer 8: Brand Bible Compliance
# ─────────────────────────────────────────────────────────────────────────────

def layer8_compliance(palette: dict, ocr_data: dict, typo: dict, bible: dict) -> dict[str, Any]:
    """Score image against brand bible."""
    weights = bible.get("compliance_score", {}).get("weights", {})
    threshold = bible.get("compliance_score", {}).get("passing_threshold", 0.70)

    dark = {parse_hex(c) for c in bible["colors"]["dark"]}
    accent = {parse_hex(c) for c in bible["colors"]["accent"]}
    light = {parse_hex(c) for c in bible["colors"]["light"]}
    all_brand = dark | accent | light

    dominant = palette["dominant_colors"][0]
    dom_rgb = tuple(dominant["rgb"])

    # Background test: dominant colour is one of the two darks, or image has high luminance_category==dark
    luminance = palette.get("luminance_category", "mid")
    bg_is_dark = (
        any(color_distance(dom_rgb, d) < 60 for d in dark)
        or luminance == "dark"
    )

    # Accent presence — check top 8 dominants AND the sampled text-block colours
    accent_dominants = [
        c for c in palette["dominant_colors"]
        if any(color_distance(tuple(c["rgb"]), a) < 80 for a in accent)
    ]
    accent_in_text = (
        typo.get("sample_text_colour")
        and any(
            color_distance(parse_hex(typo["sample_text_colour"]), a) < 80
            for a in accent
        )
    )
    accent_present = bool(accent_dominants) or accent_in_text

    # White text presence — same logic
    white_in_text = (
        typo.get("sample_text_colour")
        and any(
            color_distance(parse_hex(typo["sample_text_colour"]), w) < 40
            for w in light
        )
    )
    white_present = any(
        any(color_distance(tuple(c["rgb"]), w) < 40 for w in light)
        for c in palette["dominant_colors"]
    ) or white_in_text

    # ALL CAPS headings (from typography)
    all_caps_ok = bool(typo.get("is_all_caps")) if typo.get("detected") else None

    # Font: we can't visually detect Avenir Next without a font-matching CV model.
    # Mark as "unverified" and assign partial credit if heading is detected.
    font_heavy_italic = None  # needs CV
    body_italic = None         # needs CV

    # Off-brand colours — any dominant colour far from all brand colours
    off_brand = []
    for c in palette["dominant_colors"]:
        c_rgb = tuple(c["rgb"])
        if all(color_distance(c_rgb, b) > 120 for b in all_brand):
            off_brand.append(c["hex"])

    score = 0.0
    score_max = 0.0

    # Background dark
    if "background_is_dark_or_dark_over_image" in weights:
        w = weights["background_is_dark_or_dark_over_image"]
        score += w if bg_is_dark else 0
        score_max += w

    # Accent present
    if "accent_colour_present_where_needed" in weights:
        w = weights["accent_colour_present_where_needed"]
        score += w if accent_present else 0
        score_max += w

    # White text/border
    if "white_border_or_white_text_present" in weights:
        w = weights["white_border_or_white_text_present"]
        score += w if white_present else 0
        score_max += w

    # ALL CAPS headings
    if "headings_all_caps" in weights and all_caps_ok is not None:
        w = weights["headings_all_caps"]
        score += w if all_caps_ok else 0
        score_max += w

    # Font — partial credit if we have any typography
    if "headings_font_avenir_next_heavy_italic" in weights:
        w = weights["headings_font_avenir_next_heavy_italic"]
        if font_heavy_italic is None:
            score += w * 0.5  # unverified — half credit
        else:
            score += w if font_heavy_italic else 0
        score_max += w

    if "body_font_avenir_next_italic" in weights:
        w = weights["body_font_avenir_next_italic"]
        if body_italic is None:
            score += w * 0.5
        else:
            score += w if body_italic else 0
        score_max += w

    # Off-brand
    if "no_off_brand_background_colours" in weights:
        w = weights["no_off_brand_background_colours"]
        score += w if not off_brand else 0
        score_max += w

    final = round(score / score_max, 4) if score_max else 0

    return {
        "score": final,
        "passes": final >= threshold,
        "threshold": threshold,
        "checks": {
            "background_dark": bg_is_dark,
            "accent_present": accent_present,
            "white_text_or_border_present": white_present,
            "headings_all_caps": all_caps_ok,
            "headings_font_avenir_next_heavy_italic": font_heavy_italic,
            "body_font_avenir_next_italic": body_italic,
            "no_off_brand_dominant_colours": not off_brand,
        },
        "off_brand_dominants": off_brand,
        "notes": "Font detection requires CV model — currently assigned partial credit. Heading ALL CAPS is detected via OCR + case check.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Layer 17: Visual Recipe (schema)
# ─────────────────────────────────────────────────────────────────────────────

def layer17_recipe(meta: dict, palette: dict, comp: dict, ocr: dict, typo: dict, bible: dict) -> dict[str, Any]:
    """Produce a 'how it was made' recipe. Some fields inferred, some manual."""
    dominant = palette["dominant_colors"][0]["hex"] if palette["dominant_colors"] else None
    return {
        "schema_version": "0.1",
        "auto_extracted": {
            "background_type": (
                "dark_background" if palette.get("luminance_category") == "dark"
                else "image_with_dark_overlay" if comp.get("brightness_top", 200) > 120
                else "unknown"
            ),
            "background_colour_dominant": dominant,
            "gradient_direction": comp.get("gradient"),
            "primary_subject_position": comp.get("subject_estimate_position"),
            "ocr_text": ocr.get("text", "")[:500],
            "all_caps_detected": typo.get("is_all_caps"),
        },
        "manual_fields_required": [
            "headline",
            "body_copy",
            "cta",
            "fonts_used (visual inspection needed)",
            "designer",
            "photographer",
            "campaign_id",
            "asset_class",
            "date_used",
            "platforms_used",
            "performance_metrics",
        ],
        "reusability": {
            "background_reusable": True if palette.get("luminance_category") == "dark" else None,
            "subject_cutout_possible": None,  # needs subject detection
            "hero_club_extractable": None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def dissect(image_path: Path, bible_path: Path | None = None) -> dict[str, Any]:
    """Run full visual DNA extraction. Returns dict ready to JSON-serialize."""
    if not image_path.exists():
        return {"error": "not_found", "path": str(image_path)}

    bible = None
    if bible_path and bible_path.exists():
        bible = json.loads(bible_path.read_text())

    result: dict[str, Any] = {
        "schema_version": "0.1",
        "image_path": str(image_path),
    }

    try:
        # Layer 1: metadata
        meta = layer1_metadata(image_path)
        result["layer1_metadata"] = meta

        with Image.open(image_path) as im:
            # Layer 9: palette
            palette = layer9_palette(im)
            result["layer9_palette"] = palette

            # Layer 10: composition
            comp = layer10_composition(im)
            result["layer10_composition"] = comp

            # Layer 6: OCR
            ocr = layer6_ocr(im)
            result["layer6_ocr"] = {
                "available": ocr["available"],
                "word_count": ocr.get("word_count", 0),
                "text_preview": ocr.get("text", "")[:300],
            }

            # Layer 7: typography
            typo = layer7_typography(ocr, im)
            result["layer7_typography"] = typo

            # Layer 8: compliance (only if bible present)
            if bible:
                compliance = layer8_compliance(palette, ocr, typo, bible)
                result["layer8_compliance"] = compliance

            # Layer 17: recipe
            recipe = layer17_recipe(meta, palette, comp, ocr, typo, bible or {})
            result["layer17_recipe"] = recipe

    except Exception as e:
        result["error"] = str(e)

    return result


def dissect_directory(images_dir: Path, bible_path: Path | None = None) -> dict[str, Any]:
    """Run dissector over every JPEG in a directory. Returns index + per-file records."""
    files = sorted([p for p in images_dir.glob("*") if p.suffix.lower() in ('.jpg', '.jpeg', '.png')])
    index = {
        "schema_version": "0.1",
        "directory": str(images_dir),
        "image_count": len(files),
        "framing": "Scores are style alignment, not quality grades. Every image is approved, in-use brand material. Higher scores = closer to brand canon; lower scores = variation / vendor presence / product shots. Use all 122 as reference; lean on top-scorers as Visual Recipe templates.",
        "by_filename": {},
        "by_alignment": {"high": [], "typical": [], "variants": []},
        "by_dominant_color": {},
        "by_luminance": {"dark": 0, "mid": 0, "light": 0},
        "errors": [],
    }

    for f in files:
        try:
            dna = dissect(f, bible_path)
            out_file = f.with_suffix(".visual-dna.json")
            out_file.write_text(json.dumps(dna, indent=2))
            index["by_filename"][f.name] = {
                "dna_path": str(out_file),
                "score": dna.get("layer8_compliance", {}).get("score"),
                "passes": dna.get("layer8_compliance", {}).get("passes"),
                "luminance": dna.get("layer9_palette", {}).get("luminance_category"),
                "dominant": dna.get("layer9_palette", {}).get("dominant_colors", [{}])[0].get("hex"),
            }
            if dna.get("layer8_compliance"):
                score = dna["layer8_compliance"]["score"]
                if score >= 0.70:
                    index["by_alignment"]["high"].append(f.name)
                elif score >= 0.60:
                    index["by_alignment"]["typical"].append(f.name)
                else:
                    index["by_alignment"]["variants"].append(f.name)
            else:
                index["by_alignment"]["typical"].append(f.name)

            lum = dna.get("layer9_palette", {}).get("luminance_category")
            if lum in index["by_luminance"]:
                index["by_luminance"][lum] += 1

            dom = index["by_filename"][f.name]["dominant"]
            if dom:
                index["by_dominant_color"][dom] = index["by_dominant_color"].get(dom, 0) + 1
        except Exception as e:
            index["errors"].append({"file": f.name, "error": str(e)})

    return index


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: image_dissector.py <image_or_directory> [bible.json]")
        sys.exit(1)

    target = Path(sys.argv[1])
    bible = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if target.is_dir():
        index = dissect_directory(target, bible)
        out = target.parent / "visual-dna-index.json"
        out.write_text(json.dumps(index, indent=2))
        print(f"Indexed {index['image_count']} images → {out}")
    else:
        dna = dissect(target, bible)
        out = target.with_suffix(".visual-dna.json")
        out.write_text(json.dumps(dna, indent=2))
        print(f"Wrote {out}")
