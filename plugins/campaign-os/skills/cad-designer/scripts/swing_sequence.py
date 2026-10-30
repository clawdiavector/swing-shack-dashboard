#!/usr/bin/env python3
"""A golf swing as one picture: the seven positions (address, takeaway, top, downswing, impact, follow,
finish) drawn as ghost figures over each other, with the hand path and the club-head path as arcs.

    python3 swing_sequence.py --out out/ [--view faceon|dtl] [--style blueprint|plan] [--brand swing-shack]

faceon: the camera faces the golfer, target on the right. dtl: down the line, from behind the golfer
looking at the target. The positions are an illustration of a two-lever swing, not a measured swing:
no number from it goes into copy.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import cad3d as c  # noqa: E402
from cad3d import V  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
ORDER = ["address", "takeaway", "top", "downswing", "impact", "follow", "finish"]
ACCENT = {"swing-shack": (116, 204, 70), "stick": (0, 179, 186)}
BALL = (2.6, 3.0)


def path(key, steps=60):
    """A smooth path of one joint through the swing, by blending the rig between positions."""
    pts = []
    for a, b in zip(ORDER, ORDER[1:]):
        pa, pb = c.POSES[a], c.POSES[b]
        for i in range(steps):
            t = i / steps
            c.POSES["_blend"] = {k: pa[k] + (pb[k] - pa[k]) * t for k in pa}
            pts.append(c.swing_rig(BALL, "_blend")[key])
    c.POSES.pop("_blend", None)
    return pts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--view", choices=["faceon", "dtl"], default="faceon")
    ap.add_argument("--style", choices=["blueprint", "plan"], default="blueprint")
    ap.add_argument("--brand", choices=sorted(ACCENT), default="swing-shack")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    brand_dir = ROOT / "data" / "brand-directory" / a.brand
    fonts = brand_dir / "typography" / "fonts"
    font_l = str(next(iter(sorted(fonts.glob("Montserrat-Light*.ttf")))))
    accent = ACCENT[a.brand]

    s = c.Scene()
    s.solids.append(c.box(BALL[0] - 1.2, BALL[1] - 1.5, -0.04, BALL[0] + 0.8, BALL[1] + 1.5, 0, name="floor"))
    for pose in ORDER:
        s.capsules += c.golfer(BALL, pose, ghost=True)
    s.capsules += c.golfer(BALL, "address")                      # one solid figure at address
    s.lines.append((path("hands"), accent, 3))
    s.lines.append((path("club_head"), accent, 5))
    cam = c.Camera("faceon" if a.view == "faceon" else "front")
    im = c.render(s, cam, style=a.style, font_path=font_l, margin=110)
    d = ImageDraw.Draw(im)
    ink = (255, 255, 255) if a.style == "blueprint" else (40, 40, 40)
    d.text((60, 1350 - 90), "Illustration of a swing, not a measured one", font=ImageFont.truetype(font_l, 24), fill=ink)
    name = f"swing_sequence_{a.view}.png"
    im.save(a.out / name)
    print(f"wrote {a.out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
