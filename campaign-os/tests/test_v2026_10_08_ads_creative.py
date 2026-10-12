"""Ads creative loop: which tests get proposed, and how a launched test is judged."""
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
import test_v2026_10_08_ads_brief as bfx  # noqa: E402
from _lib import ads_brief, ads_creative  # noqa: E402

DAY = dt.date(2026, 10, 8)
BODIES = {
    "ff1": "Get your clubs checked, see the numbers, and find what suits your swing. Get measured.",
    "cat": "Get clear feedback on your swing. Data, ball flight, and a plan you can use.",
    "david": "Let's welcome Dawid to the team! He will be available for coaching.",
    "putter": "Missing the hole by that little bit? Get the specs right to drop more putts.",
}
ORGANIC = [
    {"post_id": "o1", "caption_preview": "Iron fitting day: see your numbers on TrackMan",
     "permalink": "https://instagram.com/p/o1", "format_type": "image", "score": 80, "reach": 2400},
    {"post_id": "o2", "caption_preview": "Coaching with Cat: one lesson, one fix",
     "permalink": "https://instagram.com/p/o2", "format_type": "reel", "score": 60, "reach": 1800},
    {"post_id": "o3", "caption_preview": "Putter fitting changes everything",
     "permalink": "https://instagram.com/p/o3", "format_type": "image", "score": 90, "reach": 3100},
    # Already running as an ad: same opening as the FitFacts ad.
    {"post_id": "o4", "caption_preview": BODIES["ff1"],
     "permalink": "https://instagram.com/p/o4", "format_type": "image", "score": 99, "reach": 9000},
    {"post_id": "o5", "caption_preview": "New arrivals in store this week",
     "permalink": "https://instagram.com/p/o5", "format_type": "image", "score": 95, "reach": 5000},
]


def _account():
    ads = [dict(s, creative=dict(s["creative"], body=BODIES.get(s["id"], "copy")))
           for s in fx.SWING_SHACK["ads"]]
    return dict(fx.SWING_SHACK, ads=ads)


def _plan(tests=None, organic=ORGANIC, account=None):
    snap, scored = fx._score(account or _account())
    return ads_creative.plan("swing-shack", scored, snap, organic, tests or [], DAY), snap


