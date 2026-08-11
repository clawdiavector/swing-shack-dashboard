"""
visual_dna_query.py — Query and tag the Visual DNA index.

Provides:
- search_images(query, brand='swing-shack'): free-text + filter search
- detect_products(dna_data): scan OCR text for product mentions
- tag_directory(brand): retroactively tag every image with products
- find_closest_styles(target_dna, brand, n=5): visual similarity ranking

The product taxonomy is intentionally inclusive of:
- Trackman hardware
- Bag brands (Jordan, Vessel, Vice, Srixon)
- Club brands (TaylorMade, PING, Callaway, Takomo, Titleist, FootJoy)
- Rangefinder brands (Mileseey, Bushnell)
- SS-specific SKUs (Zen Swing Stage, GTS putters)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

# Product taxonomy — single source of truth for product detection
# Each entry: (canonical_name, [match_patterns])
PRODUCT_TAXONOMY: list[tuple[str, list[str]]] = [
    # Launch monitors / fitting hardware
    ("TrackMan", ["trackman", "track man", "track-man"]),
    ("TrackMan iO", ["trackman io", "track-man io"]),

    # SS-specific equipment
    ("GTS Putter", ["gts", "zen swing stage"]),
    ("Zen Swing Stage", ["zen swing", "zenstage"]),

    # Bags
    ("Jordan Bag", ["jordan bag", "jordan_bag"]),
    ("Vessel Bag", ["vessel bag", "vessel_bag", "vesselbag"]),
    ("Vice Bag", ["vice bag", "vicebag"]),
    ("Srixon Bag", ["srixon bag", "srixon_bag"]),

    # Club brands
    ("TaylorMade", ["taylormade", "taylor made"]),
    ("PING", ["ping g440", "ping "]),
    ("Callaway", ["callaway"]),
    ("Callaway Quantum", ["quantum", "quantam"]),
    ("Takomo", ["takomo"]),
    ("Takomo 101", ["takomo 101"]),
    ("Titleist", ["titleist", "pro v1"]),
    ("FootJoy", ["footjoy", "foot joy"]),

    # Rangefinders
    ("Mileseey", ["mileseey"]),
    ("Bushnell", ["bushnell"]),

    # Apparel (Stick Golf brand context)
    ("Psycho Bunny", ["psycho bunny"]),
]


def detect_products_in_text(text: str) -> list[str]:
    """Given OCR text, return list of canonical product names mentioned."""
    if not text:
        return []
    text_low = text.lower()
    found = []
    for canonical, patterns in PRODUCT_TAXONOMY:
        if any(p in text_low for p in patterns):
            found.append(canonical)
    return found


def tag_dna_file(dna_path: Path) -> dict[str, Any]:
    """Read a single .visual-dna.json, add product_tags layer, write back."""
    dna = json.loads(dna_path.read_text())

    # Aggregate text from OCR
    ocr_text = dna.get("layer6_ocr", {}).get("text_preview", "") or ""
    # Also include full text if available (we save preview only, but try anyway)
    ocr_full = dna.get("layer6_ocr", {}).get("text", "") or ocr_text
    combined = f"{ocr_text} {ocr_full}"

    products = detect_products_in_text(combined)

    # Also detect in filename (layer1)
    filename = dna.get("layer1_metadata", {}).get("filename", "")
    products += detect_products_in_text(filename)
    products = sorted(set(products))

    dna["layer4_products"] = {
        "detected_brands": products,
        "count": len(products),
        "source": "ocr+filename",
    }
    dna_path.write_text(json.dumps(dna, indent=2))
    return dna


def tag_directory(brand: str, base_dir: Path | None = None) -> dict[str, Any]:
    """Tag every visual-dna.json in the brand's directory. Returns index update."""
    if base_dir is None:
        base_dir = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data/brand-directory")
    images_dir = base_dir / brand / "images"
    if not images_dir.exists():
        return {"error": f"directory not found: {images_dir}"}

    by_product: dict[str, list[str]] = defaultdict(list)
    tagged_count = 0

    for dna_file in images_dir.glob("*.visual-dna.json"):
        dna = tag_dna_file(dna_file)
        filename = dna.get("layer1_metadata", {}).get("filename", dna_file.stem)
        for product in dna.get("layer4_products", {}).get("detected_brands", []):
            by_product[product].append(filename)
        tagged_count += 1

    # Update index
    index_path = base_dir / brand / "visual-dna-index.json"
    if index_path.exists():
        idx = json.loads(index_path.read_text())
    else:
        idx = {}
    idx["by_product"] = dict(by_product)
    idx["product_taxonomy_version"] = "2026-07-29.1"
    idx["tagged_count"] = tagged_count
    index_path.write_text(json.dumps(idx, indent=2))

    return {
        "brand": brand,
        "tagged": tagged_count,
        "products_found": {k: len(v) for k, v in by_product.items()},
        "index_path": str(index_path),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Query API
# ─────────────────────────────────────────────────────────────────────────────

def search_images(
    brand: str,
    query: str | None = None,
    product: str | None = None,
    alignment: str | None = None,  # 'high' | 'typical' | 'variants'
    min_score: float | None = None,
    max_score: float | None = None,
    luminance: str | None = None,  # 'dark' | 'mid' | 'light'
    dominant_color: str | None = None,
    base_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Search the visual DNA index with filters. Returns matching image records + DNA preview."""
    if base_dir is None:
        base_dir = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data/brand-directory")

    index_path = base_dir / brand / "visual-dna-index.json"
    images_dir = base_dir / brand / "images"
    if not index_path.exists():
        return []
    idx = json.loads(index_path.read_text())

    by_product = idx.get("by_product", {})
    by_alignment = idx.get("by_alignment", {})
    candidates = set(idx.get("by_filename", {}).keys())

    # Apply filters
    if query:
        q_low = query.lower()
        # Search in filenames + product tags + OCR text
        for fn in list(candidates):
            fn_low = fn.lower()
            in_filename = q_low in fn_low
            in_products = any(q_low in p.lower() for p in by_product if fn in by_product[p])
            # OCR text search
            stem = fn.rsplit(".", 1)[0]
            dna_p = images_dir / f"{stem}.visual-dna.json"
            in_ocr = False
            if dna_p.exists():
                dna = json.loads(dna_p.read_text())
                text = (dna.get("layer6_ocr", {}).get("text_preview", "") or "").lower()
                in_ocr = q_low in text
            if not (in_filename or in_products or in_ocr):
                candidates.discard(fn)

    if product:
        candidates &= set(by_product.get(product, []))

    if alignment:
        candidates &= set(by_alignment.get(alignment, []))

    if min_score is not None or max_score is not None:
        filtered = set()
        for fn in candidates:
            score = idx["by_filename"][fn].get("score") or 0
            if min_score is not None and score < min_score:
                continue
            if max_score is not None and score > max_score:
                continue
            filtered.add(fn)
        candidates = filtered

    if luminance:
        filtered = set()
        for fn in candidates:
            if idx["by_filename"][fn].get("luminance") == luminance:
                filtered.add(fn)
        candidates = filtered

    if dominant_color:
        filtered = set()
        target_rgb = tuple(int(dominant_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        for fn in candidates:
            dom = idx["by_filename"][fn].get("dominant")
            if not dom:
                continue
            d_rgb = tuple(int(dom.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
            # distance < 60 ~= close colour match
            dist = sum((a-b)**2 for a, b in zip(d_rgb, target_rgb))**0.5
            if dist < 80:
                filtered.add(fn)
        candidates = filtered

    # Build response
    results = []
    for fn in sorted(candidates):
        rec = idx["by_filename"][fn].copy()
        # Add the OCR text + products for context
        stem = fn.rsplit(".", 1)[0]
        dna_p = images_dir / f"{stem}.visual-dna.json"
        if dna_p.exists():
            dna = json.loads(dna_p.read_text())
            rec["products"] = dna.get("layer4_products", {}).get("detected_brands", [])
            rec["ocr_text"] = dna.get("layer6_ocr", {}).get("text_preview", "")
            rec["heading"] = dna.get("layer7_typography", {}).get("likely_heading_text", "")
            rec["background_colour"] = dna.get("layer9_palette", {}).get("dominant_colors", [{}])[0].get("hex")
            rec["layer17_recipe"] = dna.get("layer17_recipe", {})
        results.append(rec)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Generation pipeline — visual recipe selection
# ─────────────────────────────────────────────────────────────────────────────

def select_visual_recipes(
    brand: str,
    brief: str,
    n: int = 5,
    prefer_alignment: str = "high",
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Given a generation brief, return the top N Visual Recipes to use as scaffolding.
    Algorithm:
    1. Search by brief keywords against filename/OCR/products
    2. Score by alignment (high > typical > variants)
    3. Return top N with full layer17 recipe + DNA preview
    """
    if base_dir is None:
        base_dir = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data/brand-directory")

    # Try direct brief keyword match first
    brief_words = re.findall(r"\w+", brief.lower())
    direct_matches = []
    for word in brief_words:
        if len(word) < 3:
            continue
        matches = search_images(brand, query=word, alignment=prefer_alignment, base_dir=base_dir)
        direct_matches.extend(matches)

    # Dedupe by filename, sort by score
    seen = set()
    deduped = []
    for m in direct_matches:
        fn = m.get("dna_path", "")
        if fn in seen:
            continue
        seen.add(fn)
        deduped.append(m)

    deduped.sort(key=lambda x: -(x.get("score") or 0))

    # If we have fewer than n matches, fall back to top-scored alignment bucket
    if len(deduped) < n:
        fillers = search_images(brand, alignment=prefer_alignment, base_dir=base_dir)
        for f in fillers:
            if f.get("dna_path") in seen:
                continue
            seen.add(f.get("dna_path"))
            deduped.append(f)
            if len(deduped) >= n:
                break

    top = deduped[:n]

    # Build a "generation scaffold" — aggregate recipe hints
    if not top:
        return {"brief": brief, "scaffold": None, "matches": []}

    scaffold = {
        "avg_score": round(sum(m.get("score", 0) or 0 for m in top) / len(top), 3),
        "common_backgrounds": _common_colors(top, "background_colour"),
        "common_dominants": _common_colors(top, "dominant"),
        "common_luminance": _common_field(top, "luminance"),
        "common_text_colour_samples": _common_text_colours(top),
        "all_caps_pattern": all(
            m.get("layer17_recipe", {}).get("auto_extracted", {}).get("all_caps_detected")
            for m in top
        ),
        "common_products": _common_field(top, "products"),
        "gradient_directions": _common_field(top, "gradient"),
        "subject_positions": _common_field(top, "subject_estimate_position"),
    }

    return {
        "brief": brief,
        "brand": brand,
        "scaffold": scaffold,
        "matches": [
            {
                "filename": m.get("dna_path", "").split("/")[-1].replace(".visual-dna.json", ""),
                # Include the image source for the IG-recipe-card so each match
                # can render a thumbnail without an extra round-trip.
                # m.get('dna_path') looks like .../brand-directory/<brand>/images/<file>.visual-dna.json
                # The actual image sits beside it, with the same stem + a real
                # image extension (.jpg / .jpeg / .png). Use stem-based lookup
                # so the same code handles all three extensions.
                "dna_path": m.get("dna_path", ""),
                "image_path": _resolve_image_path(m.get("dna_path", ""), base_dir / brand / "images"),
                "image_url": _image_url_for(brand, m.get("dna_path", ""), base_dir / brand / "images"),
                "score": m.get("score"),
                "alignment": (
                    "high" if m.get("score", 0) >= 0.70
                    else "typical" if m.get("score", 0) >= 0.60
                    else "variants"
                ),
                "heading": m.get("heading"),
                "background_colour": m.get("background_colour"),
                "products": m.get("products", []),
                "ocr_text": m.get("ocr_text"),
                "layer17_recipe": m.get("layer17_recipe", {}),
            }
            for m in top
        ],
    }


def _resolve_image_path(dna_path: str, images_dir: Path) -> str | None:
    """Given a DNA JSON path, return the matching image path on disk.

    The visual-dna-index records sit beside the image they describe — same
    stem, different extension. This finds whatever extension actually
    exists on disk so the UI can render a thumbnail.
    """
    if not dna_path:
        return None
    stem = dna_path.replace(".visual-dna.json", "")
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        cand = Path(stem + ext)
        if cand.exists():
            return str(cand)
    return None


def _image_url_for(brand: str, dna_path: str, images_dir: Path) -> str | None:
    """Return the public URL for the image matching this DNA record, or None."""
    p = _resolve_image_path(dna_path, images_dir)
    if not p:
        return None
    return f"/brand-images/{brand}/{Path(p).name}"


def _common_colors(matches: list[dict], field: str, top_n: int = 5) -> list[dict]:
    counts = defaultdict(int)
    for m in matches:
        val = m.get(field)
        if val:
            counts[val] += 1
    return [{"hex": h, "count": c} for h, c in sorted(counts.items(), key=lambda x: -x[1])[:top_n]]


def _common_field(matches: list[dict], field: str) -> dict[str, int]:
    counts = defaultdict(int)
    for m in matches:
        val = m.get(field)
        if val:
            counts[val] += 1
    return dict(counts)


def _common_text_colours(matches: list[dict]) -> dict[str, int]:
    counts = defaultdict(int)
    for m in matches:
        recipe = m.get("layer17_recipe", {})
        # text colour lives in typography layer
        dna_path = m.get("dna_path")
        if not dna_path:
            continue
        p = Path(dna_path)
        if p.exists():
            dna = json.loads(p.read_text())
            tc = dna.get("layer7_typography", {}).get("sample_text_colour")
            if tc:
                counts[tc] += 1
    return dict(counts)


# ─────────────────────────────────────────────────────────────────────────────
# Driver for ad-hoc CLI use
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage:")
        print("  visual_dna_query.py tag <brand>")
        print("  visual_dna_query.py search <brand> <query>")
        print("  visual_dna_query.py product <brand> <product>")
        print("  visual_dna_query.py recipe <brand> '<brief>'")
        sys.exit(1)

    cmd = sys.argv[1]
    brand = sys.argv[2]

    if cmd == "tag":
        result = tag_directory(brand)
        print(json.dumps(result, indent=2))
    elif cmd == "search":
        query = sys.argv[3] if len(sys.argv) > 3 else ""
        results = search_images(brand, query=query)
        print(f"Found {len(results)} matches")
        for r in results[:10]:
            print(f"  score={r.get('score')}  {r.get('dna_path','').split('/')[-1]}  products={r.get('products',[])}")
    elif cmd == "product":
        product = sys.argv[3]
        results = search_images(brand, product=product)
        print(f"Found {len(results)} images featuring {product}")
        for r in results[:10]:
            print(f"  score={r.get('score')}  {r.get('dna_path','').split('/')[-1]}  lum={r.get('luminance')}")
    elif cmd == "recipe":
        brief = sys.argv[3]
        result = select_visual_recipes(brand, brief)
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown command: {cmd}")
