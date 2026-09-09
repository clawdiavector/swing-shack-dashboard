"""
reference_dna.py — Visual Reference Library for Campaign OS.

Wraps the existing image_dissector with a purpose-built interface for
"point at an image, capture its DNA, reuse it later" workflows.

Reference DNA is the structured description of a SINGLE reference image that
the image generator can consume to mimic its look. It includes:

- palette           (dominant + supporting colors, hex)
- composition       (rule-of-thirds alignment, balance, focal points)
- luminance         (dark / mid / bright bucket + numeric)
- orientation       (square / portrait / landscape)
- product_tags      (what's in the image)
- typography        (font family, weight, size inferred from OCR)
- ocr               (text found in the image)
- mood              (inferred from palette + composition keywords)
- recipe            (raw layer17 recipe from dissector)

The point of this module vs the raw dissector output:

- Predictable shape — every reference gets the same fields, so the router
  can build prompts from it consistently.
- Persistence — references are saved as `data/brand-directory/<brand>/
  references/<ref_id>.reference-dna.json` so we can list, search, and
  attach them later.
- Self-contained — the reference JSON includes the source image path +
  thumbnail URL so the UI can display the reference alongside the
  generation.

Reference IDs are deterministic: `ref-<short-hash>` derived from the
source image's SHA256 + a normalised form. The same image always maps
to the same ref_id, which means re-ingesting is idempotent.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Canonical brand-directory root. Same convention used by app.py + dissector.
def _default_brand_root() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "data" / "brand-directory"


def _references_dir(brand: str, root: Path | None = None) -> Path:
    if root is None:
        root = _default_brand_root()
    out = root / brand / "references"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _thumbnails_dir(brand: str, root: Path | None = None) -> Path:
    if root is None:
        root = _default_brand_root()
    out = root / brand / "references" / "thumbnails"
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------------------
# ID derivation
# ---------------------------------------------------------------------------


def derive_ref_id(image_path: Path) -> str:
    """Stable ID for an image: SHA256 of its bytes, first 12 hex chars.

    Re-ingesting the same image always yields the same ref_id.
    """
    h = hashlib.sha256()
    with open(image_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"ref-{h.hexdigest()[:12]}"


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------


def _make_thumbnail(image_path: Path, out_path: Path, max_dim: int = 256) -> bool:
    """Resize image to a small JPG thumbnail. Returns True on success."""
    try:
        from PIL import Image  # local import — Pillow is in venv but optional here
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_dim, max_dim))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            im.save(out_path, "JPEG", quality=80)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# DNA extraction — wraps image_dissector
# ---------------------------------------------------------------------------


def _safe_dissect(image_path: Path, brand_bible_path: Path | None) -> dict[str, Any]:
    """Run the dissector, fall back to a stub if it raises."""
    try:
        from _lib.image_dissector import dissect
        return dissect(image_path, brand_bible_path)
    except Exception as exc:
        return {
            "layer1_metadata": {
                "filename": image_path.name,
                "width_px": None,
                "height_px": None,
                "aspect_ratio": None,
                "orientation": None,
            },
            "_dissector_error": str(exc),
        }


def _bible_path(brand: str, root: Path | None) -> Path | None:
    if root is None:
        root = _default_brand_root()
    p = root / brand / "bible-visual.json"
    return p if p.exists() else None


def extract_reference_dna(
    image_path: Path,
    brand: str,
    *,
    label: str | None = None,
    tags: list[str] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Run dissector + normalise into the Reference DNA shape.

    Returns a dict ready to be persisted as <ref_id>.reference-dna.json.

    Fields:
        ref_id:        stable id derived from image bytes
        brand:         brand_id
        source_path:   absolute path to the source image (for serving)
        thumbnail:     relative path to the thumbnail (relative to brand root)
        label:         human label, e.g. "black-friday-hero-2025"
        tags:          free-form tags, e.g. ["hero", "dark-bg", "premium"]
        palette:       top 5 colors as hex strings
        composition:   compact composition summary
        luminance:     bucket + numeric
        orientation:   square / portrait / landscape
        product_tags:  list of product names detected
        ocr_text:      OCR'd text (preview)
        mood:          inferred mood keywords
        typography:    typography summary (family + weight)
        recipe:        raw layer17 recipe from dissector
        created:       epoch seconds
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"reference image not found: {image_path}")

    ref_id = derive_ref_id(image_path)
    bible = _bible_path(brand, root)
    raw = _safe_dissect(image_path, bible)

    # ---- extract the fields we care about, with fallbacks -----------------
    l1 = raw.get("layer1_metadata", {})
    l9 = raw.get("layer9_palette", {})
    l10 = raw.get("layer10_composition", {})
    l6 = raw.get("layer6_ocr", {})
    l7 = raw.get("layer7_typography", {})
    l17 = raw.get("layer17_recipe", {})

    # Palette — pull dominant + supporting colours as hex
    palette: list[str] = []
    for c in l9.get("dominant_colors", []) or []:
        if isinstance(c, dict) and c.get("hex"):
            palette.append(c["hex"])
    if not palette:
        # fallback — best-effort RGB extraction via PIL
        try:
            from PIL import Image
            with Image.open(image_path) as im:
                im = im.convert("RGB").resize((50, 50))
                colours = im.getcolors(maxcolors=50 * 50)
                if colours:
                    colours.sort(reverse=True)
                    for count, rgb in colours[:5]:
                        palette.append("#" + "".join(f"{c:02x}" for c in rgb))
        except Exception:
            pass

    # Luminance — bucket from raw
    luminance_bucket = l9.get("luminance_bucket") or l9.get("luminance") or "mid"
    luminance_numeric = l9.get("luminance_value")
    if luminance_numeric is None and isinstance(l9.get("average_brightness"), (int, float)):
        luminance_numeric = float(l9["average_brightness"])

    # Composition
    composition = {
        "rule_of_thirds_score": l10.get("rule_of_thirds_score") or l10.get("rule_of_thirds_alignment"),
        "balance": l10.get("balance"),
        "focal_points": l10.get("focal_points", [])[:3],
    }

    # OCR
    ocr_text = ""
    if isinstance(l6, dict):
        ocr_text = l6.get("text_preview") or l6.get("text") or ""
    elif isinstance(l6, str):
        ocr_text = l6

    # Typography
    typography = {
        "primary_family": l7.get("primary_font_family") or l7.get("primary_family"),
        "weight": l7.get("primary_weight"),
        "size_bucket": l7.get("primary_size_bucket"),
    }

    # Product tags — use the visual_dna_query detector if available
    product_tags: list[str] = []
    try:
        from _lib.visual_dna_query import detect_products_in_text
        product_tags = detect_products_in_text(ocr_text)
        product_tags += detect_products_in_text(image_path.name)
        product_tags = sorted(set(product_tags))
    except Exception:
        pass

    # Mood — keyword inference from palette + composition + OCR
    mood = _infer_mood(palette, composition, l9, raw)

    # Thumbnail
    thumbs_dir = _thumbnails_dir(brand, root)
    thumb_filename = f"{ref_id}.jpg"
    thumb_path = thumbs_dir / thumb_filename
    _make_thumbnail(image_path, thumb_path)

    if root is None:
        root = _default_brand_root()
    rel_thumb = str(thumb_path.relative_to(root))

    return {
        "ref_id": ref_id,
        "brand": brand,
        "source_path": str(image_path),
        "source_filename": image_path.name,
        "thumbnail": rel_thumb,
        "label": label or image_path.stem.replace("_", " ").replace("-", " "),
        "tags": tags or [],
        "palette": palette[:6],
        "composition": composition,
        "luminance": {
            "bucket": luminance_bucket,
            "value": luminance_numeric,
        },
        "orientation": l1.get("orientation"),
        "product_tags": product_tags,
        "ocr_text": ocr_text[:500],
        "mood": mood,
        "typography": typography,
        "recipe": l17,
        "created": time.time(),
    }


# ---------------------------------------------------------------------------
# Mood inference — cheap heuristic, not ML
# ---------------------------------------------------------------------------


_LUMINANCE_MOOD = {
    "dark": "moody, dramatic, cinematic, low-key",
    "mid": "balanced, studio, neutral",
    "bright": "high-key, airy, daylight, optimistic",
}


def _infer_mood(
    palette: list[str],
    composition: dict[str, Any],
    palette_layer: dict[str, Any],
    raw: dict[str, Any],
) -> list[str]:
    """Return a list of mood keywords inferred from palette + composition."""
    moods: list[str] = []
    bucket = palette_layer.get("luminance_bucket") or palette_layer.get("luminance")
    if bucket in _LUMINANCE_MOOD:
        moods.extend(_LUMINANCE_MOOD[bucket].split(", "))

    # Palette-driven mood
    if palette:
        try:
            from PIL import ImageColor
            # Average saturation
            saturations: list[float] = []
            lightnesses: list[float] = []
            for hexcol in palette[:3]:
                try:
                    raw_rgb = ImageColor.getrgb(hexcol)
                    # ImageColor returns (r,g,b) or (r,g,b,a) — drop alpha if present
                    if len(raw_rgb) == 4:
                        r, g, b = raw_rgb[0], raw_rgb[1], raw_rgb[2]
                    else:
                        r, g, b = raw_rgb
                    mx, mn = max(r, g, b), min(r, g, b)
                    sat = (mx - mn) / mx if mx else 0
                    light = (mx + mn) / 2 / 255
                    saturations.append(sat)
                    lightnesses.append(light)
                except Exception:
                    pass
            if saturations:
                avg_sat = sum(saturations) / len(saturations)
                if avg_sat > 0.6:
                    moods.append("vibrant")
                elif avg_sat < 0.15:
                    moods.append("muted")
                else:
                    moods.append("balanced-colour")
            if lightnesses:
                avg_light = sum(lightnesses) / len(lightnesses)
                if avg_light < 0.25:
                    moods.append("dark-mood")
                elif avg_light > 0.75:
                    moods.append("bright-airy")
        except Exception:
            pass

    # Composition-driven mood
    rot = composition.get("rule_of_thirds_score")
    if rot and isinstance(rot, (int, float)) and rot > 0.7:
        moods.append("rule-of-thirds")

    # OCR-derived mood (search for moody words in text)
    l6 = raw.get("layer6_ocr", {})
    text = ""
    if isinstance(l6, dict):
        text = (l6.get("text_preview") or l6.get("text") or "").lower()
    if "premium" in text or "elite" in text:
        moods.append("premium")
    if "limited" in text or "exclusive" in text:
        moods.append("exclusive")
    if "deal" in text or "discount" in text or "off" in text:
        moods.append("promotional")

    # Dedup + cap
    seen = set()
    out = []
    for m in moods:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out[:6]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_reference_dna(ref_dna: dict[str, Any], brand: str, root: Path | None = None) -> Path:
    """Persist the reference DNA JSON. Returns the file path written."""
    refs_dir = _references_dir(brand, root)
    out = refs_dir / f"{ref_dna['ref_id']}.reference-dna.json"
    out.write_text(json.dumps(ref_dna, indent=2, default=str))
    return out


def list_reference_dnas(brand: str, root: Path | None = None) -> list[dict[str, Any]]:
    """Load all reference DNA records for a brand. Sorted newest first."""
    refs_dir = _references_dir(brand, root)
    out: list[dict[str, Any]] = []
    for p in refs_dir.glob("*.reference-dna.json"):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    out.sort(key=lambda r: r.get("created") or 0, reverse=True)
    return out


def load_reference_dna(ref_id: str, brand: str, root: Path | None = None) -> dict[str, Any] | None:
    p = _references_dir(brand, root) / f"{ref_id}.reference-dna.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def delete_reference_dna(ref_id: str, brand: str, root: Path | None = None) -> bool:
    """Delete reference + thumbnail. Returns True if anything was deleted."""
    refs_dir = _references_dir(brand, root)
    p = refs_dir / f"{ref_id}.reference-dna.json"
    deleted = False
    if p.exists():
        p.unlink()
        deleted = True
    thumb = refs_dir / "thumbnails" / f"{ref_id}.jpg"
    if thumb.exists():
        thumb.unlink()
    return deleted


# ---------------------------------------------------------------------------
# Reference DNA -> prompt fragment
# ---------------------------------------------------------------------------


def reference_dna_to_prompt(ref_dna: dict[str, Any]) -> str:
    """Render a reference DNA as a prompt fragment for the image generator.

    Designed to read naturally to a vision-LLM image generator. Drops into
    the prompt after the user's raw prompt + before the brand recipe.
    """
    parts: list[str] = []

    label = ref_dna.get("label") or "reference"
    parts.append(f"Visual reference: {label}.")

    # Palette
    palette = ref_dna.get("palette", [])
    if palette:
        # top 3 hex codes, with a natural-language hint
        hex_codes = palette[:3]
        parts.append(f"Use this exact colour palette: {', '.join(hex_codes)}.")

    # Luminance + orientation
    lum = ref_dna.get("luminance", {})
    if lum.get("bucket"):
        parts.append(f"Lighting: {lum['bucket']}.")
    if ref_dna.get("orientation"):
        parts.append(f"Orientation: {ref_dna['orientation']}.")

    # Composition
    comp = ref_dna.get("composition", {})
    if comp.get("rule_of_thirds_score") and isinstance(comp["rule_of_thirds_score"], (int, float)):
        if comp["rule_of_thirds_score"] > 0.7:
            parts.append("Composition: subject placed on rule-of-thirds lines.")
    if comp.get("balance"):
        parts.append(f"Balance: {comp['balance']}.")

    # Mood
    mood = ref_dna.get("mood", [])
    if mood:
        parts.append(f"Mood: {', '.join(mood)}.")

    # Typography
    typo = ref_dna.get("typography", {})
    if typo.get("primary_family"):
        family = typo["primary_family"]
        weight = typo.get("weight") or "regular"
        parts.append(f"Typography: {family}, {weight} weight.")

    # Product tags
    products = ref_dna.get("product_tags", [])
    if products:
        parts.append(f"Products visible: {', '.join(products)}.")

    # OCR — only include if it looks like meaningful text
    ocr = (ref_dna.get("ocr_text") or "").strip()
    if ocr and len(ocr) > 3 and not ocr.isspace():
        # Limit to first 120 chars
        ocr_excerpt = ocr[:120].replace("\n", " ")
        parts.append(f"Reference text visible: \"{ocr_excerpt}\".")

    # Tags (user-supplied)
    tags = ref_dna.get("tags", [])
    if tags:
        parts.append(f"Style tags: {', '.join(tags)}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Copy local file into brand references folder
# ---------------------------------------------------------------------------


def ingest_local_image(
    src_path: Path,
    brand: str,
    *,
    label: str | None = None,
    tags: list[str] | None = None,
    copy: bool = True,
    root: Path | None = None,
) -> dict[str, Any]:
    """Copy (or reference) a local image into the brand's references folder,
    then extract DNA + persist.

    Returns the persisted Reference DNA dict.
    """
    src_path = Path(src_path).resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"source not found: {src_path}")

    # If copy, place under references/sources/<ref_id>.<ext>
    refs_dir = _references_dir(brand, root)
    sources_dir = refs_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    # Use the SHA-derived ref_id to make path deterministic
    temp_ref_id = derive_ref_id(src_path)
    ext = src_path.suffix.lower() or ".jpg"
    dest = sources_dir / f"{temp_ref_id}{ext}"

    if copy:
        if not dest.exists():
            shutil.copy2(src_path, dest)

    # Run dissector on the destination so it sees a stable path
    ref_dna = extract_reference_dna(dest, brand, label=label, tags=tags, root=root)

    # Persist
    save_reference_dna(ref_dna, brand, root)
    return ref_dna


# ---------------------------------------------------------------------------
# URL ingestion
# ---------------------------------------------------------------------------


def ingest_url(
    url: str,
    brand: str,
    *,
    label: str | None = None,
    tags: list[str] | None = None,
    timeout: float = 30.0,
    root: Path | None = None,
) -> dict[str, Any]:
    """Download an image from URL, ingest as reference DNA."""
    import urllib.request
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "campaign-os/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        tmp_path.write_bytes(data)
        return ingest_local_image(tmp_path, brand, label=label, tags=tags, copy=True, root=root)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Selection helpers — find references by product / palette / mood
# ---------------------------------------------------------------------------


def select_references(
    brand: str,
    *,
    product: str | None = None,
    mood: str | None = None,
    palette_hex: list[str] | None = None,
    max_luminance: float | None = None,
    min_luminance: float | None = None,
    limit: int = 5,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Filter reference DNAs by product, mood, palette range, luminance.

    All filters are AND-ed. Empty filters return most-recent first.
    """
    candidates = list_reference_dnas(brand, root)
    out: list[dict[str, Any]] = []
    for r in candidates:
        if product and product.lower() not in [p.lower() for p in r.get("product_tags", [])]:
            continue
        if mood and mood.lower() not in [m.lower() for m in r.get("mood", [])]:
            continue
        if palette_hex:
            # accept if any of the requested hex codes is within 30 RGB of the reference's palette
            ref_palette = r.get("palette", [])
            if not _palette_overlap(ref_palette, palette_hex, threshold=30):
                continue
        lum_value = (r.get("luminance") or {}).get("value")
        if max_luminance is not None and lum_value is not None and lum_value > max_luminance:
            continue
        if min_luminance is not None and lum_value is not None and lum_value < min_luminance:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def _palette_overlap(palette_a: list[str], palette_b: list[str], threshold: float = 30.0) -> bool:
    """Return True if any color in palette_a is within `threshold` RGB units of any in palette_b."""
    try:
        from PIL import ImageColor
        def _rgb3(c):
            v = ImageColor.getrgb(c)
            return v[:3] if len(v) == 4 else v
        ra = [_rgb3(c) for c in palette_a if c]
        rb = [_rgb3(c) for c in palette_b if c]
        for a in ra:
            for b in rb:
                if sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5 <= threshold:
                    return True
        return False
    except Exception:
        return False