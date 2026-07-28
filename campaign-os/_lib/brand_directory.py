"""
brand_directory.py — Brand Directory loader.

Reads data/brand-directory/<brand-id>/ and returns a structured dict per brand.
This is the canonical loader that the image + copy generators use.

A brand is considered `ready` when all four gate files exist:
    1. voice/tone-rules.md (or do-say-dont-say.md)
    2. palette/brand.json
    3. visual-spec/archetypes.json
    4. copy/ctas.md

Until ready, generated output carries a `BRAND: PARTIAL` flag.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Repo-root / brand-directory path resolution.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]  # campaign-os/_lib/ -> campaign-os/ -> repo root
_BRAND_DIR = _REPO_ROOT / "data" / "brand-directory"


def _read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _gate_files_exist(brand_path: Path) -> dict[str, bool]:
    """Check which gate files are present for this brand."""
    return {
        "tone_rules": (brand_path / "voice" / "tone-rules.md").exists()
            or (brand_path / "voice" / "do-say-dont-say.md").exists(),
        "palette": (brand_path / "palette" / "brand.json").exists(),
        "archetypes": (brand_path / "visual-spec" / "archetypes.json").exists(),
        "ctas": (brand_path / "copy" / "ctas.md").exists(),
    }


def load_brand(brand_id: str, base_dir: Path | None = None) -> dict[str, Any]:
    """Load a single brand directory as a structured dict.

    Returns a dict with keys: brand_id, ready, gates, voice, palette,
    archetypes, copy, typography, examples, sources. Missing slots are
    returned as empty strings / None so callers can safely check.
    """
    base = base_dir or _BRAND_DIR
    brand_path = base / brand_id
    if not brand_path.exists():
        return {"brand_id": brand_id, "ready": False, "exists": False}

    palette = _read_json(brand_path / "palette" / "brand.json")
    archetypes = _read_json(brand_path / "visual-spec" / "archetypes.json")
    typography = _read_json(brand_path / "typography" / "fonts.json")

    gates = _gate_files_exist(brand_path)
    ready = all(gates.values())

    return {
        "brand_id": brand_id,
        "exists": True,
        "ready": ready,
        "gates": gates,
        "readme": _read_text(brand_path / "README.md"),
        "voice": {
            "tone_rules": _read_text(brand_path / "voice" / "tone-rules.md"),
            "do_say_dont_say": _read_text(brand_path / "voice" / "do-say-dont-say.md"),
            "punctuation": _read_text(brand_path / "voice" / "punctuation-rules.md"),
            "emojis": _read_text(brand_path / "voice" / "emojis.md"),
        },
        "palette": palette.get("palette") if palette else None,
        "palette_full": palette,
        "archetypes": archetypes.get("archetypes") if archetypes else [],
        "archetypes_full": archetypes,
        "typography": typography,
        "copy": {
            "headlines": _read_text(brand_path / "copy" / "headlines.md"),
            "ctas": _read_text(brand_path / "copy" / "ctas.md"),
            "captions": _read_text(brand_path / "copy" / "captions.md"),
            "hooks": _read_text(brand_path / "copy" / "hooks.md"),
            "taglines": _read_text(brand_path / "copy" / "taglines.md"),
        },
        "examples": {
            "good": _read_text(brand_path / "examples" / "good.md"),
            "bad": _read_text(brand_path / "examples" / "bad.md"),
            "inspiration": _read_text(brand_path / "examples" / "inspiration.md"),
        },
        "image_count": _count_images(brand_path / "images"),
        "sources": {
            "voice_bible_ref": (palette or {}).get("brand_id"),
        },
    }


def _count_images(images_path: Path) -> int:
    if not images_path.exists():
        return 0
    count = 0
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif"):
        count += len(list(images_path.rglob(ext)))
    return count


def list_brands(base_dir: Path | None = None) -> list[str]:
    """Return brand IDs that have a directory entry."""
    base = base_dir or _BRAND_DIR
    if not base.exists():
        return []
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and not d.name.startswith(("_", "."))
    )


def build_index(base_dir: Path | None = None) -> dict[str, Any]:
    """Build the flat brand-index dict for fast lookup by generators.

    Output keys: brands (dict per brand), updated (ISO timestamp),
    schema (versioned URL), total_ready (count of brands with all gates).
    """
    from datetime import datetime, timezone

    base = base_dir or _BRAND_DIR
    brand_ids = list_brands(base)
    brands: dict[str, Any] = {}
    ready_count = 0

    for brand_id in brand_ids:
        brand = load_brand(brand_id, base_dir=base)
        brands[brand_id] = {
            "ready": brand["ready"],
            "gates": brand["gates"],
            "image_count": brand["image_count"],
            "primary_color": (brand.get("palette") or {}).get("primary", {}).get("hex"),
            "accent_color": (brand.get("palette") or {}).get("accent", {}).get("hex"),
            "archetype_ids": [
                a.get("id") for a in (brand.get("archetypes") or [])
            ],
        }
        if brand["ready"]:
            ready_count += 1

    return {
        "schema": "https://campaign-os/brand-directory/index/v1",
        "version": "1.0",
        "updated": datetime.now(timezone.utc).isoformat(),
        "total_brands": len(brand_ids),
        "total_ready": ready_count,
        "brands": brands,
    }


def write_index(target_path: Path | None = None, base_dir: Path | None = None) -> Path:
    """Build the index and write it to _system/brand-index.json.

    Returns the path written.
    """
    base = base_dir or _BRAND_DIR
    target = target_path or (base / "_system" / "brand-index.json")
    index = build_index(base_dir=base)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    return target


if __name__ == "__main__":
    # Allow `python -m brand_directory` from inside the repo root.
    path = write_index()
    print(f"Wrote {path}")
