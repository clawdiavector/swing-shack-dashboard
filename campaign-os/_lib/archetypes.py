"""Load archetypes v2 and select archetype for a calendar moment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def _bundled_brand_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "brand-directory"


def _archetypes_path(brand_id: str) -> Path | None:
    import os

    data_root = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brand-directory"
    bundled = _bundled_brand_root()
    for root in (data_root, bundled):
        path = root / brand_id / "visual-spec" / "archetypes.json"
        if path.is_file():
            return path
    return None


def load_archetypes_doc(brand_id: str) -> dict[str, Any]:
    path = _archetypes_path(brand_id)
    if path is None:
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def archetype_by_id(brand_id: str, archetype_id: str) -> dict[str, Any] | None:
    doc = load_archetypes_doc(brand_id)
    for row in doc.get("archetypes") or []:
        if isinstance(row, dict) and str(row.get("id") or "") == archetype_id:
            return row
    return None


def _moment_context(brand_id: str, item_id: str) -> dict[str, Any]:
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    ctx: dict[str, Any] = {
        "has_product_item": False,
        "pillar_in": [],
        "subject": "",
    }
    if not item_id.startswith("calendar_candidate:"):
        return ctx
    _, key = item_id.split(":", 1)
    brand, cal_id = key.split(":", 1)
    if brand != brand_id:
        return ctx
    for record in canonical_records(brand_id):
        rid = str(record.get("calendar_id") or record.get("event_key") or "")
        if rid != cal_id:
            continue
        pillar = str(record.get("pillar_id") or record.get("pillar") or "")
        if pillar:
            ctx["pillar_in"] = [pillar]
        ctx["subject"] = str(record.get("subject") or record.get("topic") or "")
        products = record.get("product_ids") or record.get("products") or []
        ctx["has_product_item"] = bool(products)
        break
    return ctx


def _pillar_match_tokens(pillar_id: str) -> set[str]:
    """Tokens for selection rules — ``stick-coaching`` also matches rule ``coaching``."""
    raw = str(pillar_id or "").strip().lower()
    if not raw:
        return set()
    out = {raw}
    if "-" in raw:
        out.add(raw.split("-", 1)[-1])
    if "_" in raw:
        out.add(raw.split("_", 1)[-1])
    return out


def _rule_matches(when: dict[str, Any], ctx: dict[str, Any]) -> bool:
    if not isinstance(when, dict):
        return False
    if "has_product_item" in when and bool(when["has_product_item"]) != bool(ctx.get("has_product_item")):
        return False
    if "subject" in when and str(when.get("subject") or "") != str(ctx.get("subject") or ""):
        return False
    pillars = when.get("pillar_in")
    if isinstance(pillars, list) and pillars:
        have: set[str] = set()
        for pid in ctx.get("pillar_in") or []:
            have |= _pillar_match_tokens(str(pid))
        want = {str(p).strip().lower() for p in pillars if p}
        if not have.intersection(want):
            return False
    return True


def select_archetype(brand_id: str, item_id: str) -> dict[str, Any]:
    doc = load_archetypes_doc(brand_id)
    selection = doc.get("selection") if isinstance(doc.get("selection"), dict) else {}
    ctx = _moment_context(brand_id, item_id)
    chosen = str(selection.get("default") or "")
    for rule in selection.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when") if isinstance(rule.get("when"), dict) else {}
        if _rule_matches(when, ctx):
            chosen = str(rule.get("use") or chosen)
    archetypes = doc.get("archetypes") or []
    for row in archetypes:
        if isinstance(row, dict) and str(row.get("id") or "") == chosen:
            return row
    if archetypes and isinstance(archetypes[0], dict):
        return archetypes[0]
    return {"id": "", "applies_to": {"needs_photo": True}}


def canvas_for_channel(doc: dict[str, Any], channel: str) -> tuple[str, dict[str, Any]] | None:
    canvases = doc.get("canvases") if isinstance(doc.get("canvases"), dict) else {}
    for canvas_id, spec in canvases.items():
        if not isinstance(spec, dict):
            continue
        channels = spec.get("channels") or []
        if channel in channels:
            return str(canvas_id), spec
    return None


def palette_tokens(brand_id: str) -> dict[str, str]:
    import os

    data_root = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brand-directory"
    bundled = _bundled_brand_root()
    path = data_root / brand_id / "palette" / "brand.json"
    if not path.is_file():
        path = bundled / brand_id / "palette" / "brand.json"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    tokens = data.get("tokens")
    if isinstance(tokens, dict):
        for k, v in tokens.items():
            if isinstance(v, str) and v.startswith("#"):
                out[str(k)] = v.upper()
    palette = data.get("palette")
    if isinstance(palette, dict):
        for k, v in palette.items():
            if k == "supporting":
                continue
            if isinstance(v, dict) and isinstance(v.get("hex"), str):
                out[str(k)] = v["hex"].upper()
    out.setdefault("white", "#FFFFFF")
    return out


def resolve_colour(token_or_hex: str, brand_id: str) -> str:
    raw = (token_or_hex or "").strip()
    if raw.startswith("#"):
        return raw.upper()
    return palette_tokens(brand_id).get(raw, raw)


def font_size_for_role(brand_id: str, role: str) -> int:
    import os

    data_root = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brand-directory"
    bundled = _bundled_brand_root()
    path = data_root / brand_id / "typography" / "fonts.json"
    if not path.is_file():
        path = bundled / brand_id / "typography" / "fonts.json"
    default = {"display": 84, "h1": 64, "h2": 44, "h3": 32, "body": 18, "caption": 14, "cta": 20}
    if not path.is_file():
        return default.get(role, 32)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default.get(role, 32)
    for row in data.get("scale") or []:
        if isinstance(row, dict) and row.get("name") == role:
            try:
                return int(row.get("size_px") or default.get(role, 32))
            except (TypeError, ValueError):
                break
    return default.get(role, 32)
