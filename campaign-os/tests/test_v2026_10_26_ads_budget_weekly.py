"""The ad budget can be a weekly budget (Monday to Sunday, South African time) as well as a monthly one.

Christelle's budgets are R1,000 a week for Swing Shack and R1,500 a week for Stick. A week's budget is spent against
that week's spend, so the figures, the verdict, the hourly guard and the report all say "week", not "month"."""
import datetime as dt
import json

from _lib import ads_budget as ab
from _lib import ads_guard as g

WED = dt.date(2026, 10, 28)   # Monday 26 Oct .. Sunday 1 Nov: 4 days left after today


def _set(i, daily):
    return {"id": str(i), "name": f"set{i}", "effective_status": "ACTIVE", "daily_budget": str(int(daily * 100)),
            "lifetime_budget": None, "budget_remaining": None, "start_time": "2026-09-01T00:00:00+0200",
            "end_time": None, "campaign_id": f"c{i}", "campaign": {"id": f"c{i}", "objective": "OUTCOME_LEADS"}}


def _fig(spent, daily=50, today_spend=0.0, period="week"):
    return ab.build_figures(mtd_spend=spent, today_spend=today_spend, adsets=[_set(1, daily)], today=WED, period=period)


def test_the_week_runs_monday_to_sunday():
    assert ab.period_bounds(WED, "week") == (dt.date(2026, 10, 26), dt.date(2026, 11, 1))
    assert ab.period_bounds(dt.date(2026, 10, 26), "week") == (dt.date(2026, 10, 26), dt.date(2026, 11, 1))
    assert ab.period_bounds(dt.date(2026, 11, 1), "week") == (dt.date(2026, 10, 26), dt.date(2026, 11, 1))
    assert ab.period_bounds(WED, "month") == (dt.date(2026, 10, 1), dt.date(2026, 10, 31))


def test_period_comes_from_the_settings_and_defaults_to_month():
    assert ab.period_of({"budget_period": "week"}) == "week"
    assert ab.period_of({}) == "month"
    assert ab.period_of(None) == "month"
    assert ab.period_of({"budget_period": "fortnight"}) == "month"


def test_weekly_figures_count_the_days_left_in_the_week():
    f = _fig(400, daily=50)
    assert f["period"] == "week" and f["period_start"] == "2026-10-26" and f["period_end"] == "2026-11-01"
    assert f["days_left_after_today"] == 4
    assert f["expected_rest_of_month"] == 50.0 * 4 + 50.0   # key name kept: it means the rest of the period


def test_month_is_still_the_default():
    f = ab.build_figures(mtd_spend=0, today_spend=0, adsets=[_set(1, 50)], today=dt.date(2026, 10, 20))
    assert f["period"] == "month" and f["days_left_after_today"] == 11 and f["month"] == "2026-10"


def test_the_verdict_speaks_of_the_week():
    over = ab.evaluate(_fig(1200), 1000)
    assert over["status"] == "OVER" and over["left"] == -200.0
    assert "week's budget" in over["headline"] and "month" not in over["headline"]
    risk = ab.evaluate(_fig(700, daily=100), 1000)   # 700 + 500 = 1200
    assert risk["status"] == "AT_RISK" and "the week ends near" in risk["headline"]
    assert ab.evaluate(_fig(100, daily=50), 1000)["status"] == "OK"
    assert ab.evaluate(_fig(0), None)["headline"] == "No weekly budget set yet."
    assert "month's budget" in ab.evaluate(ab.build_figures(mtd_spend=2000, today_spend=0, adsets=[], today=WED), 1000)["headline"]


def test_the_safe_daily_room_uses_the_days_left_in_the_week():
    assert ab.evaluate(_fig(600, daily=10), 1000)["safe_per_day"] == round(400 / 4, 2)


def test_the_brief_action_names_the_week():
    daily = {"top_actions": []}
    ab.add_action(daily, ab.evaluate(_fig(1200), 1000))
    assert "weekly budget" in daily["top_actions"][0]["action"]


def test_fetch_reads_spend_from_monday():
    seen = []

    def get(path, params):
        if path.endswith("/insights"):
            seen.append(json.loads(params["time_range"]))
            return {"data": [{"spend": "10"}]}, None
        return {"data": []}, None
    out = ab.fetch_figures("act_1", "t", today=WED, get=get, period="week")
    assert seen[0] == {"since": "2026-10-26", "until": "2026-10-28"}
    assert out["period"] == "week"


def test_the_guard_pauses_when_the_weeks_budget_is_used_up_and_says_so():
    fig = dict(_fig(1200), complete=True)
    t = g.trigger(fig, 1000)
    assert t["go"] is True and "week's budget of R1,000" in t["reason"]
    near = g.trigger(dict(_fig(990, daily=240), complete=True), 1000)   # an hour of spend would pass the line
    assert near["go"] is True and "week" in near["reason"]
    ok = g.trigger(dict(_fig(100), complete=True), 1000)
    assert ok["go"] is False and "week" in ok["reason"]
    assert "week" in g.trigger(_fig(1), 0)["reason"].lower() or "weekly" in g.trigger(_fig(1), 0)["reason"].lower()
    assert "week" in g.trigger(dict(_fig(1), complete=False), 1000)["reason"].lower()


def test_the_guard_still_speaks_of_the_month_for_a_monthly_budget():
    fig = dict(ab.build_figures(mtd_spend=2000, today_spend=0, adsets=[], today=WED), complete=True)
    assert "month's budget" in g.trigger(fig, 1000)["reason"]
