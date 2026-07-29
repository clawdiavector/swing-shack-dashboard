#!/usr/bin/env python3
"""
weekly_drive_scrape.py — Weekly Drive audit + ingest cron.

Runs every Monday 06:00 SAST (after GMB rotation). Does three things:
1. Re-walk each brand's configured Drive folder
2. md5-compare against local manifest — only download new/changed files
3. Re-dissect new files
4. Re-tag products
5. Report summary to /tmp/co-nightshift/weekly-scrape-{date}.md
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard")
sys.path.insert(0, str(REPO / "campaign-os"))
from _lib import google_drive as gd
from _lib.image_dissector import dissect
from _lib.visual_dna_query import tag_directory

# Brand → Drive folder ID. Add brands here as we onboard more folders.
BRAND_FOLDERS = {
    "swing-shack": "1n9pHD6hwr7oEfRBAGBriRrsqv_I-qGge",
    # "stick":      "1hnkOUDX4mthQFcCktS5Caw7C7QU1ihH3",   # Stick Golf folder (separate ownership)
    # "bag-drop":   "<to be discovered>",
}


def walk_drive(drive, folder_id):
    """Recursively list every image file under a folder."""
    def walk(fid, rel=""):
        items = drive.files().list(
            q=f"'{fid}' in parents and trashed=false",
            fields="files(id,name,mimeType,size,modifiedTime,md5Checksum)",
            pageSize=200,
        ).execute().get("files", [])
        out = []
        for f in items:
            if f["mimeType"] == "application/vnd.google-apps.folder":
                out.extend(walk(f["id"], f"{rel}{f['name']}/"))
            elif f["mimeType"].startswith("image/"):
                f["rel_path"] = f"{rel}{f['name']}"
                out.append(f)
        return out
    return walk(folder_id)


def audit_brand(brand_id, folder_id, drive):
    """Run scrape + dissect for a single brand. Returns summary dict."""
    import hashlib
    from googleapiclient.http import MediaIoBaseDownload

    print(f"\n=== {brand_id} (folder {folder_id}) ===", flush=True)
    images_dir = REPO / "data/brand-directory" / brand_id / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    bible_path = REPO / "data/brand-directory" / brand_id / "bible-visual.json"
    manifest_path = REPO / "data/brand-directory" / brand_id / "ingest-manifest.json"

    # Audit: also detect "missed it" folders — Drive folders with content but no
    # corresponding brand directory.
    drive_root_items = drive.files().list(
        q="mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id,name,owners)",
        pageSize=100,
    ).execute().get("files", [])
    known_folders = set(BRAND_FOLDERS.values())
    missed_folders = [
        {"id": f["id"], "name": f["name"], "owners": [o.get("emailAddress") for o in f.get("owners", [])]}
        for f in drive_root_items
        if f["id"] not in known_folders
        and any(name_part in f["name"].lower() for name_part in ["stick", "bag", "drop", "swing", "shack"])
    ]

    # Discover Drive state
    files = walk_drive(drive, folder_id)
    print(f"  Drive files: {len(files)}", flush=True)

    # Local state
    existing_md5 = set()
    existing_dna_files = set()
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        for entry in existing.get("images", {}).values():
            if entry.get("md5"):
                existing_md5.add(entry["md5"])

    # Discover what's NEW or CHANGED
    new_downloads = []
    skipped_existing = 0
    for f in files:
        if f.get("md5Checksum") and f["md5Checksum"].lower() in existing_md5:
            skipped_existing += 1
            continue
        new_downloads.append(f)

    print(f"  New/changed: {len(new_downloads)} (skipped {skipped_existing} unchanged)", flush=True)

    # Download new
    download_errors = []
    for f in new_downloads:
        out = images_dir / f["name"]
        try:
            req = drive.files().get_media(fileId=f["id"])
            with open(out, "wb") as fh:
                dl = MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _, done = dl.next_chunk()
        except Exception as e:
            download_errors.append({"file": f["name"], "error": str(e)})
            if out.exists():
                out.unlink()

    # Update manifest
    manifest = {"brand": brand_id, "images": {}, "errors": [], "last_scrape": time.time()}
    for f in files:
        local_p = images_dir / f["name"]
        if local_p.exists():
            md5 = hashlib.md5(local_p.read_bytes()).hexdigest()
            manifest["images"][f["name"]] = {
                "drive_id": f["id"],
                "size": f.get("size"),
                "md5": md5,
                "modified": f.get("modifiedTime"),
                "ingested": time.time(),
            }
    if download_errors:
        manifest["errors"] = download_errors
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Re-dissect new files
    bible = bible_path if bible_path.exists() else None
    re_dissected = 0
    dissect_errors = []
    for f in new_downloads:
        local_p = images_dir / f["name"]
        if not local_p.exists():
            continue
        try:
            dna = dissect(local_p, bible)
            dna_p = images_dir / f"{local_p.stem}.visual-dna.json"
            dna_p.write_text(json.dumps(dna, indent=2))
            re_dissected += 1
        except Exception as e:
            dissect_errors.append({"file": f["name"], "error": str(e)})

    # Re-tag with products
    tag_result = tag_directory(brand_id)

    # Optionally: re-run full directory dissector if there are missing .visual-dna.json files
    missing_dna = []
    for f in files:
        local_p = images_dir / f["name"]
        if not local_p.exists():
            continue
        dna_p = images_dir / f"{local_p.stem}.visual-dna.json"
        if not dna_p.exists():
            missing_dna.append(f["name"])

    if missing_dna:
        print(f"  Missing DNA for {len(missing_dna)} files — backfilling", flush=True)
        for fn in missing_dna:
            local_p = images_dir / fn
            try:
                dna = dissect(local_p, bible)
                dna_p = images_dir / f"{local_p.stem}.visual-dna.json"
                dna_p.write_text(json.dumps(dna, indent=2))
            except Exception as e:
                dissect_errors.append({"file": fn, "error": str(e)})

    summary = {
        "brand": brand_id,
        "folder_id": folder_id,
        "drive_files_total": len(files),
        "new_or_changed": len(new_downloads),
        "skipped_existing": skipped_existing,
        "download_errors": download_errors,
        "re_dissected": re_dissected,
        "dissect_errors": dissect_errors,
        "tag_summary": tag_result,
        "missed_folders_detected": missed_folders,
    }
    print(f"  → {summary['re_dissected']} re-dissected, {len(tag_result.get('products_found', {}))} products", flush=True)
    return summary


def main():
    print(f"Weekly Drive scrape starting at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    drive = gd.connect()
    if not drive:
        print("FATAL: Drive not connected")
        sys.exit(1)

    summaries = []
    for brand_id, folder_id in BRAND_FOLDERS.items():
        try:
            summary = audit_brand(brand_id, folder_id, drive)
            summaries.append(summary)
        except Exception as e:
            print(f"  FAIL: {brand_id}: {e}")
            summaries.append({"brand": brand_id, "error": str(e)})

    # Write report
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = Path(f"/tmp/co-nightshift/weekly-scrape-{today}.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(f"# Weekly Drive Scrape — {today}\n\n")
        for s in summaries:
            f.write(f"\n## {s['brand']}\n\n")
            if "error" in s:
                f.write(f"**Error:** {s['error']}\n")
                continue
            f.write(f"- Drive files total: {s['drive_files_total']}\n")
            f.write(f"- New/changed: {s['new_or_changed']}\n")
            f.write(f"- Skipped (unchanged): {s['skipped_existing']}\n")
            f.write(f"- Re-dissected: {s['re_dissected']}\n")
            if s.get('download_errors'):
                f.write(f"- Download errors: {len(s['download_errors'])}\n")
            products = s.get('tag_summary', {}).get('products_found', {})
            if products:
                f.write(f"\n### Products detected ({len(products)})\n")
                for p, c in sorted(products.items(), key=lambda x: -x[1]):
                    f.write(f"- {p}: {c}\n")
            missed = s.get('missed_folders_detected', [])
            if missed:
                f.write(f"\n### Drive folders NOT yet indexed (audit)\n")
                for mf in missed:
                    owners = ", ".join(mf.get("owners", []))
                    f.write(f"- **{mf['name']}** (`{mf['id']}`) owner={owners}\n")
                f.write("\nThese folders match brand-related keywords but aren't in the BRAND_FOLDERS config. Add them if they should be ingested.\n")
    print(f"\nReport: {report_path}")

    # Git commit any new dissector outputs
    import subprocess
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(REPO), check=False)
        # Only commit if there are changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(REPO),
        )
        if result.returncode != 0:
            subprocess.run([
                "git", "commit", "-m",
                f"chore(weekly-scrape): {today} new dissector outputs"
            ], cwd=str(REPO), check=False)
            print("Committed new dissector outputs to git")
    except Exception as e:
        print(f"git commit skipped: {e}")


if __name__ == "__main__":
    main()
