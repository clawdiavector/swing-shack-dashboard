"""Ad suggestions: which posts to turn into ads, what kind, what spend, where the money comes from, and every setting.

Pure. Nothing reaches Meta. The page reads the files the jobs already keep.
"""
from __future__ import annotations

import datetime as dt
import sys
import urllib.parse
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import ads_naming, ads_suggest, ads_tracking  # noqa: E402

TODAY = dt.date(2026, 11, 13)


def _post(pid, caption, fmt="reel", reach=1000, score=50, days_ago=5, saves=10, shares=5):
    when = (dt.datetime(2026, 11, 13, 8, tzinfo=dt.timezone.utc) - dt.timedelta(days=days_ago))
    return {"post_id": pid, "caption_preview": caption[:100], "format_type": fmt, "reach": reach,
            "score": score, "permalink": f"https://www.instagram.com/reel/{pid}/",
            "timestamp": when.strftime("%Y-%m-%dT%H:%M:%S+0000"),
            "_media": {"id": pid, "caption_preview": caption, "saves": saves, "shares": shares,
                       "media_type": "VIDEO" if fmt == "reel" else ("CAROUSEL_ALBUM" if fmt == "carousel" else "IMAGE"),
                       "thumbnail_url": f"https://cdn.example/{pid}.jpg"}}


def _split(posts):
    outcomes = [{k: v for k, v in p.items() if k != "_media"} for p in posts]
    media = [p["_media"] for p in posts]
    return outcomes, media


def _figures(sets=(), run_rate=None):
    rows = [{"id": s[0], "name": s[1], "kind": "daily", "amount": s[2], "days_left": 10,
             "objective": "OUTCOME_LEADS"} for s in sets]
    return {"period": "week", "daily_run_rate": run_rate if run_rate is not None else sum(s[2] for s in sets),
            "sets": rows, "complete": True}


def _brief(ads=(), cpl=None):
    return {"numbers_7d": {"current": {"cost_per_lead": cpl},
                           "ads": [{"ad_name": a[0], "campaign_name": a[1], "spend": a[2], "leads": a[3],
                                    "messages": 0} for a in ads]}}


def _build(posts, *, budget=1500, sets=(), ads=(), cpl=None, running=None, brand="stick"):
    outcomes, media = _split(posts)
    return ads_suggest.build(
        brand, outcomes=outcomes, media=media, running=running or {"bodies": [], "post_ids": []},
        settings={"monthly_budget": budget, "budget_period": "week"}, figures=_figures(sets),
        brief=_brief(ads, cpl), today=TODAY)


FITTING_REEL = _post("f1", "Your driver should fit you, not the other way round. Book a fitting at Stick.")
ASSESS_REEL = _post("a1", "Free 30-minute club assessment. Bring your bag, we check what you play.")
COACH_REEL = _post("c1", "One lesson can change how your irons come off the face. Book a coach.")
RETAIL_IMAGE = _post("r1", "New in: Psycho Bunny polos, available at Stick. DM us for sizes.", fmt="image")
STATIC_FITTING = _post("s1", "Get measured on Trackman. Book a fitting.", fmt="image")
GENERAL_REEL = _post("g1", "Sunset over the range. What a day.")


def _by_post(out):
    return {s["post_id"]: s for s in out["suggestions"]}


def _skipped(out):
    return {s["post_id"]: s["reason"] for s in out["skipped"]}


# ── what becomes an ad ───────────────────────────────────────────────────

def test_a_fitting_reel_becomes_a_lead_form_ad():
    s = _by_post(_build([FITTING_REEL]))["f1"]
    assert s["ad_type"] == "lead_form"
    assert s["theme"] == "fitting"
    assert s["objective"] == "OUTCOME_LEADS"


def test_a_static_service_post_is_never_an_ad():
    out = _build([STATIC_FITTING])
    assert "s1" not in _by_post(out)
    assert "video" in _skipped(out)["s1"].lower()


