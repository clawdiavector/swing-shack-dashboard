"""Ad tracking health: UTM checks and the GA4 join. Pure; nothing reaches Meta or Google."""
import datetime as dt

from _lib import ads_tracking as at

TODAY = dt.date(2026, 10, 20)


def _ad(i, name="Ad", status="RESOLVED", url="https://shop.example/", spend=100, camp="Camp"):
    return {"ad_id": i, "ad_name": name, "effective_status": "ACTIVE", "campaign": {"name": camp},
            "destination": {"status": status, "url": url if status == "RESOLVED" else None, "reason": "r"},
            "creative": {}, "current": {"spend": spend, "link_clicks": 10, "landing_page_views": 8}}


def test_clean_tags_have_no_issues():
    p, problems = at.parse_params("utm_source=meta&utm_medium=paid_social&utm_campaign=a&utm_content=b", None)
    assert problems == [] and p["utm_campaign"] == "a"


def test_whole_url_pasted_into_tags_is_flagged_and_still_read():
    p, problems = at.parse_params("https://x.co.za/?utm_source=facebook&utm_medium=paid_social&utm_campaign=c", None)
    assert "URL_IN_TAGS" in problems and p["utm_source"] == "facebook"


def test_placeholder_typed_literally_is_flagged_but_real_macros_are_not():
    _, bad = at.parse_params("utm_source={{meta}}&utm_medium={{paid_social}}", None)
    assert "PLACEHOLDER_LITERAL" in bad
    _, good = at.parse_params("utm_source=meta&utm_campaign={{campaign.name}}&utm_content={{ad.id}}", None)
    assert good == []
    _, encoded = at.parse_params("utm_content=%7B%7BGreenPoint%7D%7D", None)
    assert "PLACEHOLDER_LITERAL" in encoded


def test_website_ad_without_tags_or_with_partial_tags():
    none = at.audit_ad(_ad("1"), {}, {})
    assert "NO_UTM" in none["issues"]
    part = at.audit_ad(_ad("2"), {"2": "utm_source=meta"}, {})
    assert "INCOMPLETE_UTM" in part["issues"] and "NO_UTM" not in part["issues"]


def test_lead_and_message_ads_are_not_faulted_for_missing_utms():
    lead = at.audit_ad(_ad("3", status="LEAD_FORM"), {}, {})
    assert lead["destination"] == "LEAD_FORM" and lead["issues"] == []
    assert "Never reaches the website" in lead["notes"][0]


def test_join_matches_on_ad_id_in_content_or_campaign_and_ignores_organic():
    rows = [["fb", "paid", "C1", "A1", "100", "40"], ["ig", "paid", "A2", "x", "50", "10"],
            ["google", "organic", "(organic)", "(not set)", "900", "800"], ["fb", "paid", "OLD", "GONE", "30", "5"]]
    by_ad, totals = at.join_ga(rows, {"A1", "A2"})
    assert by_ad == {"A1": {"sessions": 100, "engaged": 40}, "A2": {"sessions": 50, "engaged": 10}}
    assert totals == {"paid_sessions": 180, "matched": 150, "unmatched": 30}


def test_build_audits_only_running_ads_and_summarises():
    ads = [_ad("A1", spend=300), _ad("A2", status="MESSAGING", spend=50), _ad("A3", spend=0)]
    ads[2]["effective_status"] = "PAUSED"
    out = at.build("stick", ads, {"A1": "utm_source=meta&utm_medium=paid_social&utm_campaign=c"},
                   [["fb", "paid", "C", "A1", "10", "5"]], today=TODAY)
    assert [a["ad_id"] for a in out["ads"]] == ["A1", "A2"]
    s = out["summary"]
    assert (s["website_ads"], s["never_reach_site"], s["website_with_complete_utm"], s["ga_matched"]) == (1, 1, 1, 10)
    assert out["ads"][0]["ga_sessions"] == 10
