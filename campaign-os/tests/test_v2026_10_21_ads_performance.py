"""Per-ad performance: Meta's spend and results next to Google Analytics' visits, engagement and key events."""
import datetime as dt

from _lib import ads_tracking as at

TODAY = dt.date(2026, 10, 21)


def _ad(i, kind="RESOLVED", spend=200.0, clicks=100, leads=0, messages=0, impressions=5000, name="Ad"):
    return {"ad_id": i, "ad_name": name, "effective_status": "ADSET_PAUSED",
            "campaign": {"id": "c", "name": "C", "objective": "OUTCOME_TRAFFIC"}, "adset": {"id": "s", "name": "S"},
            "creative": {"media_type": "video", "body": "fitting", "title": None},
            "destination": {"status": kind, "url": "https://shop.example/" if kind == "RESOLVED" else None},
            "current": {"spend": spend, "link_clicks": clicks, "landing_page_views": 80, "leads": leads,
                        "messages": messages, "impressions": impressions}}


GA = [["fb", "paid", "C", "A1", "80", "20", "3"], ["ig", "paid", "C", "A1", "20", "5", "1"]]


def test_a_website_ad_gets_cost_per_visit_engagement_and_key_events():
    out = at.build("stick", [_ad("A1")], {}, GA, today=TODAY)
    p = out["ads"][0]["perf"]
    assert out["ads"][0]["ga_sessions"] == 100 and out["ads"][0]["ga_key_events"] == 4
    assert p["cost_per_session"] == 2.0 and p["engaged_pct"] == 25.0
    assert p["click_to_session_pct"] == 100.0 and p["key_events"] == 4 and p["cost_per_lead"] is None


def test_a_lead_ad_gets_cost_per_lead_and_no_invented_website_numbers():
    out = at.build("stick", [_ad("L1", kind="LEAD_FORM", leads=8, spend=240.0)], {}, GA, today=TODAY)
    p = out["ads"][0]["perf"]
    assert p["cost_per_lead"] == 30.0 and p["leads"] == 8
    assert p["cost_per_session"] is None and p["engaged_pct"] is None and p["key_events"] is None


def test_an_ad_nobody_visited_has_unknown_not_zero_visit_numbers():
    p = at.build("stick", [_ad("A2")], {}, [], today=TODAY)["ads"][0]["perf"]
    assert p["cost_per_session"] is None and p["engaged_pct"] is None


def test_messages_get_their_own_cost():
    p = at.build("stick", [_ad("M1", kind="MESSAGING", messages=10, spend=100.0)], {}, [], today=TODAY)["ads"][0]["perf"]
    assert p["cost_per_message"] == 10.0


def test_old_six_column_rows_still_join_without_key_events():
    by_ad, totals = at.join_ga([["fb", "paid", "C", "A1", "10", "4"]], {"A1"})
    assert by_ad == {"A1": {"sessions": 10, "engaged": 4}} and totals["matched"] == 10


def test_brand_totals_add_up():
    ads = [_ad("A1", spend=200.0), _ad("L1", kind="LEAD_FORM", leads=8, spend=240.0)]
    t = at.build("stick", ads, {}, GA, today=TODAY)["totals"]
    assert t["spend"] == 440.0 and t["leads"] == 8 and t["cost_per_lead"] == 30.0
    assert t["ga_sessions"] == 100 and t["ga_engaged_pct"] == 25.0 and t["cost_per_session"] == 2.0
    assert t["ga_key_events"] == 4
