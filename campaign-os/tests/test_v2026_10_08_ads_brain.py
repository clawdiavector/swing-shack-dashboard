"""Ads brain, Scoring V1.

Fixtures are the real 2026-09-07..2026-10-07 numbers for both ad accounts,
shaped the way the Graph API returned them on prod: boosted-post ads carry no
link on the creative, so the destination comes from the underlying post.
No network, no token.
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


def _setting(ad_id, status, goal, start, campaign_stop=None, objective="OUTCOME_TRAFFIC",
             link=None, story=None, media="video"):
    creative = {"id": "cr-" + ad_id, "body": "copy", "call_to_action_type": "BOOK_TRAVEL",
                "link_url": link, "effective_object_story_id": story}
    creative["video_id" if media == "video" else "image_url"] = "x"
    return {"id": ad_id, "name": ad_id, "effective_status": status,
            "campaign": {"id": "c-" + ad_id, "objective": objective, "stop_time": campaign_stop,
                         "start_time": start},
            "adset": {"id": None, "optimization_goal": goal, "start_time": start},
            "creative": creative}


def _post(link):
    return {"call_to_action": {"type": "BOOK_TRAVEL", "value": {"link": link}}, "id": "p"}


_RANK_OK = {"quality_ranking": "AVERAGE", "engagement_rate_ranking": "ABOVE_AVERAGE",
            "conversion_rate_ranking": "ABOVE_AVERAGE"}
_RANK_POST_CLICK = {"quality_ranking": "AVERAGE", "engagement_rate_ranking": "ABOVE_AVERAGE",
                    "conversion_rate_ranking": "BELOW_AVERAGE_35"}

STICK = {
    "current": [
        _row("fit", "50+km Paarl", "s-fit", "Fit Fact leads Campaign", "OUTCOME_LEADS",
             405.57, 8225, 1.98, 3.19, 49.3, link_clicks=151, leads=10, messages=17),
        _row("rush", "Rush web traffic Ad", "s-rush", "Rush web traffic", "LINK_CLICKS",
             1548.12, 83962, 1.75, 5.13, 18.4, link_clicks=4077, lpv=534, **_RANK_OK),
        _row("aware", "New Awareness ad", "s-aware", "New Awareness campaign", "OUTCOME_AWARENESS",
             1545.05, 306127, 1.75, 0.22, 5.0),
        _row("coach", "Coaching Web Push ad", "s-coach", "Coaching Web Push", "LINK_CLICKS",
             1116.32, 31671, 2.06, 4.77, 35.2, link_clicks=1276, lpv=610),
        _row("tip", "Tip of the Week ad", "s-tip", "Tip Of The Week - Grip", "LINK_CLICKS",
             309.64, 9265, 1.86, 3.98, 33.4, link_clicks=287, lpv=172,
             quality_ranking="AVERAGE", engagement_rate_ranking="ABOVE_AVERAGE",
             conversion_rate_ranking="BELOW_AVERAGE_20"),
        _row("ball", "New Engagement ad", "s-ball", "Ball Fitting Engagement", "OUTCOME_ENGAGEMENT",
             95.69, 3570, 1.47, 1.48, 26.8, link_clicks=28, messages=2),
    ],
    "previous": [
        _row("fit", "50+km Paarl", "s-fit", "Fit Fact leads Campaign", "OUTCOME_LEADS",
             1015.55, 29583, 2.78, 3.17, 34.3, link_clicks=546, leads=35, messages=52),
        _row("rush", "Rush web traffic Ad", "s-rush", "Rush web traffic", "LINK_CLICKS",
             1549.53, 90136, 1.9, 4.93, 17.2, link_clicks=4211, lpv=602),
        _row("free", "Free Assessments Ad", "s-free", "Free Assessments", "LINK_CLICKS",
             399.9, 42872, 1.58, 1.68, 9.3, link_clicks=542, lpv=124),
    ],
    "placements": [
        {"ad_id": "rush", "publisher_platform": "facebook", "platform_position": "feed",
         "spend": "900", "impressions": "60000", "actions": []},
        {"ad_id": "rush", "publisher_platform": "facebook", "platform_position": "facebook_stories",
         "spend": "600", "impressions": "23800", "actions": []},
        {"ad_id": "rush", "publisher_platform": "instagram", "platform_position": "feed",
         "spend": "48", "impressions": "162", "actions": []},
    ],
    "ads": [
        _setting("fit", "ACTIVE", "LEAD_GENERATION", "2026-05-14T09:00:00+0200",
                 campaign_stop="2026-09-30T23:59:00+0200", objective="OUTCOME_LEADS",
                 link="http://fb.me/"),
        _setting("rush", "ACTIVE", "LINK_CLICKS", "2026-07-30T09:00:00+0200", story="post-rush"),
        _setting("aware", "ACTIVE", "REACH", "2026-08-06T09:00:00+0200",
                 objective="OUTCOME_AWARENESS", story="post-aware"),
        _setting("coach", "CAMPAIGN_PAUSED", "LANDING_PAGE_VIEWS", "2026-09-04T09:00:00+0200",
                 story="post-coach"),
        _setting("tip", "ACTIVE", "LANDING_PAGE_VIEWS", "2026-09-29T09:00:00+0200", story="post-tip"),
        _setting("ball", "CAMPAIGN_PAUSED", "CONVERSATIONS", "2026-09-07T09:00:00+0200",
                 objective="OUTCOME_ENGAGEMENT"),
        _setting("free", "ACTIVE", "LINK_CLICKS", "2026-07-16T09:00:00+0200",
                 campaign_stop="2026-08-31T23:59:00+0200", link="https://stickgolf.co.za/",
                 media="image"),
    ],
    "posts": {
        "post-rush": _post("https://stickgolf.co.za/"),
        "post-coach": _post("https://stickgolf.co.za/"),
        "post-tip": _post("https://stickgolf.co.za/bookings/"),
        "post-aware": {"id": "p"},
    },
}

SWING_SHACK = {
    "current": [
        _row("ff1", "FItFacts", "s-ff", "FitFacts", "OUTCOME_LEADS",
             502.77, 9169, 1.86, 2.7, 54.8, link_clicks=138, leads=18, messages=2, **_RANK_OK),
        _row("ff2", "FItFacts – 2", "s-ff", "FitFacts", "OUTCOME_LEADS",
             17.85, 344, 1.21, 3.49, 51.9, link_clicks=5),
        _row("cat", "Coaching Cat 1", "s-cat", "Coaching Cat", "OUTCOME_LEADS",
             514.37, 6924, 1.7, 2.25, 74.3, link_clicks=80, leads=14),
        _row("cat2", "Coaching Cat 2", "s-cat", "Coaching Cat", "OUTCOME_LEADS",
             10.31, 185, 1.23, 1.08, 55.7, link_clicks=1),
        _row("david", "Welcome David Traffic Ad", "s-david", "Welcome David", "LINK_CLICKS",
             975.85, 32477, 1.75, 3.94, 30.0, link_clicks=915, lpv=509, **_RANK_POST_CLICK),
        _row("putter", "Putter Traffic Ad", "s-putter", "Putter Traffic", "LINK_CLICKS",
             971.59, 31104, 1.87, 3.8, 31.2, link_clicks=809, lpv=446, **_RANK_POST_CLICK),
    ],
    "previous": [
        _row("ff1", "FItFacts", "s-ff", "FitFacts", "OUTCOME_LEADS",
             519.45, 11282, 1.92, 2.75, 46.0, link_clicks=170, leads=16),
        _row("cat", "Coaching Cat 1", "s-cat", "Coaching Cat", "OUTCOME_LEADS",
             515.0, 8781, 1.78, 2.44, 58.65, link_clicks=117, leads=13),
    ],
    "placements": [],
    "ads": [
        _setting("ff1", "ACTIVE", "LEAD_GENERATION", "2026-05-20T09:00:00+0200",
                 objective="OUTCOME_LEADS", link="http://fb.me/"),
        _setting("ff2", "ACTIVE", "LEAD_GENERATION", "2026-05-20T09:00:00+0200",
                 objective="OUTCOME_LEADS", link="http://fb.me/"),
        _setting("cat", "ACTIVE", "QUALITY_LEAD", "2026-05-29T09:00:00+0200",
                 objective="OUTCOME_LEADS", link="http://fb.me/"),
        _setting("cat2", "ACTIVE", "QUALITY_LEAD", "2026-05-29T09:00:00+0200",
                 objective="OUTCOME_LEADS", link="http://fb.me/"),
        _setting("david", "ACTIVE", "LANDING_PAGE_VIEWS", "2026-09-10T09:18:00+0200",
                 story="post-david"),
        _setting("putter", "ACTIVE", "LANDING_PAGE_VIEWS", "2026-09-10T09:18:00+0200",
                 story="post-putter"),
    ],
    # post-david is absent: the lookup fails, as it does without page access.
    "posts": {"post-putter": _post("https://swing-shack.com")},
}


def _fake_get(account, fail=()):
    """Graph-shaped responses keyed on the request, plus a call log."""
    calls = []

    def get(path, params):
        calls.append((path, dict(params)))
        if path.endswith("/ads"):
            key = "ads"
        elif not path.endswith("/insights"):
            post = (account.get("posts") or {}).get(path.rsplit("/", 1)[-1])
            return (post, None) if post else (None, "HTTP 400: (#10) no page access")
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


def _one(out, rule, ad=None):
    hits = [f for f in out["findings"] if f["rule"] == rule and (ad is None or f.get("ad_id") == ad)]
    assert len(hits) == 1, (rule, ad, len(hits))
    return hits[0]


def _edit(account, ad_id, **changes):
    return dict(account, current=[dict(r, **changes) if r["ad_id"] == ad_id else r
                                  for r in account["current"]])


class StickVerdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap, cls.out = _score(STICK)

    def test_period_matches_the_paid_media_report(self):
        self.assertEqual(self.snap["period"]["current"], {"since": "2026-09-07", "until": "2026-10-07"})
        self.assertEqual(self.snap["period"]["previous"], {"since": "2026-08-07", "until": "2026-09-06"})

    def test_summary(self):
        s = self.out["summary"]
        self.assertAlmostEqual(s["spend"], 5020.39, places=2)
        self.assertEqual(s["leads"], 10)
        self.assertEqual(s["ads_running"], 3)
        self.assertEqual(self.out["scoring_version"], "v1")

    def test_stopped_lead_ad_quotes_the_last_full_window(self):
        # Meta still says ACTIVE; the campaign's stop_time passed on 30 Sept.
        f = self.out["findings"][0]
        self.assertEqual((f["rule"], f["severity"]), ("lead_ads_not_running", "high"))
        self.assertEqual(f["evidence"]["reference_window_leads"], 35)
        self.assertAlmostEqual(f["evidence"]["reference_window_cost_per_lead"], 29.02, places=2)
        self.assertEqual(f["evidence"]["reference_window"]["until"], "2026-09-06")
        self.assertIn("35 leads", f["what"])

    def test_rush_buys_clicks_that_never_land(self):
        f = _one(self.out, "click_goal_leak")
        self.assertEqual(f["ad_id"], "rush")
        self.assertAlmostEqual(f["evidence"]["lpv_rate"], 0.131, places=3)
        self.assertIn("landing page views", f["action"])

    def test_boosted_post_destination_comes_from_the_post(self):
        rush = next(a for a in self.snap["ads"] if a["ad_id"] == "rush")
        self.assertEqual(rush["destination"]["status"], "RESOLVED")
        self.assertEqual(rush["destination"]["source"], "post.call_to_action")
        self.assertEqual(_one(self.out, "home_page_destination", "rush")["status"], "HOME_PAGE")

    def test_bookings_page_is_not_flagged(self):
        self.assertEqual(_rules(self.out, "tip"), ["single_ad_no_test"])

    def test_young_ad_ranking_is_gated_on_volume(self):
        # Bottom-20% conversion ranking on 9,265 impressions: too thin to act on.
        self.assertNotIn("below_average_ranking", _rules(self.out, "tip"))

    def test_rush_findings(self):
        self.assertEqual(_rules(self.out, "rush"),
                         ["click_goal_leak", "home_page_destination", "instagram_absent",
                          "open_ended_non_lead", "single_ad_no_test"])
        self.assertIn("0.2%", _one(self.out, "instagram_absent")["what"])

    def test_awareness_is_asked_for_a_review_date_not_judged_on_leads(self):
        f = _one(self.out, "open_ended_non_lead", "aware")
        self.assertEqual((f["severity"], f["status"]), ("info", "AWARENESS_REVIEW_DATE"))
        self.assertNotIn("lead", f["what"].lower())
        self.assertEqual(_one(self.out, "open_ended_non_lead", "rush")["status"], "DECISION_DATE")
        # Not a traffic ad, so its missing destination is not a finding.
        self.assertNotIn("home_page_destination", _rules(self.out, "aware"))

    def test_paused_ads_are_left_alone(self):
        self.assertEqual(_rules(self.out, "coach"), [])
        self.assertEqual(_rules(self.out, "ball"), [])

    def test_one_creative_ad_sets(self):
        sets = [f for f in self.out["findings"] if f["rule"] == "single_ad_no_test"]
        self.assertEqual(sorted(f["ad_id"] for f in sets), ["aware", "rush", "tip"])
        self.assertTrue(all(f["status"] == "ONE_CREATIVE_ONLY" and f["level"] == "adset" for f in sets))

    def test_spend_mix_defers_to_restarting_lead_ads(self):
        f = _one(self.out, "spend_mix")
        self.assertEqual((f["severity"], f["status"]), ("high", "NO_LEAD_AD_RUNNING"))
        self.assertIn("Restart or launch", f["action"])
        # R405.57 lead ad + R95.69 conversations ad that produced chats.
        self.assertAlmostEqual(f["evidence"]["acquisition_spend"], 501.26, places=2)
        self.assertAlmostEqual(f["evidence"]["lead_spend"], 405.57, places=2)

    def test_all_video_is_scoped_to_the_window(self):
        f = _one(self.out, "all_video")
        self.assertIn("31-day window", f["what"])
        self.assertIn("Free Assessments Ad", f["what"])
        self.assertTrue(f["evidence"]["static_in_previous_window"])

    def test_rules_not_fired_are_listed(self):
        self.assertEqual(self.out["rules_not_fired"],
                         ["fatigue", "cost_per_lead_rising", "cpm_rising",
                          "below_average_ranking", "best_lead_ad"])


class SwingShackVerdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap, cls.out = _score(SWING_SHACK)

    def test_summary(self):
        s = self.out["summary"]
        self.assertEqual(s["leads"], 32)
        self.assertAlmostEqual(s["cost_per_lead"], 31.79, places=2)
        self.assertEqual(s["ads_running"], 6)
        self.assertEqual(s["unknown_destinations"], 1)

    def test_lead_ads_are_running(self):
        self.assertNotIn("lead_ads_not_running", _rules(self.out))

    def test_fitfacts_is_the_ad_to_scale(self):
        f = _one(self.out, "best_lead_ad")
        self.assertEqual(f["ad_id"], "ff1")
        self.assertAlmostEqual(f["evidence"]["cost_per_lead"], 27.93, places=2)

    def test_cpm_up_while_cost_per_lead_improves_is_quiet(self):
        # CPM R58.65 -> R74.30, cost per lead R39.62 -> R36.74.
        self.assertEqual(_rules(self.out, "cat"), ["single_ad_no_test"])

    def test_second_creative_without_delivery_gets_its_own_action(self):
        for top, other in (("ff1", "FItFacts – 2"), ("cat", "Coaching Cat 2")):
            f = _one(self.out, "single_ad_no_test", top)
            self.assertEqual(f["status"], "MULTIPLE_CREATIVES_DELIVERY_CONCENTRATED")
            self.assertIn(other, f["action"])
            self.assertNotIn("Add a second", f["action"])
        self.assertEqual(_rules(self.out, "ff2"), [])
        self.assertEqual(_rules(self.out, "cat2"), [])

    def test_unreadable_destination_is_unknown_not_a_pass(self):
        f = _one(self.out, "home_page_destination", "david")
        self.assertEqual(f["status"], "UNKNOWN")
        self.assertIn("post lookup failed", f["evidence"]["reason"])
        self.assertTrue(any("post lookup" in e for e in self.snap["errors"]))
        self.assertEqual(_one(self.out, "home_page_destination", "putter")["status"], "HOME_PAGE")

    def test_poor_conversion_with_healthy_ad_points_past_the_creative(self):
        for ad in ("david", "putter"):
            f = _one(self.out, "below_average_ranking", ad)
            self.assertEqual(f["status"], "POST_CLICK")
            self.assertIn("landing page", f["action"])
            self.assertNotIn("eplace", f["action"])

    def test_traffic_ads(self):
        for ad in ("david", "putter"):
            self.assertEqual(_rules(self.out, ad),
                             ["below_average_ranking", "home_page_destination",
                              "open_ended_non_lead", "single_ad_no_test"])

    def test_spend_mix_is_one_medium_finding(self):
        f = _one(self.out, "spend_mix")
        self.assertEqual((f["severity"], f["status"]), ("medium", "REALLOCATE"))
        # The lead ad's two chats are not added to its leads.
        self.assertAlmostEqual(f["evidence"]["acquisition_spend"], 1017.14, places=2)


class RuleBehaviour(unittest.TestCase):
    def test_ranking_diagnoses(self):
        cases = {
            "CREATIVE_QUALITY": dict(quality_ranking="BELOW_AVERAGE_10"),
            "HOOK_OR_AUDIENCE": dict(engagement_rate_ranking="BELOW_AVERAGE_20",
                                     conversion_rate_ranking="AVERAGE"),
            "ENGAGEMENT_AND_CONVERSION": dict(engagement_rate_ranking="BELOW_AVERAGE_20"),
        }
        for status, change in cases.items():
            _, out = _score(_edit(SWING_SHACK, "putter", **change))
            self.assertEqual(_one(out, "below_average_ranking", "putter")["status"], status)

    def test_cpm_rising_needs_a_supporting_signal(self):
        base = dict(SWING_SHACK, previous=SWING_SHACK["previous"] + [
            _row("putter", "Putter Traffic Ad", "s-putter", "Putter Traffic", "LINK_CLICKS",
                 700.0, 30000, 1.8, 3.8, 23.3, link_clicks=800, lpv=440)])
        _, out = _score(base)  # CPM +34%, CTR flat, no leads
        self.assertNotIn("cpm_rising", _rules(out, "putter"))
        _, out = _score(_edit(base, "putter", ctr="3.0"))  # CTR down 21%
        f = _one(out, "cpm_rising", "putter")
        self.assertIn("click-through down", f["what"])

    def test_leak_on_a_landing_page_goal_points_at_the_page(self):
        _, out = _score(_edit(SWING_SHACK, "putter", actions=[
            {"action_type": "link_click", "value": "809"},
            {"action_type": "landing_page_view", "value": "290"}]))  # 36%
        f = _one(out, "click_goal_leak", "putter")
        self.assertIn("pixel", f["action"])

    def test_leak_ignores_low_volume_and_non_traffic(self):
        _, out = _score(SWING_SHACK)
        self.assertNotIn("click_goal_leak", _rules(out))  # lead ads have clicks, no page views

    def test_fatigue_needs_frequency_and_decay(self):
        _, out = _score(_edit(SWING_SHACK, "cat", frequency="4.2"))
        self.assertNotIn("fatigue", _rules(out, "cat"))
        _, out = _score(_edit(SWING_SHACK, "cat", frequency="4.2", ctr="1.9"))
        self.assertIn("fatigue", _rules(out, "cat"))

    def test_cost_per_lead_rising(self):
        acct = dict(SWING_SHACK, previous=[
            _row("ff1", "FItFacts", "s-ff", "FitFacts", "OUTCOME_LEADS",
                 400.0, 11282, 1.92, 2.75, 46.0, link_clicks=170, leads=20)])
        _, out = _score(acct)  # R20.00 -> R27.93
        self.assertIn("cost_per_lead_rising", _rules(out, "ff1"))

    def test_same_snapshot_same_findings(self):
        snap, out = _score(STICK)
        self.assertEqual(out["findings"], ads_brain.score_snapshot(snap, now=NOW)["findings"])


class Degradation(unittest.TestCase):
    def test_rankings_rejected_falls_back_to_plain_insights(self):
        real = _fake_get(STICK)

        def flaky(path, params):
            if "quality_ranking" in params.get("fields", ""):
                return None, "HTTP 400: (#100) quality_ranking"
            return real(path, params)

        snap = ads_brain.fetch_snapshot("x", "act_1", "tok", get=flaky, today=TODAY)
        self.assertEqual(len([a for a in snap["ads"] if a["current"]["spend"] > 0]), 6)
        self.assertEqual(len(snap["errors"]), 1)

    def test_missing_settings_skips_status_rules(self):
        snap, out = _score(STICK, fail=("ads",))
        self.assertTrue(any("ad settings" in e for e in snap["errors"]))
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

    def test_lead_and_messaging_ads_have_no_web_destination(self):
        snap, _ = _score(STICK)
        dest = {a["ad_id"]: a["destination"]["status"] for a in snap["ads"]}
        self.assertEqual(dest["fit"], "LEAD_FORM")
        self.assertEqual(dest["ball"], "MESSAGING")
        self.assertEqual(dest["aware"], "UNKNOWN")

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
            self.assertEqual(len(out["ads"]), 7)
        with tempfile.TemporaryDirectory() as d:
            ads_brain.build("stick", "act_1", "tok", data_dir=d,
                            get=_fake_get(STICK, fail=("current", "previous", "placements", "ads")))
            self.assertFalse((Path(d) / "ads-brain").exists())


if __name__ == "__main__":
    unittest.main()
