"""3D designer full swing (Christelle, 2026-10-30): at the top the club reaches about level and points at
the target, as in a full swing, with the wrist inside its real range."""
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "cad3d", ROOT / "plugins/campaign-os/skills/cad-designer/scripts/cad3d.py")
cad3d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cad3d)
BALL = (2.6, 3.0)


def test_club_is_about_level_at_the_top_and_points_at_the_target():
    r = cad3d.swing_rig(BALL, "top")
    club = (r["club_head"] - r["hands"]) / np.linalg.norm(r["club_head"] - r["hands"])
    assert abs(club[2]) < 0.26                    # within 15 degrees of level
    assert club[1] > 0.8                          # towards the target (+y)


def test_hands_at_the_top_are_high_and_behind_the_ball():
    r = cad3d.swing_rig(BALL, "top")
    assert 1.4 < r["hands"][2] < 1.8 and r["hands"][1] < BALL[1]


def test_the_top_uses_wrist_extension_not_a_bent_lead_arm():
    r = cad3d.swing_rig(BALL, "top")
    assert r["wrist"]["extension"] > 0
    assert 180 - cad3d.angle_between(r["lead_shoulder"] - r["lead_elbow"], r["hands"] - r["lead_elbow"]) <= 20
