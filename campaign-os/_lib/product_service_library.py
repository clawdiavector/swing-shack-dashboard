"""
product_service_library.py — Product & Service image library.

This module is the canonical "what do we sell and what do we offer" database
that the image generator consults when generating promotional images.

Schema (data/brand-directory/<brand>/product-library.json):
{
    "version": 1,
    "brand": "swing-shack",
    "updated": 1234567890.0,
    "products": [
        {
            "id": "trackman-4",
            "kind": "product",
            "name": "TrackMan 4",
            "category": "launch-monitor",
            "description": "Tour-grade dual-radar launch monitor...",
            "headline": "See every shot, dial every club",
            "tags": ["premium", "fitting", "hardware"],
            "reference_ref_ids": ["ref-abc123...", "ref-def456..."],
            "hero_ref_id": "ref-abc123...",
            "default_palette": ["#0b0d0e", "#f5c842"],
            "preferred_mood": ["dark", "studio"],
            "default_prompt_seed": "premium product photography, dark backdrop, side-lit",
            "performance_summary": {...},  # written by feedback_loop
        }
    ],
    "services": [
        {
            "id": "coaching-1on1",
            "kind": "service",
            "name": "1-on-1 Coaching",
            "category": "instruction",
            "description": "Private 60-minute coaching session...",
            "headline": "Your swing, decoded",
            "tags": ["premium", "transformation"],
            "reference_ref_ids": [...],
            "hero_ref_id": ...,
            "default_palette": [...],
            "preferred_mood": [...],
            "default_prompt_seed": "...",
            "performance_summary": {...},
        }
    ],
    "offerings": [
        # Bundled packages combining product + service
        {
            "id": "fitting-package",
            "kind": "offering",
            "name": "Full Fitting Package",
            "products": ["trackman-4", "gts-putter"],
            "services": ["coaching-1on1"],
            "headline": "From data to driver",
            ...
        }
    ]
}

The point is to make it trivial to say "generate an image promoting
'coaching-1on1'" and have the system automatically pull the service's
description, headline, hero reference image, and learned signals into
the generation prompt.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _default_brand_root() -> Path:
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "data" / "brand-directory"


def _library_path(brand: str, root: Path | None = None) -> Path:
    if root is None:
        root = _default_brand_root()
    out = root / brand
    out.mkdir(parents=True, exist_ok=True)
    return out / "product-library.json"


# ---------------------------------------------------------------------------
# I/O — read + write the library as a single JSON document
# ---------------------------------------------------------------------------


def _empty_library(brand: str) -> dict[str, Any]:
    return {
        "version": 1,
        "brand": brand,
        "updated": time.time(),
        "products": [],
        "services": [],
        "offerings": [],
    }


def load_library(brand: str, root: Path | None = None) -> dict[str, Any]:
    p = _library_path(brand, root)
    if not p.exists():
        return _empty_library(brand)
    try:
        return json.loads(p.read_text())
    except Exception:
        return _empty_library(brand)


def save_library(library: dict[str, Any], brand: str, root: Path | None = None) -> Path:
    p = _library_path(brand, root)
    library["updated"] = time.time()
    library["brand"] = brand
    p.write_text(json.dumps(library, indent=2, default=str))
    return p


# ---------------------------------------------------------------------------
# ID derivation
# ---------------------------------------------------------------------------


def derive_ps_id(name: str, kind: str = "product") -> str:
    """Stable ID from name + kind: lowercase, hyphenated, kind-prefixed."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{kind}-{slug[:40]}"


