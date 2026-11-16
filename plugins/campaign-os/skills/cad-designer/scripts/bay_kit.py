#!/usr/bin/env python3
"""A Swing Shack simulator bay with its kit, to scale, pulled apart in layers like a building plan: the
floor; the mat, ball, golfer, TrackMan and bag; the screen and enclosure; the projector on the ceiling.

    python3 bay_kit.py --out out/ [--width 4.6 --depth 5.5 --height 3.1 --ball-to-screen 2.5] [--measured]
                       [--style blueprint|clay] [--reel]

TrackMan 4 is its real size (300 x 300 x 45 mm) and sits at least 4.7 m from the screen, TrackMan's own
minimum (trackman.com/golf/launch-monitors/tech-specs). The bay defaults are TrackMan's recommended single
bay; everything not measured at Swing Shack is labelled placeholder or estimate on the image.
"""
import argparse
import copy
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import cad3d as c  # noqa: E402
from cad3d import V  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
SS = ROOT / "data" / "brand-directory" / "swing-shack"
FONTS = SS / "typography" / "fonts"
GREEN = (116, 204, 70)
TM = dict(w=0.300, h=0.300, d=0.045, to_screen=4.7)     # TrackMan 4 tech specs
LIFT = {"floor": 0.0, "kit": 1.1, "enclosure": 2.4, "ceiling": 4.0}


def _move(scene, dz):
    out = copy.deepcopy(scene)
    off = V([0.0, 0.0, dz])
    for s in out.solids:
        s.faces = [f + off for f in s.faces]
    for cap in out.capsules:
        cap.a, cap.b = cap.a + off, cap.b + off
    for dec in out.decals:
        dec.corners = [p + off for p in dec.corners]
    out.lines = [([p + off for p in pts], col, w) for pts, col, w in out.lines]
    return out


