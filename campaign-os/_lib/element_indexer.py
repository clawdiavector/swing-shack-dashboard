"""
element_indexer.py — Element-level indexing for element discovery.

For each image's DNA, extract normalized searchable elements:
- colors: named colors per image (yellow, blue, white, etc.)
- brands: detected brand names
- text: any OCR'd strings (searchable)
- objects: product/person/scene classification
- composition: centered/rule-of-thirds/close-up/wide
- mood: energetic/calm/luxurious/playful
- quality: 1-100 score (combines compliance + sharpness proxy)

Outputs:
- Flat element index at data/brand-directory/_system/element-index.json
- Per-image enriched DNA saved back as .visual-dna.json (additive)

Design: heuristic-based, no heavy ML deps. Fast enough to re-index 1000s of images.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

# ============================================================================
# COLOR NAMING — convert RGB/hex to human color names
# ============================================================================

# Color categories with HSV-ish boundaries (rough but fast)
COLOR_RULES = [
    # (name, [hue ranges in degrees], sat threshold, val threshold)
    ("red",       [(0, 15), (345, 360)], 0.30, 0.30),
    ("orange",    [(15, 45)],             0.30, 0.30),
    ("yellow",    [(45, 70)],             0.30, 0.30),
    ("green",     [(70, 165)],            0.25, 0.25),
    ("teal",      [(165, 200)],           0.25, 0.25),
    ("blue",      [(200, 250)],           0.25, 0.25),
    ("purple",    [(250, 290)],           0.25, 0.25),
    ("pink",      [(290, 345)],           0.20, 0.30),
    ("brown",     [(15, 45)],             0.30, 0.10),  # low val
    ("black",     [(0, 360)],             0.0,  0.0),    # always possible
    ("white",     [(0, 360)],             0.0,  0.0),
    ("gray",      [(0, 360)],             0.0,  0.0),
    ("gold",      [(40, 55)],             0.40, 0.50),
    ("silver",    [(0, 360)],             0.0,  0.0),
]

# Brand golf color palette mapping
BRAND_COLORS = {
    "swing-shack": {"primary": "blue", "secondary": "white", "accent": "gold"},
    "stick": {"primary": "green", "secondary": "white", "accent": "black"},
    "bag-drop": {"primary": "black", "secondary": "gray", "accent": "white"},
    "takomo": {"primary": "blue", "secondary": "white", "accent": "red"},
}


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB (0-255) to HSV (h: 0-360, s: 0-1, v: 0-1)."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx = max(r, g, b)
    mn = min(r, g, b)
    df = mx - mn
    if mx == mn:
        h = 0
    elif mx == r:
        h = (60 * ((g - b) / df) + 360) % 360
    elif mx == g:
        h = (60 * ((b - r) / df) + 120) % 360
    else:
        h = (60 * ((r - g) / df) + 240) % 360
    s = 0 if mx == 0 else df / mx
    v = mx
    return (h, s, v)


def name_color(hex_str: str) -> str:
    """Return human color name for a hex color string."""
    r, g, b = _hex_to_rgb(hex_str)
    h, s, v = _rgb_to_hsv(r, g, b)

    # Special: neutrals first (low saturation)
    if s < 0.10:
        if v < 0.15:
            return "black"
        if v > 0.92:
            return "white"
        return "gray"

    # Saturation/value-based classification
    for name, hue_ranges, sat_min, val_min in COLOR_RULES:
        if name in ("black", "white", "gray"):
            continue  # handled above
        if s < sat_min or v < val_min:
            continue
        for h_min, h_max in hue_ranges:
            if h_min <= h < h_max:
                # Special: gold is bright yellow with high sat
                if name == "yellow" and s > 0.5 and v > 0.6:
                    return "gold"
                return name
    return "other"


def extract_colors_from_dna(dna: dict) -> list[str]:
    """Extract named colors from layer9_palette.dominant_colors."""
    palette = dna.get("layer9_palette", {})
    dom = palette.get("dominant_colors", [])
    colors = []
    for c in dom[:8]:
        hex_str = c.get("hex", "")
        if hex_str:
            name = name_color(hex_str)
            if name and name not in colors:
                colors.append(name)
    return colors


# ============================================================================
# BRAND DETECTION — extract brand names from OCR + detected_brands
# ============================================================================

# Brand dictionary for golf brands + SS-specific SKUs
BRAND_DICTIONARY = [
    "Callaway", "Callaway Quantum", "TaylorMade", "Titleist", "Ping", "PING",
    "Mizuno", "Cobra", "Wilson", "Cleveland", "Bridgestone", "Srixon",
    "FootJoy", "Scotty Cameron", "Odyssey", "PXG",
    "TrackMan", "Trackman",
    "Jordan", "Vessel", "Vice",
    "Mileseey", "Bushnell", "Garmin",
    "Takomo", "Takomo 101",
    "Zen Swing Stage", "Zen Swing",
    "GTS Putter",
    "Pro V1", "Pro V1x",
    "Chrome Soft", "TP5", "TP5x",
]


def extract_brands_from_dna(dna: dict) -> list[str]:
    """Extract brand names from layer4_products + layer6_ocr text."""
    brands = []

    # From detected_brands (layer4)
    l4 = dna.get("layer4_products", {}) or {}
    detected = l4.get("detected_brands") or []
    if isinstance(detected, list):
        for b in detected:
            if isinstance(b, str) and b.strip():
                brands.append(b.strip())
            elif isinstance(b, dict):
                name = b.get("name") or b.get("label") or b.get("brand")
                if name:
                    brands.append(str(name))

    # From OCR text (layer6)
    l6 = dna.get("layer6_ocr", {}) or {}
    text = ""
    if isinstance(l6, dict):
        lines = l6.get("lines") or []
        if lines:
            text = " ".join(lines)
        else:
            text = l6.get("text_preview", "") or ""
    text_lower = text.lower()

    for brand in BRAND_DICTIONARY:
        if brand.lower() in text_lower and brand not in brands:
            brands.append(brand)

    # From filename (often has brand clues)
    meta = dna.get("layer1_metadata", {}) or {}
    filename = meta.get("filename", "") or ""
    fn_lower = filename.lower()
    for brand in BRAND_DICTIONARY:
        if brand.lower().replace(" ", "") in fn_lower.replace(" ", "").replace("-", "").replace("_", ""):
            if brand not in brands:
                brands.append(brand)

    return brands


# ============================================================================
# OBJECT CLASSIFICATION — from products + composition + brightness
# ============================================================================

def _flatten_edge_grid(edge_grid) -> float:
    """Compute average from a (possibly nested) edge density grid."""
    if not isinstance(edge_grid, list):
        return 0
    flat = []
    for item in edge_grid:
        if isinstance(item, list):
            for sub in item:
                if isinstance(sub, (int, float)):
                    flat.append(float(sub))
        elif isinstance(item, (int, float)):
            flat.append(float(item))
    return sum(flat) / len(flat) if flat else 0


def classify_objects(dna: dict) -> list[str]:
    """Classify what's in the image: product, person, scenery, text-only, etc."""
    objects = []
    brands = extract_brands_from_dna(dna)
    l6 = dna.get("layer6_ocr", {}) or {}
    text = ""
    if isinstance(l6, dict):
        lines = l6.get("lines") or []
        if lines:
            text = " ".join(lines)
        else:
            text = l6.get("text_preview", "") or ""

    # Has detected product brand → product image
    if brands:
        objects.append("product")

    # OCR has text → text-overlay or text-heavy
    if text.strip() and len(text.strip()) > 5:
        objects.append("text-overlay")

    # Composition-based classification
    comp = dna.get("layer10_composition", {}) or {}
    palette = dna.get("layer9_palette", {}) or {}
    lum = palette.get("luminance_category", "")
    brightness = palette.get("mean_brightness", 0)
    gradient = comp.get("gradient", 0) or 0
    try:
        gradient = float(gradient)
    except (TypeError, ValueError):
        gradient = 0
    edge_grid = comp.get("edge_density_grid", [])
    avg_edge = _flatten_edge_grid(edge_grid)

    # High edge density + non-product = scenery or lifestyle
    if avg_edge > 50 and "product" not in objects:
        if lum == "dark":
            objects.append("lifestyle-dark")
        elif lum == "light":
            objects.append("lifestyle-bright")
        else:
            objects.append("lifestyle")

    # Low edge density + bright = minimal/clean
    if avg_edge < 20 and brightness > 180:
        objects.append("minimal")

    # Gradient strong (top vs bottom differs) = dramatic
    if abs(gradient) > 0.15:
        objects.append("dramatic")

    return objects


