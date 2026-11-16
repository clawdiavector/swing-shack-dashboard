"""Design page: per-type layout ledger (operating plan phase 1)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import design_layout_ledger as ll  # noqa: E402
from _lib import design_taxonomy as dt  # noqa: E402


def test_every_seeded_type_has_a_row_for_every_brand():
    ledger = ll.build_layout_ledger()
    ids = {t["id"] for t in dt.build_taxonomy()["types"]}
    assert ids <= set(ledger)
    for type_id in ids:
        assert set(ledger[type_id]) == set(ll.BRANDS)
        for cell in ledger[type_id].values():
            assert cell["status"] in ll.LABELS and cell["label"] == ll.LABELS[cell["status"]]


def test_status_follows_the_visual_gate():
    ledger = ll.build_layout_ledger()
    # these two work with no photo, so they must read as a layout on any machine
    assert ledger["tip"]["swing-shack"]["status"] == "has_layout"
    assert ledger["offer"]["bag-drop"]["status"] == "has_layout"
    # Bag Drop has no tip template other than the weekly deal: nothing built
    assert ledger["condition"]["bag-drop"]["status"] in ("not_yet", "unknown")
    assert ledger["price"]["bag-drop"]["status"] == "not_yet"


def test_not_applicable_and_one_shot():
    ledger = ll.build_layout_ledger()
    assert ledger["venue"]["bag-drop"]["status"] == "not_applicable"
    assert ledger["condition"]["stick"]["status"] == "not_applicable"
    # one-shot is only offered where the layout is not trusted yet
    for cell in ledger["service"].values():
        if cell["status"] == "has_layout":
            assert cell["one_shot_ok"] is False
    # Stick service mixes trusted and untrusted post types, so it must not read as fully done
    assert ledger["service"]["stick"]["status"] == "partial"
    assert ledger["service"]["stick"]["one_shot_ok"] is True


def test_a_broken_probe_never_breaks_the_page(monkeypatch):
    from _lib import visual_gate

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(visual_gate, "decide", boom)
    ledger = ll.build_layout_ledger()
    assert ledger["tip"]["swing-shack"]["status"] == "unknown"
    assert dt.build_taxonomy()["layout_ledger"]


# Christelle, 16 Nov 2026: 9 post types, not 11. Location is part of venue; generic is gone.


def test_ledger_has_the_nine_types():
    assert sorted(ll.PROBES) == [
        "condition", "offer", "person", "price", "product", "service", "statement", "tip", "venue",
    ]
    assert "location" in ll.PROBES["venue"]["stick"]


def test_seed_has_the_nine_types_and_new_look_names():
    import json

    seed = json.loads((Path(__file__).resolve().parents[2] / "data" / "design" / "taxonomy-seed.json").read_text())
    assert len(seed["types"]) == 9
    venue = next(t for t in seed["types"] if t["id"] == "venue")
    assert "stick-location-drive" in venue["templates"]["stick"]
    names = {s["id"]: s["name"] for s in seed["styles"]}
    assert names["teal-reel"] == "Photo fade"
    assert names["abstract"] == "Dark type-hero"
    assert names["deal-carousel"] == "Purple echo"
    for sid in ("photo-band", "clean-product", "teal-reel"):
        summary = next(s["summary"] for s in seed["styles"] if s["id"] == sid)
        assert "teal" not in summary.lower()
