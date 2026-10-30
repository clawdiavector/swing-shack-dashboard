#!/usr/bin/env python3
"""A Swing Shack simulator bay at true scale, rendered as a blueprint isometric, a floor plan and a clay
perspective, with the real logo on the screen and a golfer at address.

    python3 swing_shack_bay.py --out out/ [--width 4.6 --depth 5.5 --height 3.1 --ball-to-screen 2.5]

The defaults are TrackMan's recommended single bay (trackman.com/golf/simulator/tech-specs): placeholders
until Swing Shack's own bays are measured. Every render says so unless --measured is passed.
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import cad3d as c  # noqa: E402
from cad3d import V  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
SS = ROOT / "data" / "brand-directory" / "swing-shack"
FONT = str(SS / "typography" / "fonts" / "Montserrat-BlackItalic.ttf")
FONT_L = str(SS / "typography" / "fonts" / "Montserrat-Light.ttf")
PAD, DARK, TURF, MAT = (64, 64, 66), (40, 40, 42), (96, 150, 78), (70, 120, 60)


def bay(W, D, H, ball, pose="address"):
    s = c.Scene()
    s.solids.append(c.box(0, 0, -0.05, W, D, 0, fill=TURF, name="floor"))
    s.solids.append(c.box(ball[0] - 0.9, ball[1] - 0.75, 0, ball[0] + 0.6, ball[1] + 0.75, 0.02, fill=MAT, name="mat"))
    s.solids.append(c.box(-0.12, 0, 0, 0, D, H, fill=PAD, name="side wall"))
    s.solids.append(c.box(0, D, 0, W, D + 0.12, H, fill=DARK, name="screen wall"))
    s.solids.append(c.box(0.3, D - 0.02, 0.25, W - 0.3, D, H - 0.25, fill=(28, 28, 28), name="impact screen"))
    s.capsules.append(c.Capsule(V([ball[0], ball[1], 0.0214]), V([ball[0], ball[1], 0.0215]), 0.0214, (255, 255, 255)))
    s.capsules += c.golfer(ball, pose)
    logo = Image.open(SS / "logos" / "swing-shack-logo-white.png")
    lw = min(2.4, W - 1.2)
    lh = lw * logo.height / logo.width
    cx, cz = W / 2, H - 0.25 - lh / 2 - 0.12          # upper part of the screen, clear of the golfer's head
    y = D - 0.03
    s.decals.append(c.Decal(logo, [V([cx - lw / 2, y, cz - lh / 2]), V([cx + lw / 2, y, cz - lh / 2]),
                                   V([cx + lw / 2, y, cz + lh / 2]), V([cx - lw / 2, y, cz + lh / 2])]))
    return s


def dims(s, W, D, H, ball, height=True):
    s.dims += [c.Dim(V([0, 0, 0]), V([W, 0, 0]), V([0, -0.6, 0]), f"{W:.1f} m"),
               c.Dim(V([W, 0, 0]), V([W, D, 0]), V([0.6, 0, 0]), f"{D:.1f} m"),
               c.Dim(V([ball[0], ball[1], 0]), V([ball[0], D, 0]), V([0.9, 0, 0]), f"{D - ball[1]:.1f} m")]
    if height:
        s.dims.append(c.Dim(V([W, D, 0]), V([W, D, H]), V([0.6, 0, 0]), f"{H:.1f} m"))


def title(img, kicker, head, note, colour, accent):
    d = ImageDraw.Draw(img)
    d.text((60, 56), kicker, font=ImageFont.truetype(FONT_L, 30), fill=colour)
    d.text((56, 96), head, font=ImageFont.truetype(FONT, 88), fill=accent)
    if note:
        d.text((60, 1350 - 86), note, font=ImageFont.truetype(FONT_L, 24), fill=colour)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--width", type=float, default=4.6)
    ap.add_argument("--depth", type=float, default=5.5)
    ap.add_argument("--height", type=float, default=3.1)
    ap.add_argument("--ball-to-screen", type=float, default=2.5)
    ap.add_argument("--measured", action="store_true", help="the dimensions are Swing Shack's own, measured")
    a = ap.parse_args(argv)
    W, D, H = a.width, a.depth, a.height
    ball = (W * 0.565, D - a.ball_to_screen)
    note = "" if a.measured else "Placeholder dimensions: TrackMan's recommended single bay"
    a.out.mkdir(parents=True, exist_ok=True)

    s = bay(W, D, H, ball); dims(s, W, D, H, ball)
    im = c.render(s, c.Camera("iso", yaw=-35, pitch=32), style="blueprint", font_path=FONT_L, margin=150)
    title(im, "SWING SHACK  ·  BAY PLAN", "ONE BAY.", note, (255, 255, 255), (116, 204, 70))
    im.save(a.out / "bay_blueprint_iso.png")

    s = bay(W, D, H, ball); dims(s, W, D, H, ball, height=False)
    im = c.render(s, c.Camera("plan"), style="plan", font_path=FONT_L, margin=170)
    title(im, "SWING SHACK  ·  FLOOR PLAN", "TOP VIEW.", note, (40, 40, 40), (28, 28, 28))
    im.save(a.out / "bay_plan.png")

    s = bay(W, D, H, ball, "top")
    cam = c.Camera("persp", eye=(W * 0.22, -2.4, 1.7), target=(W * 0.6, D, 1.35), fov=46)
    c.render(s, cam, style="clay", font_path=FONT_L, margin=30).save(a.out / "bay_clay_persp.png")
    print(f"wrote 3 renders to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
