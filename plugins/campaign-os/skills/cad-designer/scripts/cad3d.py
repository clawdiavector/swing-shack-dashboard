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
    "hip_w": 0.30, "shoulder_w": 0.40, "pelvis_z": 0.95, "torso": 0.52, "neck": 0.08, "head_r": 0.11,
    "upper_arm": 0.31, "forearm": 0.27, "thigh": 0.45, "shin": 0.45, "club": 0.96,
}

POSES = {  # degrees: spine tilt forward, shoulder turn, lead/trail arm angles, knee flex, club angle
    "address": dict(tilt=35, turn=0, arm_drop=72, arm_swing=0, knee=18, club=-20),
    "top": dict(tilt=35, turn=90, arm_drop=-10, arm_swing=95, knee=15, club=200),
    "impact": dict(tilt=33, turn=20, arm_drop=75, arm_swing=-5, knee=20, club=-15),
    "finish": dict(tilt=5, turn=-100, arm_drop=-40, arm_swing=-120, knee=5, club=160),
}


def rot_z(v, deg):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return V([c * v[0] - s * v[1], s * v[0] + c * v[1], v[2]])


def golfer(ball_xy, pose="address", facing=1.0, fill=(240, 240, 240)):
    """Returns capsules for a right-handed golfer addressing a ball at ball_xy (target is +y, the screen).
    The golfer stands on the -x side of the ball, facing +x."""
    P = POSES[pose]
    bx, by = ball_xy
    feet_x = bx - 0.55                       # stance about 55 cm inside the ball
    sw = SEG["hip_w"] / 2
    caps = []
    k = math.radians(P["knee"])
    for side in (-1, 1):
        ankle = V([feet_x, by + side * 0.22, 0.08])
        knee = ankle + V([math.sin(k) * SEG["shin"], side * 0.03, math.cos(k) * SEG["shin"]])
        hip = V([feet_x - 0.06, by + side * sw, SEG["pelvis_z"]])
        caps += [Capsule(ankle, knee, 0.055, fill), Capsule(knee, hip, 0.075, fill)]
        caps.append(Capsule(ankle, ankle + V([0.20, 0, -0.04]), 0.045, fill))   # foot
    pelvis = V([feet_x - 0.06, by, SEG["pelvis_z"]])
    t = math.radians(P["tilt"])
    spine = V([math.sin(t) * SEG["torso"], 0, math.cos(t) * SEG["torso"]])
    chest = pelvis + spine
    caps.append(Capsule(pelvis, chest, 0.15, fill))
    neck = chest + V([math.sin(t) * SEG["neck"], 0, math.cos(t) * SEG["neck"]])
    caps.append(Capsule(neck, neck + V([math.sin(t) * 0.12, 0, math.cos(t) * 0.12]), SEG["head_r"], fill))
    hands = None
    for side in (-1, 1):
        sh = chest + rot_z(V([0, side * SEG["shoulder_w"] / 2, 0]), P["turn"])
        d = math.radians(P["arm_drop"])
        sw_ = math.radians(P["arm_swing"])
        arm = V([math.cos(d) * 0.25, -math.sin(sw_) * 0.9, -math.sin(d)])
        arm = arm / np.linalg.norm(arm)
        elbow = sh + arm * SEG["upper_arm"]
        h = V([bx - 0.18, by - 0.05, 0.78]) if P["arm_drop"] > 60 else elbow + arm * SEG["forearm"]
        caps += [Capsule(sh, elbow, 0.045, fill), Capsule(elbow, h, 0.04, fill)]
        hands = h if hands is None else (hands + h) / 2
    c = math.radians(P["club"])
    head = hands + V([math.cos(c) * 0.35, math.sin(c) * 0.25, -abs(math.sin(c)) * 0.2 - 0.6]) if P["club"] < 0 \
        else hands + V([-0.2, -math.sin(c) * 0.6, abs(math.cos(c)) * 0.7])
    head = hands + (head - hands) / np.linalg.norm(head - hands) * SEG["club"]
    if pose in ("address", "impact"):
        head = V([bx - 0.03, by, 0.02])      # the club head rests on the ground just behind the ball
    caps.append(Capsule(hands, head, 0.008, (40, 40, 40)))
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
