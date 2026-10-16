"""
image_scout.py — official product images found online, checked, and saved for approval.

The scout (skill: image-scout) reads the weekly stock gaps, finds the maker's own
product image for each missing product, and records it here as a candidate with its
page and image address. A candidate is checked for quality (a real image, large
enough), and only then saved into the brand's Products folder as SKU__view.<ext> and
put on the photo map as "needs-check", with where it came from. Nothing reaches the
feed until a person approves it.

Never a retailer's copy when the maker's own page has one, never a generated image,
and a standard model image is marked as such when the stock line is a custom build.
"""
from __future__ import annotations

import io
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

MIN_LONG_EDGE = 800    # px: smaller than this is a thumbnail, not a feed image
MIN_BYTES = 20_000
MAX_BYTES = 25_000_000
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
SIZE_PARAMS = {"width", "height", "w", "h", "crop", "fit", "quality", "q"}


def _path(brand_id: str) -> Path:
    from _lib.marketing_lanes import _products_dir
    return _products_dir(brand_id) / "image-candidates.json"


def load(brand_id: str) -> List[Dict[str, Any]]:
    p = _path(brand_id)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("candidates", [])
    except Exception:
        return []


def _save(brand_id: str, rows: List[Dict[str, Any]]) -> None:
    _path(brand_id).write_text(json.dumps({"brand_id": brand_id, "candidates": rows}, indent=1), encoding="utf-8")


def full_size(url: str) -> str:
    """Shopify and similar CDNs serve a small version unless the size parameters are dropped.
    A deliberate large size (width/height of 1000 or more) is kept: it caps huge originals."""
    u = urlparse(url)

    def keep(k: str, v: str) -> bool:
        if k.lower() not in SIZE_PARAMS:
            return True
        return k.lower() in {"width", "height", "w", "h"} and v.isdigit() and int(v) >= 1000

    q = [(k, v) for k, v in parse_qsl(u.query) if keep(k, v)]
    return urlunparse(u._replace(query=urlencode(q)))


def add(brand_id: str, sku: str, product: str, page_url: str, image_url: str, view: str = "front",
        note: str = "", exact_build: bool = True) -> Dict[str, Any]:
    rows = load(brand_id)
    image_url = full_size(image_url)
    for r in rows:
        if r["sku"] == sku and r["image_url"] == image_url:
            return r
    row = {"sku": sku, "product": product, "page_url": page_url, "image_url": image_url, "view": view,
           "note": note, "exact_build": exact_build, "status": "found",
           "found_on": datetime.now(timezone.utc).isoformat()}
    rows.append(row)
    _save(brand_id, rows)
    return row


def _get(url: str, referer: str = "") -> Dict[str, Any]:
    """Fetch like a browser viewing the maker's page: some image servers refuse a bare request."""
    headers = {"User-Agent": UA, "Accept": "image/*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read(MAX_BYTES + 1)
        return {"status": resp.status, "type": resp.headers.get("Content-Type", ""), "data": data}


def check(data: bytes, content_type: str) -> Dict[str, Any]:
    """Quality gate for downloaded bytes."""
    out: Dict[str, Any] = {"ok": False, "bytes": len(data), "content_type": content_type}
    if not content_type.lower().startswith("image/"):
        out["reason"] = f"not an image ({content_type or 'no type'})"
        return out
    if len(data) < MIN_BYTES:
        out["reason"] = "too small to be a product shot"
        return out
    if len(data) > MAX_BYTES:
        out["reason"] = "file is too large"
        return out
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            out["width"], out["height"] = im.size
    except Exception as e:
        out["reason"] = f"cannot read image: {e}"
        return out
    if max(out["width"], out["height"]) < MIN_LONG_EDGE:
        out["reason"] = f"only {out['width']}x{out['height']}, under {MIN_LONG_EDGE}px on the long side"
        return out
    out["ok"] = True
    return out


def _ext(content_type: str, url: str) -> str:
    t = content_type.lower()
    for key, ext in (("png", ".png"), ("webp", ".webp"), ("jpeg", ".jpg"), ("jpg", ".jpg")):
        if key in t:
            return ext
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"


def fetch(brand_id: str, row: Dict[str, Any], images: Optional[Path] = None) -> Dict[str, Any]:
    """Download one candidate, gate its quality, save it as SKU__view.<ext>, put it on the photo map."""
    from _lib import photo_map as pm
    images = images or pm.images_dir(brand_id)
    try:
        got = _get(row["image_url"], row.get("page_url", ""))
    except Exception as e:
        return {"ok": False, "reason": f"download failed: {e}"}
    qc = check(got["data"], got["type"])
    if not qc["ok"]:
        return qc
    folder = images / "Products"
    folder.mkdir(parents=True, exist_ok=True)
    safe_sku = re.sub(r"[^A-Za-z0-9\-_]", "", row["sku"]) or "NOSKU"
    name = f"{safe_sku}{pm.SEP}{row['view']}{_ext(got['type'], row['image_url'])}"
    dest = folder / name
    if dest.exists():
        qc["ok"], qc["reason"] = False, f"{name} already exists, not overwritten"
        return qc
    dest.write_bytes(got["data"])
    pm.add_entry(brand_id, f"Products/{name}", row["sku"], row["product"], row["view"], source="official-site",
                 source_url=row["page_url"], image_url=row["image_url"], note=row.get("note", ""),
                 exact_build=row.get("exact_build", True))
    qc["file"] = f"Products/{name}"
    return qc


def mark(brand_id: str, row: Dict[str, Any], status: str, detail: Dict[str, Any]) -> None:
    rows = load(brand_id)
    for r in rows:
        if r["sku"] == row["sku"] and r["image_url"] == row["image_url"]:
            r["status"] = status
            r["check"] = {k: detail.get(k) for k in ("ok", "width", "height", "bytes", "reason", "file")}
    _save(brand_id, rows)
