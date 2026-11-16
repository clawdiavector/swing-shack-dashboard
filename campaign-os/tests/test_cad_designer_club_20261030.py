"""3D designer exploded 7-iron (Christelle, 2026-10-30: "more detailed design with lots of moving parts").
The club is built from maker specs in club-7iron.json: 37 in long, loft 30.5, lie 63, shaft .370 in at
the hosel to .600 in at the butt; pulled apart, the parts move only along the shaft axis."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/campaign-os/skills/cad-designer/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC_ = importlib.util.spec_from_file_location("club_exploded", SCRIPTS / "club_exploded.py")
club = importlib.util.module_from_spec(SPEC_)
SPEC_.loader.exec_module(club)
SPEC = json.loads((SCRIPTS.parent / "club-7iron.json").read_text(encoding="utf-8"))
IN = 0.0254


def extent_along_axis(solids):
    pts = np.concatenate([f for s in solids for f in s.faces])
    t = pts @ club.AXIS
    return t.max() - t.min()


def test_specs_name_their_sources():
    assert {"t200", "shaft_tip", "shaft_butt", "ferrule", "grip"} <= set(SPEC["sources"])
    assert SPEC["loft_deg"] == 30.5 and SPEC["lie_deg"] == 63 and SPEC["length_in"] == 37


def test_assembled_club_is_37_inches_along_the_shaft():
    solids, _ = club.parts(explode=0.0)
    shaft_part = [s for s in solids if s.name in ("hosel", "ferrule", "shaft", "grip")]
    assert abs(extent_along_axis(shaft_part) - SPEC["length_in"] * IN) < 0.02


def test_shaft_and_grip_are_real_diameters():
    solids, _ = club.parts(explode=0.0)
    by = {s.name: s for s in solids}
    for name, lo, hi in (("shaft", SPEC["shaft_at_hosel_in"], SPEC["shaft_butt_in"]),
                         ("grip", *SPEC["estimates"]["grip_outer_diameter_in"])):
        pts = np.concatenate(by[name].faces)
        q = pts - pts.mean(axis=0)                         # measured from the part's own axis
        r = np.linalg.norm(q - np.outer(q @ club.AXIS, club.AXIS), axis=1)
        assert abs(r.max() * 2 / IN - hi) < 0.02 and abs(r.min() * 2 / IN - lo) < 0.05, name


def test_pulling_apart_moves_parts_only_along_the_shaft():
    a, _ = club.parts(explode=0.0)
    b, _ = club.parts(explode=1.0)
    for sa, sb in zip(a, b):
        d = np.concatenate(sb.faces) - np.concatenate(sa.faces)
        off = d - np.outer(d @ club.AXIS, club.AXIS)
        assert np.abs(off).max() < 1e-9, sa.name
        assert (d @ club.AXIS).min() >= -1e-9, sa.name


def test_still_renders_for_both_brands():
    fdir = ROOT / "data/brand-directory/stick/typography/fonts"
    fonts = {"light": str(fdir / "Montserrat-Light.ttf"), "bold": str(fdir / "Montserrat-ExtraBold.ttf")}
    for brand in ("stick", "swing-shack"):
        assert club.frame(brand, 1.0, 0, 1.0, fonts).size == (1080, 1350)
