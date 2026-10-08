"""Ads brain: the rules must reproduce the verdict read by hand on 2026-10-08.

Fixtures are the real 2026-09-07..2026-10-07 numbers for both ad accounts,
shaped the way the Graph API returns them. No network, no token.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import ads_brain  # noqa: E402

NOW = dt.datetime(2026, 10, 8, 12, 0, tzinfo=dt.timezone.utc)
TODAY = dt.date(2026, 10, 8)


def _row(ad_id, name, adset_id, campaign, objective, spend, imp, freq, ctr, cpm,
         link_clicks=0, lpv=0, leads=0, messages=0, **extra):
    actions = []
    for k, v in (("link_click", link_clicks), ("landing_page_view", lpv), ("lead", leads),
                 ("onsite_conversion.messaging_conversation_started_7d", messages)):
        if v:
            actions.append({"action_type": k, "value": str(v)})
    row = {"ad_id": ad_id, "ad_name": name, "adset_id": adset_id, "adset_name": adset_id,
           "campaign_id": "c-" + ad_id, "campaign_name": campaign, "objective": objective,
           "spend": str(spend), "impressions": str(imp), "reach": str(int(imp / max(freq, 1))),
           "frequency": str(freq), "clicks": str(link_clicks), "ctr": str(ctr), "cpm": str(cpm),
           "actions": actions}
    row.update(extra)
    return row


def _setting(ad_id, status, goal, start, link, campaign_stop=None, objective="OUTCOME_TRAFFIC"):
    return {"id": ad_id, "name": ad_id, "effective_status": status,
            "campaign": {"id": "c-" + ad_id, "objective": objective, "stop_time": campaign_stop,
                         "start_time": start},
            "adset": {"id": None, "optimization_goal": goal, "start_time": start},
            "creative": {"id": "cr-" + ad_id, "video_id": "v1", "body": "copy",
                         "call_to_action_type": "BOOK_NOW", "link_url": link}}


STICK = {
    "current": [
        _row("fit", "50+km Paarl", "s-fit", "Fit Fact leads Campaign", "OUTCOME_LEADS",
             405.57, 8225, 1.98, 3.19, 49.3, link_clicks=151, leads=10, messages=17),
        _row("rush", "Rush web traffic Ad", "s-rush", "Rush web traffic", "LINK_CLICKS",
             1548.12, 83962, 1.75, 5.13, 18.4, link_clicks=4077, lpv=534),
        _row("aware", "New Awareness ad", "s-aware", "New Awareness campaign", "OUTCOME_AWARENESS",
             1545.05, 306127, 1.75, 0.22, 5.0),
        _row("coach", "Coaching Web Push ad", "s-coach", "Coaching Web Push", "LINK_CLICKS",
             1116.32, 31671, 2.06, 4.77, 35.2, link_clicks=1276, lpv=610),
        _row("tip", "Tip of the Week ad", "s-tip", "Tip Of The Week - Grip", "LINK_CLICKS",
             309.64, 9265, 1.86, 3.98, 33.4, link_clicks=287, lpv=172),
    ],
    "previous": [
        _row("fit", "50+km Paarl", "s-fit", "Fit Fact leads Campaign", "OUTCOME_LEADS",
             1015.55, 29583, 2.78, 3.17, 34.3, link_clicks=546, leads=35, messages=52),
        _row("rush", "Rush web traffic Ad", "s-rush", "Rush web traffic", "LINK_CLICKS",
             1549.53, 90136, 1.9, 4.93, 17.2, link_clicks=4211, lpv=602),
    ],
    "placements": [
        {"ad_id": "rush", "publisher_platform": "facebook", "platform_position": "feed",
         "spend": "900", "impressions": "60000", "actions": []},
        {"ad_id": "rush", "publisher_platform": "facebook", "platform_position": "facebook_stories",
         "spend": "600", "impressions": "23000", "actions": []},
        {"ad_id": "rush", "publisher_platform": "instagram", "platform_position": "feed",
         "spend": "48", "impressions": "962", "actions": []},
    ],
    "ads": [
        _setting("fit", "ACTIVE", "LEAD_GENERATION", "2026-05-14T09:00:00+0200", None,
                 campaign_stop="2026-09-30T23:59:00+0200", objective="OUTCOME_LEADS"),
        _setting("rush", "ACTIVE", "LINK_CLICKS", "2026-07-30T09:00:00+0200", "https://stickgolf.co.za/"),
        _setting("aware", "ACTIVE", "REACH", "2026-08-06T09:00:00+0200", None,
                 objective="OUTCOME_AWARENESS"),
        _setting("coach", "CAMPAIGN_PAUSED", "LANDING_PAGE_VIEWS", "2026-09-04T09:00:00+0200",
                 "https://stickgolf.co.za/"),
        _setting("tip", "ACTIVE", "LANDING_PAGE_VIEWS", "2026-09-29T09:00:00+0200",
                 "https://stickgolf.co.za/bookings/"),
    ],
}

SWING_SHACK = {
    "current": [
        _row("ff1", "FItFacts", "s-ff", "FitFacts", "OUTCOME_LEADS",
             502.77, 9169, 1.86, 2.7, 54.8, link_clicks=138, leads=18),
        _row("ff2", "FItFacts – 2", "s-ff", "FitFacts", "OUTCOME_LEADS",
             17.85, 344, 1.21, 3.49, 51.9, link_clicks=5),
        _row("cat", "Coaching Cat 1", "s-cat", "Coaching Cat", "OUTCOME_LEADS",
             514.37, 6924, 1.7, 2.25, 74.3, link_clicks=80, leads=14),
        _row("david", "Welcome David Traffic Ad", "s-david", "Welcome David", "LINK_CLICKS",
             975.85, 32477, 1.75, 3.94, 30.0, link_clicks=915, lpv=509),
        _row("putter", "Putter Traffic Ad", "s-putter", "Putter Traffic", "LINK_CLICKS",
             971.59, 31104, 1.87, 3.8, 31.2, link_clicks=809, lpv=446),
    ],
    "previous": [
        _row("ff1", "FItFacts", "s-ff", "FitFacts", "OUTCOME_LEADS",
             526.98, 11282, 1.92, 2.75, 46.7, link_clicks=170, leads=16),
        _row("cat", "Coaching Cat 1", "s-cat", "Coaching Cat", "OUTCOME_LEADS",
             522.55, 8974, 1.78, 2.44, 58.2, link_clicks=117, leads=14),
    ],
    "placements": [],
    "ads": [
        _setting("ff1", "ACTIVE", "LEAD_GENERATION", "2026-05-20T09:00:00+0200", None,
                 objective="OUTCOME_LEADS"),
        _setting("ff2", "ACTIVE", "LEAD_GENERATION", "2026-05-20T09:00:00+0200", None,
                 objective="OUTCOME_LEADS"),
        _setting("cat", "ACTIVE", "LEAD_GENERATION", "2026-05-29T09:00:00+0200", None,
                 objective="OUTCOME_LEADS"),
        _setting("david", "ACTIVE", "LANDING_PAGE_VIEWS", "2026-09-10T09:18:00+0200",
                 "https://swing-shack.com"),
        _setting("putter", "ACTIVE", "LANDING_PAGE_VIEWS", "2026-09-10T09:18:00+0200",
                 "https://swing-shack.com/"),
    ],
}


def _fake_get(account, fail=()):
    """Graph-shaped responses keyed on the request, plus a call log."""
    calls = []

    def get(path, params):
        calls.append((path, dict(params)))
        if path.endswith("/ads"):
            key = "ads"
        elif params.get("breakdowns"):
            key = "placements"
        elif json.loads(params["time_range"])["since"] == "2026-09-07":
            key = "current"
        else:
            key = "previous"
        if key in fail:
            return None, "HTTP 400: (#100) nope"
        return {"data": account[key]}, None

    get.calls = calls
    return get


def _score(account, **kw):
    snap = ads_brain.fetch_snapshot("x", "act_1", "tok", get=_fake_get(account, **kw), today=TODAY)
    return snap, ads_brain.score_snapshot(snap, now=NOW)


def _rules(out, ad=None):
    return sorted(f["rule"] for f in out["findings"] if ad is None or f.get("ad_id") == ad)


class StickVerdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap, cls.out = _score(STICK)

    def test_period_matches_the_paid_media_contract(self):
        self.assertEqual(self.snap["period"]["current"], {"since": "2026-09-07", "until": "2026-10-07"})
        self.assertEqual(self.snap["period"]["previous"], {"since": "2026-08-07", "until": "2026-09-06"})

    def test_summary(self):
        s = self.out["summary"]
        self.assertAlmostEqual(s["spend"], 4924.70, places=2)
        self.assertEqual(s["leads"], 10)
        self.assertAlmostEqual(s["cost_per_lead"], 40.56, places=2)

    def test_stopped_lead_ad_is_the_top_finding(self):
        # Meta still says ACTIVE; the campaign's stop_time passed on 30 Sept.
        self.assertEqual(self.out["findings"][0]["severity"], "high")
        self.assertIn("lead_ads_not_running", _rules(self.out))

    def test_rush_buys_clicks_that_never_land(self):
        f = next(f for f in self.out["findings"] if f["rule"] == "click_goal_leak")
        self.assertEqual(f["ad_id"], "rush")
        self.assertAlmostEqual(f["evidence"]["lpv_rate"], 0.131, places=3)
        self.assertAlmostEqual(f["evidence"]["cost_per_landing_page_view"], 2.90, places=2)
        self.assertIn("landing page views", f["action"])

    def test_rush_other_findings(self):
        self.assertEqual(_rules(self.out, "rush"),
                         ["click_goal_leak", "home_page_destination", "instagram_absent",
                          "open_ended_non_lead", "single_ad_no_test"])

    def test_landing_page_view_ads_are_not_leaks(self):
        self.assertNotIn("click_goal_leak", _rules(self.out, "coach"))
        self.assertNotIn("click_goal_leak", _rules(self.out, "tip"))

    def test_paused_and_new_ads_are_left_alone(self):
        self.assertEqual(_rules(self.out, "coach"), [])
        # Nine days old, lands on the bookings page.
        self.assertEqual(_rules(self.out, "tip"), ["single_ad_no_test"])

    def test_account_findings(self):
        mix = next(f for f in self.out["findings"] if f["rule"] == "spend_mix")
        self.assertEqual(mix["severity"], "high")
        self.assertAlmostEqual(mix["evidence"]["lead_spend_share"], 0.082, places=3)
        self.assertIn("all_video", _rules(self.out))
        self.assertNotIn("best_lead_ad", _rules(self.out))


class SwingShackVerdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap, cls.out = _score(SWING_SHACK)

    def test_summary(self):
        s = self.out["summary"]
        self.assertEqual(s["leads"], 32)
        self.assertAlmostEqual(s["cost_per_lead"], 31.79, places=2)
        self.assertEqual(s["ads_running"], 5)

    def test_lead_ads_are_running(self):
        self.assertNotIn("lead_ads_not_running", _rules(self.out))

    def test_fitfacts_is_the_ad_to_scale(self):
        f = next(f for f in self.out["findings"] if f["rule"] == "best_lead_ad")
        self.assertEqual(f["ad_id"], "ff1")
        self.assertAlmostEqual(f["evidence"]["cost_per_lead"], 27.93, places=2)

    def test_coaching_cat_costs_more_to_show(self):
        self.assertEqual(_rules(self.out, "cat"), ["cpm_rising", "single_ad_no_test"])

    def test_traffic_ads(self):
        for ad in ("david", "putter"):
            self.assertEqual(_rules(self.out, ad),
                             ["home_page_destination", "open_ended_non_lead", "single_ad_no_test"])

    def test_spend_mix_is_medium(self):
        mix = next(f for f in self.out["findings"] if f["rule"] == "spend_mix")
        self.assertEqual(mix["severity"], "medium")

    def test_token_variant_ad_is_not_flagged(self):
        self.assertEqual(_rules(self.out, "ff2"), [])


class Degradation(unittest.TestCase):
    def test_rankings_rejected_falls_back_to_plain_insights(self):
        get = _fake_get(STICK)
        real = get

        def flaky(path, params):
            if "quality_ranking" in params.get("fields", ""):
                real.calls.append((path, dict(params)))
                return None, "HTTP 400: (#100) quality_ranking"
            return real(path, params)

        snap = ads_brain.fetch_snapshot("x", "act_1", "tok", get=flaky, today=TODAY)
        self.assertEqual(len(snap["ads"]), 5)
        self.assertEqual(len(snap["errors"]), 1)

    def test_missing_settings_skips_status_rules(self):
        snap, out = _score(STICK, fail=("ads",))
        self.assertIn("ad settings", snap["errors"][0])
        rules = _rules(out)
        # Cannot know what is running, so no claim that lead ads stopped.
        self.assertNotIn("lead_ads_not_running", rules)
        self.assertNotIn("open_ended_non_lead", rules)
        # The leak is visible from insights alone.
        self.assertIn("click_goal_leak", rules)
        self.assertIsNone(out["summary"]["ads_running"])

    def test_previous_only_ad_is_kept(self):
        acct = dict(STICK, current=[r for r in STICK["current"] if r["ad_id"] != "fit"])
        snap, out = _score(acct)
        fit = next(a for a in snap["ads"] if a["ad_id"] == "fit")
        self.assertEqual(fit["current"]["spend"], 0)
        self.assertEqual(fit["previous"]["leads"], 35)
        self.assertIn("lead_ads_not_running", _rules(out))

    def test_below_average_ranking(self):
        acct = dict(SWING_SHACK, current=[dict(r, quality_ranking="BELOW_AVERAGE_35")
                                          if r["ad_id"] == "putter" else r
                                          for r in SWING_SHACK["current"]])
        _, out = _score(acct)
        self.assertIn("below_average_ranking", _rules(out, "putter"))

    def test_fatigue(self):
        acct = dict(SWING_SHACK, current=[dict(r, frequency="4.2", ctr="1.9")
                                          if r["ad_id"] == "cat" else r
                                          for r in SWING_SHACK["current"]])
        _, out = _score(acct)
        self.assertIn("fatigue", _rules(out, "cat"))

    def test_same_snapshot_same_findings(self):
        snap, out = _score(STICK)
        self.assertEqual(out["findings"], ads_brain.score_snapshot(snap, now=NOW)["findings"])

    def test_token_never_reaches_the_snapshot(self):
        snap, out = _score(STICK)
        self.assertNotIn("tok", json.dumps(snap) + json.dumps(out, default=str))


class Cache(unittest.TestCase):
    def test_is_stale(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            self.assertTrue(ads_brain.is_stale(p, 12, now=NOW))
            p.write_text(json.dumps({"fetched_at": "2026-09-22T11:38:55Z"}))
            self.assertTrue(ads_brain.is_stale(p, 12, now=NOW))
            p.write_text(json.dumps({"fetched_at": "2026-10-08T06:55:33Z"}))
            self.assertFalse(ads_brain.is_stale(p, 12, now=NOW))
            p.write_text("not json")
            self.assertTrue(ads_brain.is_stale(p, 12, now=NOW))

    def test_build_writes_under_data_dir_only_when_there_is_data(self):
        with tempfile.TemporaryDirectory() as d:
            out = ads_brain.build("stick", "act_1", "tok", data_dir=d, get=_fake_get(STICK))
            self.assertTrue((Path(d) / "ads-brain" / "stick__31d.json").exists())
            self.assertEqual(len(out["ads"]), 5)
        with tempfile.TemporaryDirectory() as d:
            ads_brain.build("stick", "act_1", "tok", data_dir=d,
                            get=_fake_get(STICK, fail=("current", "previous", "placements", "ads")))
            self.assertFalse((Path(d) / "ads-brain").exists())


if __name__ == "__main__":
    unittest.main()