# ============================================================================
# COMPOSITION TAGS — from layer10
# ============================================================================

def extract_composition_tags(dna: dict) -> list[str]:
    """Tag composition style."""
    comp = dna.get("layer10_composition", {}) or {}
    tags = []

    subject_pos = comp.get("subject_estimate_position", "")
    if subject_pos:
        if "center" in subject_pos:
            tags.append("centered")
        elif "rule-of-thirds" in subject_pos:
            tags.append("rule-of-thirds")
        elif "left" in subject_pos:
            tags.append("left-aligned")
        elif "right" in subject_pos:
            tags.append("right-aligned")

    aspect = comp.get("aspect_ratio", 1.0)
    if aspect:
        if aspect > 1.3:
            tags.append("landscape")
        elif aspect < 0.8:
            tags.append("portrait")
        else:
            tags.append("square")

    # Edge density
    edge_grid = comp.get("edge_density_grid", [])
    avg_edge = _flatten_edge_grid(edge_grid)
    if avg_edge > 60:
        tags.append("high-detail")
    elif avg_edge > 0 and avg_edge < 20:
        tags.append("low-detail")

    return tags


# ============================================================================
# MOOD CLASSIFICATION — from palette + composition
# ============================================================================

def classify_mood(dna: dict) -> list[str]:
    """Classify mood: energetic/calm/luxurious/playful/professional."""
    palette = dna.get("layer9_palette", {}) or {}
    comp = dna.get("layer10_composition", {}) or {}

    lum = palette.get("luminance_category", "")
    brightness = palette.get("mean_brightness", 0)
    dom = palette.get("dominant_colors", [])
    gradient = comp.get("gradient", 0)
    try:
        gradient = float(gradient)
    except (TypeError, ValueError):
        gradient = 0

    moods = []

    # Bright + high gradient = energetic
    if brightness > 160 and abs(gradient) > 0.1:
        moods.append("energetic")

    # Dark or muted = calm/professional
    if lum == "dark" or brightness < 80:
        moods.append("calm")
        moods.append("professional")

    # Bright + low gradient + neutral colors = clean/professional
    if brightness > 180 and abs(gradient) < 0.05:
        moods.append("clean")

    # Check colors for luxury/playful
    color_names = extract_colors_from_dna(dna)
    if "gold" in color_names or "black" in color_names:
        moods.append("luxurious")
    if "pink" in color_names or "purple" in color_names:
        moods.append("playful")

    # Default
    if not moods:
        moods.append("neutral")

    return moods