class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards, cls.snap = _plan()
        cls.by = {c["control"]["ad_id"]: c for c in cls.cards}

    def test_lead_campaigns_first_and_at_most_three(self):
        self.assertEqual([c["control"]["ad_id"] for c in self.cards], ["cat", "ff1", "david"])
        self.assertTrue(all(c["status"] == "PROPOSED" for c in self.cards))

    def test_metric_follows_the_ad_set_goal(self):
        self.assertEqual(self.by["ff1"]["metric"], {"key": "leads", "label": "lead"})
        self.assertEqual(self.by["david"]["metric"]["key"], "landing_page_views")
        self.assertEqual(self.by["ff1"]["control"]["results"], 18)
        self.assertAlmostEqual(self.by["ff1"]["control"]["cost_per_result"], 27.93, places=2)

    def test_every_challenger_is_a_video(self):
        kinds = {x["kind"] for card in self.cards for x in card["challengers"]}
        self.assertEqual(kinds, {"ORGANIC_REEL", "NEW_VIDEO"})
        self.assertTrue(all(x["format"] == "video"
                            for card in self.cards for x in card["challengers"]))

    def test_organic_challenger_is_a_reel_on_theme_not_already_running(self):
        c = self.by["cat"]["challengers"][0]
        self.assertEqual((c["kind"], c["post_id"], c["ready"]), ("ORGANIC_REEL", "o2", True))
        picked = [x.get("post_id") for card in self.cards for x in card["challengers"]]
        # o1 and o3 are on theme but are images; o4 is already an ad; o5 is off theme.
        for post in ("o1", "o3", "o4", "o5"):
            self.assertNotIn(post, picked)

    def test_one_reel_is_not_offered_to_two_tests(self):
        # David is also a coaching ad; o2 went to Coaching Cat.
        self.assertEqual([x["kind"] for x in self.by["david"]["challengers"]], ["NEW_VIDEO"])

    def test_new_video_brief_is_always_there_and_never_ready(self):
        for card in self.cards:
            brief = card["challengers"][-1]
            self.assertEqual((brief["kind"], brief["ready"]), ("NEW_VIDEO", False))
            self.assertIn("first three seconds", brief["why"])
            self.assertTrue(brief["keep"] and brief["change"])

    def test_rule_is_fixed_up_front_and_warns_on_a_small_budget(self):
        d = self.by["ff1"]["design"]
        self.assertEqual((d["min_days"], d["max_days"], d["min_results_per_arm"]), (14, 42, 10))
        self.assertEqual(d["estimated_days"], 35)   # 18 leads in 31 days, 10 per arm
        self.assertFalse(d["budget_warning"])
        self.assertIn("A/B test", d["how"])
        cat = self.by["cat"]["design"]
        self.assertEqual(cat["estimated_days"], 45)  # 14 leads in 31 days
        self.assertTrue(cat["budget_warning"])

    def test_known_ads_are_recorded_for_detecting_the_challenger(self):
        self.assertEqual(self.by["ff1"]["known_ad_ids"], ["ff1"])

    def test_no_second_card_while_one_is_open(self):
        again, _ = _plan(tests=self.cards)
        self.assertEqual([c["control"]["ad_id"] for c in again], [])

    def test_awareness_ads_get_no_test(self):
        snap, scored = fx._score(fx.STICK)
        cards = ads_creative.plan("stick", scored, snap, ORGANIC, [], DAY)
        self.assertNotIn("aware", [c["control"]["ad_id"] for c in cards])

    def test_no_static_or_generated_creative_is_ever_named(self):
        blob = json.dumps(self.cards).lower()
        for word in ("static", "template", "render", "krea", "image", "still"):
            self.assertNotIn(word, blob)

    def test_retail_campaign_may_also_get_an_animated_still(self):
        acct = _account()
        acct = dict(acct, ads=[dict(s, creative=dict(
            s["creative"], body="The Bunny has landed. Psycho Bunny pants, available at Swing Shack."))
            if s["id"] == "david" else s for s in acct["ads"]])
        cards, _ = _plan(account=acct, organic=[])
        by = {c["control"]["ad_id"]: [x["kind"] for x in c["challengers"]] for c in cards}
        self.assertEqual(by["david"], ["NEW_VIDEO", "ANIMATED_STILL"])
        # Service campaigns never get one.
        self.assertEqual(by["cat"], ["NEW_VIDEO"])
        self.assertEqual(by["ff1"], ["NEW_VIDEO"])
        still = next(x for c in cards for x in c["challengers"] if x["kind"] == "ANIMATED_STILL")
        self.assertEqual((still["ready"], still["todo"]), (False, "needs animating"))
        self.assertIn("bags", ads_creative.RETAIL_THEMES)


def _test(**over):
    t = {"id": "c-ff1:2026-10-08", "brand_id": "swing-shack", "status": "PROPOSED",
         "proposed_on": "2026-10-08", "campaign_id": "c-ff1", "campaign_name": "FitFacts",
         "control": {"ad_id": "ff1", "ad_name": "FItFacts", "format": "video"},
         "metric": {"key": "leads", "label": "lead"}, "challengers": [],
         "known_ad_ids": ["ff1"],
         "design": {"min_results_per_arm": 10, "min_days": 14, "max_days": 42, "win_margin": 0.15,
                    "rule": "r", "how": "h", "estimated_days": 35, "budget_warning": False}}
    t.update(over)
    return t


def _snap(*ads):
    return {"ads": [{"ad_id": i, "campaign": {"id": c}, "current": m} for i, c, m in ads]}


def _m(spend, leads):
    return {"spend": spend, "leads": leads}


