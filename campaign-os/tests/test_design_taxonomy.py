"""Design taxonomy — seed load and approval overlay."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import design_taxonomy as dt


@pytest.fixture()
def taxonomy_env(monkeypatch, tmp_path):
    repo = CAMPAIGN_OS.parent
    bundled = repo / "data"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))
    approvals = tmp_path / "design-approvals.json"
    if approvals.exists():
        approvals.unlink()
    return tmp_path


def test_load_seed_has_snap():
    seed = dt.load_seed()
    snap = next(s for s in seed["styles"] if s["id"] == "snap")
    assert snap["name"] == "Snap"
    assert snap["approval"]["status"] == "not_approved"


def test_approve_snap_records_actor_and_time(taxonomy_env):
    del taxonomy_env
    approval = dt.set_approval("styles", "snap", approve=True, actor="pytest")
    assert approval["status"] == "approved"
    assert approval["by"] == "pytest"
    assert approval["at"]

    payload = dt.build_taxonomy()
    snap = next(s for s in payload["styles"] if s["id"] == "snap")
    assert snap["approval"]["status"] == "approved"
    assert snap["approval"]["by"] == "pytest"

    dt.set_approval("styles", "snap", approve=False, actor="pytest")
    payload2 = dt.build_taxonomy()
    snap2 = next(s for s in payload2["styles"] if s["id"] == "snap")
    assert snap2["approval"]["status"] == "not_approved"
    assert snap2["approval"]["by"] is None
    assert snap2["approval"]["at"] is None


def test_brand_folder_in_data_dir_does_not_hide_golden_renders(monkeypatch, tmp_path):
    """A brand folder in DATA_DIR (feedback, calendar config) must not shadow the repo's template packs."""
    (tmp_path / "brand-directory" / "swing-shack" / "feedback").mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(CAMPAIGN_OS.parent / "data"))
    tpl = next(t for t in dt.build_taxonomy()["templates"] if t["template_id"] == "ss-did-you-know")
    assert any("golden/render-instagram.png" in u for u in tpl["preview_urls"])


def test_posts_carry_pictures_and_pins(taxonomy_env):
    del taxonomy_env
    payload = dt.build_taxonomy()
    assert len(payload["posts"]) > 1000
    pictured = [p for p in payload["posts"] if p.get("pictures")]
    assert pictured and all(pic["thumb"].endswith("-t.webp") for p in pictured[:50] for pic in p["pictures"])
    assert payload["style_pins"]["snap"]
    media = dt.media_dir()
    assert all((media / pic["thumb"]).is_file() for p in pictured[:100] for pic in p["pictures"])


def test_style_labels_only_map_when_the_label_names_a_style(taxonomy_env):
    del taxonomy_env
    posts = dt.build_taxonomy()["posts"]
    assert not [p for p in posts if "snapback" in p["title"].lower() and "snap" in p["style_ids"]]
    assert not [p for p in posts if p["style"].startswith("Poster collage") and p["style_ids"] == ["snap", "night"]]


def test_style_is_read_per_picture_not_per_post(taxonomy_env):
    """A post slot can hold several looks; Snap must only claim the pictures named for it."""
    del taxonomy_env
    posts = dt.build_taxonomy()["posts"]
    for p in posts:
        for pic in p.get("pictures", []):
            if pic.get("kind"):
                continue  # looked at in the picture breakdown, which decides the style
            if "snap" in (pic.get("styles") or []):
                assert "-snap" in pic["where"].lower() or "_snap" in pic["where"].lower() or "/ss-" in pic["where"].lower()
    assert any(p["id"].startswith("extra-") for p in posts)
    assert any(pic["video"] for p in posts for pic in p.get("pictures", []))


def test_picture_breakdown_links_posts_to_style_type_template_and_source(taxonomy_env):
    """Phase 3: the breakdown names what each picture is, so a post links to its parts."""
    del taxonomy_env
    payload = dt.build_taxonomy()
    posts = payload["posts"]
    pics = [pic for p in posts for pic in p.get("pictures", [])]
    marked = [pic for pic in pics if pic.get("kind")]
    assert len(marked) > 1000
    finished = [pic for pic in marked if pic["kind"] == "post"]
    assert sum(1 for pic in finished if pic.get("type")) > 0.95 * len(finished)
    style_ids = {s["id"] for s in payload["styles"]}
    type_ids = {t["id"] for t in payload["types"]}
    template_ids = {t["id"] for t in payload["templates"]}
    assert {s for pic in marked for s in pic.get("styles", [])} <= style_ids
    assert {pic["type"] for pic in finished if pic.get("type")} <= type_ids
    assert {pic["template"] for pic in finished if pic.get("template")} <= template_ids | {"stick-photo-band-post", "bd-weekly-deal"}
    # a raw photo is never listed as a finished post, and a source link points at a real picture
    assert not [p for p in posts if p.get("kind") in ("photo", "product", "sheet") and not p.get("reference_photo")]
    thumbs = {pic["thumb"] for pic in pics}
    linked = [src for pic in marked for src in pic.get("sources", [])]
    assert linked and all(src["thumb"] in thumbs for src in linked)
    assert any(p.get("live") and p.get("pictures") for p in posts)
