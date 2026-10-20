"""Monthly ad budget: the projection and the verdict. Pure; nothing reaches Meta."""
import datetime as dt

from _lib import ads_budget as ab

TODAY = dt.date(2026, 10, 20)  # 11 days left after today in October


def _set(i, daily=None, life=None, remaining=None, end=None, start="2026-09-01T00:00:00+0200", camp=None, status="ACTIVE"):
    return {"id": str(i), "name": f"set{i}", "effective_status": status,
            "daily_budget": None if daily is None else str(int(daily * 100)),
            "lifetime_budget": None if life is None else str(int(life * 100)),
            "budget_remaining": None if remaining is None else str(int(remaining * 100)),
            "start_time": start, "end_time": end, "campaign_id": f"c{i}", "campaign": camp or {"id": f"c{i}"}}


def _fig(sets, mtd=1000.0, today=0.0):
    return ab.build_figures(mtd_spend=mtd, today_spend=today, adsets=sets, today=TODAY)


def test_daily_budgets_run_to_month_end():
    f = _fig([_set(1, daily=37), _set(2, daily=37)], mtd=2000, today=0)
    assert f["daily_run_rate"] == 74.0
    # 11 days after today plus all of today's budgets still to come
    assert f["expected_rest_of_month"] == 74.0 * 11 + 74.0


def test_todays_spend_so_far_is_not_counted_twice():
    f = _fig([_set(1, daily=100)], mtd=500, today=60)
    assert f["expected_rest_of_month"] == 100.0 * 11 + 40.0


def test_an_end_date_stops_the_counting():
    f = _fig([_set(1, daily=100, end="2026-10-25T23:59:00+0200")], today=0)
    assert [r["days_left"] for r in f["sets"]] == [5]
    assert f["expected_rest_of_month"] == 500.0 + 100.0
    gone = _fig([_set(1, daily=100, end="2026-10-01T23:59:00+0200")])
    assert gone["expected_rest_of_month"] == 0.0 and gone["sets"] == []


def test_paused_and_future_sets():
    assert _fig([_set(1, daily=100, status="PAUSED")])["expected_rest_of_month"] == 0.0
    later = _fig([_set(1, daily=100, start="2026-10-28T00:00:00+0200")])
    assert later["sets"][0]["days_left"] == 4 and later["expected_rest_of_month"] == 400.0


def test_campaign_budget_counted_once_for_many_ad_sets():
    camp = {"id": "cX", "name": "CBO", "daily_budget": "20000", "lifetime_budget": "0"}
    sets = [dict(_set(1, camp=camp), campaign_id="cX"), dict(_set(2, camp=camp), campaign_id="cX")]
    f = _fig(sets, today=0)
    assert len(f["sets"]) == 1 and f["sets"][0]["amount"] == 200.0


def test_lifetime_budget_counts_only_what_is_left():
    f = _fig([_set(1, life=1000, remaining=400, end="2026-10-30T23:59:00+0200")], today=0)
    assert f["sets"][0]["kind"] == "lifetime" and f["expected_rest_of_month"] == 400.0


def test_no_budget_set():
    fig = _fig([_set(1, daily=100)], mtd=1000, today=0)
    assert ab.evaluate(fig, None)["status"] == "NO_BUDGET"
    assert ab.evaluate(fig, 0)["status"] == "NO_BUDGET"


def test_projection_over_budget_and_worst_case_and_over():
    fig = _fig([_set(1, daily=100)], mtd=1000, today=0)  # projects 1000 + 1200 = 2200; worst 1000 + 1500 = 2500
    at_risk = ab.evaluate(fig, 2000)
    assert at_risk["status"] == "AT_RISK" and at_risk["projected_total"] == 2200.0
    watch = ab.evaluate(fig, 2300)
    assert watch["status"] == "WATCH" and watch["worst_case_total"] == 2500.0
    ok = ab.evaluate(fig, 2600)
    assert ok["status"] == "OK"
    over = ab.evaluate(_fig([_set(1, daily=100)], mtd=3000), 2500)
    assert over["status"] == "OVER" and over["left"] == -500.0


def test_safe_daily_room():
    fig = _fig([_set(1, daily=100)], mtd=1000, today=0)
    assert ab.evaluate(fig, 2000)["safe_per_day"] == round(1000 / 11, 2)


def test_fetch_reports_a_missing_read_instead_of_a_false_all_clear():
    def get(path, params):
        return None, "boom"
    out = ab.fetch_figures("act_1", "t", today=TODAY, get=get)
    assert out["complete"] is False and out["errors"]
