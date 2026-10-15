"""
photo_map.py — which real photo belongs to which stocked product.

Staff photograph a product and save the file named for its SKU, with a double
underscore before the view:

    TS001__front.jpg      Takomo SF002, front
    GDZGS001__lineup.jpg  GripDrip Zen Sky

Dropped into the brand's Products folder on Drive (pulled by the ingest script),
the file attaches to the product that owns that SKU. Nothing is guessed from
words in a filename. A new match waits as "needs-check" until a person approves
it, and only approved photos reach the planner (as the product's reference_images).

The map lives beside the product catalog so approvals survive a redeploy.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SEP = "__"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
STATUSES = ("needs-check", "approved", "rejected")


def images_dir(brand_id: str) -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "brand-directory" / brand_id / "images"


def _map_path(brand_id: str) -> Path:
    from _lib.marketing_lanes import _products_dir
    return _products_dir(brand_id) / "photo-map.json"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load(brand_id: str) -> List[Dict[str, Any]]:
    p = _map_path(brand_id)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("entries", [])
    except Exception:
        return []


def _save(brand_id: str, entries: List[Dict[str, Any]]) -> None:
    payload = {"brand_id": brand_id, "version": 1, "entries": entries}
    _map_path(brand_id).write_text(json.dumps(payload, indent=1), encoding="utf-8")


def sku_index(results: List[Dict[str, Any]]) -> Dict[str, str]:
    """SKU -> the product (or brand range) it is promoted as, from stock_pulse.analyse()."""
    out: Dict[str, str] = {}
    for r in results:
        if r.get("folded_into_range"):
            continue
        for s in r["skus"]:
            out[s] = r["name"]
    return out


def scan(brand_id: str, sku_to_product: Dict[str, str], images: Optional[Path] = None) -> Dict[str, Any]:
    """Attach SKU-named files to products. Existing entries (and their approvals) are kept."""
    images = images or images_dir(brand_id)
    by_norm: Dict[str, List[str]] = {}
    for sku in sku_to_product:
        if _norm(sku):
            by_norm.setdefault(_norm(sku), []).append(sku)
    entries = load(brand_id)
    known = {e["file"] for e in entries}
    added, unknown, ambiguous = [], [], []
    if images.exists():
        for f in sorted(images.rglob("*")):
            if f.suffix.lower() not in IMAGE_EXT or SEP not in f.stem:
                continue
            rel = f.relative_to(images).as_posix()
            if rel in known:
                continue
            sku_part, _, view = f.stem.partition(SEP)
            hits = by_norm.get(_norm(sku_part), [])
            if not hits:
                unknown.append(rel)
                continue
            if len(hits) > 1:
                ambiguous.append(rel)
                continue
            sku = hits[0]
            entries.append({
                "file": rel, "sku": sku, "product": sku_to_product[sku], "view": view or "front",
                "source": "instore", "status": "needs-check",
                "viewable": f.suffix.lower() != ".heic",
                "added": datetime.now(timezone.utc).isoformat(),
            })
            added.append(rel)
    _save(brand_id, entries)
    return {"added": added, "unknown": unknown, "ambiguous": ambiguous, "total": len(entries)}


def set_status(brand_id: str, file: str, status: str, by: str = "christelle") -> bool:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    entries = load(brand_id)
    hit = False
    for e in entries:
        if e["file"] == file or Path(e["file"]).name == file:
            e["status"] = status
            e["reviewed_by"] = by
            e["reviewed_on"] = datetime.now(timezone.utc).isoformat()
            hit = True
    if hit:
        _save(brand_id, entries)
    return hit


def status_for(entries: List[Dict[str, Any]], skus: List[str]) -> str:
    """'approved' if any photo of this product is approved, else 'needs-check' if one is waiting, else ''."""
    mine = [e for e in entries if e.get("sku") in set(skus) and e.get("status") != "rejected"]
    if any(e["status"] == "approved" for e in mine):
        return "approved"
    return "needs-check" if mine else ""


def stamp_catalog(brand_id: str, products: List[Dict[str, Any]]) -> int:
    """Put approved photos on catalog records as reference_images (what the brief builder reads)."""
    approved: Dict[str, List[Dict[str, Any]]] = {}
    for e in load(brand_id):
        if e.get("status") == "approved":
            approved.setdefault(e["sku"], []).append(e)
    n = 0
    for p in products:
        refs = []
        for e in approved.get(p.get("sku"), []):
            refs.append({"url": f"/brand-images/{brand_id}/{e['file']}", "kind": "product",
                         "source": e.get("source", "instore")})
        if refs:
            p["reference_images"] = refs
            n += 1
    return n


def shot_name(skus: List[str], view: str = "front") -> str:
    """The filename to save a photo of this product under."""
    clean = next((s for s in skus if re.fullmatch(r"[A-Za-z0-9\-_]+", s or "")), "")
    return f"{clean}{SEP}{view}.jpg" if clean else "(add a clean SKU in the stock system first)"