class Track(unittest.TestCase):
    def test_new_ad_in_the_campaign_starts_the_test(self):
        snap = _snap(("ff1", "c-ff1", _m(100, 4)), ("ff3", "c-ff1", _m(20, 1)),
                     ("other", "c-x", _m(50, 0)))
        [t] = ads_creative.track([_test()], snap, None, DAY + dt.timedelta(days=3))
        self.assertEqual((t["status"], t["challenger_ad_ids"], t["launched_on"]),
                         ("RUNNING", ["ff3"], "2026-10-11"))

    def test_unlaunched_proposal_expires_after_30_days(self):
        snap = _snap(("ff1", "c-ff1", _m(100, 4)))
        [t] = ads_creative.track([_test()], snap, None, DAY + dt.timedelta(days=30))
        self.assertEqual(t["status"], "PROPOSED")
        [t] = ads_creative.track([_test()], snap, None, DAY + dt.timedelta(days=31))
        self.assertEqual(t["status"], "EXPIRED")

    def _run(self, days, control, challenger):
        running = _test(status="RUNNING", launched_on="2026-10-11", challenger_ad_ids=["ff3"])
        asked = []

        def window(d):
            asked.append(d)
            return _snap(("ff1", "c-ff1", control), ("ff3", "c-ff1", challenger))

        [t] = ads_creative.track([running], _snap(), window,
                                 dt.date(2026, 10, 11) + dt.timedelta(days=days))
        self.assertEqual(asked, [days])  # numbers are read from the launch date only
        return t

    def test_no_decision_before_14_days_whatever_the_numbers(self):
        t = self._run(13, _m(400, 10), _m(100, 10))
        self.assertEqual(t["status"], "RUNNING")
        self.assertEqual(t["progress"]["days"], 13)

    def test_challenger_wins_when_15_percent_cheaper(self):
        t = self._run(14, _m(300, 10), _m(250, 10))   # R30 vs R25: 17% cheaper
        self.assertEqual((t["status"], t["result"]), ("DECIDED", "CHALLENGER_WON"))
        self.assertEqual(t["progress"]["challenger"]["cost_per_result"], 25.0)

    def test_control_wins_when_challenger_is_15_percent_dearer(self):
        self.assertEqual(self._run(20, _m(300, 10), _m(360, 10))["result"], "CONTROL_WON")

    def test_close_results_wait_then_close_without_a_winner(self):
        self.assertEqual(self._run(20, _m(300, 10), _m(310, 10))["status"], "RUNNING")
        self.assertEqual(self._run(42, _m(300, 10), _m(310, 10))["result"], "NO_CLEAR_WINNER")

    def test_too_few_results_is_inconclusive_not_a_win(self):
        self.assertEqual(self._run(30, _m(300, 10), _m(40, 2))["status"], "RUNNING")
        self.assertEqual(self._run(42, _m(300, 10), _m(40, 2))["result"], "INCONCLUSIVE_LOW_VOLUME")

    def test_control_switched_off(self):
        self.assertEqual(self._run(14, _m(0, 0), _m(250, 10))["result"],
                         "INCONCLUSIVE_CONTROL_STOPPED")

    def test_static_proposals_from_before_the_video_rule_are_withdrawn(self):
        old = _test(challengers=[{"kind": "TEMPLATE_STATIC", "archetype": "ss-fitting-headline"}])
        snap = _snap(("ff1", "c-ff1", _m(100, 4)))
        [t] = ads_creative.track([old], snap, None, DAY)
        self.assertEqual(t["status"], "WITHDRAWN")
        self.assertIn("real human video", t["reason"])
        # Withdrawn cards neither block a new proposal nor show on the brief.
        s = ads_creative.summarise([t], DAY)
        self.assertEqual((s["proposed"], s["running"], s["closed_recently"]), ([], [], []))

    def test_summary_counts_the_record(self):
        done = _test(status="DECIDED", result="CHALLENGER_WON", closed_on="2026-10-30")
        old = _test(status="DECIDED", result="CONTROL_WON", closed_on="2026-08-01")
        s = ads_creative.summarise([done, old, _test()], dt.date(2026, 11, 1))
        self.assertEqual((len(s["proposed"]), len(s["running"]), len(s["closed_recently"])), (1, 0, 1))
        self.assertEqual((s["record"]["CHALLENGER_WON"], s["record"]["CONTROL_WON"]), (1, 1))


