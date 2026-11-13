"""Staff messages for each facility (WhatsApp, next to Foreman's Telegram ones).

Written for shop staff, not for Christelle: what customers will see online this week,
what goes out today, stories to share, and last week's report. Approved wording 13 Nov 2026.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import staff_messages as sm  # noqa: E402

MONDAY = dt.date(2026, 11, 9)
FRIDAY = dt.date(2026, 11, 13)


def _e(date, title, view="scheduled", where="Instagram and Facebook", caption=""):
    return {"date": date, "title": title, "view": view, "where": where, "caption": caption}


WEEK = [
    _e("2026-11-09", "TikTok", where="TikTok"),
    _e("2026-11-09", "Instagram story", where="Instagram"),
    _e("2026-11-09", "Try a sleeve before you buy a dozen."),
    _e("2026-11-11", "The new Srixon RKT Range. Book a fitting at Stick to see which head suits you, "
                     "because the right loft and shaft matter more than the badge.", where="Instagram"),
    _e("2026-11-13", "Psycho Bunny spotlight", view="approval"),   # still waiting for a yes
    _e("2026-11-14", "Next to nothing", view="ideas"),             # an idea, not made
    _e("2026-11-16", "Next week's post"),                          # outside the week
    _e("2026-11-13", "Ball fitting", where="Google"),
]


def test_placeholder_titles_are_not_news():
    for t in ("TikTok", "Instagram story", "Untitled post", "facebook reel", "Story", ""):
        assert sm.is_placeholder(t), t
    for t in ("Your ball, fitted.", "Ball fitting", "Srixon Z-Star XV on the shelf"):
        assert not sm.is_placeholder(t), t


def test_a_headline_is_the_first_sentence_cut_at_a_word():
    assert sm.headline("Try a sleeve before you buy a dozen.\n\nMore here.") == "Try a sleeve before you buy a dozen"
    long = sm.headline(WEEK[3]["title"])
    assert long == "The new Srixon RKT Range"
    cut = sm.headline("word " * 40)
    assert len(cut) <= 61 and cut.endswith("…") and not cut.endswith(" …")


def test_the_monday_message_names_topics_for_staff():
    msg = sm.week_message("stick", WEEK, MONDAY, topics=["Club and ball fittings", "The new Srixon RKT irons"])
    assert msg["send"]
    text = msg["text"]
    assert text.startswith("Morning Stick team 👋")
    assert "This week online (9–15 Nov) we're talking about:" in text
    assert "• Club and ball fittings\n• The new Srixon RKT irons" in text
    assert text.endswith("If a customer mentions something they saw online, it's probably one of these.")
    assert "TikTok" not in text and "more" not in text


def test_without_topics_the_monday_message_lists_the_real_headlines():
    text = sm.week_message("stick", WEEK, MONDAY)["text"]
    assert "• Try a sleeve before you buy a dozen" in text
    assert "• The new Srixon RKT Range" in text
    assert "• Ball fitting" in text
    for left_out in ("TikTok\n", "Instagram story", "Psycho Bunny", "Next to nothing", "Next week's post"):
        assert left_out not in text


def test_the_headline_list_is_short_and_has_no_repeats():
    many = [_e("2026-11-10", f"Post number {i}") for i in range(9)] + [_e("2026-11-11", "Post number 1")]
    text = sm.week_message("swing-shack", many, MONDAY)["text"]
    assert text.startswith("Morning Swing Shack team 👋")
    assert text.count("• ") == sm.MAX_ITEMS
    assert text.count("Post number 1") == 1


def test_an_empty_week_is_not_sent():
    msg = sm.week_message("stick", [WEEK[0], WEEK[4]], MONDAY)
    assert msg["send"] is False and msg["text"] == ""


def test_topics_from_the_model_are_checked_before_use():
    assert sm.parse_topics("- Club and ball fittings\n* Srixon RKT irons\n3. Golf bags in store") == [
        "Club and ball fittings", "Srixon RKT irons", "Golf bags in store"]
    assert sm.parse_topics("") is None
    assert sm.parse_topics("- 20% off bags") is None              # no numbers the posts didn't source
    assert sm.parse_topics("- " + "x" * 80) is None              # not a topic, a caption
    assert sm.parse_topics("\n".join(f"- Topic {chr(65 + i)}" for i in range(8))) is None


def test_the_daily_message_lists_what_goes_out_today():
    msg = sm.today_message("stick", WEEK, FRIDAY)
    assert msg["send"]
    assert msg["text"] == (
        "Today on Stick's socials (Fri 13 Nov):\n"
        "• Google: Ball fitting\n\n"
        "Nothing for you to do. Just know what customers might ask about."
    )
    assert sm.today_message("stick", WEEK, dt.date(2026, 11, 12))["send"] is False


def test_stories_to_share_are_numbered_with_the_how_to():
    items = [{"url": "https://www.instagram.com/p/abc/", "note": "Srixon RKT reel"},
             {"url": "https://www.instagram.com/p/def/", "note": ""}]
    msg = sm.stories_message("stick", items)
    assert msg["send"]
    assert msg["text"] == (
        "2 stories to share today 📲\n"
        "1. Srixon RKT reel: https://www.instagram.com/p/abc/\n"
        "2. https://www.instagram.com/p/def/\n\n"
        "Open the link on your phone, tap the paper plane, then \"Add to story\"."
    )
    assert sm.stories_message("stick", items[:1])["text"].startswith("1 story to share today 📲")
    assert sm.stories_message("stick", [])["send"] is False


def test_the_tuesday_message_is_one_line_and_the_link():
    msg = sm.report_message("swing-shack", "https://x/weekly-report?brand=swing-shack&share=t")
    assert msg["send"]
    assert msg["text"] == (
        "How Swing Shack did online last week 📊\n"
        "https://x/weekly-report?brand=swing-shack&share=t\n\n"
        "Opens without a login, works for 7 days."
    )


@pytest.fixture(scope="module")
def loaded_app(tmp_path_factory):
    base = tmp_path_factory.mktemp("cosdata")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(base))
    mp.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    sys.modules.pop("app", None)
    import app as app_module

    app_module._GIT_SYNC_DONE = True
    yield app_module
    mp.undo()


def test_the_route_needs_the_job_token_one_facility_and_a_known_kind(loaded_app, monkeypatch):
    monkeypatch.setattr(loaded_app, "COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setattr(loaded_app, "_staff_week_entries", lambda brand, today: list(WEEK))
    monkeypatch.setattr(loaded_app, "_staff_topics", lambda brand, entries: None)
    auth = {"Authorization": "Bearer test-job-token-not-a-secret"}
    anon = loaded_app.app.test_client(cos_anon=True)
    path = "/api/jobs/staff-message"

    assert anon.get(path + "?kind=week&brand=stick").status_code == 401
    assert anon.get(path + "?kind=week&brand=all", headers=auth).status_code == 400
    assert anon.get(path + "?kind=gossip&brand=stick", headers=auth).status_code == 400

    r = anon.get(path + "?kind=week&brand=stick", headers=auth).get_json()
    assert r["ok"] and r["send"] and r["text"].startswith("Morning Stick team 👋")
    assert "• Try a sleeve before you buy a dozen" in r["text"]

    r = anon.get(path + "?kind=stories&brand=stick", headers=auth).get_json()
    assert r["ok"] and r["send"] is False

    r = anon.get(path + "?kind=report&brand=stick", headers=auth).get_json()
    assert r["ok"] and "/weekly-report?brand=stick&share=" in r["text"]
