"""Ads on Meta's flexible creative cannot be tagged from here, and the tracking check says so."""
import datetime as dt

from _lib import ads_tracking as at

TODAY = dt.date(2026, 10, 21)


def _ad(i):
    return {"ad_id": i, "ad_name": "Ad", "effective_status": "ACTIVE", "campaign": {"id": "c", "name": "C", "objective": "OUTCOME_TRAFFIC"},
            "adset": {"id": "s", "name": "S"}, "creative": {"media_type": "video", "body": "fitting", "title": None},
            "destination": {"status": "RESOLVED", "url": "https://shop.example/"},
            "current": {"spend": 10, "link_clicks": 1, "landing_page_views": 1}}


def test_fetch_tag_info_reports_tags_and_flexible_ads():
    rows = [{"id": "1", "creative": {"url_tags": "utm_source=meta", "asset_feed_spec": {"x": 1}}},
            {"id": "2", "creative": {"url_tags": None}}]
    tags, flexible, err = at.fetch_tag_info("act_1", "t", get=lambda path, params: ({"data": rows}, None))
    assert tags == {"1": "utm_source=meta", "2": None} and flexible == {"1"} and err is None


def test_fetch_url_tags_still_works_for_old_callers():
    tags, err = at.fetch_url_tags("act_1", "t", get=lambda path, params: ({"data": [{"id": "1", "creative": {"url_tags": "a=b"}}]}, None))
    assert tags == {"1": "a=b"} and err is None


def test_rows_say_whether_the_tags_can_be_fixed_from_here():
    out = at.build("stick", [_ad("1"), _ad("2")], {}, [], today=TODAY, flexible={"1"})
    fixable = {r["ad_id"]: r["tags_fixable"] for r in out["ads"]}
    assert fixable == {"1": False, "2": True}
    assert all(r["tags_fixable"] for r in at.build("stick", [_ad("3")], {}, [], today=TODAY)["ads"])
