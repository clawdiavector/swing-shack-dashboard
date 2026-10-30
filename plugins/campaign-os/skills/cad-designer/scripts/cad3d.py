"""CAD-lite: true-scale 3D scenes in metres, drawn from any camera in a chosen style. Pillow + numpy only.

A scene is a list of solids (boxes, quads, capsules, polylines) plus image decals (a logo on a wall).
Cameras: iso (isometric), plan (top-down), front/side elevation, persp (eye + target + fov).
Styles: blueprint (white lines on navy, grid, dimensions), plan (dark lines on paper), clay (lit flat faces).
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

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
    r2: float = None       # radius at b, for a tapered limb (None: same as r)


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
    bands: list = field(default_factory=list)    # muscles: (a, b, belly radius in metres, RGBA), drawn see-through on top


# ── golfer: real anatomy (every number's source is in ../anatomy.json) ────

ANATOMY = json.loads((Path(__file__).resolve().parents[1] / "anatomy.json").read_text(encoding="utf-8"))
STATURE = 1.75                                       # the golfer's height in metres
_DL, _AN = ANATOMY["segments_de_leva_m"], ANATOMY["ansur_men_mm"]


def _ansur(key):
    """An ANSUR II mean, in metres, scaled to the golfer's height."""
    return _AN[key] / 1000 * STATURE / (_AN["stature"] / 1000)


def _girth(key):
    """The radius of an ANSUR II circumference."""
    return _ansur(key) / (2 * math.pi)


SEG = {k: _DL[k] * STATURE / _DL["stature"] for k in ("upper_arm", "forearm", "hand", "thigh", "shank", "foot", "trunk")}
SEG.update(
    head_r=(_ansur("head_breadth") + _ansur("head_length")) / 4,
    shoulder_half=_ansur("biacromial_breadth") / 2,
    hip_half=ANATOMY["golf"]["hip_joint_centre_separation_m_estimate"] / 2,
    ankle_h=_ansur("lateral_malleolus_height"),
    neck_to_head=STATURE - _ansur("tragion_to_top_of_head") - _ansur("suprasternale_height"),
)
CLUB_FROM_HANDS = 0.92     # a 7-iron is 37 in (0.94 m); the lead wrist sits about 2 cm below the butt (estimate)

# Seven positions. pelvis/thorax: turn away from the target in degrees (thorax about the spine); arm: the
# lead arm swinging across the chest; lift: the lead arm raised in front of the chest; hinge: wrist cock
# from address (radial deviation +); roll: forearm rotation (pronation/supination); elbow: lead elbow flexion (it folds in the finish); tilt: spine forward from vertical; side: spine bent away from the
# target; tray: how far the trail elbow lifts away from the body (0 tucked; at the top it carries like a
# waiter's tray); shift: pelvis slide towards the target (m); squat: pelvis lowered by bending the knees (m); heel: trail heel lift (m); pro: how far each
# shoulder blade slides forward round the ribs (lead, trail; m), which is how an arm reaches across.
POSES = {
    "address":   dict(pelvis=0,   thorax=0,    arm=0,   lift=0,  hinge=0,   roll=0,   elbow=8,   tilt=41.5, side=6,  shift=0.0,   squat=0.0, heel=0.0,  tray=0, pro=(0.0, 0.06)),
    "takeaway":  dict(pelvis=12,  thorax=35,   arm=10,  lift=14, hinge=-46, roll=-26, elbow=8,   tilt=41,   side=6,  shift=-0.01, squat=0.0, heel=0.0,  tray=0.5, pro=(0.03, 0.03)),
    "top":       dict(pelvis=45,  thorax=97,   arm=90,  lift=105, hinge=48, roll=80,  elbow=5,  tilt=39,   side=4,  shift=-0.02, squat=0.0, heel=0.0,  tray=6, pro=(0.06, -0.02)),
    "downswing": dict(pelvis=8,   thorax=55,   arm=85,  lift=85, hinge=47.5, roll=7,  elbow=10,  tilt=39,   side=12, shift=0.06,  squat=0.0, heel=0.0,  tray=1.5, pro=(0.04, 0.02)),
    "impact":    dict(pelvis=-35, thorax=-3,   arm=1,   lift=2,  hinge=-7,  roll=-14, elbow=9,   tilt=44,   side=4,  shift=0.08,  squat=0.0, heel=0.03, tray=0, pro=(0.0, 0.06)),
    "follow":    dict(pelvis=-60, thorax=-85,  arm=-3,  lift=-9, hinge=1,   roll=6,   elbow=45,  tilt=28,   side=18, shift=0.11,  squat=0.0, heel=0.07, tray=0, pro=(-0.02, 0.06)),
    "finish":    dict(pelvis=-88, thorax=-118, arm=-15, lift=80, hinge=-48, roll=-80, elbow=137, tilt=6,    side=14, shift=0.12,  squat=0.0, heel=0.10, tray=0, pro=(-0.02, 0.06)),
}


