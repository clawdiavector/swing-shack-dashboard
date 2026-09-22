"""Archive rotten JSON on $DATA_DIR in place (ignore flag, no deletes)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import describe_exception
from ..freshness_heuristic import (
    ARCHIVE_META_KEY,
    STALE_DAYS,
    classify,
    is_archived_ignored,
    walk_data_json_files,
)
from ..layer1._io import atomic_write, data_dir, utc_now_iso

MANIFEST_REL = "archive/manifest.json"
MANIFEST_SCHEMA = "campaign-os/data-archive/v1"


def _archive_date_folder() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _archive_meta(*, age_days: float, relocated_to: str | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {
        "ignored": True,
        "archived_at": utc_now_iso(),
        "age_days_at_archive": age_days,
        "reason": "rotten",
    }
    if relocated_to:
        block["relocated_to"] = relocated_to
    return block


def _load_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_REL
    if not path.is_file():
        return {"schema": MANIFEST_SCHEMA, "generated_at": utc_now_iso(), "entries": []}
    try:
        with path.open(encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError):
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    entries = doc.get("entries")
    if not isinstance(entries, list):
        entries = []
    return {
        "schema": MANIFEST_SCHEMA,
        "generated_at": utc_now_iso(),
        "entries": [e for e in entries if isinstance(e, dict)],
    }


def _write_json_path(abs_path: Path, obj: Any) -> None:
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=abs_path.parent, prefix=f".{abs_path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, abs_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _archive_dict_in_place(abs_path: Path, parsed: dict[str, Any], age_days: float) -> None:
    if is_archived_ignored(parsed):
        return
    parsed[ARCHIVE_META_KEY] = _archive_meta(age_days=age_days)
    _write_json_path(abs_path, parsed)


def _archive_array_relocate(
    root: Path,
    abs_path: Path,
    rel_path: str,
    age_days: float,
    *,
    date_folder: str,
) -> str:
    dest_rel = f"archive/{date_folder}/{rel_path.replace(os.sep, '/')}"
    dest_abs = root / dest_rel
    dest_abs.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(abs_path, dest_abs)
    stub = {ARCHIVE_META_KEY: _archive_meta(age_days=age_days, relocated_to=dest_rel)}
    _write_json_path(abs_path, stub)
    return dest_rel


def run(*, stale_days: int = STALE_DAYS) -> dict[str, Any]:
    """Flag or relocate JSON files older than stale_days * 3 (rotten only)."""
    try:
        root = data_dir()
        if not root.is_dir():
            return {"ok": False, "error": "data_dir missing"}

        archived = 0
        skipped = 0
        writes: list[str] = []
        manifest = _load_manifest(root)
        entries_by_path: dict[str, dict[str, Any]] = {
            str(e.get("path")): e for e in manifest["entries"] if e.get("path")
        }
        date_folder = _archive_date_folder()
        rotten_cutoff = stale_days * 3

        for abs_s, rel_s in walk_data_json_files(root):
            abs_path = Path(abs_s)
            rel_path = rel_s.replace("\\", "/")
            try:
                with abs_path.open(encoding="utf-8") as fh:
                    parsed = json.load(fh)
            except (OSError, json.JSONDecodeError):
                skipped += 1
                continue

            if is_archived_ignored(parsed):
                skipped += 1
                continue

            try:
                mtime_ms = abs_path.stat().st_mtime * 1000.0
            except OSError:
                skipped += 1
                continue

            staleness, _iso, _raw, age_days = classify(parsed, mtime_ms, stale_days=stale_days)
            if staleness != "rotten" or age_days is None or age_days <= rotten_cutoff:
                skipped += 1
                continue

            relocated_to: str | None = None
            if isinstance(parsed, list):
                relocated_to = _archive_array_relocate(
                    root,
                    abs_path,
                    rel_path,
                    age_days,
                    date_folder=date_folder,
                )
                writes.append(relocated_to)
            elif isinstance(parsed, dict):
                _archive_dict_in_place(abs_path, parsed, age_days)
            else:
                skipped += 1
                continue

            archived += 1
            entry = {
                "path": rel_path,
                "archived_at": utc_now_iso(),
                "reason": "rotten",
                "age_days_at_archive": age_days,
            }
            if relocated_to:
                entry["relocated_to"] = relocated_to
            entries_by_path[rel_path] = entry

        manifest["entries"] = sorted(entries_by_path.values(), key=lambda e: str(e.get("path", "")))
        manifest["generated_at"] = utc_now_iso()
        atomic_write(MANIFEST_REL, manifest)
        writes.append(MANIFEST_REL)

        return {
            "ok": True,
            "archived": archived,
            "skipped": skipped,
            "writes": sorted(set(writes)),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": describe_exception(exc)}