def test_a_retail_photo_becomes_an_animated_still_job_not_the_photo_itself():
    s = _by_post(_build([RETAIL_IMAGE]))["r1"]
    assert s["ad_type"] == "animated_still"
    assert s["ready"] is False


def test_a_retail_reel_becomes_a_messages_ad():
    reel = _post("r2", "New in: Psycho Bunny polos, available at Stick. DM us for sizes.")
    s = _by_post(_build([reel]))["r2"]
    assert s["ad_type"] == "messages"
    assert s["objective"] == "OUTCOME_ENGAGEMENT"


def test_a_reel_with_nothing_to_sell_stays_organic():
    out = _build([GENERAL_REEL])
    assert "g1" not in _by_post(out)
    assert "offer" in _skipped(out)["g1"].lower()


def test_a_post_already_running_as_an_ad_is_left_out():
    running = {"bodies": [ads_suggest.norm(FITTING_REEL["_media"]["caption_preview"])], "post_ids": []}
    out = _build([FITTING_REEL], running=running)
    assert "f1" not in _by_post(out)
    assert "already" in _skipped(out)["f1"].lower()


def test_old_and_unseen_posts_are_left_out():
    old = _post("o1", "Book a fitting at Stick.", days_ago=90)
    unseen = _post("u1", "Book a fitting at Stick, driver day.", reach=0)
    out = _build([old, unseen])
    assert not out["suggestions"]


def test_one_suggestion_per_subject_best_first():
    weak = _post("f2", "Book a fitting at Stick for your irons.", score=10)
    out = _build([weak, FITTING_REEL, COACH_REEL])
    ids = [s["post_id"] for s in out["suggestions"]]
    assert ids.index("f1") < ids.index("c1")
    assert "f2" not in ids


# ── spend and where the money comes from ─────────────────────────────────

def test_spend_is_a_whole_test_and_never_below_the_floor():
    s = _by_post(_build([FITTING_REEL]))["f1"]["spend"]
    assert s["days"] == 7
    assert s["daily"] >= ads_suggest.FLOOR_DAILY
    assert s["total"] == s["daily"] * s["days"]


def test_known_cost_per_lead_gives_an_expected_number_of_leads():
    s = _by_post(_build([FITTING_REEL], cpl=40))["f1"]["spend"]
    assert s["expected_results"] >= 1
    assert "lead" in s["expected_text"]


def test_money_comes_from_unused_room_first():
    s = _by_post(_build([FITTING_REEL], budget=1500, sets=[("a", "x_set", 30)]))["f1"]
    assert s["funding"]["source"] == "room"
    assert "R1,500" in s["funding"]["text"]


def test_then_from_the_weakest_running_ad_set():
    sets = [("a", "stick_leads_fitting_may26_set", 100), ("b", "stick_traffic_general_may26_set", 100)]
    ads = [("fitting_video_v1", "stick_leads_fitting_may26", 300, 8),
           ("general_video_v1", "stick_traffic_general_may26", 250, 0)]
    s = _by_post(_build([FITTING_REEL], budget=1400, sets=sets, ads=ads))["f1"]
    assert s["funding"]["source"] == "move"
    assert s["funding"]["from"] == "stick_traffic_general_may26_set"


def test_and_last_asks_for_more_budget():
    s = _by_post(_build([FITTING_REEL], budget=0))["f1"]
    assert s["funding"]["source"] == "extra"
    assert "herman" in s["funding"]["text"].lower()


def test_room_is_used_up_in_order():
    out = _build([FITTING_REEL, COACH_REEL], budget=300)
    sources = [s["funding"]["source"] for s in out["suggestions"] if s["ad_type"] != "animated_still"]
    assert sources[0] == "room"
    assert sources[1] != "room"


# ── the settings ─────────────────────────────────────────────────────────

