"""Tools for the image scout: what is missing, record what was found, check and save it.

    python campaign-os/scripts/image_scout_cli.py gaps  --brand stick --csv stock.csv
    python campaign-os/scripts/image_scout_cli.py add   --brand stick --file found.json
    python campaign-os/scripts/image_scout_cli.py list  --brand stick
    python campaign-os/scripts/image_scout_cli.py fetch --brand stick [--sku TS001]

found.json is a list of {sku, product, page_url, image_url, view?, note?, exact_build?}.
fetch downloads each candidate, applies the quality gate, saves it as SKU__view.<ext> in
the brand's Products folder and puts it on the photo map as needs-check.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import image_scout as sc  # noqa: E402
from _lib import photo_map as pm  # noqa: E402
from _lib import stock_pulse as sp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["gaps", "add", "list", "fetch"])
    ap.add_argument("--brand", required=True)
    ap.add_argument("--csv")
    ap.add_argument("--file")
    ap.add_argument("--sku")
    ap.add_argument("--images")
    a = ap.parse_args()

    if a.command == "gaps":
        if a.csv:
            snaps = [{"date": "now", "rows": sp.parse_stock_csv(Path(a.csv).read_text(encoding="utf-8-sig"))}]
        else:
            snaps = sp.load_snapshots(a.brand)
        entries, cands = pm.load(a.brand), sc.load(a.brand)
        have = {c["sku"] for c in cands}
        for r in sp.analyse(snaps):
            if r.get("folded_into_range") or r["not_for_feed"] or r["status"] in ("out", "error"):
                continue
            if pm.status_for(entries, r["skus"]) or any(s in have for s in r["skus"]):
                continue
            print(f"{r['qty']:>4}  {r['status']:<8} {r['name']}  [{pm.shot_name(r['skus'])[:-12]}]")
        return 0

    if a.command == "add":
        rows = json.loads(Path(a.file).read_text(encoding="utf-8"))
        for r in rows:
            sc.add(a.brand, r["sku"], r["product"], r["page_url"], r["image_url"], r.get("view", "front"),
                   r.get("note", ""), r.get("exact_build", True))
        print(f"{len(rows)} candidate(s) recorded, {len(sc.load(a.brand))} on file.")
        return 0

    if a.command == "list":
        for r in sc.load(a.brand):
            chk = r.get("check") or {}
            size = f" {chk.get('width')}x{chk.get('height')}" if chk.get("width") else ""
            why = f" ({chk['reason']})" if chk.get("reason") else ""
            print(f"{r['status']:<10} {r['sku']:<16} {r['product']}{size}{why}")
        return 0

    done = failed = 0
    for r in sc.load(a.brand):
        if r["status"] != "found" or (a.sku and r["sku"] != a.sku):
            continue
        out = sc.fetch(a.brand, r, Path(a.images) if a.images else None)
        sc.mark(a.brand, r, "saved" if out["ok"] else "rejected", out)
        if out["ok"]:
            done += 1
            print(f"saved    {out['file']}  {out['width']}x{out['height']}")
        else:
            failed += 1
            print(f"rejected {r['sku']} {r['product']}: {out.get('reason')}")
    print(f"{done} saved, {failed} rejected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
