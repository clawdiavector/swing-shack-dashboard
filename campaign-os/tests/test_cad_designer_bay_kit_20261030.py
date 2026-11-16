"""3D designer kitted bay (Christelle, 2026-10-30): a Swing Shack bay with its kit, to scale, pulled apart in
layers. TrackMan 4 is its real size (300 x 300 x 45 mm) and at least 4.7 m from the screen (TrackMan's
minimum); everything not measured at Swing Shack is labelled a placeholder."""
import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/campaign-os/skills/cad-designer/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("bay_kit", SCRIPTS / "bay_kit.py")
kit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kit)


def bounds(solids):
    pts = np.concatenate([f for s in solids for f in s.faces])
    return pts.min(axis=0), pts.max(axis=0)


def test_trackman_is_its_real_size():
    layers, _ = kit.kit(4.6, 5.5, 3.1, 2.5, explode=0.0)
    tm = [s for s in layers["kit"].solids if s.name == "trackman"]
    lo, hi = bounds(tm)
    assert sorted(np.round(hi - lo, 3)) == sorted([0.300, 0.300, 0.045])


def test_trackman_is_at_least_4_7_m_from_the_screen():
    layers, info = kit.kit(4.6, 5.5, 3.1, 2.5, explode=0.0)
    lo, hi = bounds([s for s in layers["kit"].solids if s.name == "trackman"])
    assert info["screen_y"] - hi[1] >= 4.7 - 1e-9


def test_ball_sits_on_the_mat_at_the_set_distance():
    layers, info = kit.kit(4.6, 5.5, 3.1, 2.5, explode=0.0)
    lo, hi = bounds([s for s in layers["kit"].solids if s.name == "mat"])
    bx, by = info["ball"]
    assert lo[0] <= bx <= hi[0] and lo[1] <= by <= hi[1]
    assert abs(info["screen_y"] - by - 2.5) < 1e-9


def test_layers_lift_in_order_when_pulled_apart():
    layers, _ = kit.kit(4.6, 5.5, 3.1, 2.5, explode=1.0)
    low = {k: bounds(v.solids)[0][2] for k, v in layers.items() if v.solids}
    assert low["floor"] < low["kit"] < low["enclosure"] < low["ceiling"]


def test_unmeasured_kit_is_labelled_placeholder():
    _, info = kit.kit(4.6, 5.5, 3.1, 2.5, explode=1.0, measured=False)
    for name, (_, title, spec) in info["labels"].items():
        if name != "trackman":
            assert "placeholder" in spec.lower() or "estimate" in spec.lower(), name


def test_renders():
    assert kit.render_kit(4.6, 5.5, 3.1, 2.5, explode=1.0).size == (1080, 1350)
