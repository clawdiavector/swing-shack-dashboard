"""Ads history: whole weeks read from Meta, the trend series and the winners.

No network, no token. The weekly rows are made up to exercise the maths; the
ad names are the real ones so the output reads like the page will.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brain as fx  # noqa: E402
from _lib import ads_history  # noqa: E402

TODAY = dt.date(2026, 10, 8)  # a Thursday
LAST_WEEK = "2026-09-28"

BODIES = {
    "ff1": "Get your clubs checked, see the numbers, and find what suits your swing. Get measured.",
    "cat": "Get clear feedback on your swing. Data, ball flight, and a plan you can use.",
    "putter": "Missing the hole by that little bit? Get the specs right to drop more putts.",
    "old": "Driver fitting day.\nBook now.",
}


def _week(n: int) -> str:
    """Monday of the week ``n`` weeks before the last full one."""
    return (dt.date.fromisoformat(LAST_WEEK) - dt.timedelta(weeks=n)).isoformat()


def _wrow(weeks_ago, ad_id, name, campaign, objective, spend, imp, video_views=0, **kw):
    row = fx._row(ad_id, name, "s-" + ad_id, campaign, objective, spend, imp, 1.5, 2.0, 40.0, **kw)
    row["date_start"] = _week(weeks_ago)
    row["date_stop"] = (dt.date.fromisoformat(row["date_start"]) + dt.timedelta(days=6)).isoformat()
    if video_views:
        row["actions"].append({"action_type": "video_view", "value": str(video_views)})
    return row


def weekly_rows():
    rows = []
    for n in range(0, 12):  # FItFacts: 12 weeks, 2 leads a week, R60 a week
        rows.append(_wrow(n, "ff1", "FItFacts", "FitFacts", "OUTCOME_LEADS", 60.0, 1000,
                          video_views=300, link_clicks=15, leads=2))
    for n in range(0, 8):  # Coaching Cat: 8 weeks, 1 lead a week, R65 a week
        rows.append(_wrow(n, "cat", "Coaching Cat 1", "Coaching Cat", "OUTCOME_LEADS", 65.0, 900,
                          video_views=180, link_clicks=10, leads=1))
    for n in range(0, 4):  # Putter traffic: 4 weeks
        rows.append(_wrow(n, "putter", "Putter Traffic Ad", "Putter Traffic", "OUTCOME_TRAFFIC",
                          240.0, 8000, video_views=1600, link_clicks=200, lpv=110))
    for n in range(20, 23):  # an old lead ad that stopped, 3 leads in all
        rows.append(_wrow(n, "old", "Driver day", "Driver fitting", "OUTCOME_LEADS", 100.0, 2000,
                          link_clicks=20, leads=1))
    # Awareness: nothing to count but attention.
    rows.append(_wrow(1, "aware", "New Awareness ad", "Awareness", "OUTCOME_AWARENESS",
                      50.0, 20000, video_views=9000))
    # A lead campaign that spent and got nothing: still costs.
    rows.append(_wrow(14, "dry", "Dry week", "FitFacts", "OUTCOME_LEADS", 40.0, 500))
    return rows


WATCH = [{"ad_id": "ff1", "video_play_actions": [{"action_type": "video_view", "value": "5000"}],
          "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "900"}],
          "video_avg_time_watched_actions": [{"action_type": "video_view", "value": "4"}]},
         {"ad_id": "old"}]
SETTINGS = [fx._setting(i, "ACTIVE", "LEAD_GENERATION", "2026-05-20T09:00:00+0200")
            for i in ("ff1", "cat", "putter", "old")]
for _s in SETTINGS:
    _s["creative"]["body"] = BODIES[_s["id"]]


def fake_get(rows=None, fail=(), archive=None):
    """Graph-shaped answers for the history reads, plus a call log.
    ``fail`` holds chunk starts, 'watch' or 'ads' to refuse."""
    rows = weekly_rows() if rows is None else rows
    calls = []

    def get(path, params):
        calls.append((path, dict(params)))
        if path.endswith("/ads_archive"):
            return archive(params) if archive else (None, "HTTP 400: (#10) no permission")
        if path.endswith("/ads"):
            return (None, "HTTP 400: nope") if "ads" in fail else ({"data": SETTINGS}, None)
        tr = json.loads(params["time_range"])
        if "time_increment" not in params:
            return (None, "HTTP 400: (#100) bad field") if "watch" in fail else ({"data": WATCH}, None)
        if tr["since"] in fail:
            return None, "HTTP 500: try later"
        return {"data": [r for r in rows if "date_start" not in r
                         or tr["since"] <= r["date_start"] <= tr["until"]]}, None

    get.calls = calls
    return get


def history(**kw):
    get = fake_get(**{k: v for k, v in kw.items() if k in ("rows", "fail")})
    return ads_history.fetch_weekly("swing-shack", "act_1", "tok", get=get, today=TODAY,
                                    previous=kw.get("previous")), get


class Weeks(unittest.TestCase):
    def test_only_whole_weeks_monday_to_sunday(self):
        self.assertEqual(ads_history.last_full_week(TODAY).isoformat(), LAST_WEEK)
        # On a Sunday the week is not over; on the Monday after, it is.
        self.assertEqual(ads_history.last_full_week(dt.date(2026, 10, 4)).isoformat(), "2026-09-21")
        self.assertEqual(ads_history.last_full_week(dt.date(2026, 10, 5)).isoformat(), LAST_WEEK)
        starts = ads_history.week_starts(TODAY)
        self.assertEqual((len(starts), starts[0], starts[-1]), (52, "2025-10-06", LAST_WEEK))
        self.assertTrue(all(dt.date.fromisoformat(s).weekday() == 0 for s in starts))


class Fetch(unittest.TestCase):
    def test_reads_a_year_in_four_weekly_chunks(self):
        h, get = history()
        chunks = [json.loads(p["time_range"]) for path, p in get.calls if p.get("time_increment")]
        self.assertEqual([c["since"] for c in chunks],
                         ["2025-10-06", "2026-01-05", "2026-04-06", "2026-07-06"])
        self.assertEqual(chunks[-1]["until"], "2026-10-04")
        self.assertTrue(all(p["time_increment"] == 7 and p["level"] == "ad"
                            for _, p in get.calls if p.get("time_increment")))
        self.assertEqual(h["period"], {"since": "2025-10-06", "until": "2026-10-04", "weeks": 52})
        self.assertEqual(len(h["rows"]), len(weekly_rows()))
        self.assertEqual(h["errors"], [])
        row = next(r for r in h["rows"] if r["ad_id"] == "ff1" and r["week"] == LAST_WEEK)
        self.assertEqual((row["spend"], row["leads"], row["video_views"], row["objective"]),
                         (60.0, 2, 300, "OUTCOME_LEADS"))

    def test_rows_without_a_week_are_dropped(self):
        # What the brief's own fixtures return to a request they do not know.
        h, _ = history(rows=[fx._row("x", "X", "s", "C", "LINK_CLICKS", 5, 100, 1, 1, 1)])
        self.assertEqual(h["rows"], [])

    def test_a_refused_chunk_keeps_the_weeks_it_had(self):
        first, _ = history()
        h, _ = history(fail=("2026-07-06",), previous=first)
        self.assertEqual(len(h["rows"]), len(first["rows"]))
        self.assertEqual(len(h["errors"]), 1)
        self.assertIn("2026-07-06", h["errors"][0])
        # With nothing on file the weeks are simply missing, and say so.
        h, _ = history(fail=("2026-07-06",))
        self.assertFalse([r for r in h["rows"] if r["week"] >= "2026-07-06"])
        self.assertTrue([r for r in h["rows"] if r["week"] < "2026-07-06"])

    def test_watch_time_and_ad_text_fail_on_their_own(self):
        first, _ = history()
        self.assertEqual(first["watch"], {"ff1": {"plays": 5000, "thruplays": 900, "p25": 0,
                                                  "p50": 0, "p75": 0, "p100": 0,
                                                  "avg_seconds": 4.0}})
        self.assertEqual(first["creatives"]["ff1"]["body"], BODIES["ff1"])
        h, _ = history(fail=("watch", "ads"), previous=first)
        self.assertEqual(len(h["rows"]), len(first["rows"]))
        self.assertEqual(h["watch"], first["watch"])
        self.assertEqual(h["creatives"], first["creatives"])
        self.assertEqual(len(h["errors"]), 2)


class Trends(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = ads_history.trends(history()[0])
        cls.by = {w["week"]: w for w in cls.t["weeks"]}

    def test_starts_at_the_first_week_with_delivery_and_keeps_the_gaps(self):
        weeks = self.t["weeks"]
        # The oldest ad started 22 weeks before the last full week.
        self.assertEqual((len(weeks), weeks[0]["week"], weeks[-1]["week"]),
                         (23, _week(22), LAST_WEEK))
        empty = self.by[_week(17)]
        self.assertEqual((empty["spend"], empty["leads"], empty["cost_per_lead"], empty["ads"]),
                         (0, 0, None, 0))
        rows = [r for r in weekly_rows() if r["ad_id"] == "putter"]
        weeks = ads_history.trends(history(rows=rows)[0])["weeks"]
        self.assertEqual((len(weeks), weeks[0]["week"]), (4, _week(3)))

    def test_charts_at_most_26_weeks(self):
        rows = weekly_rows() + [_wrow(40, "ff1", "FItFacts", "FitFacts", "OUTCOME_LEADS", 60.0,
                                      1000, leads=2)]
        weeks = ads_history.trends(history(rows=rows)[0])["weeks"]
        self.assertEqual((len(weeks), weeks[0]["week"], weeks[-1]["week"]),
                         (26, _week(25), LAST_WEEK))

    def test_cost_per_lead_is_lead_campaign_spend_over_leads(self):
        last = self.by[LAST_WEEK]
        # FItFacts R60 + Coaching Cat R65 over 3 leads; the traffic ad's R240 is not in it.
        self.assertEqual((last["spend"], last["leads"], last["lead_spend"], last["cost_per_lead"]),
                         (365.0, 3, 125.0, 41.67))
        self.assertEqual(last["ads"], 3)
        # A lead campaign that spent and got nothing has no cost per lead that week.
        dry = self.by[_week(14)]
        self.assertEqual((dry["lead_spend"], dry["leads"], dry["cost_per_lead"]), (40.0, 0, None))

    def test_last_four_weeks_against_the_four_before(self):
        self.assertEqual(self.t["last_4"]["leads"], 12)
        self.assertEqual(self.t["prior_4"]["leads"], 12)
        self.assertEqual(self.t["last_4"]["landing_page_views"], 440)
        self.assertEqual(self.t["change"]["leads"], 0.0)
        # Page visits only started four weeks ago: nothing to compare with.
        self.assertIsNone(self.t["change"]["landing_page_views"])
        self.assertEqual(self.t["change"]["spend"], round((1510 - 500) / 500, 3))

    def test_no_history_is_empty_not_an_error(self):
        self.assertEqual(ads_history.trends({})["weeks"], [])


class Winners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = history()[0]
        cls.w = ads_history.winners(cls.h)

    def test_lead_ads_ranked_by_cost_proven_first(self):
        leads = self.w["ranked"]["leads"]
        self.assertEqual([a["ad_id"] for a in leads["ads"]], ["ff1", "cat", "old"])
        ff1, cat, old = leads["ads"]
        self.assertEqual((ff1["result"]["count"], ff1["result"]["cost"], ff1["result"]["proven"]),
                         (24, 30.0, True))
        # Eight leads is under the floor, however cheap or dear.
        self.assertEqual((cat["result"]["count"], cat["result"]["proven"]), (8, False))
        self.assertEqual((old["result"]["count"], old["result"]["cost"]), (3, 100.0))
        self.assertEqual((leads["proven"], leads["compared"]), (1, 3))

    def test_ads_are_only_compared_within_what_they_were_bought_for(self):
        self.assertEqual([a["ad_id"] for a in self.w["ranked"]["landing_page_views"]["ads"]],
                         ["putter"])
        self.assertNotIn("messages", self.w["ranked"])
        # Awareness has no result to cost, and a dry lead ad has none to rank.
        self.assertIsNone(self.w["by_ad"]["aware"]["result"])
        self.assertNotIn("dry", [a["ad_id"] for a in self.w["ranked"]["leads"]["ads"]])

    def test_each_ad_says_how_long_it_ran_and_how_it_opened(self):
        ff1, old = self.w["by_ad"]["ff1"], self.w["by_ad"]["old"]
        self.assertEqual((ff1["weeks_active"], ff1["first_week"], ff1["last_week"],
                          ff1["still_running"]), (12, _week(11), LAST_WEEK, True))
        self.assertEqual((old["weeks_active"], old["still_running"]), (3, False))
        self.assertEqual(ff1["opening"],
                         "Get your clubs checked, see the numbers, and find what suits your swing.")
        self.assertEqual(old["opening"], "Driver fitting day.")
        self.assertEqual(ff1["themes"], ["fitting"])
        # "Get the specs right to drop more putts" is about fitting a putter.
        self.assertEqual(self.w["by_ad"]["putter"]["themes"], ["fitting", "putter"])

    def test_attention_is_three_second_views_over_impressions(self):
        ff1 = self.w["by_ad"]["ff1"]
        self.assertEqual(ff1["hook_rate"], 0.3)
        self.assertEqual(ff1["hold_rate"], 0.25)  # 900 watched through of 3,600 who stayed
        self.assertEqual(ff1["watch"]["avg_seconds"], 4.0)
        self.assertIsNone(self.w["by_ad"]["old"]["hook_rate"])
        # Best first, and only ads shown often enough for the rate to mean something.
        self.assertEqual([a["ad_id"] for a in self.w["best_openings"]],
                         ["aware", "ff1", "cat", "putter"])

    def test_leads_by_subject(self):
        by = {t["theme"]: t for t in self.w["lead_themes"]}
        # FItFacts and the old driver day; the dry ad names no subject.
        self.assertEqual((by["fitting"]["ads"], by["fitting"]["leads"]), (2, 27))
        self.assertEqual(by["coaching"]["cost_per_lead"], 65.0)
        self.assertEqual(self.w["lead_themes"][0]["theme"], "fitting")

    def test_proven_for_needs_a_shared_subject_and_enough_results(self):
        self.assertEqual(ads_history.proven_for(self.w, ["fitting", "irons"], "leads")["ad_id"],
                         "ff1")
        self.assertIsNone(ads_history.proven_for(self.w, ["coaching"], "leads"))
        self.assertIsNone(ads_history.proven_for(self.w, ["fitting"], "messages"))
        self.assertIsNone(ads_history.proven_for(None, ["fitting"], "leads"))

    def test_opening_is_the_first_sentence_of_the_first_line(self):
        self.assertEqual(ads_history.opening("One. Two."), "One.")
        self.assertEqual(ads_history.opening("No full stop\nsecond line"), "No full stop")
        self.assertEqual(ads_history.opening("  Why?   Because."), "Why?")
        self.assertIsNone(ads_history.opening(None))
        self.assertIsNone(ads_history.opening("\n\n"))


if __name__ == "__main__":
    unittest.main()
