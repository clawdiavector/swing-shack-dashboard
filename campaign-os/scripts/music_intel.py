#!/usr/bin/env python3
"""music_intel.py <brand> worksheet [-o file.csv] | health | import file.csv

worksheet  write the brand's reels that still need their audio filled in
import     load the filled sheet (columns: platform,post_id,title,artist,bpm,...)
health     print what the evidence base can support
"""
import argparse, csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import music_intel as mi

ap = argparse.ArgumentParser()
ap.add_argument("brand"); ap.add_argument("cmd", choices=["worksheet", "health", "import"])
ap.add_argument("arg", nargs="?"); ap.add_argument("-o", "--out")
a = ap.parse_args()
if a.cmd == "health":
    print(json.dumps(mi.health(a.brand), indent=2))
elif a.cmd == "import":
    print(mi.import_post_audio(a.brand, mi.load_csv(Path(a.arg))))
else:
    rows = mi.worksheet(a.brand)
    out = open(a.out, "w", newline="", encoding="utf-8") if a.out else sys.stdout
    w = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["post_id"]); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} reels need audio", file=sys.stderr)
