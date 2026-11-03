"""
image_library.py — where logos, maker logos and sourced images live, and whether we may use them.

    <brand>/logos/                  the brand's own logos, listed in logos/logos.json
    _shared/maker-logos/<slug>.png  every maker's logo, once, for all brands
    _shared/catalogue/              official images found on a maker's own site:
        catalogue.json              what each one is and where it came from (in git)
        images/<maker>/<model>__N   the files (not in git: they are the maker's).
                                    Master copy on Drive in Catalogue/<maker>/ (CATALOGUE_DRIVE_ID);
                                    pull_catalogue() fills any machine or the live volume.
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

# Drive folder "Catalogue" inside the shared parent, beside Stick and Swing Shack. Created 2026-11-03.
CATALOGUE_DRIVE_ID = "1Aj6BzbUFVvpmG3g-fpQuHc0l-xBxIX9R"

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


def _picture_roots(root: Optional[Path]) -> List[Path]:
    """Where a catalogue picture may be: the live volume first, then the repo copy."""
    if root:
        return [root]
    import os
    roots = []
    data_dir = os.environ.get("DATA_DIR", "").strip()
    if data_dir:
        roots.append(Path(data_dir) / "brand-directory" / "_shared" / "catalogue")
    roots.append(CATALOGUE)
    return roots


def catalogue_bytes(row: Dict[str, Any], root: Optional[Path] = None) -> Optional[bytes]:
    for base in _picture_roots(root):
        p = base / row["file"]
        if p.is_file():
            return p.read_bytes()
    return None


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


def to_upload(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Catalogue pictures saved here but not yet on Drive, with the Drive subfolder each goes in."""
    out = []
    for row in load_catalogue(root):
        if not row.get("drive_id"):
            parts = row["file"].split("/")
            out.append({**row, "drive_folder": parts[1] if len(parts) > 2 else ""})
    return out


def mark_on_drive(file: str, drive_id: str, root: Optional[Path] = None) -> bool:
    rows = load_catalogue(root)
    for row in rows:
        if row["file"] == file:
            row["drive_id"] = drive_id
            _save_catalogue(rows, root)
            return True
    raise KeyError(file)


def backfill_from_photo_map(brand_id: str, images: Optional[Path] = None,
                            entries: Optional[List[Dict[str, Any]]] = None,
                            root: Optional[Path] = None) -> Dict[str, Any]:
    """File every maker image already on a brand's photo map into the catalogue, once.

    Each catalogue row lists the brand photos it backs in `used_by` ("<brand>:<file>")."""
    from _lib import photo_map as pm
    images = images or pm.images_dir(brand_id)
    entries = pm.load(brand_id) if entries is None else entries
    got: Dict[str, Any] = {"added": 0, "already": 0, "missing": []}
    for e in entries:
        if e.get("source") != "official-site":
            continue
        p = images / e["file"]
        if not p.is_file():
            got["missing"].append(e["file"])
            continue
        data = p.read_bytes()
        url = str(e.get("image_url") or "")
        sha = hashlib.sha256(data).hexdigest()
        user = f"{brand_id}:{e['file']}"
        known = any(r.get("image_url") == url or r.get("sha256") == sha for r in load_catalogue(root))
        page = str(e.get("source_url") or "")
        maker = maker_for_url(url) or maker_for_url(page) or "unknown"
        row = add_to_catalogue(maker, e.get("product") or "", page, url, data, p.suffix.lower(), root=root,
                               exact_build=e.get("exact_build", True))
        rows = load_catalogue(root)
        for r in rows:
            if r["file"] == row["file"] and user not in r.setdefault("used_by", []):
                r["used_by"].append(user)
        _save_catalogue(rows, root)
        got["already" if known else "added"] += 1
    return got


def link_drive_ids(folder_id: str = CATALOGUE_DRIVE_ID, root: Optional[Path] = None, lister=None) -> Dict[str, int]:
    """Record the Drive id of each catalogue picture someone has put in Drive Catalogue/<maker>/."""
    if lister is None:
        from _lib import google_drive as gd
        lister = gd.list_public_folder
    on_drive = {}
    for entry in lister(folder_id):
        folder = str(entry.get("folder") or "").strip("/")
        on_drive[f"images/{folder}/{entry['name']}" if folder else f"images/{entry['name']}"] = entry["id"]
    rows = load_catalogue(root)
    linked = 0
    for r in rows:
        if not r.get("drive_id") and r["file"] in on_drive:
            r["drive_id"] = on_drive[r["file"]]
            linked += 1
    if linked:
        _save_catalogue(rows, root)
    return {"linked": linked, "still_to_upload": sum(1 for r in rows if not r.get("drive_id"))}


def pull_catalogue(folder_id: str = CATALOGUE_DRIVE_ID, data_dir: Optional[Path] = None,
                   lister=None, downloader=None) -> Dict[str, Any]:
    """Copy Drive Catalogue/<maker>/<file> to <data_dir>/brand-directory/_shared/catalogue/images/.

    data_dir is the directory that CONTAINS brand-directory/ (the repo's data/ locally, $DATA_DIR on live).
    Existing files are kept; nothing is deleted."""
    if lister is None or downloader is None:
        from _lib import google_drive as gd
        lister = lister or gd.list_public_folder
        downloader = downloader or gd.download_public_file
        is_image = gd.is_public_drive_image
    else:
        is_image = lambda e: str(e.get("mime") or "").startswith("image/")  # noqa: E731
    base = Path(data_dir) if data_dir else BD.parent
    images = (base / "brand-directory" / "_shared" / "catalogue" / "images").resolve()
    got: Dict[str, Any] = {"downloaded": [], "skipped_existing": [], "errors": []}
    for entry in lister(folder_id):
        if not is_image(entry):
            continue
        folder = str(entry.get("folder") or "").strip("/")
        key = f"{folder}/{entry['name']}" if folder else entry["name"]
        dest = (images / key).resolve()
        try:
            dest.relative_to(images)
        except ValueError:
            got["errors"].append({"file": key, "error": "path escape"})
            continue
        if dest.is_file() and dest.stat().st_size > 0:
            got["skipped_existing"].append(key)
            continue
        try:
            downloader(entry["id"], dest)
            got["downloaded"].append(key)
        except Exception as e:  # noqa: BLE001
            got["errors"].append({"file": key, "error": str(e)})
    return got


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
