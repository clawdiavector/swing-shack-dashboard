#!/usr/bin/env python3
"""Keep the shared catalogue's pictures and Drive's Catalogue folder in step.

    # copy everything on Drive down (locally, or on live into the volume)
    python3 campaign-os/scripts/sync_catalogue.py pull
    python3 campaign-os/scripts/sync_catalogue.py pull --data-dir "$DATA_DIR"

    # file the maker images already on the brands' photo maps into the catalogue
    python3 campaign-os/scripts/sync_catalogue.py backfill

    # after dragging images/<maker>/ folders into Drive Catalogue/: record their Drive ids
    python3 campaign-os/scripts/sync_catalogue.py link

    # pictures the scout saved here that are not on Drive yet
    python3 campaign-os/scripts/sync_catalogue.py to-upload

    # after uploading one to Drive Catalogue/<maker>/ (Claude, with the Drive connector)
    python3 campaign-os/scripts/sync_catalogue.py mark images/vessel/player-v__1.png <drive file id>

The app never writes to Drive: uploads go through the Drive connector or a person.
Guide: data/brand-directory/_system/IMAGES.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import image_library as il  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull", help="copy Drive Catalogue/ down")
    p.add_argument("--data-dir", help="directory CONTAINING brand-directory/ (default: the repo's data/)")
    sub.add_parser("backfill", help="file maker images from both brands' photo maps into the catalogue")
    sub.add_parser("link", help="record Drive ids for pictures now in Drive Catalogue/")
    sub.add_parser("to-upload", help="list pictures not on Drive yet")
    m = sub.add_parser("mark", help="record a picture's Drive file id after uploading it")
    m.add_argument("file")
    m.add_argument("drive_id")
    a = ap.parse_args()

    if a.cmd == "pull":
        got = il.pull_catalogue(data_dir=Path(a.data_dir) if a.data_dir else None)
        print(json.dumps({k: (len(v) if k != "errors" else v) for k, v in got.items()}, indent=1))
        return 1 if got["errors"] else 0
    if a.cmd == "backfill":
        for brand in ("stick", "swing-shack", "bag-drop"):
            print(brand, json.dumps(il.backfill_from_photo_map(brand)))
        return 0
    if a.cmd == "link":
        print(json.dumps(il.link_drive_ids()))
        return 0
    if a.cmd == "to-upload":
        rows = il.to_upload()
        for r in rows:
            r["local_path"] = str(il.CATALOGUE / r["file"])
        print(json.dumps({"drive_parent": il.CATALOGUE_DRIVE_ID, "to_upload": rows}, indent=1))
        return 0
    il.mark_on_drive(a.file, a.drive_id)
    print(f"marked {a.file} -> {a.drive_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
