"""Ads brief: the daily job, what counts as new / resolved, and the page.

Runs the real job against a temp DATA_DIR with Graph-shaped fixtures borrowed
from the Scoring V1 tests. No network, no token.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brain as fx  # noqa: E402
from _lib import ads_brief  # noqa: E402

DAY = dt.date(2026, 10, 8)  # the scoring fixtures' "today"
RECENT = {
    "stick": {
        "current": [
            fx._row("rush", "Rush web traffic Ad", "s-rush", "Rush web traffic", "LINK_CLICKS",
                    350.0, 19000, 1.4, 5.0, 18.4, link_clicks=900, lpv=120),
            fx._row("aware", "New Awareness ad", "s-aware", "New Awareness campaign",
                    "OUTCOME_AWARENESS", 349.0, 70000, 1.3, 0.2, 5.0),
        ],
        "previous": [
            fx._row("rush", "Rush web traffic Ad", "s-rush", "Rush web traffic", "LINK_CLICKS",
                    350.0, 19500, 1.4, 5.0, 18.0, link_clicks=950, lpv=125),
            fx._row("fit", "50+km Paarl", "s-fit", "Fit Fact leads Campaign", "OUTCOME_LEADS",
                    126.0, 2500, 1.5, 3.2, 50.0, link_clicks=40, leads=3),
        ],
    },
}


def _get(account, recent):
    """31-day requests get the scoring fixtures; 7-day requests get ``recent``."""
    full = fx._fake_get(account)

    def get(path, params):
        tr = json.loads(params["time_range"]) if "time_range" in params else None
        if tr:
            since, until = (dt.date.fromisoformat(tr[k]) for k in ("since", "until"))
            if (until - since).days == 6:
                key = "current" if until == DAY - dt.timedelta(days=1) else "previous"
                return {"data": recent[key]}, None
        return full(path, params)
    return get


class _JobCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self.tmp.name
        from _lib.jobs.layer7 import ads_brief as job
        self.job = job
        self.lane = Path(self.tmp.name) / "brands" / "stick" / "ads-brief"

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._old
        self.tmp.cleanup()

    def run_job(self, account, today, recent=None):
        return self.job.run(brand="stick", today=today,
                            get=_get(account, recent or RECENT["stick"]),
                            get_as=fx._fake_get_as(account))

    def read(self, name):
        return json.loads((self.lane / name).read_text(encoding="utf-8"))


class FirstRun(_JobCase):
    def test_writes_a_baseline_brief_into_the_brand_lane(self):
        out = self.run_job(fx.STICK, DAY)
        self.assertTrue(out["ok"], out)
        brief = self.read("latest.json")
        self.assertEqual((brief["kind"], brief["date"], brief["scoring_version"]),
                         ("daily", "2026-10-08", "v1.1"))
        self.assertTrue(brief["baseline"])
        # First run: nothing is "new", everything is the starting point.
        self.assertEqual(brief["new"], [])
        self.assertEqual(brief["headline"]["open"], len(brief["open"]))
        self.assertTrue(all(f["days_open"] == 0 for f in brief["open"]))
        self.assertTrue((self.lane / "daily" / "2026-10-08.json").exists())
        self.assertTrue(out["wrote_weekly"])  # none existed yet

    def test_scores_31_days_and_reports_7(self):
        self.run_job(fx.STICK, DAY)
        brief = self.read("latest.json")
        self.assertEqual(brief["scoring_window"], {"since": "2026-09-07", "until": "2026-10-07"})
        n = brief["numbers_7d"]
        self.assertEqual(n["window"], {"since": "2026-10-01", "until": "2026-10-07"})
        self.assertEqual(n["previous_window"], {"since": "2026-09-24", "until": "2026-09-30"})
        self.assertAlmostEqual(n["current"]["spend"], 699.0)
        self.assertEqual((n["current"]["leads"], n["previous"]["leads"]), (0, 3))
        self.assertIsNone(n["current"]["cost_per_lead"])
        self.assertAlmostEqual(n["previous"]["cost_per_lead"], 42.0)
        self.assertEqual(n["change"]["leads"], -1.0)
        self.assertEqual([r["ad_id"] for r in n["ads"]], ["rush", "aware"])

    def test_top_actions_follow_the_priority_order(self):
        self.run_job(fx.STICK, DAY)
        top = self.read("latest.json")["top_actions"]
        self.assertEqual([a["rule"] for a in top],
                         ["lead_ads_not_running", "click_goal_leak", "home_page_destination"])
        # spend_mix says the same thing as the first action when no lead ad runs.
        self.assertNotIn("spend_mix", [a["rule"] for a in top])


class NextDay(_JobCase):
    def test_tracks_new_resolved_and_age(self):
        self.run_job(fx.STICK, DAY)
        # Overnight: Rush's ad set goal is fixed (clicks now land) and it gets an end date.
        fixed = fx._edit(fx.STICK, "rush", actions=[
            {"action_type": "link_click", "value": "4077"},
            {"action_type": "landing_page_view", "value": "2300"}])
        fixed = dict(fixed, ads=[dict(s, adset=dict(s["adset"], end_time="2026-10-31T23:59:00+0200"))
                                 if s["id"] == "rush" else s for s in fixed["ads"]])
        # The fixtures' windows are anchored on the 8th, so re-run the same day
        # with yesterday's state back-dated.
        state = self.read("state.json")
        for v in state["findings"].values():
            v["first_seen"] = "2026-10-05"
        (self.lane / "state.json").write_text(json.dumps(state), encoding="utf-8")

        out = self.run_job(fixed, DAY)
        brief = self.read("latest.json")
        self.assertFalse(brief["baseline"])
        resolved = sorted(f["rule"] for f in brief["resolved"])
        self.assertEqual(resolved, ["click_goal_leak", "open_ended_non_lead"])
        self.assertTrue(all(f["days_open"] == 3 for f in brief["resolved"]))
        self.assertEqual(brief["new"], [])
        self.assertEqual(out["headline"]["resolved"], 2)
        still = next(f for f in brief["open"] if f["rule"] == "lead_ads_not_running")
        self.assertEqual((still["first_seen"], still["days_open"]), ("2026-10-05", 3))
        events = self.read("events.json")
        self.assertEqual(sorted(e["event"] for e in events), ["resolved", "resolved"])

    def test_a_retired_rule_is_not_reported_as_resolved(self):
        self.run_job(fx.STICK, DAY)
        state = self.read("state.json")
        state["findings"]["all_video||account"] = {
            "rule": "all_video", "status": None, "severity": "low", "ad_name": None,
            "what": "All 6 ads are videos.", "action": "Run a static.", "first_seen": "2026-10-08"}
        (self.lane / "state.json").write_text(json.dumps(state), encoding="utf-8")
        self.run_job(fx.STICK, DAY)
        brief = self.read("latest.json")
        self.assertEqual(brief["resolved"], [])
        self.assertNotIn("all_video||account", self.read("state.json")["findings"])
        self.assertEqual(self.read("events.json"), [])

    def test_a_new_finding_is_listed_once(self):
        self.run_job(fx.STICK, DAY)
        worse = fx._edit(fx.STICK, "aware", quality_ranking="BELOW_AVERAGE_10")
        self.run_job(worse, DAY)
        brief = self.read("latest.json")
        self.assertEqual([f["rule"] for f in brief["new"]], ["below_average_ranking"])
        self.run_job(worse, DAY)
        self.assertEqual(self.read("latest.json")["new"], [])

    def test_failed_read_keeps_the_last_brief(self):
        self.run_job(fx.STICK, DAY)
        before = (self.lane / "latest.json").read_text(encoding="utf-8")
        out = self.job.run(brand="stick", today=DAY,
                           get=fx._fake_get(fx.STICK, fail=("current", "previous", "placements", "ads")),
                           get_as=fx._fake_get_as(fx.STICK))
        self.assertFalse(out["ok"])
        self.assertEqual((self.lane / "latest.json").read_text(encoding="utf-8"), before)
        self.assertEqual(len(self.read("state.json")["findings"]),
                         len(json.loads(before)["open"]))


class Weekly(_JobCase):
    def test_written_on_mondays_and_lists_the_weeks_events(self):
        self.run_job(fx.STICK, DAY)
        events = [{"date": "2026-10-06", "event": "opened", "key": "k1", "rule": "fatigue",
                   "status": None, "severity": "high", "ad_name": "Rush", "what": "seen 4 times"},
                  {"date": "2026-09-20", "event": "resolved", "key": "k0", "rule": "cpm_rising",
                   "status": None, "severity": "low", "ad_name": "Old", "what": "old", "days_open": 9}]
        daily = self.read("latest.json")
        weekly = ads_brief.build_weekly(daily, events, DAY)
        self.assertEqual(weekly["kind"], "weekly")
        self.assertEqual([e["key"] for e in weekly["opened_this_week"]], ["k1"])
        self.assertEqual(weekly["resolved_this_week"], [])
        self.assertNotIn("new", weekly)
        self.assertEqual(weekly["week"], {"since": "2026-10-01", "until": "2026-10-07"})

    def test_not_rewritten_midweek(self):
        self.assertNotEqual(DAY.weekday(), 0)
        self.run_job(fx.STICK, DAY)
        out = self.run_job(fx.STICK, DAY)
        self.assertFalse(out["wrote_weekly"])

    def test_open_over_7_days_only_lists_things_to_act_on(self):
        self.run_job(fx.STICK, DAY)
        daily = self.read("latest.json")
        for f in daily["open"]:
            f["days_open"] = 9
        weekly = ads_brief.build_weekly(daily, [], DAY)
        self.assertTrue(weekly["open_over_7_days"])
        self.assertTrue(all(f["severity"] in ("high", "medium") for f in weekly["open_over_7_days"]))


class SwingShackActions(unittest.TestCase):
    def test_same_action_on_two_ads_is_one_line(self):
        from _lib import ads_brain
        snap, scored = fx._score(fx.SWING_SHACK)
        recent = ads_brain.fetch_snapshot("swing-shack", "act_1", "tok", insights_only=True,
                                          get=fx._fake_get(fx.SWING_SHACK), today=fx.TODAY, days=7)
        brief, _, _ = ads_brief.build_daily("swing-shack", scored, recent, None, DAY)
        top = brief["top_actions"]
        self.assertEqual([a["rule"] for a in top],
                         ["spend_mix", "below_average_ranking", "home_page_destination"])
        self.assertEqual(top[1]["ads"], ["Welcome David Traffic Ad", "Putter Traffic Ad"])
        self.assertEqual(top[0]["ads"], [])


class Page(_JobCase):
    def test_renders_both_brands_and_escapes(self):
        self.run_job(fx.STICK, DAY)
        brief = self.read("latest.json")
        brief["top_actions"][0]["action"] = "<script>alert(1)</script>"
        page = ads_brief.render_html([brief], "daily", missing=["swing-shack"])
        self.assertIn("Daily ads brief", page)
        self.assertIn("<h2>Stick</h2>", page)
        self.assertIn("first brief", page)
        self.assertIn("Swing Shack", page)
        self.assertIn("No brief yet", page)
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("nothing here changes an ad", page)
        self.assertIn('<a href="/daily">', page)

    def test_unchanged_number_does_not_read_as_minus_zero(self):
        self.assertIn("no change", ads_brief._delta(-0.001))
        self.assertIn("no change", ads_brief._delta(-0.005))  # prod showed "-0%" for this
        self.assertIn("no change", ads_brief._delta(0.0))
        self.assertIn("-16%", ads_brief._delta(-0.16))
        self.assertIn('class="good"', ads_brief._delta(-0.08, lower_is_better=True))
        self.assertIn('class="good"', ads_brief._delta(0.6))
        self.assertIn('class=""', ads_brief._delta(-0.16))
        self.assertIn('class=""', ads_brief._delta(0.47, neutral=True))

    def test_weekly_page(self):
        self.run_job(fx.STICK, DAY)
        page = ads_brief.render_html([self.read("weekly-latest.json")], "weekly")
        self.assertIn("Weekly ads brief", page)
        self.assertIn("Opened this week", page)
        self.assertIn('href="/ads-brief?kind=weekly" class="on"', page)

    def test_sast_day_rolls_over_at_22_utc(self):
        self.assertEqual(ads_brief.sast_today(dt.datetime(2026, 10, 7, 21, 59, tzinfo=dt.timezone.utc)),
                         dt.date(2026, 10, 7))
        self.assertEqual(ads_brief.sast_today(dt.datetime(2026, 10, 7, 22, 1, tzinfo=dt.timezone.utc)),
                         dt.date(2026, 10, 8))


if __name__ == "__main__":
    unittest.main()