def rotate(v, axis, deg):
    """Rodrigues rotation of vector v about a unit axis."""
    k = axis / np.linalg.norm(axis)
    t = math.radians(deg)
    return v * math.cos(t) + np.cross(k, v) * math.sin(t) + k * np.dot(k, v) * (1 - math.cos(t))


def angle_between(a, b):
    """Angle between two vectors in degrees."""
    c = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _reach(shoulder, hands, length):
    d = hands - shoulder
    n = np.linalg.norm(d)
    return hands if n <= length else shoulder + d * (length / n)


def _two_bone(root, end, a, b, pole):
    """The middle joint of a two-bone limb (shoulder-elbow-wrist, hip-knee-ankle): bones keep their length
    and the joint bends towards `pole`, the way that joint really bends."""
    d = end - root
    n = min(np.linalg.norm(d), a + b - 1e-9)
    axis = d / np.linalg.norm(d)
    x = (a * a - b * b + n * n) / (2 * n)
    h = math.sqrt(max(a * a - x * x, 0.0))
    side = pole - axis * np.dot(pole, axis)
    side = side / (np.linalg.norm(side) or 1.0)
    return root + axis * x + side * h


def _basis(tilt, side, turn):
    """Thorax axes: l (towards the target at address), u (up the spine), f (out of the chest)."""
    t = math.radians(tilt)
    u, f, l = V([math.sin(t), 0.0, math.cos(t)]), V([math.cos(t), 0.0, -math.sin(t)]), V([0.0, 1.0, 0.0])
    u, l = rotate(u, f, side), rotate(l, f, side)          # + bends the spine away from the target
    l, f = rotate(l, u, -turn), rotate(f, u, -turn)        # + turns away from the target
    return np.stack([l, u, f], axis=1)


def _legs(pelvis, ball_xy, pelvis_turn, heel):
    bx, by = ball_xy
    hips = [pelvis + rotate(V([0.0, s * SEG["hip_half"], 0.0]), V([0, 0, 1.0]), -pelvis_turn) for s in (1, -1)]
    toes, ankles = [], []
    for s, lift in ((1, 0.0), (-1, heel)):
        toe = V([pelvis[0] + 0.19, by + s * 0.21, 0.03])
        ankle = V([toe[0] - 0.19 + 0.6 * lift, toe[1], SEG["ankle_h"] + lift])   # heel up: the ankle rolls over the toes
        toes.append(toe), ankles.append(ankle)
    return hips, ankles, toes


def _arm_len(elbow_flex):
    """Shoulder-to-wrist distance with the elbow bent elbow_flex degrees (law of cosines)."""
    ua, fa = SEG["upper_arm"], SEG["forearm"]
    return math.sqrt(ua * ua + fa * fa + 2 * ua * fa * math.cos(math.radians(elbow_flex)))


