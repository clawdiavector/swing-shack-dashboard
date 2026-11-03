"""Reality check (Christelle, 2026-10-29: "Actual lengths of objects and spaces, shapes, depth... because
this looks wack"). Objects measured in pixels against a known reference in the same plane must come out at
their real-world size; the 'Fresh off the pin' caps came out 2.4x too big against a 2.13 m flagstick."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "reality_check", ROOT / "plugins/campaign-os/skills/campaign-os-carousel/scripts/reality_check.py")
reality_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reality_check)


def test_oversized_caps_on_the_flagstick_fail():
    # S1 plate A: pole 2100 px tip to cup, cap 450 px wide
    out = reality_check.check([{"object": "flagstick", "px": 2100, "ref": True},
                               {"object": "cap", "px": 450}])
    cap = next(r for r in out if r["object"] == "cap")
    assert cap["verdict"] == "FAIL"
    assert 2.2 < cap["ratio"] < 2.6


def test_cap_beside_a_person_passes():
    # S1 plate B: man 1927 px head to heel, cap 196 px wide
    out = reality_check.check([{"object": "person", "px": 1927, "ref": True},
                               {"object": "cap", "px": 196}])
    assert next(r for r in out if r["object"] == "cap")["verdict"] == "PASS"


def test_borderline_is_check_not_pass():
    out = reality_check.check([{"object": "golf_ball", "px": 100, "ref": True},
                               {"object": "hole", "px": 300}])     # hole 2.0x the ball, real is 2.53x
    assert next(r for r in out if r["object"] == "hole")["verdict"] in ("CHECK", "FAIL")


def test_every_size_has_a_source():
    sizes = json.loads((ROOT / "plugins/campaign-os/skills/campaign-os-carousel/real-sizes.json")
                       .read_text(encoding="utf-8"))
    for name, s in sizes["objects"].items():
        assert s["min_mm"] <= s["typical_mm"] <= s["max_mm"], name
        assert s.get("source"), f"{name} has no source"


def test_unknown_object_is_an_error():
    with pytest.raises(KeyError):
        reality_check.check([{"object": "flagstick", "px": 2100, "ref": True}, {"object": "unicorn", "px": 5}])


def test_needs_a_reference():
    with pytest.raises(ValueError):
        reality_check.check([{"object": "cap", "px": 450}])


def test_main_reads_a_json_file(tmp_path):
    f = tmp_path / "plate.json"
    f.write_text(json.dumps([{"object": "flagstick", "px": 2100, "ref": True}, {"object": "cap", "px": 450}]))
    assert reality_check.main([str(f)]) == 1           # a FAIL exits 1
    f.write_text(json.dumps([{"object": "person", "px": 1927, "ref": True}, {"object": "cap", "px": 196}]))
    assert reality_check.main([str(f)]) == 0
