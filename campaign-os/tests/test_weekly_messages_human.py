"""The Monday and Tuesday Foreman messages read like a person wrote them, not a database dump."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parent.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import plan_todo as pt  # noqa: E402

MONDAY = dt.date(2026, 10, 26)


def _text(items, brand="stick"):
    return pt.weekly_selling_text({brand: {"items": [{"date": d, "title": t} for d, t in items]}}, MONDAY)


def test_generic_story_reel_and_post_rows_are_left_out():
    text = _text([("2026-10-26", "Instagram story"), ("2026-10-26", "Instagram reel"),
                  ("2026-10-27", "Facebook post"), ("2026-10-28", "Titleist AVX 2026")])
    assert "Instagram" not in text and "Facebook" not in text
    assert "• Wed 28 Oct: Titleist AVX 2026" in text


def test_resend_and_variant_tags_are_dropped_and_repeats_shown_once():
    text = _text([("2026-10-26", "Vice Pro Air sleeve (resend)"), ("2026-10-26", "Vice Pro Air sleeve (retail B)"),
                  ("2026-10-27", "Vice Pro Air sleeve")])
    assert text.count("Vice Pro Air sleeve") == 1
    assert "resend" not in text and "retail B" not in text


def test_caption_lines_are_not_shown_as_product_names():
    text = _text([("2026-10-26", "Everything thing you see in this video is taken into account in both the fitting and the build process."),
                  ("2026-10-26", "Callaway Chrome Tour is in at Stick."),
                  ("2026-10-27", "Callaway Chrome Tour")])
    assert text.count("Callaway Chrome Tour") == 1
    assert "Everything thing" not in text


def test_a_long_week_is_cut_to_six_and_says_so_in_plain_words():
    items = [(f"2026-10-{26 + i % 5}", f"Product {i}") for i in range(10)]
    text = _text(items)
    assert text.count("• ") == 6
    assert "Plus 4 more lined up." in text and "…" not in text


def test_a_facility_with_only_noise_says_nothing_is_planned():
    text = _text([("2026-10-26", "Instagram story")])
    assert "— Stick —\nNothing on the calendar yet." in text


def test_the_monday_message_talks_to_a_person_and_signs_off():
    text = _text([("2026-10-28", "Titleist AVX 2026")])
    assert text.startswith("Good morning. What we are selling this week, Mon 26 Oct to Sun 1 Nov.\n\nHere's what is lined up")
    assert text.endswith("Have a good week.")


def test_the_tuesday_message_introduces_the_links():
    text = pt.weekly_report_text({"stick": "https://x/s"}, dt.date(2026, 10, 27))
    assert "Here's how last week went" in text and "Stick: https://x/s" in text
