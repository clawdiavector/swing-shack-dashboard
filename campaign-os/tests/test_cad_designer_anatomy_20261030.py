"""3D designer golfer built on real anatomy (Christelle, 2026-10-30: "take real human anatomy into account
and how muscles really move"). Bone lengths come from de Leva 1996, widths and girths from ANSUR II, joint
limits from the AAOS ranges, the swing's turn and sequence from golf biomechanics studies, and the firing
muscles only from EMG studies. All sources are in plugins/campaign-os/skills/cad-designer/anatomy.json."""
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
ANAT = json.loads((SKILL / "anatomy.json").read_text(encoding="utf-8"))

BALL = (2.6, 3.0)
POSITIONS = ["address", "takeaway", "top", "downswing", "impact", "follow", "finish"]
H = cad3d.STATURE


def rig(pose):
    return cad3d.swing_rig(BALL, pose)


def angle(u, v):
    c = np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def flexion(a, joint, b):
    """Joint flexion in degrees: 0 is a straight limb."""
    return 180.0 - angle(a - joint, b - joint)


def test_every_number_names_a_source():
    for key, text in ANAT["sources"].items():
        assert text.strip(), key
    for phase, muscles in ANAT["muscle_activity"].items():
        if phase.startswith("_"):
            continue
        for name, (level, source) in muscles.items():
            assert level in (1, 2) and source in ANAT["sources"], (phase, name)


def test_bone_lengths_are_de_leva_scaled_to_the_golfer():
    s = H / ANAT["segments_de_leva_m"]["stature"]
    for seg in ("upper_arm", "forearm", "thigh", "shank"):
        assert abs(cad3d.SEG[seg] - ANAT["segments_de_leva_m"][seg] * s) < 0.001, seg


def test_bones_keep_their_length_in_every_position():
    for p in POSITIONS:
        r = rig(p)
        for side in ("lead", "trail"):
            assert abs(np.linalg.norm(r[f"{side}_hip"] - r[f"{side}_knee"]) - cad3d.SEG["thigh"]) < 0.002, (p, side)
            assert abs(np.linalg.norm(r[f"{side}_knee"] - r[f"{side}_ankle"]) - cad3d.SEG["shank"]) < 0.002, (p, side)
            assert abs(np.linalg.norm(r[f"{side}_shoulder"] - r[f"{side}_elbow"]) - cad3d.SEG["upper_arm"]) < 0.002, (p, side)
            wrist = r["hands"] if side == "lead" else r["trail_wrist"]
            assert abs(np.linalg.norm(r[f"{side}_elbow"] - wrist) - cad3d.SEG["forearm"]) < 0.002, (p, side)


def test_shoulders_are_a_real_shoulder_width_apart():
    width = ANAT["ansur_men_mm"]["biacromial_breadth"] / 1000 * H / (ANAT["ansur_men_mm"]["stature"] / 1000)
    for p in POSITIONS:
        r = rig(p)
        assert abs(np.linalg.norm(r["lead_shoulder"] - r["trail_shoulder"]) - width) < 0.02, p


def test_head_is_a_real_head_size():
    a = ANAT["ansur_men_mm"]
    assert a["head_breadth"] / 2000 - 0.005 <= cad3d.SEG["head_r"] <= a["head_length"] / 2000 + 0.005


def test_elbows_and_knees_stay_inside_their_range_of_motion():
    rom = ANAT["rom_deg"]
    for p in POSITIONS:
        r = rig(p)
        for side in ("lead", "trail"):
            wrist = r["hands"] if side == "lead" else r["trail_wrist"]
            assert 0 <= flexion(r[f"{side}_shoulder"], r[f"{side}_elbow"], wrist) <= rom["elbow_flexion"], (p, side)
            assert 0 <= flexion(r[f"{side}_hip"], r[f"{side}_knee"], r[f"{side}_ankle"]) <= rom["knee_flexion"], (p, side)