def _shoulders(sup, B, pro):
    """Shoulder joint centres: behind and below the top of the breastbone (estimate), a biacromial width
    apart, each slid forward round the ribs by its shoulder blade (pro)."""
    l, u, f = B[:, 0], B[:, 1], B[:, 2]
    centre = sup - f * 0.04 - u * 0.04
    return (centre + l * SEG["shoulder_half"] + f * pro[0], centre - l * SEG["shoulder_half"] + f * pro[1])


def _ELBOW_POLE(B):
    return V([0, 0, -1.0]) - B[:, 2] * 0.3                 # the lead elbow points down and in, at the body


def _address(ball_xy):
    """Solve the set-up: club head behind the ball at the lie of a 7-iron, both hands on the grip, spine
    at a tour player's forward bend, and the golfer standing exactly far enough away for the lead arm to
    hang long."""
    bx, by = ball_xy
    head = V([bx, by - 0.035, 0.02])
    lie = math.radians(62.5)                             # a 7-iron's lie angle, sole flat (typical spec)
    shaft = V([-math.cos(lie), 0.07, math.sin(lie)])
    wrist = head + shaft / np.linalg.norm(shaft) * CLUB_FROM_HANDS
    P = POSES["address"]
    want = _arm_len(P["elbow"])
    B = _basis(P["tilt"], P["side"], 0)

    def body(px):
        # knees flexed about 22 degrees: shins lean 10 forward, thighs 12 back
        z = SEG["ankle_h"] + SEG["shank"] * math.cos(math.radians(10)) + SEG["thigh"] * math.cos(math.radians(12))
        pelvis = V([px, by, z])
        sup = pelvis + B[:, 1] * SEG["trunk"]
        return pelvis, _shoulders(sup, B, P["pro"])[0]

    lo, hi = bx - 1.6, bx - 0.1                            # further back = further from the hands
    for _ in range(60):
        mid = (lo + hi) / 2
        if np.linalg.norm(body(mid)[1] - wrist) > want:
            lo = mid
        else:
            hi = mid
    pelvis, lead_sh = body((lo + hi) / 2)
    elbow = _two_bone(lead_sh, wrist, SEG["upper_arm"], SEG["forearm"], _ELBOW_POLE(B))
    return dict(pelvis=pelvis, B=B, arm=B.T @ (wrist - lead_sh), forearm=B.T @ (wrist - elbow),
                club=B.T @ ((head - wrist) / CLUB_FROM_HANDS))


