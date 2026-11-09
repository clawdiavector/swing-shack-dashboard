"""Taxonomy of Design — seed load, approval overlay, API payloads."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _lib import template_gallery

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_BUNDLED = _REPO_ROOT / "data"
APPROVALS_BASENAME = "design-approvals.json"


def _bundled_data_dir() -> Path:
    env = os.environ.get("BUNDLED_DATA_DIR", "").strip()
    if env:
        return Path(env)
    return _DEFAULT_BUNDLED


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or "/data/campaign-os")


def seed_path() -> Path:
    return _bundled_data_dir() / "design" / "taxonomy-seed.json"


def media_dir() -> Path:
    return _bundled_data_dir() / "design" / "media"


def media_doc_path() -> Path:
    return _bundled_data_dir() / "design" / "taxonomy-media.json"


def approvals_path() -> Path:
    return _data_dir() / APPROVALS_BASENAME


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_seed() -> dict[str, Any]:
    path = seed_path()
    doc = _read_json(path)
    if not doc:
        raise FileNotFoundError(f"taxonomy seed missing: {path}")
    return doc


def load_approvals() -> dict[str, dict[str, dict[str, Any]]]:
    doc = _read_json(approvals_path())
    if not doc:
        return {"styles": {}, "types": {}, "methods": {}, "posts": {}, "templates": {}}
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for section in ("styles", "types", "methods", "posts", "templates"):
        block = doc.get(section)
        out[section] = block if isinstance(block, dict) else {}
    return out


def save_approvals(store: dict[str, dict[str, dict[str, Any]]]) -> None:
    _write_json_atomic(approvals_path(), store)


def _default_approval() -> dict[str, Any]:
    return {"status": "not_approved", "by": None, "at": None}


def _overlay_item(item: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(item)
    base = row.get("approval")
    if not isinstance(base, dict):
        base = _default_approval()
    if overlay and overlay.get("status") == "approved":
        row["approval"] = {
            "status": "approved",
            "by": overlay.get("by"),
            "at": overlay.get("at"),
        }
    else:
        row["approval"] = {
            "status": "not_approved",
            "by": None,
            "at": None,
        }
    return row


def _section_rows(seed: dict[str, Any], section: str, overlays: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = seed.get(section)
    if not isinstance(rows, list):
        return []
    return [_overlay_item(row, overlays.get(str(row.get("id") or row.get("post_id") or ""))) for row in rows if isinstance(row, dict)]


def _templates_with_approval(brand_id: str, overlays: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        gallery = template_gallery.build_template_gallery(brand_id)
    except ValueError:
        return []
    templates = gallery.get("templates") or []
    coverage_rows = (gallery.get("coverage") or {}).get("rows") or []
    status_by_id: dict[str, str] = {}
    for row in coverage_rows:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("archetype_id") or row.get("template_id") or "")
        if tid and row.get("status"):
            status_by_id[tid] = str(row["status"])

    out: list[dict[str, Any]] = []
    for tpl in templates:
        if not isinstance(tpl, dict):
            continue
        tid = str(tpl.get("template_id") or "")
        merged = dict(tpl)
        merged["brand"] = brand_id
        merged["status"] = status_by_id.get(tid) or tpl.get("status")
        merged = _overlay_item(merged, overlays.get(tid))
        merged["id"] = tid
        out.append(merged)
    for row in coverage_rows:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("archetype_id") or row.get("template_id") or "")
        if not tid or any(t.get("template_id") == tid or t.get("id") == tid for t in out):
            continue
        merged = dict(row)
        merged["brand"] = brand_id
        merged["id"] = tid
        merged = _overlay_item(merged, overlays.get(tid))
        out.append(merged)
    return out


def build_taxonomy(*, brand: str | None = None) -> dict[str, Any]:
    seed = load_seed()
    approvals = load_approvals()
    brand_id = (brand or "swing-shack").strip() or "swing-shack"

    styles = _section_rows(seed, "styles", approvals["styles"])
    types = _section_rows(seed, "types", approvals["types"])
    methods = _section_rows(seed, "methods", approvals["methods"])
    media = _read_json(media_doc_path())
    if media and isinstance(media.get("posts"), list):
        # picture layer (scripts/build_design_media.py) replaces the capped seed list
        posts = _section_rows({"posts": media["posts"]}, "posts", approvals["posts"])
    else:
        posts = _section_rows(seed, "posts", approvals["posts"])
    # all brands: styles are shared across brands, so the page filters posts itself

    templates: list[dict[str, Any]] = []
    for bid in dict.fromkeys([brand_id, "swing-shack", "stick", "bag-drop"]):
        templates.extend(_templates_with_approval(bid, approvals["templates"]))

    return {
        "schema_version": seed.get("schema_version", "taxonomy-seed-v1"),
        "brand_id": brand_id,
        "styles": styles,
        "types": types,
        "methods": methods,
        "posts": posts,
        "media_stats": (media or {}).get("stats") or {},
        "style_pins": (media or {}).get("style_pins") or {},
        "templates": templates,
        "template_gallery": {
            "brand_bible": (template_gallery.build_template_gallery(brand_id).get("brand_bible") or {})
            if brand_id
            else {},
        },
    }


def set_approval(section: str, item_id: str, *, approve: bool, actor: str) -> dict[str, Any]:
    section = str(section or "").strip()
    item_id = str(item_id or "").strip()
    if section not in ("styles", "types", "methods", "posts", "templates"):
        raise ValueError("section must be styles, types, methods, posts, or templates")
    if not item_id:
        raise ValueError("id required")

    if section != "templates":
        seed = load_seed()
        rows = seed.get(section)
        if not isinstance(rows, list):
            raise ValueError(f"unknown section {section}")
        known = {str(r.get("id") or r.get("post_id") or "") for r in rows if isinstance(r, dict)}
        if item_id not in known:
            raise ValueError(f"unknown {section} id: {item_id}")

    store = load_approvals()
    block = store.setdefault(section, {})
    if approve:
        block[item_id] = {
            "status": "approved",
            "by": actor,
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
    else:
        block.pop(item_id, None)
    save_approvals(store)
    return block.get(item_id) or _default_approval()
