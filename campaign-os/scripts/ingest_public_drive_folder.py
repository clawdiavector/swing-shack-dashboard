#!/usr/bin/env python3
"""Ingest images from a public Google Drive folder (no OAuth).

Writes under data/brand-directory/<brand>/images/<Folder>/<filename>,
updates ingest-manifest.json, source.json, runs dissector + product tagging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import google_drive as gd  # noqa: E402
from _lib.image_dissector import dissect  # noqa: E402
from _lib.visual_dna_query import tag_directory  # noqa: E402

STICK_PUBLIC_ROOT = "1k5icaxY3AKBD9z2-oIO6i42PUnq1gYUG"


def _manifest_key(folder: str, name: str) -> str:
    folder = (folder or "").strip("/")
    return f"{folder}/{name}" if folder else name


def _load_manifest(path: Path, brand: str) -> dict:
    if path.exists():
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    return {"brand": brand, "images": {}, "skipped": []}


def _load_source(path: Path, brand: str) -> dict:
    if path.exists():
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    return {"brand": brand, "ingestions": []}


def _existing_md5s(manifest: dict) -> set[str]:
    out: set[str] = set()
    for entry in manifest.get("images", {}).values():
        md5 = entry.get("md5")
        if md5:
            out.add(md5.lower())
    return out


def run_ingest(
    brand: str,
    folder_id: str,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    repo_root: Path | None = None,
) -> dict:
    root = repo_root or REPO_ROOT
    brand_dir = root / "data" / "brand-directory" / brand
    images_root = brand_dir / "images"
    manifest_path = brand_dir / "ingest-manifest.json"
    source_path = brand_dir / "source.json"
    bible_path = brand_dir / "bible-visual.json"
    bible = bible_path if bible_path.exists() else None

    manifest = _load_manifest(manifest_path, brand)
    manifest.setdefault("skipped", [])
    known_md5 = _existing_md5s(manifest)

    all_entries = gd.list_public_folder(folder_id)
    images = [e for e in all_entries if gd.is_public_drive_image(e)]
    skipped_non_image = [e for e in all_entries if not gd.is_public_drive_image(e)]

    if limit is not None:
        images = images[:limit]

    downloaded: list[str] = []
    skipped_dedupe: list[str] = []
    download_errors: list[dict] = []
    dissect_errors: list[dict] = []
    new_for_dissect: list[Path] = []

    import requests

    session = requests.Session()

    for entry in images:
        folder = entry.get("folder") or ""
        name = entry["name"]
        key = _manifest_key(folder, name)
        dest = images_root / folder / name if folder else images_root / name
        dest = dest.resolve()
        try:
            dest.relative_to(images_root.resolve())
        except ValueError:
            download_errors.append({"file": key, "error": "path escape"})
            continue

        if dry_run:
            downloaded.append(key)
            continue

        if dest.exists() and dest.stat().st_size > 0:
            md5 = hashlib.md5(dest.read_bytes()).hexdigest()
            if md5.lower() in known_md5:
                skipped_dedupe.append(key)
                continue

        try:
            gd.download_public_file(entry["id"], dest, session=session)
            md5 = hashlib.md5(dest.read_bytes()).hexdigest()
            if md5.lower() in known_md5:
                skipped_dedupe.append(key)
                continue
            known_md5.add(md5.lower())
            manifest["images"][key] = {
                "drive_id": entry["id"],
                "size": str(dest.stat().st_size),
                "md5": md5,
                "modified": None,
                "folder": folder,
                "ingested": time.time(),
            }
            downloaded.append(key)
            new_for_dissect.append(dest)
        except Exception as exc:  # noqa: BLE001
            download_errors.append({"file": key, "error": str(exc)})
            if dest.exists():
                dest.unlink(missing_ok=True)

    for entry in skipped_non_image:
        folder = entry.get("folder") or ""
        key = _manifest_key(folder, entry["name"])
        skip_row = {
            "drive_id": entry["id"],
            "name": entry["name"],
            "folder": folder,
            "mime": entry.get("mime"),
            "reason": "non_image",
        }
        if not any(
            s.get("drive_id") == skip_row["drive_id"] for s in manifest["skipped"]
        ):
            manifest["skipped"].append(skip_row)

    re_dissected = 0
    if not dry_run:
        for local_p in new_for_dissect:
            try:
                dna = dissect(local_p, bible)
                dna_p = local_p.parent / f"{local_p.stem}.visual-dna.json"
                dna_p.write_text(json.dumps(dna, indent=2))
                re_dissected += 1
            except Exception as exc:  # noqa: BLE001
                dissect_errors.append({"file": str(local_p), "error": str(exc)})

        manifest_path.write_text(json.dumps(manifest, indent=2))

        source = _load_source(source_path, brand)
        counts_by_folder: dict[str, int] = {}
        for key in downloaded:
            folder = key.split("/", 1)[0] if "/" in key else ""
            counts_by_folder[folder] = counts_by_folder.get(folder, 0) + 1
        source["ingestions"].append(
            {
                "date": date.today().isoformat(),
                "method": "public_folder_http",
                "folder_id": folder_id,
                "files_downloaded": len(downloaded),
                "files_skipped_dedupe": len(skipped_dedupe),
                "files_skipped_non_image": len(skipped_non_image),
                "download_errors": len(download_errors),
                "counts_by_folder": counts_by_folder,
                "dry_run": False,
            }
        )
        source_path.write_text(json.dumps(source, indent=2))

        tag_result = tag_directory(brand, base_dir=root / "data" / "brand-directory")
    else:
        tag_result = {"skipped": "dry_run"}

    folder_totals: dict[str, int] = {}
    for e in all_entries:
        if not gd.is_public_drive_image(e):
            continue
        f = e.get("folder") or "(root)"
        folder_totals[f] = folder_totals.get(f, 0) + 1

    return {
        "brand": brand,
        "folder_id": folder_id,
        "dry_run": dry_run,
        "drive_listed": len(all_entries),
        "images_eligible": len([e for e in all_entries if gd.is_public_drive_image(e)]),
        "folder_totals": folder_totals,
        "downloaded": len(downloaded),
        "skipped_dedupe": len(skipped_dedupe),
        "skipped_non_image": len(skipped_non_image),
        "download_errors": download_errors,
        "re_dissected": re_dissected,
        "dissect_errors": dissect_errors,
        "tag_summary": tag_result,
        "skipped_ai": [
            e["name"]
            for e in skipped_non_image
            if str(e.get("name", "")).lower().endswith(".ai")
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest public Google Drive folder")
    parser.add_argument("--brand", required=True)
    parser.add_argument("--folder-id", default=STICK_PUBLIC_ROOT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary = run_ingest(
        args.brand,
        args.folder_id,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2))
    return 1 if summary.get("download_errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