def swing_rig(ball_xy, pose="address"):
    """Joint positions (metres) for a right-handed golfer at ball_xy; target is +y, the golfer faces +x.
    The pelvis turns over the feet, the thorax turns about the spine, the lead arm swings across the chest
    and the club cocks at the wrist; every bone keeps its de Leva length and every joint bends the way it
    can (sources: anatomy.json)."""
    P = POSES[pose]
    A = _address(ball_xy)
    pelvis = A["pelvis"] + V([0.0, P["shift"], -P["squat"]])
    hips, ankles, toes = _legs(pelvis, ball_xy, P["pelvis"], P["heel"])
    reach = SEG["thigh"] + SEG["shank"] - 0.002
    drop = 0.0
    for h, a in zip(hips, ankles):                         # sink the hips just enough for both legs to reach
        dxy = np.linalg.norm((h - a)[:2])
        dz = h[2] - a[2]
        if dxy < reach and math.hypot(dxy, dz) > reach:
            drop = max(drop, dz - math.sqrt(reach * reach - dxy * dxy))
    pelvis, hips = pelvis - V([0, 0, drop]), [h - V([0, 0, drop]) for h in hips]
    knees = [_two_bone(h, a, SEG["thigh"], SEG["shank"], (t - a) * V([1, 1, 0]) + V([0, 0, 0.2]))
             for h, a, t in zip(hips, ankles, toes)]

    B = _basis(P["tilt"], P["side"], P["thorax"])
    l, u, f = B[:, 0], B[:, 1], B[:, 2]
    sup = pelvis + u * SEG["trunk"]                        # suprasternale: the top of the breastbone
    lead_sh, trail_sh = _shoulders(sup, B, P["pro"])

    def carry(local):                                       # address direction, carried by the turn and arm swing
        v = rotate(rotate(local, V([0, 1.0, 0]), -P["arm"]), V([1.0, 0, 0]), -P["lift"])
        return B @ v

    arm = carry(A["arm"])
    hands = lead_sh + arm / np.linalg.norm(arm) * _arm_len(P["elbow"])
    lead_el = _two_bone(lead_sh, hands, SEG["upper_arm"], SEG["forearm"], _ELBOW_POLE(B))
    fa_was, fa_now = carry(A["forearm"]), hands - lead_el    # the club is held by the hand, so it follows the forearm
    axis = np.cross(fa_was, fa_now)
    club = carry(A["club"])
    if np.linalg.norm(axis) > 1e-9:
        club = rotate(club, axis, angle_between(fa_was, fa_now))
    club = rotate(club, np.cross(fa_now, club), P["hinge"])  # cocking opens the angle between forearm and club
    club = rotate(club, fa_now, P["roll"])                   # the forearm rolls (pronation/supination)
    club = club / np.linalg.norm(club)
    grip = hands + club * 0.09                               # the trail hand sits a hand-width down the grip
    reach_t = SEG["upper_arm"] + SEG["forearm"] - 1e-6
    extra = 0.0
    while np.linalg.norm(grip - trail_sh) > reach_t and P["pro"][1] + extra < 0.12:
        extra += 0.005                                       # still short: the trail shoulder blade wraps further forward
        trail_sh = trail_sh + f * 0.005 + l * 0.0015
    trail_wrist = _reach(trail_sh, grip, reach_t)

    return {
        "hands": hands, "trail_wrist": trail_wrist, "club_head": hands + club * CLUB_FROM_HANDS,
        "pelvis": pelvis, "neck": sup, "chest": sup - u * 0.17, "head": sup + u * SEG["neck_to_head"],
        "lead_shoulder": lead_sh, "trail_shoulder": trail_sh,
        "lead_elbow": lead_el,
        "trail_elbow": _two_bone(trail_sh, trail_wrist, SEG["upper_arm"], SEG["forearm"], V([0, 0, -1.0]) - l * P["tray"]),
        "lead_hip": hips[0], "trail_hip": hips[1], "lead_knee": knees[0], "trail_knee": knees[1],
        "lead_ankle": ankles[0], "trail_ankle": ankles[1], "lead_toe": toes[0], "trail_toe": toes[1],
        "axes": B, "pelvis_turn": P["pelvis"],
        "turn": {k: P[k] for k in ("pelvis", "thorax", "arm", "hinge")},
    }


