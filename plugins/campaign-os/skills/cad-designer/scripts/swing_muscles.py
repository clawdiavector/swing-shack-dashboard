#!/usr/bin/env python3
"""Which muscles drive the swing: the golfer in one position with the working muscles drawn see-through
on the body, and the muscles the backswing stretches.

    python3 swing_muscles.py --out out/ [--pose top|downswing|impact] [--view faceon|dtl] [--brand swing-shack]

Red: a muscle an EMG study found working in this position (solid high, lighter moderate). Blue: a muscle
stretched more than 8% past its address length, loaded like a spring. Only positions with an EMG source
show red; the study is named on the image. Sources: ../anatomy.json.
"""
import argparse
import sys
from pathlib import Path

from PIL import ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import cad3d as c  # noqa: E402
from cad3d import V  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
BALL = (2.6, 3.0)
SHORT = {"bechler_1995": "Bechler et al. 1995", "jobe_perry_pink_1989": "Jobe, Perry & Pink 1989",
         "emg_review_2012": "EMG review, J Electromyogr Kinesiol 2012"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pose", choices=list(c.POSES), default="impact")
    ap.add_argument("--view", choices=["faceon", "dtl"], default="faceon")
    ap.add_argument("--brand", choices=["swing-shack", "stick"], default="swing-shack")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    fonts = ROOT / "data" / "brand-directory" / a.brand / "typography" / "fonts"
    font_l = str(next(iter(sorted(fonts.glob("Montserrat-Light*.ttf")))))

    s = c.Scene()
    s.solids.append(c.box(BALL[0] - 1.3, BALL[1] - 0.9, -0.04, BALL[0] + 0.5, BALL[1] + 0.9, 0, fill=(200, 200, 200), name="floor"))
    s.capsules += c.golfer(BALL, a.pose, fill=(236, 228, 220))
    s.capsules.append(c.Capsule(V([BALL[0], BALL[1], 0.0214]), V([BALL[0], BALL[1], 0.0215]), 0.0214, (255, 255, 255)))
    s.bands += [(p, q, r * 1.4, col) for p, q, r, col in c.muscle_bands(BALL, a.pose)]
    fit = [V([BALL[0] - 1.3, BALL[1] - 0.9, 0]), V([BALL[0] + 0.5, BALL[1] + 0.9, 2.0])]
    im = c.render(s, c.Camera("faceon" if a.view == "faceon" else "front"), style="clay", font_path=font_l,
                  margin=150, fit_points=fit)

    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(font_l, 24)
    y = 1350 - 60
    working = [m for m in c.muscles(BALL, a.pose) if m["activity"]]
    sources = sorted({SHORT.get(m["source"], m["source"]) for m in working})
    lines = ["Red: working (EMG). Blue: stretched by the swing. Illustration, not a measured swing."]
    if working:
        lines.insert(0, "Working: " + ", ".join(m["name"] for m in working))
        lines.insert(1, "Source: " + "; ".join(sources))
    wrapped = []
    for line in lines:                               # wrap to the frame
        words, cur = line.split(" "), ""
        for w in words:
            if cur and d.textlength(cur + " " + w, font=f) > 1000:
                wrapped.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        wrapped.append(cur)
    for line in reversed(wrapped):
        y -= 34
        d.text((40, y), line, font=f, fill=(40, 40, 40))
    name = f"swing_muscles_{a.pose}_{a.view}.png"
    im.save(a.out / name)
    print(f"wrote {a.out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
