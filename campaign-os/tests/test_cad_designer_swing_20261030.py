"""3D designer swing model (Christelle, 2026-10-30: "3d illustration of clubs and swings and movements").
The golfer is a two-lever swing: hands on a circle around the chest, the club hinged at the wrists. Real
limits hold in every position: arms never stretch past their length, feet stay on the floor, the club head
rests on the ground behind the ball at address."""
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "cad3d", ROOT / "plugins/campaign-os/skills/cad-designer/scripts/cad3d.py")
cad3d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cad3d)

BALL = (2.6, 3.0)
POSITIONS = ["address", "takeaway", "top", "downswing", "impact", "follow", "finish"]


def rig(pose):
    return cad3d.swing_rig(BALL, pose)


def test_all_seven_positions_exist():
    for p in POSITIONS:
        assert set(rig(p)) >= {"hands", "club_head", "lead_shoulder", "trail_shoulder", "lead_elbow", "trail_elbow", "head"}


def test_club_head_rests_behind_the_ball_at_address():
    r = rig("address")
    head = r["club_head"]
    assert abs(head[0] - BALL[0]) < 0.05 and -0.08 < head[1] - BALL[1] < 0.0
    assert 0.0 <= head[2] <= 0.04


def test_arms_never_stretch_past_their_length():
    reach = cad3d.SEG["upper_arm"] + cad3d.SEG["forearm"] + 0.01
    for p in POSITIONS:
        r = rig(p)
        for side in ("lead", "trail"):
            assert np.linalg.norm(r["hands"] - r[f"{side}_shoulder"]) <= reach, (p, side)


def test_club_is_a_real_seven_iron_length():
    for p in POSITIONS:
        r = rig(p)
        assert abs(np.linalg.norm(r["club_head"] - r["hands"]) - cad3d.CLUB_FROM_HANDS) < 1e-6


def test_top_of_backswing_is_up_and_away_from_the_target():
    r, a = rig("top"), rig("address")
    assert r["hands"][2] > a["lead_shoulder"][2] - 0.1      # hands about shoulder height or higher
    assert r["hands"][1] < BALL[1]                          # back, away from the target (+y)


def test_finish_is_past_the_target_and_high():
    r = rig("finish")
    assert r["hands"][1] > BALL[1] - 0.2 and r["hands"][2] > 1.2


def test_feet_on_the_floor_and_adult_height_in_every_position():
    for p in POSITIONS:
        caps = cad3d.golfer(BALL, p)
        top = max(max(c.a[2], c.b[2]) + c.r for c in caps)
        low = min(min(c.a[2], c.b[2]) - c.r for c in caps)
        assert top < 1.95 and -0.02 < low < 0.06, p


def test_swing_sequence_renders():
    s = cad3d.Scene()
    s.solids.append(cad3d.box(0, 0, -0.05, 4.6, 5.5, 0, name="floor"))
    for p in POSITIONS:
        s.capsules += cad3d.golfer(BALL, p, ghost=True)
    im = cad3d.render(s, cad3d.Camera("front"), style="blueprint")
    assert im.size == (1080, 1350)