# Muscles as origin-to-insertion bands. Base radius is the belly at address (estimate); the belly thickens
# as the muscle shortens because muscle keeps its volume.
def _muscle_anchors(r):
    l, u, f = r["axes"][:, 0], r["axes"][:, 1], r["axes"][:, 2]
    pl = rotate(V([0.0, 1.0, 0.0]), V([0, 0, 1.0]), -r["pelvis_turn"])
    pf = rotate(V([1.0, 0.0, 0.0]), V([0, 0, 1.0]), -r["pelvis_turn"])
    z, pc, sup = V([0, 0, 1.0]), r["pelvis"], r["neck"]

    def along(a, b, t):
        return r[a] + (r[b] - r[a]) * t

    return {
        "lead latissimus dorsi": (pc + pl * 0.07 - pf * 0.10 + z * 0.14, along("lead_shoulder", "lead_elbow", 0.25), 0.035),
        "trail latissimus dorsi": (pc - pl * 0.07 - pf * 0.10 + z * 0.14, along("trail_shoulder", "trail_elbow", 0.25), 0.035),
        "lead pectoralis major": (sup - u * 0.10 + f * 0.06, along("lead_shoulder", "lead_elbow", 0.2), 0.033),
        "trail pectoralis major": (sup - u * 0.10 + f * 0.06, along("trail_shoulder", "trail_elbow", 0.2), 0.033),
        "trail erector spinae": (pc - pl * 0.04 - pf * 0.11 + z * 0.05, sup - l * 0.05 - f * 0.12 - u * 0.05, 0.028),
        "obliques": (sup - u * 0.30 + l * 0.10 + f * 0.08, pc - pl * 0.12 + pf * 0.10 + z * 0.08, 0.03),
        "trail gluteus maximus": (pc - pl * 0.05 - pf * 0.11 + z * 0.03, along("trail_hip", "trail_knee", 0.25) - pf * 0.04, 0.045),
        "lead adductor magnus": (pc + pl * 0.02 - pf * 0.03 - z * 0.08, along("lead_hip", "lead_knee", 0.85) - pl * 0.03, 0.035),
        "lead hamstrings": (pc + pl * 0.06 - pf * 0.08 - z * 0.08, along("lead_knee", "lead_ankle", 0.08) - pf * 0.04, 0.035),
        "trail biceps": (r["trail_shoulder"] + f * 0.02, along("trail_elbow", "trail_wrist", 0.12), 0.022),
        "trail triceps": (r["trail_shoulder"] - f * 0.03, along("trail_elbow", "trail_wrist", -0.08), 0.025),
    }


def muscles(ball_xy, pose="address"):
    """Each muscle's ends, length, belly radius (thicker when shorter) and, where an EMG study says so, how
    hard it is working in this position (2 high, 1 moderate) with that study's key from anatomy.json."""
    rest = {k: np.linalg.norm(b - a) for k, (a, b, _) in _muscle_anchors(swing_rig(ball_xy, "address")).items()}
    fired = ANATOMY["muscle_activity"].get(pose, {})
    out = []
    for name, (a, b, r0) in _muscle_anchors(swing_rig(ball_xy, pose)).items():
        n = float(np.linalg.norm(b - a))
        level, source = fired.get(name, (0, ""))
        out.append(dict(name=name, a=a, b=b, length=n, stretch=n / rest[name],
                        radius=r0 * math.sqrt(rest[name] / n), activity=level, source=source))
    return out


def golfer(ball_xy, pose="address", facing=1.0, fill=(240, 240, 240), ghost=False):
    """Capsules for a right-handed golfer at ball_xy (target +y), shaped from ANSUR II girths: thighs
    taper to the knee, calves have a belly, forearms taper to the wrist. ghost=True draws only the arms
    and the club as thin lines: the strobe look, where the club repeats and the body stays one figure."""
    r = swing_rig(ball_xy, pose)
    if ghost:
        return [Capsule(r["lead_shoulder"], r["lead_elbow"], 0.012, fill),
                Capsule(r["lead_elbow"], r["hands"], 0.012, fill),
                Capsule(r["hands"], r["club_head"], 0.006, fill),
                Capsule(r["club_head"], r["club_head"] + V([0, 0, 0.001]), 0.02, fill)]
    u = r["axes"][:, 1]
    club = (r["club_head"] - r["hands"]) / CLUB_FROM_HANDS
    knee_r, calf_r = _girth("lower_thigh_circumference"), _girth("calf_circumference")
    caps = []
    for side in ("lead", "trail"):
        hip, knee, ankle, toe = r[f"{side}_hip"], r[f"{side}_knee"], r[f"{side}_ankle"], r[f"{side}_toe"]
        belly = knee + (ankle - knee) * 0.3
        heel = ankle - (toe - ankle) * V([0.3, 0.3, 0.0]) - V([0, 0, ankle[2] - 0.035])
        caps += [Capsule(hip, knee, _girth("thigh_circumference") * 0.95, fill, knee_r),
                 Capsule(knee, belly, knee_r * 0.85, fill, calf_r),
                 Capsule(belly, ankle, calf_r, fill, _girth("ankle_circumference")),
                 Capsule(heel, toe, 0.035, fill, 0.03)]
        sh, el = r[f"{side}_shoulder"], r[f"{side}_elbow"]
        wrist = r["hands"] if side == "lead" else r["trail_wrist"]
        caps += [Capsule(sh, el, 0.05, fill, 0.038),
                 Capsule(el, wrist, _girth("forearm_circumference_flexed"), fill, _girth("wrist_circumference")),
                 Capsule(wrist, wrist + club * 0.06, 0.03, fill)]
    head = r["head"]
    caps += [Capsule(r["lead_hip"], r["trail_hip"], _ansur("hip_breadth") / 2 - SEG["hip_half"], fill),
             Capsule(r["pelvis"] + u * 0.05, r["chest"], 0.125, fill, 0.13),
             Capsule(r["chest"], r["neck"] - u * 0.04, 0.13, fill, 0.11),
             Capsule(r["lead_shoulder"], r["trail_shoulder"], 0.05, fill),
             Capsule(r["neck"], head, _girth("neck_circumference"), fill),
             Capsule(head - u * 0.02, head + u * 0.045, SEG["head_r"], fill),
             Capsule(r["hands"], r["club_head"], 0.008, (40, 40, 40)),
             Capsule(r["club_head"], r["club_head"] + V([0, 0, 0.001]), 0.022, (40, 40, 40))]
    return caps