class InTheJob(bfx._JobCase):
    def setUp(self):
        super().setUp()
        self.lane = Path(self.tmp.name) / "brands" / "swing-shack" / "ads-brief"
        lane = Path(self.tmp.name) / "brands" / "swing-shack"
        lane.mkdir(parents=True)
        (lane / "post-outcomes.json").write_text(json.dumps({"outcomes": ORGANIC}), encoding="utf-8")

    def run_ss(self, account):
        return self.job.run(brand="swing-shack", today=DAY, get=fx._fake_get(account),
                            get_as=fx._fake_get_as(account))

    def test_proposes_once_and_shows_on_the_page(self):
        out = self.run_ss(_account())
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["creative_tests"], {"proposed": 3, "running": 0})
        self.assertEqual(out["organic"], {"posts_on_file": 5, "reels": 1, "reels_with_a_theme": 1,
                                          "reels_with_reach": 1, "with_a_link": 5})
        brief = self.read("latest.json")
        self.assertEqual(len(brief["creative"]["proposed"]), 3)
        tests_path = self.lane.parent / "ads-creative" / "tests.json"
        self.assertEqual(len(json.loads(tests_path.read_text(encoding="utf-8"))), 3)
        # A static card left by the earlier version is withdrawn and replaced in one run.
        stored = json.loads(tests_path.read_text(encoding="utf-8"))
        stored[0]["challengers"] = [{"kind": "TEMPLATE_STATIC", "archetype": "x"}]
        tests_path.write_text(json.dumps(stored), encoding="utf-8")
        self.run_ss(_account())
        after = json.loads(tests_path.read_text(encoding="utf-8"))
        self.assertEqual([t["status"] for t in after].count("WITHDRAWN"), 1)
        self.assertEqual([t["status"] for t in after].count("PROPOSED"), 3)
        tests_path.write_text(json.dumps([t for t in after if t["status"] == "PROPOSED"]),
                              encoding="utf-8")
        # Second run: nothing new is proposed while those are open.
        self.run_ss(_account())
        self.assertEqual(len(json.loads(tests_path.read_text(encoding="utf-8"))), 3)

        page = ads_brief.render_html([brief], "daily")
        self.assertIn("Creative to test", page)
        self.assertIn("Coaching with Cat: one lesson, one fix", page)
        self.assertIn('href="https://instagram.com/p/o2"', page)
        self.assertIn("Film a new real-person video", page)
        self.assertIn("needs filming", page)
        creative_html = page[page.index("Creative to test"):page.index("New since the last brief")]
        self.assertNotIn("emplate", creative_html)
        self.assertNotIn("static", creative_html.lower())
        self.assertIn("longer than the six-week limit", page)

    def test_page_says_why_no_organic_post_is_offered(self):
        (self.lane.parent / "post-outcomes.json").write_text(json.dumps({"outcomes": [
            {"post_id": "x", "caption_preview": "New arrivals in store", "permalink": "https://i/p/x",
             "format_type": "image", "score": 9, "reach": 10}]}), encoding="utf-8")
        self.run_ss(_account())
        page = ads_brief.render_html([self.read("latest.json")], "daily")
        self.assertIn("of 1 recent organic posts, 0 are reels and none matches", page)

    def test_brief_without_creative_still_renders(self):
        self.run_ss(_account())
        brief = self.read("latest.json")
        brief.pop("creative")
        self.assertNotIn("Creative to test", ads_brief.render_html([brief], "daily"))


if __name__ == "__main__":
    unittest.main()