def kit(W, D, H, ball_to_screen, explode=1.0, measured=False, style="blueprint"):
    """Layers (name -> cad3d.Scene) and info: ball, screen_y, labels (name -> (point, title, spec))."""
    screen_y = D - 0.05
    ball = (W * 0.565, screen_y - ball_to_screen)
    ph = "" if measured else " · placeholder"
    L = {k: c.Scene() for k in LIFT}

    L["floor"].solids.append(c.box(0, 0, -0.05, W, D, 0, fill=(70, 72, 74), name="floor"))

    k = L["kit"]
    k.solids.append(c.box(ball[0] - 0.9, ball[1] - 0.75, 0, ball[0] + 0.6, ball[1] + 0.75, 0.02, fill=(70, 120, 60), name="mat"))
    k.capsules.append(c.Capsule(V([ball[0], ball[1], 0.041]), V([ball[0], ball[1], 0.0411]), 0.0214, (255, 255, 255)))
    k.capsules += c.golfer(ball, "address")
    tm_front = screen_y - TM["to_screen"]                   # the face of the unit nearest the screen
    tx = ball[0]
    k.solids.append(c.box(tx - TM["w"] / 2, tm_front - TM["d"], 0.20, tx + TM["w"] / 2, tm_front, 0.20 + TM["h"],
                          fill=(30, 30, 32), name="trackman"))
    k.solids.append(c.frustum((tx, tm_front - TM["d"] / 2, 0.0), (tx, tm_front - TM["d"] / 2, 0.20), 0.03, 0.015,
                              fill=(60, 60, 60), name="trackman stand", n=8, line=True))
    bag = (0.35, ball[1] - 0.4)
    k.solids.append(c.frustum((bag[0], bag[1], 0.0), (bag[0], bag[1], 0.89), 0.12, 0.13, fill=(40, 40, 44), name="bag", n=12, line=True))

    e = L["enclosure"]
    e.solids.append(c.box(0.3, screen_y - 0.02, 0.25, W - 0.3, screen_y, H - 0.25, fill=(225, 225, 225), name="screen"))
    for x in (0.0, W):
        e.solids.append(c.box(x - 0.01, screen_y - 2.0, 0.0, x + 0.01, screen_y, H, fill=(50, 50, 50), name="netting"))
        e.solids.append(c.frustum((x, screen_y, 0), (x, screen_y, H), 0.03, 0.03, fill=(80, 80, 80), name="post", n=8, line=True))
    logo = Image.open(SS / "logos" / ("swing-shack-logo-white.png" if style == "blueprint" else "swing-shack-logo-dark.png"))
    lw = min(2.0, W - 1.4)
    lh = lw * logo.height / logo.width
    cz = H - 0.25 - lh / 2 - 0.15
    y = screen_y - 0.025
    e.decals.append(c.Decal(logo, [V([W / 2 - lw / 2, y, cz - lh / 2]), V([W / 2 + lw / 2, y, cz - lh / 2]),
                                   V([W / 2 + lw / 2, y, cz + lh / 2]), V([W / 2 - lw / 2, y, cz + lh / 2])]))

    cl = L["ceiling"]
    proj = (W / 2, screen_y - 2.9)
    cl.solids.append(c.box(proj[0] - 0.18, proj[1] - 0.15, H - 0.14, proj[0] + 0.18, proj[1] + 0.15, H - 0.02,
                           fill=(220, 220, 220), name="projector"))
    rim = [V([0, 0, H]), V([W, 0, H]), V([W, D, H]), V([0, D, H]), V([0, 0, H])]
    cl.lines.append((rim, (235, 242, 250) if style == "blueprint" else (90, 90, 90), 2))   # the ceiling, as its outline
    lens = V([proj[0], proj[1] + 0.15, H - 0.08])
    for cx_, cz_ in ((0.3, 0.25), (W - 0.3, 0.25), (W - 0.3, H - 0.25), (0.3, H - 0.25)):
        cl.lines.append(([lens, V([cx_, screen_y, cz_ - LIFT["ceiling"] * explode + LIFT["enclosure"] * explode])],
                         GREEN, 1))

    layers = {name: _move(sc, LIFT[name] * explode) for name, sc in L.items()}
    up = {n: V([0, 0, LIFT[n] * explode]) for n in LIFT}
    labels = {
        "projector": (V([proj[0], proj[1], H - 0.08]) + up["ceiling"], "Projector", "ceiling mounted" + (ph or " · estimate")),
        "screen": (V([W - 0.6, screen_y, H * 0.35]) + up["enclosure"], "Impact screen",
                   f"{W - 0.6:.1f} × {H - 0.5:.1f} m" + (ph or "")),
        "trackman": (V([tx, tm_front, 0.35]) + up["kit"], "TrackMan 4", "300 × 300 × 45 mm · 4.7 m to the screen"),
        "mat": (V([ball[0] - 0.6, ball[1] - 0.5, 0.02]) + up["kit"], "Hitting mat", "1.5 × 1.5 m · estimate"),
        "bag": (V([bag[0], bag[1], 0.6]) + up["kit"], "Stand bag", "0.89 m tall · estimate"),
        "floor": (V([W * 0.75, 0.6, 0.0]) + up["floor"], "Bay", f"{W:.1f} × {D:.1f} × {H:.1f} m" + (ph or " · measured")),
    }
    return layers, dict(ball=ball, screen_y=screen_y, labels=labels)


