"""
image_library.py — where logos, maker logos and sourced images live, and whether we may use them.

    <brand>/logos/                  the brand's own logos, listed in logos/logos.json
    _shared/maker-logos/<slug>.png  every maker's logo, once, for all brands
    _shared/catalogue/              official images found on a maker's own site:
        catalogue.json              what each one is and where it came from (in git)
        images/<maker>/<model>__N   the files (not in git: they are the maker's)
    _system/image-sources.json      per maker: how to get the images, and `rights`

A photo the scout found online waits on the photo map like any other, and cannot be
approved until its maker's rights status is "cleared" (Christelle, 2026-10-28: confirm
rights before using any sourced image). The guide is _system/IMAGES.md.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

BD = Path(__file__).resolve().parents[2] / "data" / "brand-directory"
CATALOGUE = BD / "_shared" / "catalogue"
SOURCES = BD / "_system" / "image-sources.json"

LOGO_STATUSES = ("official", "outdated", "needs-check")
RIGHTS_STATUSES = ("cleared", "not-cleared", "unknown")


class RightsNotCleared(ValueError):
    """Approving a sourced photo whose maker's image rights are not recorded as cleared."""


def slug(name: str) -> str:
    """'L.A.B. Golf' -> 'lab-golf', 'RIPIT' -> 'ripit'."""
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower().replace(".", "")).strip("-")


def maker_logo_path(brand_id: str, name: str) -> Optional[Path]:
    """The maker's logo: the shared one first, then a brand's own logos/vendors/ copy."""
    from _lib.brand_overlay import _resolve_brand_relative

    s = slug(name)
    if not s:
        return None
    return (_resolve_brand_relative("_shared", f"maker-logos/{s}.png")
            or _resolve_brand_relative(brand_id, f"logos/vendors/{s}.png"))


# --- catalogue ---------------------------------------------------------------------------------

def _index(root: Optional[Path]) -> Path:
    return (root or CATALOGUE) / "catalogue.json"


def load_catalogue(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = _index(root)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("images", [])
    except Exception:
        return []


def _save_catalogue(rows: List[Dict[str, Any]], root: Optional[Path]) -> None:
    p = _index(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"images": rows}, indent=1), encoding="utf-8")


def find_in_catalogue(image_url: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    for row in load_catalogue(root):
        if row.get("image_url") == image_url:
            return row
    return None


def catalogue_bytes(row: Dict[str, Any], root: Optional[Path] = None) -> Optional[bytes]:
    p = (root or CATALOGUE) / row["file"]
    return p.read_bytes() if p.is_file() else None


def add_to_catalogue(maker: str, product: str, page_url: str, image_url: str, data: bytes, ext: str,
                     root: Optional[Path] = None, **extra: Any) -> Dict[str, Any]:
    """File one official image under images/<maker>/<product>__N<ext>. Same address or same bytes: kept once."""
    root = root or CATALOGUE
    sha = hashlib.sha256(data).hexdigest()
    rows = load_catalogue(root)
    for row in rows:
        if row.get("image_url") == image_url or row.get("sha256") == sha:
            return row
    folder = root / "images" / (slug(maker) or "unknown")
    folder.mkdir(parents=True, exist_ok=True)
    base = slug(product) or "image"
    n = 1
    while (folder / f"{base}__{n}{ext}").exists():
        n += 1
    dest = folder / f"{base}__{n}{ext}"
    dest.write_bytes(data)
    row = {"file": dest.relative_to(root).as_posix(), "maker": maker, "product": product,
           "page_url": page_url, "image_url": image_url, "sha256": sha,
           "added": datetime.now(timezone.utc).isoformat(), **extra}
    rows.append(row)
    _save_catalogue(rows, root)
    return row


# --- rights ------------------------------------------------------------------------------------

def _sources() -> Dict[str, Any]:
    try:
        return json.loads(SOURCES.read_text(encoding="utf-8")).get("brands", {})
    except Exception:
        return {}


def _host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def maker_for_url(url: str) -> str:
    """Which maker an image or page address belongs to, from the hosts in image-sources.json."""
    host = _host(url)
    if not host:
        return ""
    for name, src in _sources().items():
        if not isinstance(src, dict):
            continue
        for key in ("site", "images"):
            for found in re.findall(r"https?://[^\s/<>\"']+", str(src.get(key) or "")):
                h = _host(found)
                if h and (host == h or host.endswith("." + h)):
                    return name
        for h in src.get("hosts", []) or []:
            if host == h or host.endswith("." + h):
                return name
    return ""


def rights_for(maker: str) -> str:
    src = _sources().get(maker)
    r = src.get("rights") if isinstance(src, dict) else None
    status = r.get("status") if isinstance(r, dict) else None
    return status if status in RIGHTS_STATUSES else "unknown"


def check_can_approve(entry: Dict[str, Any]) -> None:
    """Raise RightsNotCleared for a sourced photo whose maker is not cleared. Our own photos always pass."""
    if entry.get("source") != "official-site":
        return
    url = str(entry.get("image_url") or entry.get("source_url") or "")
    hit = find_in_catalogue(url) if url else None
    maker = str(entry.get("maker") or (hit or {}).get("maker") or maker_for_url(url))
    if rights_for(maker) != "cleared":
        raise RightsNotCleared(
            f"{entry.get('file')}: image rights for {maker or 'this source'} are not recorded as cleared "
            f"(data/brand-directory/_system/image-sources.json)")