def muscle_bands(ball_xy, pose, colour=(255, 90, 60), stretched=(120, 200, 255), show_stretch=True):
    """Bands for Scene.bands: muscles an EMG study says are working, in `colour` (opaque for high, lighter
    for moderate), and muscles stretched more than 8% past their address length, in `stretched`."""
    out = []
    for m in muscles(ball_xy, pose):
        if m["activity"]:
            out.append((m["a"], m["b"], m["radius"], colour + ((235,) if m["activity"] == 2 else (150,))))
        elif show_stretch and m["stretch"] > 1.08:
            out.append((m["a"], m["b"], m["radius"] * 0.8, stretched + (150,)))
    return out


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
            ra = max(2.0, obj.r * k)
            rb = max(2.0, (obj.r if obj.r2 is None else obj.r2) * k)
            col = tuple(int(c) for c in obj.fill) if st["fill"] else st["line"]
            for grow, c in (((1.5, (70, 70, 70)),) if st["fill"] else ()) + ((0.0, col),):
                _limb(d, pa, pb, ra + grow, rb + grow, c)
        elif kind == "decal":
            img = paste_decal(img, obj.image, geo)
            d = ImageDraw.Draw(img, "RGBA")

    if scene.bands:                                 # muscles, see-through over the body
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for a, b, rad, col in scene.bands:
            (pa, _), (pb, _) = P(a), P(b)
            _spindle(ld, pa, pb, rad * k, col)
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
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


def _limb(d, pa, pb, ra, rb, col):
    """A tapered capsule on screen: circles of radius ra and rb joined by their tangent sides."""
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    n = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / n, dx / n
    d.polygon([(pa[0] + nx * ra, pa[1] + ny * ra), (pb[0] + nx * rb, pb[1] + ny * rb),
               (pb[0] - nx * rb, pb[1] - ny * rb), (pa[0] - nx * ra, pa[1] - ny * ra)], fill=col)
    for q, r in ((pa, ra), (pb, rb)):
        d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)


def _spindle(d, pa, pb, r, col, steps=16):
    """A muscle on screen: thick at the belly, thin at the tendons."""
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    n = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / n, dx / n
    w = [r * (0.2 + 0.8 * math.sin(math.pi * i / steps)) for i in range(steps + 1)]
    pts = [(pa[0] + dx * i / steps, pa[1] + dy * i / steps) for i in range(steps + 1)]
    d.polygon([(x + nx * wi, y + ny * wi) for (x, y), wi in zip(pts, w)] +
              [(x - nx * wi, y - ny * wi) for (x, y), wi in reversed(list(zip(pts, w)))], fill=col)


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
