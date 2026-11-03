#!/usr/bin/env python3
"""Reality check: are the things in a picture the right size for each other?

Measure objects in pixels along the dimension named in ../real-sizes.json, mark one or more as the
reference (something whose size you trust in that picture, at the same distance from the camera), and
the check says what every other object measures in the real world:

    python3 reality_check.py plate.json

    plate.json: [{"object": "flagstick", "px": 2100, "ref": true},
                 {"object": "cap", "px": 450}]

Verdicts: PASS inside the real range (10% slack for perspective and fabric), CHECK up to 35% outside
it, FAIL beyond that. Exit 1 on any FAIL. A generated scene that fails here looks wrong to people
even when they can't say why ("this looks wack"): a cap the size of an umbrella, a ball the size of
an orange.

It can't see depth: only compare objects at about the same distance from the camera, and measure
along the same dimension the table names.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SIZES = Path(__file__).resolve().parents[1] / "real-sizes.json"
SLACK, CHECK_BAND = 0.10, 0.35


def sizes() -> dict:
    return json.loads(SIZES.read_text(encoding="utf-8"))["objects"]


def check(measured: list[dict]) -> list[dict]:
    table = sizes()
    for m in measured:
        if m["object"] not in table:
            raise KeyError(f"no real size for {m['object']!r}; add it to real-sizes.json with a source")
    refs = [m for m in measured if m.get("ref")]
    if not refs:
        raise ValueError("mark at least one object as the reference (\"ref\": true)")
    mm_per_px = sum(table[r["object"]]["typical_mm"] / r["px"] for r in refs) / len(refs)

    out = []
    for m in measured:
        s = table[m["object"]]
        mm = m["px"] * mm_per_px
        ratio = mm / s["typical_mm"]
        if m.get("ref"):
            verdict = "REF"
        elif s["min_mm"] * (1 - SLACK) <= mm <= s["max_mm"] * (1 + SLACK):
            verdict = "PASS"
        elif s["min_mm"] * (1 - CHECK_BAND) <= mm <= s["max_mm"] * (1 + CHECK_BAND):
            verdict = "CHECK"
        else:
            verdict = "FAIL"
        out.append({"object": m["object"], "px": m["px"], "mm": round(mm), "real_mm": s["typical_mm"],
                    "ratio": round(ratio, 2), "verdict": verdict})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plate", type=Path, help="JSON list of {object, px, ref?}")
    args = ap.parse_args(argv)
    rows = check(json.loads(args.plate.read_text(encoding="utf-8")))
    for r in rows:
        note = "" if r["verdict"] in ("REF", "PASS") else f"  ({r['ratio']}x real size)"
        print(f"{r['verdict']:5}  {r['object']:12} {r['px']:>6} px = {r['mm']:>6} mm   real {r['real_mm']:>6} mm{note}")
    return 1 if any(r["verdict"] == "FAIL" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
