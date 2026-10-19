"""Attach SKU-named product photos to stocked products, and approve them.

    python campaign-os/scripts/photo_map_cli.py scan    --brand stick --csv stock.csv
    python campaign-os/scripts/photo_map_cli.py list    --brand stick [--status needs-check]
    python campaign-os/scripts/photo_map_cli.py approve --brand stick TS001__front.jpg
    python campaign-os/scripts/photo_map_cli.py reject  --brand stick TS001__front.jpg

Photos are named SKU__view.jpg (TS001__front.jpg). scan reads the latest saved stock
snapshot, or --csv for a one-off. Only approved photos reach the planner.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import photo_map as pm  # noqa: E402
from _lib import stock_pulse as sp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["scan", "list", "approve", "reject"])
    ap.add_argument("file", nargs="?", help="photo file (approve / reject)")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--csv", help="stock csv to read SKUs from (default: latest saved snapshot)")
    ap.add_argument("--status", help="list only this status")
    ap.add_argument("--images", help="images folder (default: the brand's)")
    ap.add_argument("--by", default="christelle")
    a = ap.parse_args()

    if a.command == "scan":
        if a.csv:
            rows = sp.parse_stock_csv(Path(a.csv).read_text(encoding="utf-8-sig"))
            snaps = [{"date": "now", "rows": rows}]
        else:
            snaps = sp.load_snapshots(a.brand)
        if not snaps:
            print("No stock list yet. Pass --csv or save a snapshot first.")
            return 1
        out = pm.scan(a.brand, pm.sku_index(sp.analyse(snaps)), Path(a.images) if a.images else None)
        print(f"{len(out['added'])} new photo(s) waiting for a check, {out['total']} on the map.")
        for f in out["added"]:
            print(f"  + {f}")
        for f in out["unknown"]:
            print(f"  ? {f}: SKU not in the stock list (typo, or not stocked)")
        for f in out["ambiguous"]:
            print(f"  ! {f}: two SKUs look the same once punctuation is removed")
        return 0

    if a.command == "list":
        for e in pm.load(a.brand):
            if a.status and e["status"] != a.status:
                continue
            note = "" if e.get("viewable", True) else "  (HEIC: convert to view)"
            print(f"{e['status']:<11} {e['file']}  ->  {e['product']}{note}")
        return 0

    if not a.file:
        print("Give the photo file name.")
        return 1
    ok = pm.set_status(a.brand, a.file, "approved" if a.command == "approve" else "rejected", a.by)
    print("Done." if ok else "No such photo on the map.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
