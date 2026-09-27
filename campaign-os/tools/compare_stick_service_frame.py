#!/usr/bin/env python3
"""Compare golden render to swingasses.jpg (1080×1350 reference)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data/brand-directory/stick/images/Services/swingasses.jpg"
GOLDEN = (
    ROOT
    / "data/brand-directory/stick/templates/service-frame/golden/render-instagram.png"
)


def _ssim_gray(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_a = a.mean()
    mu_b = b.mean()
    sig_a = a.var()
    sig_b = b.var()
    sig_ab = ((a - mu_a) * (b - mu_b)).mean()
    num = (2 * mu_a * mu_b + c1) * (2 * sig_ab + c2)
    den = (mu_a**2 + mu_b**2 + c1) * (sig_a + sig_b + c2)
    return float(num / den) if den else 0.0


def _zone_mean_delta(rend: np.ndarray, ref: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = box
    d = np.abs(rend[y0:y1, x0:x1].astype(float) - ref[y0:y1, x0:x1].astype(float))
    return float(d.mean())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--render", type=Path, default=GOLDEN, help="render PNG (default: golden)")
    ap.add_argument("--ref", type=Path, default=REF, help="reference image (default: swingasses.jpg)")
    args = ap.parse_args(argv)
    render_path, ref_path = args.render, args.ref
    if not render_path.is_file():
        print(f"missing golden {render_path}", file=sys.stderr)
        return 1
    if not ref_path.is_file():
        print(f"missing reference {ref_path}", file=sys.stderr)
        return 1
    ref = Image.open(ref_path).convert("RGB")
    rend = Image.open(render_path).convert("RGB")
    if ref.size != (1080, 1350):
        ref = ref.resize((1080, 1350), Image.LANCZOS)
    if rend.size != (1080, 1350):
        print(f"render size {rend.size}, expected 1080x1350", file=sys.stderr)
        return 1
    a = np.array(rend)
    b = np.array(ref)
    diff = np.abs(a.astype(float) - b.astype(float))
    mean_all = float(diff.mean())
    pct_big = float((diff.max(axis=2) > 32).mean() * 100)
    gray_a = a.mean(axis=2)
    gray_b = b.mean(axis=2)
    ssim = _ssim_gray(gray_a, gray_b)
    zones = {
        "headline": (110, 220, 980, 580),
        "cta_band": (62, 669, 1079, 999),
        "cta_text": (120, 750, 940, 910),
        "footer": (130, 1100, 950, 1200),
    }
    print(f"mean_delta_all={mean_all:.3f}/255 pct_diff_gt32={pct_big:.2f}% ssim={ssim:.4f}")
    for name, box in zones.items():
        print(f"  zone {name} mean_delta={_zone_mean_delta(a, b, box):.3f}")
    score = max(0.0, 100.0 - mean_all * 4.0 - pct_big * 0.5 + ssim * 10.0)
    print(f"score={score:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
