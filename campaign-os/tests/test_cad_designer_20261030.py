"""3D designer (Christelle, 2026-10-30): true-scale scenes in metres (a Swing Shack bay, a golfer, the
screen with the logo) drawn from any camera in blueprint, plan or clay style, as layouts to build posts on."""
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "cad3d", ROOT / "plugins/campaign-os/skills/cad-designer/scripts/cad3d.py")
cad3d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cad3d)
V = cad3d.V


def small_bay():
    s = cad3d.Scene()
    s.solids.append(cad3d.box(0, 0, -0.05, 4.6, 5.5, 0, fill=(96, 150, 78), name="floor"))
    s.solids.append(cad3d.box(0, 5.5, 0, 4.6, 5.62, 3.1, fill=(40, 40, 42), name="screen wall"))
    s.capsules += cad3d.golfer((2.6, 3.0), "address")
    return s


def test_box_is_six_faces_in_metres():
    b = cad3d.box(0, 0, 0, 4.6, 5.5, 3.1)
    assert len(b.faces) == 6
    allp = np.concatenate(b.faces)
    assert allp.max(axis=0).tolist() == [4.6, 5.5, 3.1]


def test_golfer_is_adult_height_at_address():
    caps = cad3d.golfer((2.6, 3.0), "address")
    top = max(max(c.a[2], c.b[2]) + c.r for c in caps)
    assert 1.35 < top < 1.80           # a 1.75 m adult bends forward at address
    feet = min(min(c.a[2], c.b[2]) - c.r for c in caps)
    assert -0.02 < feet < 0.06          # feet on the floor, not floating or sunk


def test_every_style_and_camera_renders_a_post_size_image():
    for style in ("blueprint", "plan", "clay"):
        for cam in (cad3d.Camera("iso"), cad3d.Camera("plan"), cad3d.Camera("front"),
                    cad3d.Camera("persp", eye=(3.6, -2.2, 1.75), target=(2.2, 5.5, 1.3), fov=46)):
            im = cad3d.render(small_bay(), cam, style=style)
            assert im.size == (1080, 1350)


def test_plan_view_draws_the_golfer_over_the_floor():
    im = cad3d.render(small_bay(), cad3d.Camera("plan"), style="clay", margin=60)
    a = np.asarray(im).astype(int)
    floor = np.array([96, 150, 78])
    # the golfer is light grey; some of those pixels must survive on top of the green floor
    light = ((a > 200).all(axis=2)).sum()
    assert light > 500


def test_decal_seen_edge_on_is_skipped_not_an_error():
    s = small_bay()
    logo = Image.new("RGBA", (160, 75), (255, 255, 255, 255))
    s.decals.append(cad3d.Decal(logo, [V([1, 5.49, 1]), V([3, 5.49, 1]), V([3, 5.49, 2]), V([1, 5.49, 2])]))
    im = cad3d.render(s, cad3d.Camera("plan"), style="plan")   # the wall is edge-on from above
    assert im.size == (1080, 1350)


def test_dimension_label_defaults_to_metres():
    s = small_bay()
    s.dims.append(cad3d.Dim(V([0, 0, 0]), V([4.6, 0, 0]), V([0, -0.5, 0])))
    cad3d.render(s, cad3d.Camera("iso"), style="blueprint")
    assert s.dims[0].label == "" and abs(np.linalg.norm(s.dims[0].b - s.dims[0].a) - 4.6) < 1e-9
