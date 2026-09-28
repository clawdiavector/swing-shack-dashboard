"""Load template-recipe/v1 from brand template packs + gen slot cache."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RECIPE_SCHEMA = "campaign-os/template-recipe/v1"

_CACHE_TTL_DAYS: dict[str, int] = {
    "coaching_service_7d": 7,
    "tips_3d": 3,
}


def _brand_root() -> Path:
    runtime = os.environ.get("DATA_DIR")
    if runtime:
        root = Path(runtime) / "brand-directory"
        root.mkdir(parents=True, exist_ok=True)
        return root
    bundled = Path(__file__).resolve().parents[2] / "data" / "brand-directory"
    return bundled


def _template_pack_dir(brand_id: str, template_pack: str) -> Path | None:
    rel = template_pack.strip().lstrip("/")
    if not rel:
        return None
    root = _brand_root()
    path = root / brand_id / rel
    return path if path.is_dir() else None


def load_recipe_json(brand_id: str, template_pack: str) -> dict[str, Any] | None:
    pack = _template_pack_dir(brand_id, template_pack)
    if pack is None:
        return None
    recipe_path = pack / "recipe.json"
    if not recipe_path.is_file():
        return None
    try:
        doc = json.loads(recipe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    if str(doc.get("schema") or "") != RECIPE_SCHEMA:
        return None
    return doc


def load_recipe_for_archetype(brand_id: str, archetype: dict[str, Any]) -> dict[str, Any] | None:
    pack = str(archetype.get("template_pack") or "").strip()
    if not pack:
        return None
    return load_recipe_json(brand_id, pack)


def load_recipe_for_moment(brand_id: str, item_id: str) -> dict[str, Any] | None:
    from _lib.archetypes import select_archetype  # noqa: PLC0415

    archetype = select_archetype(brand_id, item_id)
    return load_recipe_for_archetype(brand_id, archetype)


def _iso_week_bucket(pillar_id: str) -> str:
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    week = f"{iso.year}-W{iso.week:02d}"
    pillar = (pillar_id or "pillar").strip() or "pillar"
    return f"{pillar}:{week}"


def cache_bucket_key(
    *,
    brand_id: str,
    recipe: dict[str, Any],
    item_id: str,
    campaign_id: str | None = None,
    pillar_id: str | None = None,
    seed_bump: int = 0,
) -> str:
    from _lib.archetypes import _moment_context  # noqa: PLC0415

    ctx = _moment_context(brand_id, item_id)
    pillar = pillar_id or (ctx.get("pillar_in") or [""])[0] if ctx.get("pillar_in") else ""
    policy = str(recipe.get("cache_policy") or "coaching_service_7d")
    if policy == "tips_3d":
        bucket = _iso_week_bucket(str(pillar))
    elif campaign_id:
        bucket = campaign_id
    else:
        bucket = _iso_week_bucket(str(pillar))
    raw = f"{brand_id}|{recipe.get('id')}|{bucket}|{seed_bump}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_file_path(
    *,
    brand_id: str,
    template_pack: str,
    slot_id: str,
    bucket_hash: str,
) -> Path:
    pack = _template_pack_dir(brand_id, template_pack)
    if pack is None:
        raise ValueError("template pack missing")
    cache_dir = pack / "cache" / "gen"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{slot_id}-{bucket_hash}.png"


def cache_sidecar_path(png_path: Path) -> Path:
    return png_path.with_suffix(png_path.suffix + ".meta.json")


def cache_is_fresh(png_path: Path, *, policy_key: str) -> bool:
    if not png_path.is_file() or png_path.stat().st_size <= 0:
        return False
    ttl_days = _CACHE_TTL_DAYS.get(policy_key, 7)
    meta_path = cache_sidecar_path(png_path)
    mtime = datetime.fromtimestamp(png_path.stat().st_mtime, tz=timezone.utc)
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            saved = str(meta.get("saved_at") or "")
            if saved:
                mtime = datetime.fromisoformat(saved.replace("Z", "+00:00"))
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    age = datetime.now(timezone.utc) - mtime
    return age <= timedelta(days=ttl_days)


def write_cache_entry(
    png_path: Path,
    *,
    brand_id: str,
    slot_id: str,
    bucket_hash: str,
    prompt_used: str = "",
) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar = {
        "schema": "campaign-os/template-gen-cache/v1",
        "brand_id": brand_id,
        "slot_id": slot_id,
        "bucket_hash": bucket_hash,
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "prompt_used": prompt_used,
    }
    cache_sidecar_path(png_path).write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