def test_knees_bend_over_the_toes_never_backwards():
    for p in POSITIONS:
        r = rig(p)
        for side in ("lead", "trail"):
            hip, knee, ankle = r[f"{side}_hip"], r[f"{side}_knee"], r[f"{side}_ankle"]
            line = ankle - hip
            t = np.dot(knee - hip, line) / np.dot(line, line)
            off = knee - (hip + t * line)
            toes = r[f"{side}_toe"] - ankle
            toes[2] = 0
            assert np.dot(off, toes) > 0, (p, side)


def test_the_wrist_hinge_stays_inside_the_wrist_range():
    """The club cocks against the lead forearm by radial and ulnar deviation only: 20 + 30 degrees."""
    rom = ANAT["rom_deg"]
    limit = rom["wrist_radial_deviation"] + rom["wrist_ulnar_deviation"] + 5

    def hinge(r):
        return angle(r["hands"] - r["lead_elbow"], r["club_head"] - r["hands"])

    a = hinge(rig("address"))
    for p in POSITIONS:
        assert abs(hinge(rig(p)) - a) <= limit, p


def test_address_posture_bends_forward_like_tour_players():
    r = rig("address")
    spine = r["neck"] - r["pelvis"]
    tilt = angle(spine, np.array([0.0, 0.0, 1.0]))
    assert abs(tilt - ANAT["golf"]["address_trunk_flexion_deg"]) < 4


def test_top_of_backswing_turn_and_x_factor_are_real():
    g = ANAT["golf"]
    turn = rig("top")["turn"]
    assert g["top_pelvis_turn_deg"][0] <= turn["pelvis"] <= g["top_pelvis_turn_deg"][1]
    assert g["top_thorax_turn_deg"][0] <= turn["thorax"] <= g["top_thorax_turn_deg"][1]
    assert g["top_x_factor_deg"][0] <= turn["thorax"] - turn["pelvis"] <= g["top_x_factor_deg"][1]


def test_the_hip_line_really_turns_by_the_pelvis_angle():
    for p in POSITIONS:
        r = rig(p)
        hips = r["lead_hip"] - r["trail_hip"]
        measured = math.degrees(math.atan2(hips[0], hips[1]))      # lead hip moving towards the ball is +
        assert abs(measured - r["turn"]["pelvis"]) < 1.0, p


def test_downswing_follows_the_kinematic_sequence():
    """Proximal to distal: by the downswing position the pelvis has unwound the most, then the thorax, then
    the lead arm, and the club (wrist hinge) the least: the lag."""
    top, mid, imp = rig("top")["turn"], rig("downswing")["turn"], rig("impact")["turn"]
    done = {k: (top[k] - mid[k]) / (top[k] - imp[k]) for k in ("pelvis", "thorax", "arm", "hinge")}
    assert done["pelvis"] > done["thorax"] > done["arm"] > done["hinge"], done


def test_firing_muscles_come_only_from_the_emg_sources():
    for p in POSITIONS:
        sourced = ANAT["muscle_activity"].get(p, {})
        for m in cad3d.muscles(BALL, p):
            if m["activity"]:
                assert m["name"] in sourced and m["activity"] == sourced[m["name"]][0], (p, m["name"])
                assert m["source"] == sourced[m["name"]][1]
    names = {m["name"] for m in cad3d.muscles(BALL, "impact") if m["activity"]}
    assert set(ANAT["muscle_activity"]["impact"]) <= names


def test_a_shortening_muscle_gets_thicker():
    """Muscle keeps its volume: the trail biceps shortens as the trail elbow folds at the top and bulges."""
    a = {m["name"]: m for m in cad3d.muscles(BALL, "address")}["trail biceps"]
    t = {m["name"]: m for m in cad3d.muscles(BALL, "top")}["trail biceps"]
    assert t["length"] < a["length"] and t["radius"] > a["radius"]
    assert abs(t["radius"] / a["radius"] - math.sqrt(a["length"] / t["length"])) < 1e-6


def test_backswing_stretches_the_lead_lat_and_obliques():
    a = {m["name"]: m["length"] for m in cad3d.muscles(BALL, "address")}
    t = {m["name"]: m["length"] for m in cad3d.muscles(BALL, "top")}
    assert t["lead latissimus dorsi"] > a["lead latissimus dorsi"]
    assert t["obliques"] > a["obliques"]
