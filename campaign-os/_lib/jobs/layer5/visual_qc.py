"""Visual QC gate for draft_photo candidates."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _lib import archetypes_v2 as archetypes
from _lib.image_dissector import HAS_TESSERACT, dissect


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _hex_rgb(hexstr: str) -> tuple[int, int, int]:
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _is_neutral(rgb: tuple[int, int, int]) -> bool:
    return max(rgb) - min(rgb) <= 24


def _brand_tokens(brand_id: str) -> list[tuple[str, tuple[int, int, int]]]:
    from _lib.brand_overlay import _find_color_palette

    doc = _find_color_palette(brand_id)
    palette = doc.get("palette") if isinstance(doc, dict) else {}
    out: list[tuple[str, tuple[int, int, int]]] = []
    if isinstance(palette, dict):
        for name, entry in palette.items():
            if isinstance(entry, dict) and entry.get("hex"):
                out.append((name, _hex_rgb(str(entry["hex"]))))
    return out


def _photo_zone_rect(archetype: dict[str, Any]) -> dict[str, float] | None:
    zones = archetype.get("zones") if isinstance(archetype.get("zones"), dict) else {}
    photo = zones.get("photo")
    if isinstance(photo, dict):
        rect = photo.get("rect")
        if isinstance(rect, dict):
            return rect
    return None


def _bbox_in_photo_zone(block: dict[str, Any], photo_rect: dict[str, float] | None, w: int, h: int) -> bool:
    if not photo_rect:
        return False
    inset = 0.02
    px0 = (photo_rect["x0"] + inset) * w
    py0 = (photo_rect["y0"] + inset) * h
    px1 = (photo_rect["x1"] - inset) * w
    py1 = (photo_rect["y1"] - inset) * h
    left = int(block.get("left") or 0)
    top = int(block.get("top") or 0)
    width = int(block.get("width") or 0)
    height = int(block.get("height") or 0)
    return left >= px0 and top >= py0 and (left + width) <= px1 and (top + height) <= py1


def _aspect_ratio(w: int, h: int) -> float:
    return w / max(1, h)


def visual_check(
    candidate_png: bytes | Path,
    *,
    brand_id: str,
    archetype_id: str,
) -> dict[str, Any]:
    """Run QC checks; never pass when OCR is unavailable."""
    archetype = archetypes.archetype_by_id(brand_id, archetype_id) or {}
    doc = archetypes.load_archetypes_doc(brand_id)
    canvas_id = str(archetype.get("canvas") or "ig_post")
    canvas = (doc.get("canvases") or {}).get(canvas_id) if isinstance(doc.get("canvases"), dict) else {}
    target_aspect = _aspect_ratio(int(canvas.get("w") or 1080), int(canvas.get("h") or 1350))
    reasons: list[str] = []
    scores: dict[str, Any] = {}
    if not HAS_TESSERACT:
        return {
            "verdict": "needs_human",
            "reasons": ["ocr_unavailable"],
            "ocr_available": False,
            "checked_at": _utc_now_iso(),
            "scores": scores,
        }

    if isinstance(candidate_png, Path):
        tmp_path = candidate_png
        cleanup = False
    else:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(candidate_png)
            tmp_path = Path(tmp.name)
        cleanup = True
    try:
        bible = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brand-directory" / brand_id / "bible-visual.json"
        if not bible.is_file():
            bible = Path(__file__).resolve().parents[3] / "data" / "brand-directory" / brand_id / "bible-visual.json"
        dna = dissect(str(tmp_path), str(bible) if bible.is_file() else None)
    finally:
        if cleanup:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    meta = dna.get("layer1_metadata") if isinstance(dna.get("layer1_metadata"), dict) else {}
    w = int(meta.get("width_px") or 0)
    h = int(meta.get("height_px") or 0)
    aspect = float(meta.get("aspect_ratio") or _aspect_ratio(w, h))
    if abs(aspect - target_aspect) > 0.02:
        reasons.append("wrong_aspect")
    if 0.92 <= aspect <= 1.08 and target_aspect < 0.85:
        reasons.append("contact_sheet_grid")

    ocr = dna.get("layer6_ocr") if isinstance(dna.get("layer6_ocr"), dict) else {}
    photo_rect = _photo_zone_rect(archetype)
    for block in ocr.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        conf = float(block.get("conf") or 0)
        text = str(block.get("text") or "").strip()
        if conf >= 60 and len(text) >= 3 and not _bbox_in_photo_zone(block, photo_rect, w, h):
            reasons.append("model_rendered_text")
            break

    tokens = _brand_tokens(brand_id)
    palette = dna.get("layer9_palette") if isinstance(dna.get("layer9_palette"), dict) else {}
    dom = palette.get("dominant_colors") if isinstance(palette.get("dominant_colors"), list) else []
    max_dist = 0.0
    for row in dom:
        if not isinstance(row, dict):
            continue
        share = float(row.get("share") or 0)
        hexval = str(row.get("hex") or "")
        if not hexval:
            continue
        rgb = _hex_rgb(hexval)
        if share >= 0.08:
            if _is_neutral(rgb):
                continue
            nearest = min((_rgb_distance(rgb, t[1]) for t in tokens), default=999.0)
            max_dist = max(max_dist, nearest)
            if nearest > 36:
                reasons.append("off_brand_colour")
        if share >= 0.05:
            nearest = min((_rgb_distance(rgb, t[1]) for t in tokens), default=999.0)
            if not _is_neutral(rgb) and nearest > 120:
                reasons.append("off_brand_dominant")
    scores["palette_max_distance"] = round(max_dist, 1)

    bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
    if bg.get("kind") in ("solid", "photo_band") and str(bg.get("fill") or "") in ("navy_deep", "primary"):
        lum = str(palette.get("luminance_category") or "")
        if lum == "light":
            reasons.append("field_too_light")

    comp = dna.get("layer8_compliance") if isinstance(dna.get("layer8_compliance"), dict) else None
    if comp and comp.get("score") is not None:
        scores["compliance"] = float(comp.get("score"))
        if float(comp.get("score")) < 0.70:
            reasons.append("low_compliance")
    else:
        scores["compliance"] = "unavailable"

    l10 = dna.get("layer10_composition") if isinstance(dna.get("layer10_composition"), dict) else {}
    grid = l10.get("edge_density_grid")
    if isinstance(grid, list) and grid and photo_rect:
        flat = [float(x) for row in grid for x in (row if isinstance(row, list) else [row])]
        if flat:
            idx = flat.index(max(flat))
            cols = int(math.sqrt(len(flat))) or 1
            row_i, col_i = divmod(idx, cols)
            y_frac = (row_i + 0.5) / cols
            if not (photo_rect["y0"] <= y_frac <= photo_rect["y1"]):
                reasons.append("subject_outside_photo_zone")

    hard = {"wrong_aspect", "model_rendered_text", "hallucinated_logo", "off_brand_dominant", "contact_sheet_grid"}
    soft = {"off_brand_colour", "field_too_light"}
    if not reasons:
        verdict = "pass"
    elif any(r in hard for r in reasons):
        verdict = "fail"
    elif all(r in soft for r in reasons):
        verdict = "soft_fail"
    else:
        verdict = "fail"
    return {
        "verdict": verdict,
        "reasons": sorted(set(reasons)),
        "ocr_available": True,
        "checked_at": _utc_now_iso(),
        "scores": scores,
    }


def build_edit_instruction(
    check: dict[str, Any] | None = None,
    *,
    brand_id: str,
    failed: list[str] | None = None,
) -> str:
    reasons = set(failed or (check.get("reasons") if check else []) or [])
    tokens = _brand_tokens(brand_id)
    token_txt = ", ".join(f"{n} {h}" for n, h in tokens[:6])
    parts = [
        "Edit this photograph in place. Keep the subject, framing, lens and lighting exactly as they are.",
    ]
    if "model_rendered_text" in reasons:
        parts.append(
            "Remove all text, lettering, captions and typography from the image. Leave the surface clean and unmarked. Do not replace the text with anything."
        )
    if "hallucinated_logo" in reasons:
        parts.append(
            "Remove every logo, wordmark, badge and watermark that is not physically printed on the product itself. Do not invent replacements."
        )
    if "off_brand_colour" in reasons or "off_brand_dominant" in reasons:
        parts.append(f"Shift the colour grade so the dominant tones sit on {token_txt}. Do not recolour the product itself.")
    if "field_too_light" in reasons:
        parts.append("Darken the overall field so the frame reads as a deep #073C52 ground. Preserve highlight detail on the subject.")
    if "subject_outside_photo_zone" in reasons:
        parts.append("Recompose so the subject sits within the lower 56% of the frame with clear negative space above it.")
    parts.extend(
        [
            "Do not add text. Do not add logos. Do not add watermarks.",
        ]
    )
    return " ".join(parts)
