#!/usr/bin/env python3
"""Measure layout facts from reference posts: frame, coloured text lines, white text, accents.

Prints a per-image table plus a consistency summary, and writes JSON with --json.
All numbers are pixels in the reference's own size (note it — refs are often 1081×1201).

  python3 measure_refs.py refs/*.jpg --json measured.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def runs(mask_1d: np.ndarray, min_len: int, max_gap: int = 0) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = None
    gap = 0
    for i, v in enumerate(mask_1d):
        if v:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > max_gap:
                end = i - gap + 1
                if end - start >= min_len:
                    out.append((start, end))
                start, gap = None, 0
    if start is not None and len(mask_1d) - start >= min_len:
        out.append((start, len(mask_1d)))
    return out


def edge_line(profile: np.ndarray) -> dict | None:
    """Thin bright band near an edge: profile is luminance from the edge inward."""
    base = float(np.median(profile))
    hits = runs(profile > base + 40, 2)
    if not hits:
        return None
    a, b = hits[0]
    if b - a > 20:
        return None
    return {"inset": a, "stroke": b - a, "level": round(float(profile[a:b].mean()), 1)}


def frame(L: np.ndarray) -> dict:
    h, w = L.shape
    band = slice(int(h * 0.2), int(h * 0.8))
    bandx = slice(int(w * 0.2), int(w * 0.8))
    return {
        "left": edge_line(np.median(L[band, :150], axis=0)),
        "right": edge_line(np.median(L[band, -150:], axis=0)[::-1]),
        "top": edge_line(np.median(L[:150, bandx], axis=1)),
        "bottom": edge_line(np.median(L[-150:, bandx], axis=1)[::-1]),
    }


def lines(mask: np.ndarray, min_h: int, pad: int) -> list[dict]:
    h, w = mask.shape
    m = mask.copy()
    m[:pad, :] = m[-pad:, :] = False
    m[:, :pad] = m[:, -pad:] = False
    out = []
    for y0, y1 in runs(m.sum(axis=1) > max(3, w * 0.004), min_h, max_gap=2):
        ys, xs = np.nonzero(m[y0:y1])
        out.append({"y0": y0, "y1": y1, "h": y1 - y0, "x0": int(xs.min()), "x1": int(xs.max())})
    return out


def measure(path: Path) -> dict:
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(int)
    h, w, _ = rgb.shape
    L = rgb.mean(axis=2)
    sat = np.ptp(rgb, axis=2)
    fr = frame(L)
    pad = max([(v["inset"] + v["stroke"] + 4) for v in fr.values() if v] or [8])
    colour_mask = (sat > 90) & (L > 50)
    white_mask = (L > 170) & (sat < 40)
    col_lines = lines(colour_mask, int(h * 0.02), pad)
    white_lines = lines(white_mask, 6, pad)
    accent = None
    if colour_mask.any():
        med = np.median(rgb[colour_mask], axis=0).astype(int)
        accent = "#%02X%02X%02X" % tuple(med)
    pitch = [b["y0"] - a["y0"] for a, b in zip(col_lines, col_lines[1:])]
    return {
        "file": path.name,
        "size": [w, h],
        "frame": fr,
        "accent": accent,
        "colour_lines": col_lines,
        "colour_cap_px": int(np.median([ln["h"] for ln in col_lines])) if col_lines else None,
        "colour_pitch_px": int(np.median(pitch)) if pitch else None,
        "white_lines": white_lines,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--json")
    args = ap.parse_args()
    rows = [measure(Path(p)) for p in args.images]
    for r in rows:
        fr = {k: (v["inset"], v["stroke"]) if v else None for k, v in r["frame"].items()}
        print(f"\n{r['file']}  {r['size'][0]}x{r['size'][1]}  accent {r['accent']}  frame(inset,stroke) {fr}")
        print(f"  colour lines cap {r['colour_cap_px']} pitch {r['colour_pitch_px']}:")
        for ln in r["colour_lines"]:
            print(f"    y {ln['y0']}-{ln['y1']} (h {ln['h']})  x {ln['x0']}-{ln['x1']}")
        print("  white text rows:")
        for ln in r["white_lines"]:
            print(f"    y {ln['y0']}-{ln['y1']} (h {ln['h']})  x {ln['x0']}-{ln['x1']}")
    caps = [r["colour_cap_px"] for r in rows if r["colour_cap_px"]]
    lefts = [r["colour_lines"][0]["x0"] for r in rows if r["colour_lines"]]
    if len(caps) > 1:
        print(f"\nconsistency: cap {min(caps)}–{max(caps)}  first-line x0 {min(lefts)}–{max(lefts)}  "
              f"accents {sorted({r['accent'] for r in rows if r['accent']})}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
