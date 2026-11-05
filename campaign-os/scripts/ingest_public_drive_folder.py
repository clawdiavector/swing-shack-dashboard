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

# Per-brand ingest roots. The folder humans share is the parent of these two,
# not a third brand. Roles, the parent id, and the subsets that must not be
# ingested as roots live in `.claude/skills/campaign-os-map/SKILL.md`
# ("Brand imagery"). Keep this table and that section in step.
# `drive.map_names_roots` fails if the skill drops an id from this table.
#
#   stick        306 images  Location/{In Store Photos for walkthrough,Photos of iron sets}, Other, Products, Services
#   swing-shack  136 images  Products, Services, Swing Shack RAW, Others
#
# Stick also reads its Shot List (BRAND_EXTRA_SOURCES below): 560 images by line,
# filed under images/Shot List/.
#
# A third id, 1FYeac0rVLezYFcS_02Yqsn7fOw1ecghd, appears in
# tests/test_google_drive_public.py as SERVICES_FOLDER_ID. It is NOT a third
# root: it is Stick's own Services subfolder (all 34 of its images are a strict
# subset of the Stick root) and exists only as a parse fixture. Do not ingest it
# directly or its files land at the images root instead of under Services/.
BRAND_PUBLIC_ROOTS = {
    "stick": "1k5icaxY3AKBD9z2-oIO6i42PUnq1gYUG",
    "swing-shack": "1n9pHD6hwr7oEfRBAGBriRrsqv_I-qGge",
    # "Bagdrop" (Five Friday), link-viewable since 2026-11-05: webp edits (own
    # club cut-outs), New Logo, and Generic Bagdrop, which is skipped below.
    "bag-drop": "1bBToPcp6xKchcATcyrmIEpbXnUVVaOnc",
}

# Folders inside a root that are never ingested. Generic Bagdrop holds club images
# saved from other websites (Amazon, demo shops, retailers), which are not cleared
# to use (Christelle, 2026-11-05); the scout fetches maker-site images instead.
BRAND_SKIP_FOLDERS = {
    "bag-drop": ("Generic Bagdrop",),
}


def skipped_folders(brand: str) -> tuple[str, ...]:
    return BRAND_SKIP_FOLDERS.get(brand, ())

# Back-compat for callers that imported the old single-brand constant.
STICK_PUBLIC_ROOT = BRAND_PUBLIC_ROOTS["stick"]

# Folders a brand owns outside its root, read where they live and filed under
# images/<label>/ (Christelle, 2026-11-05). Stick's Shot List belongs to
# info@stickgolf.co.za; copying its ~6 GB into the Five Friday root would fill that
# Drive and drift from new shots. Never put a brand root or the catalogue here.
BRAND_EXTRA_SOURCES = {
    "stick": {"Shot List": "11VFWJOrRi6B3MYjCB78Qew4QXe1D7NSx"},
}


def brand_sources(brand: str) -> list[tuple[str, str]]:
    """[(folder label, Drive id)] to ingest for a brand: its root first (label ""), then extras."""
    root = BRAND_PUBLIC_ROOTS.get(brand)
    if not root:
        return []
    return [("", root)] + list(BRAND_EXTRA_SOURCES.get(brand, {}).items())


# iPhone photos arrive as HEIC, which browsers and the dissector cannot open unless
# pillow-heif is installed. They are filed as JPEG instead (Christelle, 2026-11-05);
# the original stays on Drive. Long edge capped at 4000px, quality 90.
_HEIC_SUFFIXES = {".heic", ".heif"}


def _is_heic(name: str) -> bool:
    return Path(name).suffix.lower() in _HEIC_SUFFIXES


