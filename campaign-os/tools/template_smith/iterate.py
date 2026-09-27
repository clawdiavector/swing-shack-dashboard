#!/usr/bin/env python3
"""measure → author → render → compare loop with measured-feedback corrections.

Iteration 1 renders the spec straight from ``author.py``. Each later iteration
re-measures the render with the same probe used on the reference, and nudges
origins / tracking / asset rects by the observed ink-box deltas.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from measure import measure  # noqa: E402

FRAME = ROOT / "data/brand-directory/stick/templates/service-frame"
W, H = 1080, 1350


def _run(*args: str) -> str:
    res = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"{args[0]} failed:\n{res.stdout}\n{res.stderr}")
    return res.stdout


def _compare(render: Path, ref: Path) -> tuple[float, str]:
    out = _run("campaign-os/tools/compare_stick_service_frame.py", "--render", str(render), "--ref", str(ref))
    m = re.search(r"score=([\d.]+)", out)
    return float(m.group(1)) if m else 0.0, out


def _mean(vals: list[float]) -> float:
    return sum(vals) / max(1, len(vals))


def _correct(spec: dict, ref_m: dict, rend_m: dict, headline: list[str], cta: list[str]) -> dict:
    z = spec["zones"]
    notes: dict = {}

    hd = [(a["x0"] - b["x0"], a["y0"] - b["y0"]) for a, b in zip(rend_m["headline_lines"], ref_m["headline_lines"])]
    dx, dy = _mean([d[0] for d in hd]), _mean([d[1] for d in hd])
    z["headline"]["text_origin_x"] = round(z["headline"]["text_origin_x"] - dx)
    for k in ("y0", "y1"):
        z["headline"]["rect"][k] = round(z["headline"]["rect"][k] - dy / H, 4)
    notes["headline_dx_dy"] = [round(dx, 2), round(dy, 2)]

    cd = list(zip(rend_m["cta_lines"], ref_m["cta_lines"]))
    dx = _mean([a["x0"] - b["x0"] for a, b in cd])
    dy = _mean([a["y0"] - b["y0"] for a, b in cd])
    z["cta"]["text_origin_x"] = round(z["cta"]["text_origin_x"] - dx)
    for k in ("y0", "y1"):
        z["cta"]["rect"][k] = round(z["cta"]["rect"][k] - dy / H, 4)
    size = spec["_derivation"]["cta_font_px"]
    per_px = []
    for (a, b), text in zip(cd, cta):
        wd_err = (a["x1"] - a["x0"]) - (b["x1"] - b["x0"])
        ntrack = sum(len(w) - 1 for w in text.split())
        per_px.append(wd_err / max(1, ntrack))
    dtrack = _mean(per_px)
    z["cta"]["tracking_em"] = round(z["cta"]["tracking_em"] - dtrack / size, 4)
    notes["cta_dx_dy_dtrack_px"] = [round(dx, 2), round(dy, 2), round(dtrack, 3)]

    for name in ("logo", "tagline"):
        a, b = rend_m["footer"][name], ref_m["footer"][name]
        s = (b["x1"] - b["x0"]) / max(1e-6, a["x1"] - a["x0"])
        r = z[name]["rect"]
        # scale rect about the rendered ink's left/bottom, then move ink onto the reference
        ax0, ay1 = a["x0"] / W, a["y1"] / H
        nx0 = ax0 + (r["x0"] - ax0) * s + (b["x0"] - a["x0"]) / W
        nx1 = ax0 + (r["x1"] - ax0) * s + (b["x0"] - a["x0"]) / W
        ny0 = ay1 + (r["y0"] - ay1) * s + (b["y1"] - a["y1"]) / H
        ny1 = ay1 + (r["y1"] - ay1) * s + (b["y1"] - a["y1"]) / H
        z[name]["rect"] = {k: round(v, 4) for k, v in zip(("x0", "y0", "x1", "y1"), (nx0, ny0, nx1, ny1))}
        notes[f"{name}_scale"] = round(s, 4)
    return notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", type=Path, default=FRAME / "references/ref-01.jpg")
    ap.add_argument("--spec", type=Path, default=FRAME / "agent/spec.json")
    ap.add_argument("--render", type=Path, default=FRAME / "agent/render-instagram.png")
    ap.add_argument("--log", type=Path, default=FRAME / "agent/iterations.json")
    ap.add_argument("--target", type=float, default=85.0)
    ap.add_argument("--max-iter", type=int, default=3)
    ap.add_argument("--headline", default="CONSISTENCY|STARTS WITH|DATA")
    ap.add_argument("--cta", default="BOOK YOUR FREE|SWING ASSESSMENT")
    args = ap.parse_args()
    headline, cta = args.headline.split("|"), args.cta.split("|")

    tools = "campaign-os/tools/template_smith"
    _run(f"{tools}/measure.py", str(args.ref), "--out", str(FRAME / "agent/measured.json"))
    _run(f"{tools}/author.py", "--out", str(args.spec))
    ref_m = measure(args.ref)

    log = []
    best: tuple[float, dict] | None = None
    for i in range(1, args.max_iter + 1):
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        notes: dict = {}
        if i > 1:
            notes = _correct(spec, ref_m, measure(args.render), headline, cta)
            args.spec.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        _run(f"{tools}/render.py", "--spec", str(args.spec), "--out", str(args.render))
        score, report = _compare(args.render, args.ref)
        print(f"iteration {i}: score={score:.1f} {json.dumps(notes)}")
        log.append({"iteration": i, "score": score, "corrections": notes, "report": report.strip().splitlines()})
        if best is None or score > best[0]:
            best = (score, spec)
        if score >= args.target:
            break

    if best and best[0] > log[-1]["score"]:
        args.spec.write_text(json.dumps(best[1], indent=2) + "\n", encoding="utf-8")
        _run(f"{tools}/render.py", "--spec", str(args.spec), "--out", str(args.render))
    args.log.write_text(json.dumps({"ref": str(args.ref.relative_to(ROOT)), "iterations": log, "final_score": best[0] if best else None}, indent=2) + "\n", encoding="utf-8")
    print(f"final score={best[0]:.1f}" if best else "no iterations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