# ============================================================================
# QUALITY SCORE (1-100) — combine compliance + sharpness proxy
# ============================================================================

def compute_quality_score(dna: dict) -> int:
    """Compute quality score 1-100 from compliance + composition metrics."""
    # Start with compliance score (0-1) → 0-70 points
    compliance = dna.get("layer8_compliance", {}) or {}
    comp_score = compliance.get("score", 0)
    base = comp_score * 70

    # Bonus for high edge detail (sharp/in-focus) → 0-15 points
    comp = dna.get("layer10_composition", {}) or {}
    edge_grid = comp.get("edge_density_grid", [])
    avg_edge = _flatten_edge_grid(edge_grid)
    sharpness_bonus = min(15, avg_edge / 4)

    # Bonus for centered composition → 0-10 points
    subject_pos = comp.get("subject_estimate_position", "")
    composition_bonus = 10 if "center" in subject_pos else 5 if subject_pos else 0

    # Bonus for clear palette → 0-5 points
    palette = dna.get("layer9_palette", {}) or {}
    dom = palette.get("dominant_colors", [])
    palette_bonus = 5 if len(dom) >= 3 else 2 if dom else 0

    total = base + sharpness_bonus + composition_bonus + palette_bonus
    return max(1, min(100, int(total)))


# ============================================================================
# TEXT INDEXING — searchable OCR text
# ============================================================================