def render_kit(W, D, H, ball_to_screen, explode=1.0, measured=False, style="blueprint", yaw=-38, label_alpha=1.0):
    layers, info = kit(W, D, H, ball_to_screen, explode, measured, style)
    s = c.Scene()
    for sc in layers.values():
        s.solids += sc.solids
        s.capsules += sc.capsules
        s.decals += sc.decals
        s.lines += sc.lines
    fit = [V([0, 0, -0.1]), V([W, D, H + LIFT["ceiling"]])]
    im, P = c.render(s, c.Camera("iso", yaw=yaw, pitch=30), style=style, margin=170, fit_points=fit,
                     font_path=str(FONTS / "Montserrat-Light.ttf"), projector=True)
    d = ImageDraw.Draw(im, "RGBA")
    ink = (255, 255, 255) if style == "blueprint" else (40, 40, 40)
    a = int(255 * label_alpha)
    ft, fs = ImageFont.truetype(str(FONTS / "Montserrat-ExtraBold.ttf"), 30), ImageFont.truetype(str(FONTS / "Montserrat-Light.ttf"), 24)
    if a:
        placed, texts = {True: [], False: []}, []         # labels on each side, pushed apart so none overlap
        bg = c.STYLES[style]["bg"]
        for name, (pt, title, spec) in sorted(info["labels"].items(), key=lambda kv: P(kv[1][0])[1]):
            x, y = P(pt)
            right = x > im.width / 2
            w = max(d.textlength(title, font=ft), d.textlength(spec, font=fs))
            tx = im.width - 40 - w if right else 40
            covers = tx - 20 <= x <= tx + w + 20                # the box would sit on the part: drop below it
            ly = max([y + (70 if covers else 0)] + [q + 92 for q in placed[right]])
            placed[right].append(ly)
            ex = tx - 12 if right else tx + w + 12
            d.line([(x, y), (ex, ly)], fill=GREEN + (a,), width=2)
            d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=GREEN + (a,))
            texts.append((tx, ly, w, title, spec))
        for tx, ly, w, title, spec in texts:                # text on a backing box, over every line
            d.rectangle([tx - 8, ly - 42, tx + w + 8, ly + 34], fill=bg + (int(225 * label_alpha),))
            d.text((tx, ly - 38), title, font=ft, fill=GREEN + (a,))
            d.text((tx, ly + 2), spec, font=fs, fill=ink + (a,))
    d.text((60, 56), "SWING SHACK  ·  BAY KIT", font=ImageFont.truetype(str(FONTS / "Montserrat-Light.ttf"), 30), fill=ink)
    if not measured:
        d.text((60, im.height - 70), "Placeholder dimensions: TrackMan's recommended single bay", font=fs, fill=ink)
    return im


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--width", type=float, default=4.6)
    ap.add_argument("--depth", type=float, default=5.5)
    ap.add_argument("--height", type=float, default=3.1)
    ap.add_argument("--ball-to-screen", type=float, default=2.5)
    ap.add_argument("--measured", action="store_true", help="the dimensions are Swing Shack's own, measured")
    ap.add_argument("--style", choices=["blueprint", "clay"], default="blueprint")
    ap.add_argument("--reel", action="store_true", help="also write a 1080x1350 mp4 of the bay coming apart (needs ffmpeg)")
    a = ap.parse_args(argv)
    if a.depth - 0.05 - TM["to_screen"] - TM["d"] < 0:
        print(f"a {a.depth} m deep bay is too short for TrackMan 4's 4.7 m to the screen", file=sys.stderr)
        return 1
    a.out.mkdir(parents=True, exist_ok=True)
    args = (a.width, a.depth, a.height, a.ball_to_screen)
    still = a.out / f"bay_kit_{a.style}.png"
    render_kit(*args, explode=1.0, measured=a.measured, style=a.style).save(still)
    print(f"wrote {still}")
    if a.reel:
        if not shutil.which("ffmpeg"):
            print("ffmpeg not found: install it to make the reel", file=sys.stderr)
            return 1
        n = 210
        ease = lambda x: 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, x)))  # noqa: E731
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(n):
                t = i / (n - 1)
                render_kit(*args, explode=ease((t - 0.15) / 0.5), measured=a.measured, style=a.style,
                           yaw=-60 + 22 * ease(t), label_alpha=ease((t - 0.7) / 0.15)).save(f"{tmp}/f{i:04d}.png")
            reel = a.out / f"bay_kit_{a.style}.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30", "-i", f"{tmp}/f%04d.png",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(reel)], check=True)
        print(f"wrote {reel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