def test_names_follow_the_naming_rule():
    s = _by_post(_build([FITTING_REEL]))["f1"]
    assert s["names"]["campaign"] == "stick_leads_fitting_nov26"
    assert s["names"]["adset"] == "stick_leads_fitting_nov26_set"
    for n in s["names"].values():
        assert ads_naming.valid_name(n) == n


def test_utm_tags_are_valid_and_carry_the_ad_id_macro():
    s = _by_post(_build([FITTING_REEL]))["f1"]
    tags = s["url_params"]
    assert ads_naming.valid_tags(tags) == tags
    q = dict(urllib.parse.parse_qsl(tags))
    assert q["utm_source"] == "meta" and q["utm_medium"] == "paid_social"
    assert q["utm_campaign"] == s["names"]["campaign"]
    assert q["utm_content"] == s["names"]["ad"]
    assert q["utm_id"] == "{{ad.id}}"
    _, problems = ads_tracking.parse_params(tags, s["landing_url"])
    assert problems == []


def test_landing_and_privacy_links_are_the_brands_own_site():
    s = _by_post(_build([FITTING_REEL]))["f1"]
    assert s["landing_url"].startswith("https://stickgolf.co.za/")
    form = s["form"]
    assert form["privacy_url"].startswith("https://stickgolf.co.za/")
    ss = _by_post(_build([_post("f9", "Book a fitting at Swing Shack.")], brand="swing-shack"))["f9"]
    assert ss["landing_url"].startswith("https://swingshack.co.za/")


def test_lead_form_is_higher_intent_with_contact_fields_and_a_qualifying_question():
    form = _by_post(_build([FITTING_REEL]))["f1"]["form"]
    assert form["type"] == "Higher intent"
    labels = " ".join(q["label"].lower() for q in form["questions"])
    assert "phone" in labels and "name" in labels
    assert any(q.get("options") for q in form["questions"])
    assert form["thank_you"]["button_url"].startswith("https://")


def test_a_free_assessment_form_never_asks_fitting_details():
    form = _by_post(_build([ASSESS_REEL]))["a1"]["form"]
    text = repr(form).lower()
    for word in ("loft", "shaft", "lie angle", "grip size", "swing speed"):
        assert word not in text


def test_every_suggestion_has_the_full_setup_and_checks():
    out = _build([FITTING_REEL, COACH_REEL, _post("r2", "New in: Vessel bags, available at Stick.")])
    for s in out["suggestions"]:
        titles = [sec["title"] for sec in s["setup"]]
        if s["ad_type"] == "animated_still":
            continue
        assert titles[:3] == ["Campaign", "Ad set", "Ad"]
        assert any("music" in c.lower() for c in s["checks"])
        cta = dict(next(sec for sec in s["setup"] if sec["title"] == "Ad")["rows"])["Call to action button"]
        assert cta


def test_a_messages_ad_has_conversation_starters_not_a_form():
    s = _by_post(_build([_post("r2", "New in: Vessel bags, available at Stick.")]))["r2"]
    assert s.get("form") is None
    assert len(s["starters"]) >= 3


def test_a_deal_in_the_caption_asks_to_check_the_dates():
    deal = _post("d1", "20% off all fittings this Black Friday. Book a fitting at Stick.")
    s = _by_post(_build([deal]))["d1"]
    assert any("still on" in c.lower() for c in s["checks"])


# ── the page ─────────────────────────────────────────────────────────────

def test_page_lists_suggestions_with_tabs_and_escapes_captions():
    evil = _post("e1", "Book a fitting <script>alert(1)</script> at Stick.")
    out = _build([evil, RETAIL_IMAGE])
    html = ads_suggest.render_html([out], missing=["swing-shack"])
    assert "<script>alert" not in html
    assert "/ads-brief?kind=suggest" in html
    assert "https://www.instagram.com/reel/e1/" in html
    assert "Swing Shack" in html
    assert "—" not in html  # no em dash on the page


def test_tabs_on_the_other_ads_pages_link_to_suggestions():
    from _lib import ads_brief
    assert any(k == "suggest" for k, _, _ in ads_brief._TABS)
