"""CAD-lite: true-scale 3D scenes in metres, drawn from any camera in a chosen style. Pillow + numpy only.

A scene is a list of solids (boxes, quads, capsules, polylines) plus image decals (a logo on a wall).
Cameras: iso (isometric), plan (top-down), front/side elevation, persp (eye + target + fov).
Styles: blueprint (white lines on navy, grid, dimensions), plan (dark lines on paper), clay (lit flat faces).
"""

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

V = np.array


# ── geometry ──────────────────────────────────────────────────────────────

@dataclass
class Solid:
    faces: list            # list of (n,3) arrays in metres
    fill: tuple = (210, 210, 210)
    line: bool = True
    name: str = ""


def box(x0, y0, z0, x1, y1, z1, fill=(210, 210, 210), name="", line=True):
    """Axis-aligned box. x = across the bay, y = towards the screen, z = up."""
    p = [V([x, y, z], float) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    idx = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    return Solid([np.stack([p[i] for i in f]) for f in idx], fill, line, name)


def quad(a, b, c, d, fill=(210, 210, 210), name="", line=True):
    return Solid([np.stack([V(a, float), V(b, float), V(c, float), V(d, float)])], fill, line, name)


@dataclass
class Capsule:
    a: np.ndarray
    b: np.ndarray
    r: float               # radius in metres
    fill: tuple = (235, 235, 235)


@dataclass
class Decal:
    """An image laid flat on a quad (corners: bottom-left, bottom-right, top-right, top-left)."""
    image: Image.Image
    corners: list


@dataclass
class Dim:
    """A dimension line between two points, labelled in metres, offset along `off`."""
    a: np.ndarray
    b: np.ndarray
    off: np.ndarray
    label: str = ""


@dataclass
class Scene:
    solids: list = field(default_factory=list)
    capsules: list = field(default_factory=list)
    decals: list = field(default_factory=list)
    dims: list = field(default_factory=list)
    lines: list = field(default_factory=list)    # (points, colour, width)


# ── golfer: a poseable mannequin with adult proportions ──────────────────

SEG = {  # metres, for a 1.75 m adult (anthropometric proportions)
    "upper_arm": 0.31, "forearm": 0.27, "head_r": 0.11,
}
CLUB_FROM_HANDS = 0.84     # a 7-iron is 37 in (0.94 m); the hands hold it about 10 cm below the butt

# Seven positions of a two-lever swing. theta: how far the hands have travelled round the chest
# (+ back, away from the target; - through); hinge: extra wrist angle of the club; tilt: spine
# angle from vertical.
POSES = {
    "address":   dict(theta=0,    hinge=0,    tilt=30),
    "takeaway":  dict(theta=45,   hinge=15,   tilt=30),
    "top":       dict(theta=130,  hinge=135,  tilt=30),
    "downswing": dict(theta=90,   hinge=40,   tilt=30),
    "impact":    dict(theta=-5,   hinge=-5,   tilt=29),
    "follow":    dict(theta=-90,  hinge=-40,  tilt=20),
    "finish":    dict(theta=-160, hinge=-110, tilt=8),
}


def rotate(v, axis, deg):
    """Rodrigues rotation of vector v about a unit axis."""
    k = axis / np.linalg.norm(axis)
    t = math.radians(deg)
    return v * math.cos(t) + np.cross(k, v) * math.sin(t) + k * np.dot(k, v) * (1 - math.cos(t))


def _reach(shoulder, hands, length):
    d = hands - shoulder
    n = np.linalg.norm(d)
    return hands if n <= length else shoulder + d * (length / n)


def _elbow(shoulder, hands):
    u, f = SEG["upper_arm"], SEG["forearm"]
    d = hands - shoulder
    n = np.linalg.norm(d)
    a = (u * u - f * f + n * n) / (2 * n)
    h = math.sqrt(max(u * u - a * a, 0.0))
    axis = d / n
    down = V([0.0, 0.0, -1.0]) - axis * axis[2]          # bend the elbow downwards, the way arms hang
    down = down / (np.linalg.norm(down) or 1.0)
    return shoulder + axis * a + down * h


def swing_rig(ball_xy, pose="address"):
    """Joint positions (metres) for a right-handed golfer at ball_xy; target is +y, the golfer faces +x.
    Hands travel round the chest on the swing plane, the club follows them with a wrist hinge, the
    shoulders and hips turn with the swing, and the arms can never stretch past their length."""
    P = POSES[pose]
    bx, by = ball_xy
    t_dir = V([0.0, 1.0, 0.0])
    head_addr = V([bx, by - 0.035, 0.02])                # club head resting just behind the ball
    dx, dy = 0.45, 0.085
    hands_addr = V([bx - dx, by + 0.05, 0.02 + math.sqrt(CLUB_FROM_HANDS ** 2 - dx ** 2 - dy ** 2)])
    pelvis = V([bx - 0.70, by, 0.92])
    tilt = math.radians(P["tilt"])
    chest = pelvis + 0.394 * V([math.sin(tilt), 0.0, math.cos(tilt)])
    chest_addr = pelvis + 0.394 * V([math.sin(math.radians(30)), 0.0, math.cos(math.radians(30))])
    spine = (chest - pelvis) / np.linalg.norm(chest - pelvis)

    v = hands_addr - chest_addr
    n = np.cross(v, -t_dir)                              # swing-plane axis: +theta moves the hands back
    hands = chest + rotate(v, n, P["theta"])
    club_dir = rotate((head_addr - hands_addr) / CLUB_FROM_HANDS, n, P["theta"] + P["hinge"])

    turn = float(np.clip(0.7 * P["theta"], -100, 92))
    lead_sh = chest + rotate(V([0.0, 0.20, 0.03]), spine, -turn)
    trail_sh = chest + rotate(V([0.0, -0.20, -0.03]), spine, -turn)
    reach = SEG["upper_arm"] + SEG["forearm"]
    for _ in range(12):                                  # keep both hands on the grip within reach
        hands = _reach(lead_sh, hands, reach)
        hands = _reach(trail_sh, hands, reach)

    club_head = hands + club_dir * CLUB_FROM_HANDS
    hip_turn = turn * 0.5
    hips = [pelvis + rotate(V([0.0, s * 0.15, 0.0]), V([0, 0, 1.0]), -hip_turn) for s in (1, -1)]
    ankles = [V([bx - 0.68, by + s * 0.24, 0.08]) for s in (1, -1)]
    knees = [(h + a) / 2 + V([0.08, 0.0, 0.0]) for h, a in zip(hips, ankles)]
    return {
        "hands": hands, "club_head": club_head, "chest": chest, "pelvis": pelvis,
        "head": chest + spine * 0.30,
        "lead_shoulder": lead_sh, "trail_shoulder": trail_sh,
        "lead_elbow": _elbow(lead_sh, hands), "trail_elbow": _elbow(trail_sh, hands),
        "lead_hip": hips[0], "trail_hip": hips[1], "lead_knee": knees[0], "trail_knee": knees[1],
        "lead_ankle": ankles[0], "trail_ankle": ankles[1],
    }


def golfer(ball_xy, pose="address", facing=1.0, fill=(240, 240, 240), ghost=False):
    """Capsules for a right-handed golfer at ball_xy (target +y). ghost=True draws only the arms and the
    club as thin lines: the strobe look, where the club repeats and the body stays one figure."""
    r = swing_rig(ball_xy, pose)
    if ghost:
        caps = [Capsule(r["lead_shoulder"], r["lead_elbow"], 0.012, fill),
                Capsule(r["lead_elbow"], r["hands"], 0.012, fill),
                Capsule(r["hands"], r["club_head"], 0.006, fill),
                Capsule(r["club_head"], r["club_head"] + V([0, 0, 0.001]), 0.02, fill)]
        return caps
    k = 1.0
    caps = []
    for side in ("lead", "trail"):
        ankle, knee, hip = r[f"{side}_ankle"], r[f"{side}_knee"], r[f"{side}_hip"]
        caps += [Capsule(ankle, knee, 0.055 * k, fill), Capsule(knee, hip, 0.075 * k, fill),
                 Capsule(V([ankle[0] - 0.04, ankle[1], 0.04]), V([ankle[0] + 0.16, ankle[1], 0.04]), 0.04 * k, fill)]
        sh, el = r[f"{side}_shoulder"], r[f"{side}_elbow"]
        caps += [Capsule(sh, el, 0.045 * k, fill), Capsule(el, r["hands"], 0.04 * k, fill)]
    caps += [Capsule(r["pelvis"], r["chest"], 0.14 * k, fill),
             Capsule(r["lead_shoulder"], r["trail_shoulder"], 0.06 * k, fill),
             Capsule(r["head"], r["head"] + V([0, 0, 0.001]), SEG["head_r"] * (0.7 if ghost else 1.0), fill),
             Capsule(r["hands"], r["club_head"], 0.008, (40, 40, 40) if not ghost else fill),
             Capsule(r["club_head"], r["club_head"] + V([0, 0, 0.001]), 0.022 * (0.8 if ghost else 1.0),
                     (40, 40, 40) if not ghost else fill)]
    return caps


# ── cameras ───────────────────────────────────────────────────────────────

@dataclass
class Camera:
    kind: str = "iso"                        # iso | plan | front | side | persp
    eye: tuple = (0, 0, 0)
    target: tuple = (0, 0, 0)
    fov: float = 40.0
    yaw: float = 45.0                        # iso: rotation about z
    pitch: float = 35.264                    # iso: true isometric

    def view(self, p):
        p = V(p, float)
        if self.kind == "plan":              # looking down: higher is nearer, so depth is -z
            return V([p[0], p[1], -p[2]])
        if self.kind == "front":             # looking along +y at the screen wall: further is larger y
            return V([p[0], p[2], p[1]])
        if self.kind == "side":
            return V([p[1], p[2], p[0]])
        if self.kind == "faceon":            # facing the golfer (who faces +x): the target is on screen right
            return V([p[1], p[2], -p[0]])
        if self.kind == "iso":
            y, pt = math.radians(self.yaw), math.radians(self.pitch)
            x1 = p[0] * math.cos(y) - p[1] * math.sin(y)
            y1 = p[0] * math.sin(y) + p[1] * math.cos(y)
            return V([x1, p[2] * math.cos(pt) + y1 * math.sin(pt), y1 * math.cos(pt) - p[2] * math.sin(pt)])
        # persp
        e, t = V(self.eye, float), V(self.target, float)
        f = (t - e) / np.linalg.norm(t - e)
        r = np.cross(f, V([0, 0, 1.0])); r /= np.linalg.norm(r)
        u = np.cross(r, f)
        d = p - e
        z = max(np.dot(d, f), 1e-3)
        s = 1 / math.tan(math.radians(self.fov) / 2)
        return V([np.dot(d, r) * s / z, np.dot(d, u) * s / z, z])


# ── renderer ──────────────────────────────────────────────────────────────

STYLES = {
    "blueprint": dict(bg=(16, 44, 86), line=(235, 242, 250), fill=None, grid=(32, 66, 116), dim=(120, 200, 255)),
    "plan": dict(bg=(246, 244, 240), line=(40, 40, 40), fill=None, grid=(228, 224, 218), dim=(28, 28, 28)),
    "clay": dict(bg=(236, 234, 230), line=(90, 90, 90), fill=True, grid=None, dim=(60, 60, 60)),
}


def render(scene: Scene, cam: Camera, size=(1080, 1350), style="blueprint", margin=90, font_path=None,
           fit_points=None, light=V([-0.4, -0.6, 0.7])):
    st = STYLES[style]
    W, H = size
    img = Image.new("RGB", size, st["bg"])
    d = ImageDraw.Draw(img, "RGBA")

    # fit: project every point, scale to the frame
    pts = [v for s in scene.solids for f in s.faces for v in f] + [c.a for c in scene.capsules] + [c.b for c in scene.capsules]
    pts += list(fit_points or [])
    pv = np.stack([cam.view(p) for p in pts])
    x0, x1, y0, y1 = pv[:, 0].min(), pv[:, 0].max(), pv[:, 1].min(), pv[:, 1].max()
    k = min((W - 2 * margin) / (x1 - x0), (H - 2 * margin) / (y1 - y0))
    ox, oy = W / 2 - k * (x0 + x1) / 2, H / 2 + k * (y0 + y1) / 2

    def P(p):
        v = cam.view(p)
        return (ox + k * v[0], oy - k * v[1]), v[2]

    if st["grid"] and cam.kind in ("plan", "iso", "front"):
        for g in np.arange(-10, 10.01, 0.5):        # 50 cm grid on the floor (or wall in front view)
            a = (g, -10, 0) if cam.kind != "front" else (g, 0, -10)
            b = (g, 10, 0) if cam.kind != "front" else (g, 0, 10)
            c = (-10, g, 0) if cam.kind != "front" else (-10, 0, g)
            e = (10, g, 0) if cam.kind != "front" else (10, 0, g)
            for p, q in ((a, b), (c, e)):
                d.line([P(p)[0], P(q)[0]], fill=st["grid"], width=1)

    # painter's algorithm: faces and capsule segments sorted far to near
    items = []
    for s in scene.solids:
        for f in s.faces:
            proj = [P(v) for v in f]
            depth = np.mean([z for _, z in proj])
            n = np.cross(f[1] - f[0], f[2] - f[0]); nn = np.linalg.norm(n)
            shade = 1.0 if nn == 0 else 0.62 + 0.38 * abs(np.dot(n / nn, light / np.linalg.norm(light)))
            items.append((depth, "face", [xy for xy, _ in proj], s, shade))
    for c in scene.capsules:
        (pa, za), (pb, zb) = P(c.a), P(c.b)
        items.append(((za + zb) / 2 - 0.01, "cap", (pa, pb), c, 1.0))
    for dec in scene.decals:
        proj = [P(v) for v in dec.corners]
        items.append((np.mean([z for _, z in proj]) - 0.005, "decal", [xy for xy, _ in proj], dec, 1.0))
    items.sort(key=lambda t: -t[0])

    lw = max(2, int(k * 0.012))
    for depth, kind, geo, obj, shade in items:
        if kind == "face":
            if st["fill"]:
                col = tuple(int(c * shade) for c in obj.fill)
                d.polygon(geo, fill=col)
            elif style == "blueprint":
                d.polygon(geo, fill=st["bg"] + (235,))
            else:
                d.polygon(geo, fill=st["bg"] + (240,))
            if obj.line:
                d.line(geo + [geo[0]], fill=st["line"], width=lw)
        elif kind == "cap":
            pa, pb = geo
            r = max(2, int(obj.r * k))
            col = tuple(int(c) for c in obj.fill) if st["fill"] else st["line"]
            if st["fill"]:
                d.line([pa, pb], fill=(70, 70, 70), width=2 * r + 3)
            d.line([pa, pb], fill=col, width=2 * r)
            for q in (pa, pb):
                if st["fill"]:
                    d.ellipse([q[0] - r - 1, q[1] - r - 1, q[0] + r + 1, q[1] + r + 1], fill=(70, 70, 70))
                d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)
        elif kind == "decal":
            img = paste_decal(img, obj.image, geo)
            d = ImageDraw.Draw(img, "RGBA")

    for pts_, col, w in scene.lines:
        d.line([P(p)[0] for p in pts_], fill=col, width=w)

    font = ImageFont.truetype(font_path, 26) if font_path else ImageFont.load_default()
    for dm in scene.dims:
        a, b = dm.a + dm.off, dm.b + dm.off
        (pa, _), (pb, _) = P(a), P(b)
        d.line([P(dm.a)[0], pa], fill=st["dim"], width=1)
        d.line([P(dm.b)[0], pb], fill=st["dim"], width=1)
        d.line([pa, pb], fill=st["dim"], width=2)
        for q, o in ((pa, pb), (pb, pa)):            # arrow ticks
            d.ellipse([q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4], fill=st["dim"])
        label = dm.label or f"{np.linalg.norm(dm.b - dm.a):.1f} m"
        mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        tb = d.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        d.rectangle([mx - tw / 2 - 6, my - th / 2 - 6, mx + tw / 2 + 6, my + th / 2 + 8], fill=st["bg"])
        d.text((mx - tw / 2, my - th / 2 - 2), label, font=font, fill=st["dim"])
    return img


def paste_decal(img, decal, quad_xy):
    """Perspective-map an image onto a projected quad (bottom-left, bottom-right, top-right, top-left)."""
    w, h = decal.size
    src = [(0, h), (w, h), (w, 0), (0, 0)]
    dst = quad_xy
    xs, ys = [p[0] for p in dst], [p[1] for p in dst]
    area = 0.5 * abs(sum(xs[i] * ys[(i + 1) % 4] - xs[(i + 1) % 4] * ys[i] for i in range(4)))
    if area < 50:                                   # seen edge-on (a wall in plan view): nothing to show
        return img
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        B += [u, v]
    coeffs = np.linalg.solve(np.array(A, float), np.array(B, float))
    warped = decal.convert("RGBA").transform(img.size, Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    out = img.convert("RGBA")
    out.alpha_composite(warped)
    return out.convert("RGB")
