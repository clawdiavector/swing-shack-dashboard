"""The CMO brief speaks of the week when the ad budget is a weekly one (R1,000 and R1,500 a week)."""
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

from _lib import cmo_brief  # noqa: E402
import test_v2026_10_26_cmo_brief as fx  # noqa: E402


def weekly(**budget):
    f = fx.swing_shack()
    f["ads"]["budget"].update(period="week", budget=1000, mtd_spend=1043.0, projected_total=1043.0,
                              days_left_after_today=4, **budget)
    return f


def _text(b):
    return fx.text(b)


def test_the_verdict_and_the_numbers_say_week():
    b = cmo_brief.build(weekly())
    t = _text(b)
    assert "week's ad budget of R1,000 is used up" in t
    assert "month's" not in t and "month end" not in t
    labels = {n["label"] for n in b["numbers"]}
    assert "This week's ad budget" in labels and "This month's ad budget" not in labels
    assert b["verdict"]["tone"] == "act"


def test_the_budget_decision_prices_the_rest_of_the_week():
    d = next(x for x in cmo_brief.build(weekly())["decisions"] if "budget" in x["decision"].lower())
    s = d["recommendation"] + d["because"]
    assert "rest of the week" in d["decision"]
    # lead ad sets run on R52 a day; 4 days left = R208; at R31 a lead that is about 6 leads
    assert "R208" in s and "6 leads" in s and "end of the week" in s
    assert "if the cost per lead holds" in s and "worth" in d["recommendation"]


def test_a_monthly_budget_is_unchanged():
    t = _text(cmo_brief.build(fx.swing_shack()))
    assert "month's ad budget" in t or "month's" in t or "month end" in t
    assert "week's ad budget" not in t
