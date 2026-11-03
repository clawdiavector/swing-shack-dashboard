"""CMO brief: the verdict, the decisions and the direction at the top of the weekly report.

Fixtures are the two live weeks of 19-25 Oct 2026 (Swing Shack and Stick), so the tests check the real situation:
the monthly ad budget used up, the hard stop pausing the ads on 21 Oct, paid visitors who leave quickly, lead ads
that are the only thing producing a measurable result, and no booking data to say what a lead is worth.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import cmo_brief  # noqa: E402


def _row(name, spend, sessions, engaged, keys=0, leads=0, cpl=None, dest="WEBSITE"):
    web = dest == "WEBSITE"
    return {"ad_name": name, "campaign": "c", "destination": dest, "spend": spend,
            "ga_sessions": sessions if web else 0,
            "perf": {"leads": leads, "cost_per_lead": cpl, "cost_per_session": round(spend / sessions, 2) if web and sessions else None,
                     "engaged_pct": engaged if web else None, "key_events": keys if web else None}}


def swing_shack(**over):
    f = {
        "brand": "Swing Shack", "week": {"current": "19 Oct → 25 Oct", "previous": "12 Oct → 18 Oct"},
        "sessions": {"cur": 607, "prev": 926}, "engagement": {"cur": 50.3, "prev": 40.5},
        "enquiries": {"cur": 6, "prev": 0, "since": "21 Oct"},
        "channels": [{"channel": "Organic Search", "cur": 306, "prev": 321}, {"channel": "Paid Social", "cur": 93, "prev": 381},
                     {"channel": "Direct", "cur": 103, "prev": 80}],
        "paid": {"spend": {"cur": 184.0, "prev": 852.0}, "leads": {"cur": 13, "prev": 40},
                 "campaigns": [
                     {"name": "ss_traffic_fitting_sep26", "objective": "OUTCOME_TRAFFIC", "spend": 59.0, "prev_spend": 246.0, "results": 26, "cost": 2.29},
                     {"name": "ss_leads_fitting_may26", "objective": "OUTCOME_LEADS", "spend": 53.0, "prev_spend": 242.0, "results": 1, "cost": 52.52},
                     {"name": "ss_traffic_coaching_sep26", "objective": "OUTCOME_TRAFFIC", "spend": 52.0, "prev_spend": 249.0, "results": 41, "cost": 1.27},
                     {"name": "ss_leads_coaching_may26", "objective": "OUTCOME_LEADS", "spend": 20.0, "prev_spend": 115.0, "results": 12, "cost": 1.69}]},
        "ads": {
            "budget": {"status": "OVER", "budget": 1000, "mtd_spend": 2241.0, "projected_total": 2241.0, "days_left_after_today": 5,
                       "sets": [{"level": "adset", "objective": "OUTCOME_LEADS", "kind": "daily", "amount": 35.0},
                                {"level": "adset", "objective": "OUTCOME_LEADS", "kind": "daily", "amount": 17.0},
                                {"level": "adset", "objective": "OUTCOME_TRAFFIC", "kind": "daily", "amount": 37.0}]},
            "guard_on": True, "paused_now": 4,
            "tracking": {"totals": {"spend": 3289.0, "leads": 38, "cost_per_lead": 31.0, "ga_sessions": 1417, "ga_engaged_pct": 13.6,
                                    "ga_key_events": 0, "cost_per_session": 1.4},
                         "ads": [_row("fitting_video_v1", 1043.0, 587, 9.9), _row("coaching_video_v1", 1035.0, 830, 16.3),
                                 _row("fitting_video_v2", 700.0, 0, None, leads=22, cpl=32.0, dest="LEAD_FORM")]}},
        "bookings_linked": False, "targets": None,
    }
    f.update(over)
    return f


def stick(**over):
    f = swing_shack()
    f.update({
        "brand": "Stick", "sessions": {"cur": 110, "prev": 345}, "engagement": {"cur": 49.1, "prev": 37.7},
        "enquiries": {"cur": 4, "prev": 0, "since": "21 Oct"},
        "paid": {"spend": {"cur": 366.0, "prev": 1100.0}, "leads": {"cur": 4, "prev": 6},
                 "campaigns": [{"name": "stick_leads_fitting_may26", "objective": "OUTCOME_LEADS", "spend": 120.0, "prev_spend": 480.0, "results": 4, "cost": 30.0},
                               {"name": "stick_traffic_coaching_sep26", "objective": "OUTCOME_TRAFFIC", "spend": 0.0, "prev_spend": 93.0, "results": 0, "cost": None}]},
    })
    f["ads"] = dict(f["ads"], budget={"status": "OVER", "budget": 1500, "mtd_spend": 2391.0, "projected_total": 2391.0,
                                      "days_left_after_today": 5,
                                      "sets": [{"level": "adset", "objective": "OUTCOME_LEADS", "kind": "daily", "amount": 30.0},
                                               {"level": "adset", "objective": "OUTCOME_TRAFFIC", "kind": "daily", "amount": 37.0}]},
                    paused_now=2,
                    tracking={"totals": {"spend": 4027.0, "leads": 10, "cost_per_lead": 49.0, "ga_sessions": 909, "ga_engaged_pct": 20.0,
                                         "ga_key_events": 0, "cost_per_session": 3.0},
                              "ads": [_row("coaching_video_v1", 554.0, 374, 11.2), _row("coaching_video_v1", 479.0, 173, 12.7),
                                      _row("fitting_video_v1", 1170.0, 288, 37.8), _row("fitting_video_v1", 489.0, 0, None, leads=10, cpl=49.0, dest="LEAD_FORM")]})
    f.update(over)
    return f


def text(b):
    parts = list(b["verdict"]["lines"]) + [b["verdict"]["headline"]]
    for d in b["decisions"]:
        parts += [d["decision"], d["recommendation"], d["because"]]
    for k in ("working", "not_working", "risks", "gaps", "next_week"):
        parts += [x if isinstance(x, str) else " ".join(map(str, x.values())) for x in b[k]]
    return "\n".join(parts)


class Verdict(unittest.TestCase):
    def test_says_the_budget_is_used_up_and_ads_are_paused_and_explains_the_traffic_dip(self):
        b = cmo_brief.build(swing_shack())
        t = text(b)
        self.assertIn("R1,000", t)
        self.assertIn("used up", t)
        self.assertIn("paused", t)
        # visits fell 34% but the cause is the ads stopping: paid social visits fell 76% as spend fell 78%
        self.assertIn("34%", t)
        self.assertIn("76%", t)
        self.assertEqual(b["verdict"]["tone"], "act")

    def test_one_headline_and_at_most_three_lines(self):
        b = cmo_brief.build(stick())
        self.assertTrue(b["verdict"]["headline"])
        self.assertLessEqual(len(b["verdict"]["lines"]), 3)

    def test_nothing_unfinished_leaks_into_the_text(self):
        for f in (swing_shack(), stick(), swing_shack(ads=None), swing_shack(sessions={"cur": None, "prev": None})):
            t = text(cmo_brief.build(f))
            for bad in ("None", "NaN", "undefined", "{", "}"):
                self.assertNotIn(bad, t, f"{bad!r} in {t[:300]}")


class Numbers(unittest.TestCase):
    def test_six_numbers_with_this_week_and_last_week(self):
        n = {x["label"]: x for x in cmo_brief.build(swing_shack())["numbers"]}
        self.assertEqual(len(n), 6)
        self.assertEqual(n["Website visits"]["value"], "607")
        self.assertIn("926", n["Website visits"]["vs"])
        self.assertEqual(n["Ad spend this week"]["value"], "R184")
        self.assertIn("R852", n["Ad spend this week"]["vs"])
        self.assertEqual(n["Enquiries on the website"]["value"], "6")
        self.assertIn("21 Oct", n["Enquiries on the website"]["note"])
        self.assertIn("R1,000", n["This month's ad budget"]["vs"])

    def test_no_percentage_against_a_zero_or_missing_week(self):
        n = {x["label"]: x for x in cmo_brief.build(swing_shack())["numbers"]}
        self.assertNotIn("%", n["Enquiries on the website"]["vs"])
        n2 = {x["label"]: x for x in cmo_brief.build(swing_shack(sessions={"cur": 607, "prev": None}))["numbers"]}
        self.assertNotIn("%", n2["Website visits"]["vs"])


class Decisions(unittest.TestCase):
    def _by(self, b, word):
        return next((d for d in b["decisions"] if word in d["decision"].lower()), None)

    def test_budget_decision_has_the_rand_and_what_it_buys_if_the_cost_holds(self):
        d = self._by(cmo_brief.build(swing_shack()), "budget")
        self.assertIsNotNone(d)
        # lead ad sets run on R52 a day; 5 days left = R260; at R31 a lead that is about 8 leads
        self.assertIn("R260", d["recommendation"] + d["because"])
        self.assertIn("8 leads", d["recommendation"] + d["because"])
        self.assertIn("worth", d["recommendation"])  # the deciding question is what a lead is worth
        self.assertIn("if the cost per lead holds", d["recommendation"] + d["because"])

    def test_landing_page_decision_names_the_ads_and_the_cost_of_an_engaged_visit(self):
        d = self._by(cmo_brief.build(swing_shack()), "page")
        self.assertIsNotNone(d)
        s = d["recommendation"] + d["because"]
        self.assertIn("9.9%", s)
        self.assertIn("fitting_video_v1", s)
        # R1,043 over 587 visits at 9.9% engaged = about R18 per engaged visit
        self.assertIn("R18", s)

    def test_no_landing_page_decision_when_visitors_stay(self):
        f = swing_shack()
        f["ads"]["tracking"]["ads"] = [_row("good", 500.0, 400, 60.0)]
        f["ads"]["tracking"]["totals"].update(ga_engaged_pct=60.0)
        self.assertIsNone(self._by(cmo_brief.build(f), "page"))

    def test_measurement_decision_when_bookings_are_not_linked(self):
        d = self._by(cmo_brief.build(swing_shack()), "booking")
        self.assertIsNotNone(d)
        self.assertIn("worth", d["because"] + d["recommendation"])

    def test_targets_are_asked_for_when_none_are_set(self):
        b = cmo_brief.build(swing_shack())
        self.assertTrue(any("target" in g.lower() for g in b["gaps"]))

    def test_at_most_four_decisions_each_with_all_parts(self):
        for f in (swing_shack(), stick()):
            ds = cmo_brief.build(f)["decisions"]
            self.assertLessEqual(len(ds), 4)
            for d in ds:
                for k in ("decision", "recommendation", "because", "confidence"):
                    self.assertTrue(d.get(k), k)
                self.assertIn(d["confidence"], ("high", "medium", "low"))


class WorkingAndNot(unittest.TestCase):
    def test_a_result_from_a_tiny_spend_is_not_called_the_best(self):
        # 12 "leads" at R1.69 from R20 of spend is too small to trust; it must not be held up as the winner
        b = cmo_brief.build(swing_shack())
        w = " ".join(b["working"])
        self.assertNotIn("R1.69", w)
        self.assertTrue(any("too small" in r.lower() or "not enough" in r.lower() for r in b["risks"] + b["not_working"] + b["gaps"]))

    def test_google_search_is_named_as_the_steady_base(self):
        w = " ".join(cmo_brief.build(swing_shack())["working"])
        self.assertIn("Google", w)
        self.assertIn("306", w)

    def test_pages_that_lose_visitors_are_in_not_working(self):
        n = " ".join(cmo_brief.build(stick())["not_working"])
        self.assertIn("11.2%", n)

    def test_the_best_page_is_praised(self):
        w = " ".join(cmo_brief.build(stick())["working"])
        self.assertIn("37.8%", w)


class Direction(unittest.TestCase):
    def test_next_week_names_who_does_what(self):
        nw = cmo_brief.build(swing_shack())["next_week"]
        self.assertTrue(nw)
        for x in nw:
            self.assertTrue(x.startswith(("Herman:", "Christelle:", "Kyle:")), x)

    def test_missing_ad_data_still_gives_a_verdict_and_says_what_is_missing(self):
        b = cmo_brief.build(swing_shack(ads=None))
        self.assertTrue(b["verdict"]["headline"])
        self.assertTrue(any("ad" in g.lower() for g in b["gaps"]))

    def test_a_calm_week_is_not_dressed_up_as_a_crisis(self):
        f = swing_shack()
        f["ads"]["budget"].update(status="OK", mtd_spend=400.0, projected_total=900.0)
        f["ads"]["paused_now"] = 0
        f["paid"]["spend"] = {"cur": 800.0, "prev": 850.0}
        f["sessions"] = {"cur": 920, "prev": 926}
        f["channels"][1] = {"channel": "Paid Social", "cur": 370, "prev": 381}
        b = cmo_brief.build(f)
        self.assertNotEqual(b["verdict"]["tone"], "act")
        self.assertNotIn("used up", text(b))


if __name__ == "__main__":
    unittest.main()
