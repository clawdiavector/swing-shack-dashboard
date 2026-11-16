"""One plain numbered list for Herman: what to run, what it costs, where the money comes from, yes or no each."""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ad_suggestions as t  # noqa: E402
import test_v2026_11_13_ad_suggestions_types as ty  # noqa: E402
from _lib import ads_suggest  # noqa: E402


def _docs():
    stick = t._build([t.FITTING_REEL, t.COACH_REEL, t.RETAIL_IMAGE], budget=300)
    ss = t._build([ty.WEBSITE_REEL], brand="swing-shack", budget=1000)
    return [stick, ss]


def test_one_numbered_line_per_ad_with_cost_and_money_source():
    text = ads_suggest.herman_text(_docs())
    lines = [ln for ln in text.splitlines() if ln[:2].rstrip(".").isdigit()]
    assert len(lines) == 3  # the animated still is a job, not a decision
    assert all("R210" in ln for ln in lines)
    assert "Swing Shack" in text and "Stick" in text


def test_ads_that_need_extra_money_come_first_and_say_so():
    text = ads_suggest.herman_text(_docs())
    first = next(ln for ln in text.splitlines() if ln.startswith("1."))
    assert "extra" in first.lower()
    assert "over the budget" in text.lower()


def test_no_ad_jargon_and_no_em_dash():
    text = ads_suggest.herman_text(_docs()).lower()
    for word in ("utm", "objective", "thruplay", "advantage+", "cpl", "lead_form", "campaign_"):
        assert word not in text
    assert "\u2014" not in text


def test_reply_line_and_total():
    text = ads_suggest.herman_text(_docs())
    assert "reply with the numbers" in text.lower()
    assert "R630" in text  # three tests of R210


def test_page_carries_the_herman_text_to_copy():
    html = ads_suggest.render_html(_docs())
    assert "For Herman" in html and "<textarea" in html
