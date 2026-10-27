"""Stories (2026-10-27): Sub 70 and Fujimoto on both retail lists, ladies' golf pages, and the
suggested list keeps room for product posts and ladies' golf instead of vibe posts only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import story_scout  # noqa: E402

BRANDS = CAMPAIGN_OS.parent / "data" / "brand-directory"


def _load(brand):
    return json.loads((BRANDS / brand / "story-brands.json").read_text(encoding="utf-8"))


def _cand(page_id, kind, score, women=False):
    return {"page_id": page_id, "kind": kind, "score": score, "women": women, "url": f"https://x/{page_id}/{score}"}


def test_sub70_and_fujimoto_on_both_retail_lists():
    for brand in ("swing-shack", "stick"):
        retail = {p["id"]: p for p in _load(brand)["retail"]}
        assert retail["sub70"]["instagram"] == "https://www.instagram.com/golfsub70/"
        assert retail["fujimoto"]["instagram"] == "https://www.instagram.com/fujimoto_golf/"


def test_ladies_golf_pages_on_both_brands_and_flagged_women():
    for brand in ("swing-shack", "stick"):
        moments = {m["id"]: m for m in _load(brand)["moments"]}
        for pid in ("sunshine-ladies-tour", "let", "lpga", "womens-golf-day"):
            assert moments[pid]["women"] is True
            assert moments[pid]["instagram"]


def test_rank_page_carries_the_women_flag():
    page = {"id": "let", "name": "Ladies European Tour", "women": True}
    post = {"caption": "Sunday golf.", "like_count": 10, "comments_count": 0, "media_type": "IMAGE",
            "permalink": "https://www.instagram.com/p/A/", "timestamp": "2026-10-26T08:00:00+0000"}
    from datetime import datetime, timezone
    got = story_scout.rank_page(page, [post], datetime(2026, 10, 27, tzinfo=timezone.utc))
    assert got[0]["women"] is True


def test_pick_keeps_room_for_product_posts_when_vibes_score_higher():
    cands = [_cand(f"v{i}", "vibe", 10 - i) for i in range(8)] + [
        _cand("p1", "product", 1.0), _cand("p2", "product", 0.9), _cand("p3", "product", 0.8)]
    got = story_scout.pick(cands)
    assert len(got) <= story_scout.PER_BRAND
    assert sum(c["kind"] == "product" for c in got) >= story_scout.PRODUCT_SLOTS


def test_pick_keeps_a_slot_for_ladies_golf_even_when_winners_news_scores_higher():
    cands = [_cand(f"v{i}", "vibe", 10 - i) for i in range(8)] + [_cand("let", "story", 0.5, women=True)]
    got = story_scout.pick(cands)
    assert any(c["women"] for c in got)


def test_pick_still_caps_a_page_and_the_list():
    cands = [_cand("p1", "product", 5 - i * 0.1) for i in range(6)]
    got = story_scout.pick(cands)
    assert len(got) == story_scout.PER_PAGE
