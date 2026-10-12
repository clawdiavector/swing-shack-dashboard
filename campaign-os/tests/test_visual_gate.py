"""Visual gate — decide(), stand-ins, vetted flags."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def gate_env(monkeypatch, tmp_path):
    import shutil

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    bundled = REPO / "data"
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))
    for brand in ("stick", "swing-shack", "bag-drop"):
        src = bundled / "brand-directory" / brand
        dst = tmp_path / "brand-directory" / brand
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore_dangling_symlinks=True)
    from _lib import marketing_calendar as mc

    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    mc._CALENDAR_DIR = cal_dir
    mc._CALENDAR_DIR_READY = True
    return tmp_path, cal_dir


def _write_moment(cal_dir: Path, brand: str, record: dict) -> None:
    path = cal_dir / f"{brand}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def test_unmatched_post_type_is_gap(gate_env):
    tmp_path, cal_dir = gate_env
    del tmp_path
    item_id = "calendar_candidate:stick:cal-mystery"
    _write_moment(
        cal_dir,
        "stick",
        {
            "calendar_id": "cal-mystery",
            "status": "approved",
            "post_type": "mystery",
            "title": "Mystery post",
            "event_date": "2026-10-15",
        },
    )
    from _lib.visual_gate import decide

    d = decide("stick", item_id)
    assert d.is_gap()
    assert d.reason == "no_layout"
    assert d.label == "No layout for mystery"


def test_gap_enqueues_no_image_actions(gate_env):
    _, cal_dir = gate_env
    item_id = "calendar_candidate:stick:cal-mystery-2"
    _write_moment(
        cal_dir,
        "stick",
        {
            "calendar_id": "cal-mystery-2",
            "status": "approved",
            "post_type": "mystery",
            "title": "Mystery",
            "event_date": "2026-10-15",
        },
    )
    from _lib.l5_create_enqueue import create_actions_for_moment

    assert create_actions_for_moment("stick", item_id, phase="image") == []
    all_actions = create_actions_for_moment("stick", item_id, phase="all")
    assert "draft_photo" not in all_actions
    assert "compose_post" not in all_actions
    assert "draft_caption" in all_actions


def test_default_archetypes_are_gap(gate_env):
    from _lib.visual_gate import decide

    for brand, default_id in (
        ("stick", "stick-photo-band-post"),
        ("swing-shack", "ss-photo-post"),
        ("bag-drop", "bd-member-moment"),
    ):
        item_id = f"calendar_candidate:{brand}:cal-default"
        d = decide(brand, item_id)
        assert d.is_gap(), brand
        assert d.reason in ("no_layout", "layout_not_vetted")
        if d.archetype_id == default_id:
            assert d.reason in ("layout_not_vetted", "no_layout")


def test_vetted_flag_backed_by_golden(gate_env):
    from _lib.archetypes import load_archetypes_doc
    from _lib.visual_gate import _golden_nonempty

    for brand in ("stick", "swing-shack", "bag-drop"):
        doc = load_archetypes_doc(brand)
        for row in doc.get("archetypes") or []:
            if not isinstance(row, dict) or not row.get("vetted"):
                continue
            pack = str(row.get("template_pack") or "")
            assert pack, f"{brand}/{row.get('id')} vetted without template_pack"
            assert _golden_nonempty(brand, pack), f"{brand}/{row.get('id')} golden missing"


def test_stand_ins_and_references_never_used(gate_env):
    from _lib.archetype_compose import _library_photo
    from _lib.draft_review_actions import _first_library_photo_bytes
    from _lib.visual_gate import is_stand_in, list_trusted_library_photos

    assert is_stand_in("standin-1.jpg")
    assert is_stand_in("stand-in-01.jpg")
    assert is_stand_in("templates/foo/references/ref.png")

    lib = "templates/lesson-corner/photos"
    trusted = list_trusted_library_photos("swing-shack", lib)
    assert trusted
    assert all(not is_stand_in(p) for p in trusted)
    assert all("references" not in {part.lower() for part in p.parts} for p in trusted)

    assert _first_library_photo_bytes("swing-shack", lib) is not None
    assert _library_photo("swing-shack", lib, "seed") is not None

    only_standin_dir = gate_env[0] / "brand-directory" / "stick" / "templates" / "service-start" / "photos"
    if only_standin_dir.is_dir():
        assert _library_photo("stick", "templates/service-start/photos", "x") is None
