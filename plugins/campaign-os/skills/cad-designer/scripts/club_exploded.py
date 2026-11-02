#!/usr/bin/env python3
"""A 7-iron pulled apart into its parts (head, ferrule, shaft, grip), built from maker specs, as a still
with labelled parts and as a short reel that turns the club and pulls it apart.

    python3 club_exploded.py --out out/ --brand stick|swing-shack [--reel] [--seconds 7]

Specs and their sources: ../club-7iron.json. The head outline is a generic cavity blade, not any brand's
head; draw a real head from its maker's photos before showing one as a product.
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import cad3d as c  # noqa: E402
from cad3d import V  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
SPEC = json.loads((Path(__file__).resolve().parents[1] / "club-7iron.json").read_text(encoding="utf-8"))
IN = 0.0254
BRAND = {"stick": dict(bg=(7, 60, 82), accent=(0, 179, 186)),             # navy_deep, teal
         "swing-shack": dict(bg=(24, 24, 26), accent=(116, 204, 70))}
STEEL, BLACK, HEAD = (196, 200, 206), (34, 34, 36), (176, 180, 186)


AXIS = V([0.62, 0.0, 0.785]) / np.linalg.norm(V([0.62, 0.0, 0.785]))   # the club lies corner to corner


def _spin(axis, deg):
    """Rotation matrix about a unit axis."""
    a = math.radians(deg)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def _rot_to(s, z):
    """Rotation matrix taking unit vector s to unit vector z."""
    axis = np.cross(s, z)
    n = np.linalg.norm(axis)
    if n < 1e-9:
        return np.eye(3)
    axis /= n
    a = math.acos(max(-1.0, min(1.0, float(np.dot(s, z)))))
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def parts(explode=1.0, spin=0.0):
    """The club laid corner to corner on its shaft axis, turned `spin` degrees about it, parts as cad3d
    solids pulled apart by `explode` (0 to 1).
    Built at address (heel at the origin, toe +x, face towards -y, shaft rising towards -x at the lie)."""
    e = SPEC["estimates"]
    lie, loft = math.radians(SPEC["lie_deg"]), math.radians(SPEC["loft_deg"])
    s = V([-math.cos(lie), 0.0, math.sin(lie)])               # shaft axis, heel up to butt
    L, hl, ht = e["head_length_mm"] / 1000, e["head_heel_height_mm"] / 1000, e["head_toe_height_mm"] / 1000
    outline = [(0.004, 0.004), (L * 0.55, 0.0), (L * 0.92, 0.004), (L, 0.016), (L * 1.0, 0.034),
               (L * 0.93, ht), (L * 0.6, ht * 0.86), (L * 0.2, hl * 1.08), (0.0, hl)]
    face = [V([x, z * math.tan(loft), z]) for x, z in outline]   # the face leans back by the loft
    head = c.prism(face, V([0.0, e["head_depth_mm"] / 1000, 0.0]), fill=HEAD, name="head")
    hosel_a = V([0.006, 0.012, 0.012])
    hosel_b = hosel_a + s * e["hosel_length_mm"] / 1000
    d0, d1 = e["hosel_diameter_mm"]
    hosel = c.frustum(hosel_a, hosel_b, d0 / 2000, d1 / 2000, fill=HEAD, name="hosel")
    ferrule_b = hosel_b + s * SPEC["ferrule_length_in"] * IN
    butt = hosel_a + s * (SPEC["length_in"] * IN - 0.012)       # sole to butt is the club's length
    grip_a = butt - s * e["grip_length_in"] * IN
    go0, go1 = e["grip_outer_diameter_in"]
    pieces = {
        "head": ([head, hosel], 0.0),
        "ferrule": ([c.frustum(hosel_b, ferrule_b, SPEC["shaft_at_hosel_in"] * IN * 0.62, SPEC["shaft_at_hosel_in"] * IN * 0.55,
                               fill=BLACK, name="ferrule")], 0.06),
        "shaft": ([c.frustum(ferrule_b, grip_a, SPEC["shaft_at_hosel_in"] * IN / 2, SPEC["shaft_butt_in"] * IN / 2,
                             fill=STEEL, name="shaft")], 0.12),
        "grip": ([c.frustum(grip_a, butt, go0 * IN / 2, go1 * IN / 2, fill=BLACK, name="grip", n=24)], 0.20),
    }
    R = _rot_to(s, AXIS) @ _spin(s, spin)
    out, anchors = [], {}
    for name, (solids, gap) in pieces.items():
        shift = s * gap * explode
        for sol in solids:
            sol.faces = [np.array([R @ (p + shift) for p in f]) for f in sol.faces]
            out.append(sol)
        pts = np.concatenate([f for sol in solids for f in sol.faces])
        anchors[name] = pts.mean(axis=0)
    anchors["head"] = R @ V([L * 0.55, 0.0, ht * 0.45])          # label the face, not the hosel
    return out, anchors


LABELS = {
    "grip": lambda: ("Grip", f"{SPEC['grip_core_in']:.3f} in core  ·  {SPEC['grip_mass_g']} g"),
    "shaft": lambda: ("Shaft", f"{SPEC['shaft_tip_in']:.3f} in tip to {SPEC['shaft_butt_in']:.3f} in butt"),
    "ferrule": lambda: ("Ferrule", f"{SPEC['ferrule_length_in']:.0f} in"),
    "head": lambda: ("Head", f"loft {SPEC['loft_deg']}°  ·  lie {SPEC['lie_deg']}°"),
}


def frame(brand, explode, spin, label_alpha, fonts):
    b = BRAND[brand]
    c.STYLES["studio"] = dict(bg=b["bg"], line=(60, 60, 60), fill=True, grid=None, dim=(230, 230, 230))
    s = c.Scene()
    solids, anchors = parts(explode, spin)
    s.solids += solids
    cam = c.Camera("persp", eye=(0.42, -2.6, 0.62), target=(0.42, 0.0, 0.52), fov=32)
    span = AXIS * 1.18
    fit = [V([-0.06, 0, -0.06]), span + V([0.06, 0, 0.06])]
    im, P = c.render(s, cam, style="studio", margin=70, fit_points=fit, projector=True, light=V([-0.5, -0.8, 0.6]))
    if label_alpha > 0:
        d = ImageDraw.Draw(im, "RGBA")
        f, fb = ImageFont.truetype(fonts["light"], 28), ImageFont.truetype(fonts["bold"], 36)
        a = int(255 * label_alpha)
        (x0, y0), (x1, y1) = P(V([0.0, 0.0, 0.0])), P(AXIS)
        n = math.hypot(x1 - x0, y1 - y0)
        nx, ny = (y1 - y0) / n, -(x1 - x0) / n                    # on screen, square off the club, up and left
        for name in ("grip", "shaft", "ferrule", "head"):
            x, y = P(anchors[name])
            title, spec = LABELS[name]()
            side = -1 if name == "head" else 1                   # the head's label goes straight right, in the open
            lx, ly = (x + nx * 120, y + ny * 120) if side == 1 else (x + 150, y + 40)
            w = max(d.textlength(title, font=fb), d.textlength(spec, font=f))
            tx = max(40, lx - w) if side == 1 else lx + 10
            d.line([(x, y), (lx, ly)], fill=b["accent"] + (a,), width=3)
            d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=b["accent"] + (a,))
            d.text((tx, ly - 84), title, font=fb, fill=b["accent"] + (a,))
            d.text((tx, ly - 40), spec, font=f, fill=(255, 255, 255, a))
        d.text((60, 56), f"A {SPEC['length_in']} in 7-iron, built from maker specs. Head outline is generic.",
               font=ImageFont.truetype(fonts["light"], 24), fill=(220, 220, 220, a))
    return im


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--brand", choices=sorted(BRAND), required=True)
    ap.add_argument("--reel", action="store_true", help="also write a 1080x1350 mp4 (needs ffmpeg)")
    ap.add_argument("--seconds", type=float, default=7.0)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    fdir = ROOT / "data" / "brand-directory" / a.brand / "typography" / "fonts"
    fonts = {"light": str(fdir / "Montserrat-Light.ttf"), "bold": str(fdir / "Montserrat-ExtraBold.ttf")}
    still = a.out / f"club_7iron_exploded_{a.brand}.png"
    frame(a.brand, 1.0, 0, 1.0, fonts).save(still)
    print(f"wrote {still}")
    if not a.reel:
        return 0
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found: install it to make the reel", file=sys.stderr)
        return 1
    fps, n = 30, int(a.seconds * 30)
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = i / (n - 1)
            ease = lambda x: 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, x)))  # noqa: E731
            explode = ease((t - 0.15) / 0.45)                        # still, then the parts pull apart
            labels = ease((t - 0.62) / 0.15)                         # then the labels come in
            frame(a.brand, explode, -60 + 60 * ease(t / 0.6), labels, fonts).save(f"{tmp}/f{i:04d}.png")
        reel = a.out / f"club_7iron_exploded_{a.brand}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", f"{tmp}/f%04d.png",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(reel)], check=True)
    print(f"wrote {reel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