def extract_text(dna: dict) -> str:
    """Extract all searchable text from OCR + typography."""
    parts = []
    l6 = dna.get("layer6_ocr", {}) or {}
    if isinstance(l6, dict):
        lines = l6.get("lines") or []
        if lines:
            parts.append(" ".join(lines))
        else:
            tp = l6.get("text_preview", "")
            if tp:
                parts.append(str(tp))

    l7 = dna.get("layer7_typography", {}) or {}
    heading = l7.get("likely_heading_text", "")
    if heading:
        parts.append(str(heading))

    return " ".join(parts).strip()


# ============================================================================
# MAIN ENRICHMENT — apply all extractors to one DNA
# ============================================================================

def enrich_dna(dna: dict) -> dict:
    """Add element-level indexing fields to a DNA dict (in-place + return)."""
    # New layers (L2, L3, L5, L11, L12, L13, L14, L15, L16, L18)
    # Map them to the discovery features
    element_data = {
        "colors": extract_colors_from_dna(dna),
        "brands": extract_brands_from_dna(dna),
        "objects": classify_objects(dna),
        "composition_tags": extract_composition_tags(dna),
        "mood": classify_mood(dna),
        "text": extract_text(dna),
        "quality_score": compute_quality_score(dna),
    }

    # Store as layer18_elements (newest, additive — doesn't touch existing layers)
    dna["layer18_elements"] = element_data

    # Also store as discrete layers for compatibility with the layer naming system
    dna["layer2_subject"] = {
        "categories": element_data["objects"],
        "primary": element_data["objects"][0] if element_data["objects"] else "unknown",
    }
    dna["layer3_mood"] = {
        "tags": element_data["mood"],
    }
    dna["layer5_objects"] = {
        "tags": element_data["objects"],
    }
    dna["layer11_fonts"] = {
        # Extend layer7 with weight estimate
        "detected": dna.get("layer7_typography", {}).get("detected", False),
        "weight": _estimate_font_weight(dna),
        "color": dna.get("layer7_typography", {}).get("sample_text_colour", ""),
    }
    dna["layer12_scene"] = {
        "luminance": dna.get("layer9_palette", {}).get("luminance_category", ""),
        "type": "outdoor" if dna.get("layer9_palette", {}).get("mean_brightness", 0) > 100 else "indoor",
    }
    dna["layer13_brand_emphasis"] = {
        "brands": element_data["brands"],
        "count": len(element_data["brands"]),
    }
    dna["layer14_logo_presence"] = {
        "logos_detected": element_data["brands"],
    }
    dna["layer15_motion"] = {
        "static": True,  # all golf images are static photos
        "edge_density": dna.get("layer10_composition", {}).get("edge_density_grid", []),
    }
    dna["layer16_focal_point"] = {
        "position": dna.get("layer10_composition", {}).get("subject_estimate_position", ""),
    }
    dna["layer18_quality"] = {
        "score": element_data["quality_score"],
        "components": {
            "compliance": dna.get("layer8_compliance", {}).get("score", 0),
            "sharpness_proxy": _flatten_edge_grid(dna.get("layer10_composition", {}).get("edge_density_grid", [])),
        },
    }

    return dna


