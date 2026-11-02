"""The morning message says what today's job is in the weekly routine (Christelle, 2 Nov)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import plan_todo as pt  # noqa: E402

MONDAY = dt.date(2026, 11, 2)
BASE = "https://cos.example"


def day(n):
    return MONDAY + dt.timedelta(days=n)


def test_each_weekday_has_its_own_job():
    jobs = [pt.daily_focus(day(n))["job"] for n in range(5)]
    assert jobs == ["Plan the week and stories", "Marketing report and ads", "SEO and GEO",
                    "Make the posts", "Replies and close-out"]


def test_the_weekend_has_no_job():
    assert pt.daily_focus(day(5)) is None and pt.daily_focus(day(6)) is None


def test_the_message_says_today_s_job_right_after_the_greeting_with_full_links():
    text = pt.morning_text({"stick": {"alerts": [], "steps": []}}, day(1), base_url=BASE)
    lines = text.split("\n")
    assert lines[0].startswith("Good morning.")
    assert lines[2] == "Today: Marketing report and ads."
    assert f"{BASE}/app/results/week" in text
    assert text.endswith("Nothing needs you today.")


def test_every_link_is_a_real_page_on_the_app():
    for n in range(5):
        for label, path in pt.daily_focus(day(n))["links"]:
            assert label and path.startswith("/app/")


def test_without_a_base_url_the_job_is_still_said_but_no_link():
    text = pt.morning_text({"stick": {"alerts": [], "steps": []}}, day(2))
    assert "Today: SEO and GEO." in text and "/app/" not in text


def test_saturday_message_is_unchanged():
    text = pt.morning_text({"stick": {"alerts": [], "steps": []}}, day(5), base_url=BASE)
    assert "Today:" not in text
