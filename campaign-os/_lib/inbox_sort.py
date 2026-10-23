"""inbox_sort.py — turn files dropped in a brand's Drive Inbox into a tidy folder and file name.

Staff drop anything into Inbox with any name. A person says what each file is (product, facility,
service, video); this module turns that into the destination folder and the final name, following
the Drive naming rules:

    Products/SKU__view.jpg
    Location/<area>/YYYY-MM-DD__<area>__<what>__NN.jpg
    Services/YYYY-MM-DD__<service>__<what>__NN.jpg
    Video/1-raw/YYYY-MM-DD__<topic>__<what>__NN.mp4

Nothing here touches Drive. The plan is saved beside the photo map; the move itself is done by
whoever applies it (Claude, through the Drive connector, or a person), then marked "moved".
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".webm"}
KINDS = ("product", "facility", "service", "video")
AREAS = ("bays", "lounge-bar", "shop-floor", "fitting-area", "exterior", "team", "events")
STATUSES = ("planned", "moved")

_DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)")
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SortError(ValueError):
    pass


def _map_path(brand_id: str) -> Path:
    from _lib.marketing_lanes import _products_dir
    return _products_dir(brand_id) / "inbox-map.json"


def load(brand_id: str) -> List[Dict[str, Any]]:
    p = _map_path(brand_id)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("entries", [])
    except Exception:
        return []


def _save(brand_id: str, entries: List[Dict[str, Any]]) -> None:
    _map_path(brand_id).write_text(
        json.dumps({"brand_id": brand_id, "version": 1, "entries": entries}, indent=1), encoding="utf-8")


def slug(text: str) -> str:
    """lowercase, spaces and punctuation to single dashes."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (text or "").lower())).strip("-")


def date_from_name(name: str) -> Optional[str]:
    """2026-10-19 from IMG_20261019_..., PXL_20261019..., 'WhatsApp Image 2026-10-19 at ...'."""
    m = _DATE_IN_NAME.search(name)
    if not m:
        return None
    try:
        return datetime(int(m[1]), int(m[2]), int(m[3])).date().isoformat()
    except ValueError:
        return None


def date_from_exif(path: Path) -> Optional[str]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            raw = (im.getexif().get_ifd(0x8769).get(0x9003)) or im.getexif().get(0x0132)
        if raw:
            return datetime.strptime(str(raw)[:10], "%Y:%m:%d").date().isoformat()
    except Exception:
        return None
    return None


def guess(name: str, path: Optional[Path], sku_to_product: Dict[str, str]) -> Dict[str, Any]:
    """What can be known without a person: the kind where the name says so, and a date."""
    ext = Path(name).suffix.lower()
    stem = Path(name).stem
    out: Dict[str, Any] = {"kind": None, "sku": None, "view": None, "date": None}
    if ext in VIDEO_EXT:
        out["kind"] = "video"
    elif "__" in stem:
        sku, _, view = stem.partition("__")
        hits = [s for s in sku_to_product if re.sub(r"[^a-z0-9]", "", s.lower()) == re.sub(r"[^a-z0-9]", "", sku.lower())]
        if len(hits) == 1:
            out.update(kind="product", sku=hits[0], view=slug(view) or "front")
    out["date"] = date_from_name(name) or (date_from_exif(path) if path and path.exists() else None)
    return out


def _next_number(entries: List[Dict[str, Any]], prefix: str) -> int:
    used = [e.get("new_name", "") for e in entries if e.get("new_name", "").startswith(prefix)]
    return len(used) + 1


def plan_name(entries: List[Dict[str, Any]], file: str, kind: str, *, date: str = "", area: str = "",
              what: str = "", sku: str = "", sku_to_product: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Destination folder and final file name for one Inbox file. Raises SortError when something is missing."""
    ext = Path(file).suffix.lower()
    if kind not in KINDS:
        raise SortError("kind must be one of: " + ", ".join(KINDS))
    what = slug(what)
    if not what:
        raise SortError("say what it shows, in a few words (for example bay-3-evening)")
    if kind == "product":
        if not sku:
            raise SortError("a product photo needs its SKU")
        if sku_to_product is not None and sku not in sku_to_product:
            raise SortError("that SKU is not in the saved stock list")
        return {"dest_folder": "Products", "new_name": f"{sku}__{what}{ext}"}
    if not re.fullmatch(r"20\d{2}-[01]\d-[0-3]\d", date or ""):
        raise SortError("give the date it was shot, as year-month-day")
    if kind == "facility":
        if area not in AREAS:
            raise SortError("area must be one of: " + ", ".join(AREAS))
        folder, part = f"Location/{area}", area
    else:
        part = slug(area)
        if not part:
            raise SortError("say which service" if kind == "service" else "say the video's topic")
        folder = "Services" if kind == "service" else "Video/1-raw"
    prefix = f"{date}__{part}__{what}__"
    return {"dest_folder": folder, "new_name": f"{prefix}{_next_number(entries, prefix):02d}{ext}"}


def save_plan(brand_id: str, file: str, plan: Dict[str, str], kind: str, drive_id: str = "") -> Dict[str, Any]:
    entries = load(brand_id)
    entries = [e for e in entries if e["file"] != file]
    entry = {"file": file, "kind": kind, **plan, "drive_id": drive_id, "status": "planned",
             "planned_on": datetime.now(timezone.utc).isoformat()}
    entries.append(entry)
    _save(brand_id, entries)
    return entry


def set_status(brand_id: str, file: str, status: str) -> bool:
    if status not in STATUSES:
        raise SortError("status must be one of: " + ", ".join(STATUSES))
    entries = load(brand_id)
    hit = False
    for e in entries:
        if e["file"] == file:
            e["status"] = status
            hit = True
    if hit:
        _save(brand_id, entries)
    return hit


def inbox_files(brand_id: str, images_root: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Files in the brand's Inbox: images on disk, videos and others the ingest skipped (from the manifest)."""
    out: Dict[str, Dict[str, Any]] = {}
    inbox = images_root / "Inbox"
    if inbox.exists():
        for f in sorted(inbox.rglob("*")):
            if f.is_file() and f.suffix.lower() in IMAGE_EXT:
                rel = f.relative_to(images_root).as_posix()
                drive_id = (manifest.get("images", {}).get(rel) or {}).get("drive_id", "")
                out[rel] = {"file": rel, "path": f, "drive_id": drive_id, "viewable": f.suffix.lower() != ".heic"}
    for s in manifest.get("skipped", []):
        folder = (s.get("folder") or "").strip("/")
        if folder == "Inbox" or folder.startswith("Inbox/"):
            rel = f"{folder}/{s['name']}"
            if Path(s["name"]).suffix.lower() in VIDEO_EXT:
                out.setdefault(rel, {"file": rel, "path": None, "drive_id": s.get("drive_id", ""), "viewable": False})
    return list(out.values())
