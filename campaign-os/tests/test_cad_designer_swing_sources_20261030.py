"""3D designer swing checked against the sources Christelle sent on 2026-10-30: Lesiuta's biomechanics
presentation (set-up shoulder tilt, trail arm at the top, the trail arm coming in on the way down) and Cole &
Grimshaw 2016 (the pelvis slides towards the target in the downswing). Sources in anatomy.json."""
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "plugins/campaign-os/skills/cad-designer"
SPEC = importlib.util.spec_from_file_location("cad3d", SKILL / "scripts/cad3d.py")
cad3d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cad3d)
GOLF = json.loads((SKILL / "anatomy.json").read_text(encoding="utf-8"))["golf"]
BALL = (2.6, 3.0)


def rig(pose):
    return cad3d.swing_rig(BALL, pose)


def trail_arm_from_trunk(r):
    return cad3d.angle_between(r["trail_elbow"] - r["trail_shoulder"], -r["axes"][:, 1])


def test_set_up_tilts_the_trail_shoulder_down_16_degrees():
    r = rig("address")
    s = r["lead_shoulder"] - r["trail_shoulder"]
    tilt = math.degrees(math.atan2(s[2], np.linalg.norm(s[:2])))
    assert abs(tilt - GOLF["address_shoulder_tilt_deg"]) <= 4


def test_trail_arm_is_raised_75_to_90_degrees_at_the_top():
    lo, hi = GOLF["top_trail_arm_abduction_deg"]
    assert lo <= trail_arm_from_trunk(rig("top")) <= hi


def test_trail_arm_comes_back_in_on_the_way_down():
    assert trail_arm_from_trunk(rig("downswing")) < trail_arm_from_trunk(rig("top"))
    assert trail_arm_from_trunk(rig("impact")) < trail_arm_from_trunk(rig("downswing"))


def test_pelvis_slides_towards_the_target_in_the_downswing():
    assert rig("downswing")["pelvis"][1] > rig("top")["pelvis"][1]
    assert rig("impact")["pelvis"][1] > rig("top")["pelvis"][1]
