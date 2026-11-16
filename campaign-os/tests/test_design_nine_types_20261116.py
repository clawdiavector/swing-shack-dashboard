"""Christelle, 16 Nov 2026: 9 post types, not 11, and her names for three looks."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import design_layout_ledger as ll  # noqa: E402



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