def _ensure_unique_id(library: dict[str, Any], candidate: str, kind: str) -> str:
    """If the candidate ID already exists for this kind, append -2, -3, ..."""
    pool = library.get(kind + "s", [])
    used = {p["id"] for p in pool}
    if candidate not in used:
        return candidate
    n = 2
    while f"{candidate}-{n}" in used:
        n += 1
    return f"{candidate}-{n}"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def add_item(
    brand: str,
    *,
    kind: str,                     # "product" | "service" | "offering"
    name: str,
    category: str = "",
    description: str = "",
    headline: str = "",
    tags: list[str] | None = None,
    reference_ref_ids: list[str] | None = None,
    hero_ref_id: str | None = None,
    default_palette: list[str] | None = None,
    preferred_mood: list[str] | None = None,
    default_prompt_seed: str = "",
    products: list[str] | None = None,
    services: list[str] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Add a new product / service / offering. Returns the saved item dict.

    For offerings, the products + services lists must contain existing IDs.
    """
    if kind not in ("product", "service", "offering"):
        raise ValueError(f"kind must be product|service|offering, got {kind}")

    lib = load_library(brand, root)
    pool_key = kind + "s"
    pool = lib.setdefault(pool_key, [])

    # Auto-derive ID if not provided
    base_id = derive_ps_id(name, kind)
    item_id = _ensure_unique_id(lib, base_id, kind)

    item: dict[str, Any] = {
        "id": item_id,
        "kind": kind,
        "name": name,
        "category": category,
        "description": description,
        "headline": headline,
        "tags": list(tags or []),
        "created": time.time(),
    }

    if kind in ("product", "service"):
        item["reference_ref_ids"] = list(reference_ref_ids or [])
        item["hero_ref_id"] = hero_ref_id
        item["default_palette"] = list(default_palette or [])
        item["preferred_mood"] = list(preferred_mood or [])
        item["default_prompt_seed"] = default_prompt_seed
        item["performance_summary"] = {}
    elif kind == "offering":
        # Validate referenced product/service IDs exist
        all_ps_ids = {p["id"] for p in lib.get("products", [])} | {s["id"] for s in lib.get("services", [])}
        unknown = []
        for pid in products or []:
            if pid not in all_ps_ids:
                unknown.append(pid)
        for sid in services or []:
            if sid not in all_ps_ids:
                unknown.append(sid)
        if unknown:
            raise ValueError(f"offering references unknown IDs: {unknown}")
        item["products"] = list(products or [])
        item["services"] = list(services or [])
        item["headline"] = headline
        item["description"] = description
        item["tags"] = list(tags or [])

    pool.append(item)
    save_library(lib, brand, root)
    return item


def update_item(
    brand: str,
    item_id: str,
    *,
    root: Path | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    """Update fields on an existing item. Returns updated item or None."""
    lib = load_library(brand, root)
    for kind in ("product", "service", "offering"):
        pool = lib.get(kind + "s", [])
        for i, item in enumerate(pool):
            if item["id"] == item_id:
                for k, v in fields.items():
                    if k in item:
                        item[k] = v
                item["updated"] = time.time()
                pool[i] = item
                save_library(lib, brand, root)
                return item
    return None


def delete_item(brand: str, item_id: str, root: Path | None = None) -> bool:
    lib = load_library(brand, root)
    for kind in ("product", "service", "offering"):
        pool = lib.get(kind + "s", [])
        new_pool = [it for it in pool if it["id"] != item_id]
        if len(new_pool) != len(pool):
            lib[kind + "s"] = new_pool
            save_library(lib, brand, root)
            return True
    return False


def get_item(brand: str, item_id: str, root: Path | None = None) -> dict[str, Any] | None:
    lib = load_library(brand, root)
    for kind in ("product", "service", "offering"):
        for it in lib.get(kind + "s", []):
            if it["id"] == item_id:
                return it
    return None


def list_items(
    brand: str,
    kind: str | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    lib = load_library(brand, root)
    if kind:
        return list(lib.get(kind + "s", []))
    return list(lib.get("products", [])) + list(lib.get("services", [])) + list(lib.get("offerings", []))


# ---------------------------------------------------------------------------
# Prompt composition — what an item contributes to the generation prompt
# ---------------------------------------------------------------------------


def item_to_prompt(item: dict[str, Any], *, max_chars: int = 600) -> str:
    """Render a product/service/offering as a prompt fragment.

    Includes: name, headline, description, default palette hint,
    preferred mood, default seed. Truncates the description to keep
    the fragment under max_chars.
    """
    parts: list[str] = []

    # Name + headline
    name = item.get("name", "")
    headline = item.get("headline", "")
    if name:
        parts.append(f"{name}.")
    if headline:
        parts.append(f"Headline: \"{headline}\".")

    # Description — truncate to fit
    desc = (item.get("description") or "").strip()
    if desc:
        # leave room for the rest
        remaining = max_chars - sum(len(p) + 2 for p in parts) - 200
        if remaining > 50:
            desc = desc[:remaining].rsplit(".", 1)[0] + "." if "." in desc[:remaining] else desc[:remaining]
            parts.append(desc)

    # Offering expansion — pull headline from product/service children
    if item.get("kind") == "offering":
        lib = load_library(item.get("brand", ""))
        for pid in item.get("products", []):
            child = next((p for p in lib.get("products", []) if p["id"] == pid), None)
            if child:
                parts.append(f"Includes product: {child.get('name')}.")
        for sid in item.get("services", []):
            child = next((s for s in lib.get("services", []) if s["id"] == sid), None)
            if child:
                parts.append(f"Includes service: {child.get('name')}.")

    # Palette + mood hints
    palette = item.get("default_palette") or []
    if palette:
        parts.append(f"Brand colours for this item: {', '.join(palette[:3])}.")
    mood = item.get("preferred_mood") or []
    if mood:
        parts.append(f"Mood: {', '.join(mood)}.")

    # Default seed
    seed = (item.get("default_prompt_seed") or "").strip()
    if seed:
        parts.append(seed + ".")

    # Tags
    tags = item.get("tags") or []
    if tags:
        parts.append(f"Tags: {', '.join(tags)}.")

    # Apply max_chars cap (rough — character count on joined string)
    joined = " ".join(parts)
    if len(joined) > max_chars:
        joined = joined[:max_chars].rsplit(".", 1)[0] + "."
    return joined


# ---------------------------------------------------------------------------
# Attach / detach reference DNA to an item
# ---------------------------------------------------------------------------


def attach_reference(
    brand: str,
    item_id: str,
    ref_id: str,
    *,
    as_hero: bool = False,
    root: Path | None = None,
) -> dict[str, Any] | None:
    """Attach a reference DNA to an item (product/service).

    If as_hero=True, also set as the item's hero_ref_id.
    """
    from _lib.reference_dna import load_reference_dna
    ref = load_reference_dna(ref_id, brand, root)
    if not ref:
        return None

    lib = load_library(brand, root)
    for kind in ("product", "service"):
        pool = lib.get(kind + "s", [])
        for i, item in enumerate(pool):
            if item["id"] == item_id:
                ids = item.setdefault("reference_ref_ids", [])
                if ref_id not in ids:
                    ids.append(ref_id)
                if as_hero:
                    item["hero_ref_id"] = ref_id
                item["updated"] = time.time()
                pool[i] = item
                save_library(lib, brand, root)
                return item
    return None


def detach_reference(
    brand: str,
    item_id: str,
    ref_id: str,
    root: Path | None = None,
) -> dict[str, Any] | None:
    lib = load_library(brand, root)
    for kind in ("product", "service"):
        pool = lib.get(kind + "s", [])
        for i, item in enumerate(pool):
            if item["id"] == item_id:
                ids = item.get("reference_ref_ids", [])
                if ref_id in ids:
                    ids.remove(ref_id)
                if item.get("hero_ref_id") == ref_id:
                    item["hero_ref_id"] = ids[0] if ids else None
                item["updated"] = time.time()
                pool[i] = item
                save_library(lib, brand, root)
                return item
    return None


# ---------------------------------------------------------------------------
# Seed with sensible defaults for Swing Shack
# ---------------------------------------------------------------------------


# These are the canonical offerings Christelle runs. Seeded once on first
# load so the library is immediately useful.
SS_DEFAULT_PRODUCTS = [
    {
        "id": "product-trackman",
        "name": "TrackMan Launch Monitor",
        "category": "launch-monitor",
        "headline": "Tour-grade data for your game",
        "description": "Dual-radar launch monitor used on tour. See club speed, ball speed, launch angle, spin, smash factor, and carry distance for every shot.",
        "tags": ["premium", "fitting", "hardware", "data"],
        "default_palette": ["#0b0d0e", "#f5c842"],
        "preferred_mood": ["dark", "studio", "premium"],
        "default_prompt_seed": "Premium product photography, dark backdrop, side-lit with rim light, no people",
    },
    {
        "id": "product-gts-putter",
        "name": "GTS Putter",
        "category": "putter",
        "headline": "Your stroke, perfected",
        "description": "GTS (Get The Stroke) putters — custom fit and balanced to your stroke. Available in multiple head shapes.",
        "tags": ["premium", "putting", "fitting"],
        "default_palette": ["#1a1a1a", "#c8b273"],
        "preferred_mood": ["studio", "premium"],
        "default_prompt_seed": "Premium putter product photography, dark studio backdrop, soft side light, sharp focus on head",
    },
    {
        "id": "product-zen-swing-stage",
        "name": "Zen Swing Stage",
        "category": "training-aid",
        "headline": "Find your perfect impact position",
        "description": "Tour-grade swing training aid that locks the perfect impact position and lets you feel the right move.",
        "tags": ["training", "premium", "instruction"],
        "default_palette": ["#0d0d0d", "#d4a849"],
        "preferred_mood": ["studio", "premium"],
        "default_prompt_seed": "Studio product shot of a golf training aid, dark backdrop, dramatic side lighting",
    },
    {
        "id": "product-takomo-101",
        "name": "Takomo 101T Irons",
        "category": "iron-set",
        "headline": "Forged feel, modern distance",
        "description": "Tour-style forged cavity-back irons with the look and feel of a players iron at game-improvement distance.",
        "tags": ["iron-set", "premium", "fitting"],
        "default_palette": ["#1c1c1c", "#c0a062"],
        "preferred_mood": ["studio", "premium"],
        "default_prompt_seed": "Premium iron-set product photography, dark studio, multiple clubs fanned, sharp",
    },
    {
        "id": "product-mileseey-rangefinder",
        "name": "Mileseey Rangefinder",
        "category": "rangefinder",
        "headline": "Pin-lock precision",
        "description": "High-accuracy golf rangefinder with pin-lock vibration and slope-adjusted distance.",
        "tags": ["rangefinder", "premium", "tech"],
        "default_palette": ["#0a0a0a", "#e74c3c"],
        "preferred_mood": ["studio", "tech"],
        "default_prompt_seed": "Rangefinder product shot, studio, dark backdrop with red accent lighting",
    },
]

SS_DEFAULT_SERVICES = [
    {
        "id": "service-coaching-1on1",
        "name": "1-on-1 Coaching",
        "category": "instruction",
        "headline": "Your swing, decoded",
        "description": "Private 60-minute coaching session. Video analysis, launch monitor data, and a personalised drill plan. With a PGA pro at our indoor studio.",
        "tags": ["premium", "transformation", "1-on-1"],
        "default_palette": ["#0b0d0e", "#f5c842"],
        "preferred_mood": ["premium", "studio"],
        "default_prompt_seed": "Premium coaching promo, indoor studio setting, dark moody backdrop, motion blur on swing",
    },
    {
        "id": "service-fitting",
        "name": "Club Fitting",
        "category": "fitting",
        "headline": "From data to driver",
        "description": "TrackMan-driven club fitting. We use launch monitor data + swing DNA to dial in every club in your bag.",
        "tags": ["premium", "fitting", "data"],
        "default_palette": ["#0d0d0d", "#d4a849"],
        "preferred_mood": ["studio", "data"],
        "default_prompt_seed": "Fitting session, indoor studio, TrackMan screen in background, premium feel",
    },
    {
        "id": "service-beginner-lessons",
        "name": "Beginner Lessons",
        "category": "instruction",
        "headline": "New to golf? Start here.",
        "description": "4-pack of beginner lessons covering grip, stance, swing basics, and short game. Indoor studio, no pressure.",
        "tags": ["beginner", "entry-level"],
        "default_palette": ["#2c3e50", "#27ae60"],
        "preferred_mood": ["bright", "approachable"],
        "default_prompt_seed": "Approachable beginner-friendly golf lesson scene, indoor studio, warm tones, welcoming",
    },
    {
        "id": "service-ladies-lessons",
        "name": "Ladies Lessons",
        "category": "instruction",
        "headline": "Your game. Your community.",
        "description": "Ladies-only coaching sessions. Group format, relaxed atmosphere, expert instruction.",
        "tags": ["ladies", "community", "group"],
        "default_palette": ["#8e44ad", "#e91e63"],
        "preferred_mood": ["bright", "community"],
        "default_prompt_seed": "Ladies-only golf session, indoor studio, warm welcoming tones, group setting",
    },
]


def seed_defaults(brand: str, root: Path | None = None, force: bool = False) -> dict[str, Any]:
    """Seed the library with default SS products/services if not present.

    Skips existing items unless force=True. Returns the library.
    """
    lib = load_library(brand, root)
    existing_p = {p["id"] for p in lib.get("products", [])}
    existing_s = {s["id"] for s in lib.get("services", [])}

    now = time.time()
    for p in SS_DEFAULT_PRODUCTS:
        if p["id"] in existing_p and not force:
            continue
        # ensure seed items get the full record shape
        record = {
            **p,
            "kind": "product",
            "reference_ref_ids": [],
            "hero_ref_id": None,
            "performance_summary": {},
            "created": now,
        }
        lib.setdefault("products", []).append(record)

    for s in SS_DEFAULT_SERVICES:
        if s["id"] in existing_s and not force:
            continue
        record = {
            **s,
            "kind": "service",
            "reference_ref_ids": [],
            "hero_ref_id": None,
            "performance_summary": {},
            "created": now,
        }
        lib.setdefault("services", []).append(record)

    save_library(lib, brand, root)
    return lib