def _estimate_font_weight(dna: dict) -> str:
    """Estimate font weight from typography metrics."""
    l7 = dna.get("layer7_typography", {}) or {}
    max_h = l7.get("max_text_height_px", 0)
    median_h = l7.get("median_text_height_px", 0)
    if max_h == 0 or median_h == 0:
        return "unknown"
    ratio = max_h / median_h if median_h else 1
    if ratio > 1.5:
        return "bold-display"
    if l7.get("is_all_caps"):
        return "bold-caps"
    return "regular"


# ============================================================================
# BATCH INDEX — process all DNA files for one brand
# ============================================================================

def index_brand(brand_id: str, base_dir: str | Path = None) -> dict:
    """Enrich every DNA file in a brand directory with element-level indexing.

    Returns the element index (flat dict for discovery queries).
    """
    base = Path(base_dir) if base_dir else Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")
    img_dir = base / "brand-directory" / brand_id / "images"

    if not img_dir.exists():
        return {"brand": brand_id, "error": f"no images dir: {img_dir}", "images": {}}

    element_index = {
        "brand": brand_id,
        "indexed_count": 0,
        "by_filename": {},
        "by_color": {},
        "by_brand": {},
        "by_object": {},
        "by_mood": {},
        "by_quality": {"high": [], "mid": [], "low": []},
    }

    dna_files = sorted([f for f in img_dir.iterdir() if f.name.endswith(".visual-dna.json")])
    for dna_path in dna_files:
        try:
            dna = json.loads(dna_path.read_text())
        except Exception:
            continue

        # Enrich in place
        enriched = enrich_dna(dna)
        # Save back (additive — preserves existing layers)
        try:
            dna_path.write_text(json.dumps(enriched, indent=2))
        except Exception:
            pass

        # Index entry
        fn = dna_path.name.replace(".visual-dna.json", "")
        elements = enriched.get("layer18_elements", {})
        entry = {
            "filename": fn,
            "dna_path": str(dna_path),
            "colors": elements.get("colors", []),
            "brands": elements.get("brands", []),
            "objects": elements.get("objects", []),
            "composition_tags": elements.get("composition_tags", []),
            "mood": elements.get("mood", []),
            "text": elements.get("text", ""),
            "quality_score": elements.get("quality_score", 0),
        }
        element_index["by_filename"][fn] = entry
        element_index["indexed_count"] += 1

        # Build inverted indexes for fast discovery
        for color in entry["colors"]:
            element_index["by_color"].setdefault(color, []).append(fn)
        for brand in entry["brands"]:
            element_index["by_brand"].setdefault(brand, []).append(fn)
        for obj in entry["objects"]:
            element_index["by_object"].setdefault(obj, []).append(fn)
        for mood in entry["mood"]:
            element_index["by_mood"].setdefault(mood, []).append(fn)

        # Quality bucket
        score = entry["quality_score"]
        if score >= 75:
            element_index["by_quality"]["high"].append(fn)
        elif score >= 50:
            element_index["by_quality"]["mid"].append(fn)
        else:
            element_index["by_quality"]["low"].append(fn)

    return element_index


def save_element_index(element_index: dict, output_path: str | Path) -> None:
    """Save the element index to disk."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(element_index, indent=2))


def load_element_index(brand_id: str, base_dir: str | Path = None) -> dict:
    """Load a previously-saved element index."""
    base = Path(base_dir) if base_dir else Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data")
    path = base / "brand-directory" / "_system" / "element-index.json"
    if not path.exists():
        return {}
    all_indexes = json.loads(path.read_text())
    return all_indexes.get(brand_id, {})
