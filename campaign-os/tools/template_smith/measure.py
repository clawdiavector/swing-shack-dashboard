#!/usr/bin/env python3
"""Measure a service-frame reference image and emit a pixel-derived spec draft.

All geometry/colours come from the reference pixels; nothing is read from the
hand-authored spec.json. Coordinates are reported both in reference pixels and
normalised to the 1080x1350 base canvas.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
FRAME = ROOT / "data/brand-directory/stick/templates/service-frame"
BASE_W, BASE_H = 1080, 1350


def _hex(rgb) -> str:
    r, g, b = (int(round(float(c))) for c in rgb[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def _runs(mask_1d: np.ndarray, min_len: int = 1, max_gap: int = 0) -> list[tuple[int, int]]:
    """Return [start, end) runs of True, merging gaps <= max_gap."""
    runs: list[tuple[int, int]] = []
    start = None
    for i, v in enumerate(mask_1d):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask_1d)))
    merged: list[tuple[int, int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= max_gap:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] >= min_len]


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def measure(path: Path) -> dict:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    a = np.asarray(img).astype(np.int32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]

    white = (a.min(axis=2) > 170)
    teal = (g > 130) & (b > 130) & (r < 90) & (np.abs(g - b) < 45)

    # --- teal band: rows mostly teal, then columns within those rows.
    row_teal = teal.mean(axis=1)
    band_rows = _runs(row_teal > 0.4, min_len=int(h * 0.05))
    if not band_rows:
        raise SystemExit("no teal band found")
    by0, by1 = max(band_rows, key=lambda t: t[1] - t[0])
    col_teal = teal[by0:by1].mean(axis=0)
    band_cols = _runs(col_teal > 0.5, min_len=int(w * 0.3), max_gap=int(w * 0.02))
    bx0, bx1 = max(band_cols, key=lambda t: t[1] - t[0])
    inner = teal[by0 + 3 : by1 - 3, bx0 + 3 : bx1 - 3] & ~white[by0 + 3 : by1 - 3, bx0 + 3 : bx1 - 3]
    teal_rgb = np.median(a[by0 + 3 : by1 - 3, bx0 + 3 : bx1 - 3][inner], axis=0)

    # --- background: clean navy pixels (not white, not teal), fit linear per channel vs x and y.
    clean = ~white & ~teal & (a.max(axis=2) < 120)
    clean[:, :3] = False
    clean[:, -3:] = False
    ys, xs = np.nonzero(clean)
    sel = np.arange(len(xs))[:: max(1, len(xs) // 200000)]
    xs_s, ys_s = xs[sel], ys[sel]
    cols = a[ys_s, xs_s].astype(np.float64)
    A = np.stack([np.ones_like(xs_s, dtype=np.float64), xs_s / (w - 1), ys_s / (h - 1)], axis=1)
    coef, *_ = np.linalg.lstsq(A, cols, rcond=None)
    # coef rows: intercept, x-slope, y-slope (per channel)
    x_slope = np.abs(coef[1]).sum()
    y_slope = np.abs(coef[2]).sum()
    if x_slope >= y_slope:
        direction = "horizontal"
        c_from = coef[0] + coef[2] * 0.5
        c_to = coef[0] + coef[1] + coef[2] * 0.5
    else:
        direction = "vertical"
        c_from = coef[0] + coef[1] * 0.5
        c_to = coef[0] + coef[2] + coef[1] * 0.5

    # --- headline: white rows above the band.
    head = white[:by0]
    head_rows = _runs(head.sum(axis=1) > 2, min_len=int(h * 0.02), max_gap=2)
    head_lines = []
    for y0, y1 in head_rows:
        bb = _bbox(head[y0:y1])
        head_lines.append({"y0": y0, "y1": y1, "x0": bb[0], "x1": bb[2]})

    # --- CTA: white rows inside band.
    cta = white[by0:by1, bx0:bx1]
    cta_rows = _runs(cta.sum(axis=1) > 1, min_len=int(h * 0.015), max_gap=2)
    cta_lines = []
    for y0, y1 in cta_rows:
        bb = _bbox(cta[y0:y1])
        # stroke weight per word cluster to find emphasis runs
        seg = cta[y0:y1]
        colmask = seg.any(axis=0)
        words = _runs(colmask, min_len=3, max_gap=int((y1 - y0) * 0.25))
        wstats = []
        for wx0, wx1 in words:
            sub = seg[:, wx0:wx1]
            ink = float(sub.mean())
            wstats.append({"x0": bx0 + wx0, "x1": bx0 + wx1, "ink": round(ink, 3)})
        cta_lines.append(
            {"y0": by0 + y0, "y1": by0 + y1, "x0": bx0 + bb[0], "x1": bx0 + bb[2], "words": wstats}
        )

    # --- footer: white below band; split by the widest horizontal gap.
    foot = white[by1:]
    fb = _bbox(foot)
    footer = {}
    if fb:
        colmask = foot.any(axis=0)
        clusters = _runs(colmask, min_len=2, max_gap=int(w * 0.03))
        if len(clusters) >= 2:
            gaps = [(clusters[i + 1][0] - clusters[i][1], i) for i in range(len(clusters) - 1)]
            _, split = max(gaps)
            left = (clusters[0][0], clusters[split][1])
            right = (clusters[split + 1][0], clusters[-1][1])
            for name, (cx0, cx1) in (("logo", left), ("tagline", right)):
                sub = foot[:, cx0:cx1]
                bb = _bbox(sub)
                footer[name] = {
                    "x0": cx0 + bb[0],
                    "y0": by1 + bb[1],
                    "x1": cx0 + bb[2],
                    "y1": by1 + bb[3],
                }

    sx, sy = BASE_W / w, BASE_H / h

    def scale_box(d: dict) -> dict:
        out = dict(d)
        for k in ("x0", "x1"):
            if k in out:
                out[k] = round(out[k] * sx, 2)
        for k in ("y0", "y1"):
            if k in out:
                out[k] = round(out[k] * sy, 2)
        if "words" in out:
            out["words"] = [scale_box(wd) for wd in out["words"]]
        return out

    return {
        "source": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "ref_size": [w, h],
        "base_canvas": [BASE_W, BASE_H],
        "scale": [round(sx, 5), round(sy, 5)],
        "background": {
            "direction": direction,
            "from": _hex(np.clip(c_from, 0, 255)),
            "to": _hex(np.clip(c_to, 0, 255)),
            "x_slope_sum": round(float(x_slope), 2),
            "y_slope_sum": round(float(y_slope), 2),
        },
        "teal_band": {
            "colour": _hex(teal_rgb),
            **scale_box({"x0": bx0, "y0": by0, "x1": bx1, "y1": by1}),
        },
        "headline_lines": [scale_box(ln) for ln in head_lines],
        "cta_lines": [scale_box(ln) for ln in cta_lines],
        "footer": {k: scale_box(v) for k, v in footer.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("refs", nargs="*", type=Path, default=[FRAME / "references/ref-01.jpg"])
    ap.add_argument("--out", type=Path, default=FRAME / "agent/measured.json")
    args = ap.parse_args()
    results = [measure(p) for p in args.refs]
    doc = {"primary": results[0], "others": results[1:]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results[0], indent=2))
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