def _heic_to_jpeg(src: Path) -> Path:
    """Write src as a .jpg beside it, delete the HEIC, return the .jpg path."""
    import pillow_heif
    from PIL import Image, ImageOps

    pillow_heif.register_heif_opener()
    dst = src.with_suffix(".jpg")
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((4000, 4000))
        im.save(dst, "JPEG", quality=90, optimize=True)
    src.unlink()
    return dst


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
    data_dir: Path | None = None,
    folder_prefix: str = "",
) -> dict:
    # data_dir names the directory that CONTAINS brand-directory/. Locally that
    # is <repo>/data; on Railway it is the volume at $DATA_DIR, which the app
    # resolves before the bundled repo copy. Passing it lets prod refill its own
    # volume from Drive instead of depending on images being committed to git.
    root = repo_root or REPO_ROOT
    base = Path(data_dir) if data_dir else (root / "data")
    brand_dir = base / "brand-directory" / brand
    images_root = brand_dir / "images"
    manifest_path = brand_dir / "ingest-manifest.json"
    source_path = brand_dir / "source.json"
    bible_path = brand_dir / "bible-visual.json"
    bible = bible_path if bible_path.exists() else None

    manifest = _load_manifest(manifest_path, brand)
    manifest.setdefault("skipped", [])
    known_md5 = _existing_md5s(manifest)

    all_entries = gd.list_public_folder(folder_id)
    skip = skipped_folders(brand)
    skipped_folder = [
        e for e in all_entries
        if any((e.get("folder") or "") == f or (e.get("folder") or "").startswith(f + "/") for f in skip)
    ]
    if skipped_folder:
        all_entries = [e for e in all_entries if e not in skipped_folder]
    prefix = folder_prefix.strip("/")
    if prefix:
        all_entries = [
            {**e, "folder": f"{prefix}/{e['folder']}".rstrip("/") if e.get("folder") else prefix}
            for e in all_entries
        ]
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

        # A HEIC filed earlier now lives as its .jpg.
        if _is_heic(name) and dest.with_suffix(".jpg").exists():
            skipped_dedupe.append(key)
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
            row = {}
            if _is_heic(name):
                # A file the reader cannot open is kept as it came, not lost.
                try:
                    dest = _heic_to_jpeg(dest)
                    key = _manifest_key(folder, dest.name)
                    row["converted_from"] = name
                except Exception as exc:  # noqa: BLE001
                    row["convert_error"] = str(exc)
            manifest["images"][key] = {
                "drive_id": entry["id"],
                "size": str(dest.stat().st_size),
                "md5": md5,
                "modified": None,
                "folder": folder,
                "ingested": time.time(),
                **row,
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

        tag_result = tag_directory(brand, base_dir=base / "brand-directory")
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
        "skipped_folder": len(skipped_folder),
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


def convert_existing_heic(
    brand: str,
    *,
    repo_root: Path | None = None,
    data_dir: Path | None = None,
) -> dict:
    """Convert HEIC files already on disk to JPEG, move their manifest rows and re-dissect them."""
    root = repo_root or REPO_ROOT
    base = Path(data_dir) if data_dir else (root / "data")
    brand_dir = base / "brand-directory" / brand
    images_root = brand_dir / "images"
    manifest_path = brand_dir / "ingest-manifest.json"
    bible_path = brand_dir / "bible-visual.json"
    bible = bible_path if bible_path.exists() else None
    manifest = _load_manifest(manifest_path, brand) if manifest_path.exists() else {"images": {}}
    images = manifest.setdefault("images", {})

    converted: list[str] = []
    errors: list[dict] = []
    for src in sorted(p for p in images_root.rglob("*") if p.is_file() and _is_heic(p.name)):
        old_key = src.relative_to(images_root).as_posix()
        try:
            dst = _heic_to_jpeg(src)
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": old_key, "error": str(exc)})
            continue
        new_key = dst.relative_to(images_root).as_posix()
        row = images.pop(old_key, None)
        if row is not None:
            row["size"] = str(dst.stat().st_size)
            row["converted_from"] = src.name
            images[new_key] = row
        try:
            dna = dissect(dst, bible)
            (dst.parent / f"{dst.stem}.visual-dna.json").write_text(json.dumps(dna, indent=2))
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": new_key, "error": f"dissect: {exc}"})
        converted.append(new_key)

    if converted:
        manifest_path.write_text(json.dumps(manifest, indent=2))
        tag_directory(brand, base_dir=base / "brand-directory")
    return {"brand": brand, "converted": converted, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest public Google Drive folder")
    parser.add_argument("--brand", required=True)
    parser.add_argument(
        "--folder-id",
        default=None,
        help="Override the brand's canonical root from BRAND_PUBLIC_ROOTS.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory CONTAINING brand-directory/. Defaults to <repo>/data. "
             "On Railway pass $DATA_DIR (/data/campaign-os) so the ingest fills "
             "the volume, which the image routes resolve before the repo copy.",
    )
    parser.add_argument(
        "--convert-existing-heic",
        action="store_true",
        help="Convert HEIC files already on disk to JPEG and re-dissect them, then stop.",
    )
    args = parser.parse_args()

    if args.convert_existing_heic:
        got = convert_existing_heic(
            args.brand, data_dir=Path(args.data_dir) if args.data_dir else None
        )
        print(json.dumps({**got, "converted": len(got["converted"])}, indent=2))
        return 1 if got["errors"] else 0

    # Never fall back to another brand's root: that silently files one brand's
    # imagery under the other, and md5 dedupe is per-brand so nothing catches it.
    sources = [("", args.folder_id)] if args.folder_id else brand_sources(args.brand)
    if not sources:
        parser.error(
            f"no canonical Drive root for brand {args.brand!r}. "
            f"Known: {', '.join(sorted(BRAND_PUBLIC_ROOTS))}. "
            f"Pass --folder-id explicitly to ingest something else."
        )

    failed = False
    for prefix, folder_id in sources:
        summary = run_ingest(
            args.brand,
            folder_id,
            limit=args.limit,
            dry_run=args.dry_run,
            data_dir=Path(args.data_dir) if args.data_dir else None,
            folder_prefix=prefix,
        )
        print(json.dumps(summary, indent=2))
        failed = failed or bool(summary.get("download_errors"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
