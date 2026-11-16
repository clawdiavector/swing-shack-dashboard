"""Bag Drop gets daily story ideas like Swing Shack and Stick (2026-11-06, step 2).

After PR #341 the story ideas route asked for Bag Drop but returned nothing, because
Bag Drop had no data/brand-directory/bag-drop/story-brands.json. The list holds the
makers it stocks (its own store collections: Callaway, Cobra, TaylorMade, Titleist),
trade-ins as its one service (no fittings or coaching: it is an online store), and
golf moments.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

FILE = REPO_ROOT / "data" / "brand-directory" / "bag-drop" / "story-brands.json"


def _data() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def test_bag_drop_has_a_story_brands_file():
    d = _data()
    assert d["brand"] == "bag-drop"
    ids = {b["id"] for b in d["retail"]}
    assert {"callaway", "cobra", "taylormade", "titleist"} <= ids


def test_bag_drop_never_offers_fittings_or_coaching():
    for s in _data()["services"]:
        name = s["name"].lower()
        assert "fitting" not in name and "coaching" not in name and "lesson" not in name


def test_no_swing_shack_or_stick_only_pages():
    text = json.dumps(_data()).lower()
    for other in ("psycho", "takomo", "trackman", "swing shack", "stick"):
        assert other not in text, other


def test_every_page_is_an_official_link_or_left_blank():
    for b in _data()["retail"] + _data()["moments"]:
        for key in ("instagram", "facebook"):
            url = b.get(key)
            assert url is None or url.startswith(f"https://www.{key}.com/"), (b["id"], url)


def test_story_ideas_come_back_for_bag_drop_every_day():
    from _lib import story_suggestion

    for d in range(7):
        out = story_suggestion.suggest("bag-drop", date(2026, 11, 9 + d), {})
        kinds = {x["kind"] for x in out}
        assert "retail" in kinds and "moment" in kinds, d
        for x in out:
            assert x["brand"] == "bag-drop"
            assert x["repost_from"]["instagram"] or x["repost_from"]["facebook"]
