"""The weekly report leads with the CMO brief: HTML, markdown, the JSON the Reports page reads, and the facts it is built from."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

from _lib import weekly_report_v3 as wr  # noqa: E402
import test_v2026_10_26_cmo_brief as fx  # noqa: E402

PERIODS = {"current_week_start": "2026-10-19", "current_week_end": "2026-10-25",
           "previous_week_start": "2026-10-12", "previous_week_end": "2026-10-18"}


def _v24():
    def k(label, cur, prev, status="LIVE"):
        return {"label": label, "current": cur, "previous": prev, "data_status": status}
    return {
        "kpi_scorecard": {"rows": [k("Sessions", 607, 926), k("Engagement rate", 50.3, 40.5), k("Conversions", 6, 0),
                                   k("Verified Leads", None, None, "PENDING")]},
        "sections": {"channel_mix": {"rows": [
            {"channel": "Organic Search", "current_sessions": 306, "previous_sessions": 321},
            {"channel": "Paid Social", "current_sessions": 93, "previous_sessions": 381}]}},
        "paid_media_v24": {"data_status": "LIVE", "per_campaign": [
            {"campaign_name": "ss_leads_fitting_may26", "objective": "OUTCOME_LEADS",
             "current": {"spend": 53.0, "impressions": 1000, "reach": 800, "clicks": 20},
             "previous": {"spend": 242.0, "impressions": 4000, "reach": 3000, "clicks": 90},
             "primary_result": {"primary_metric_label": "Meta-reported leads", "primary_value": 1, "primary_cost_per_unit": 52.52}},
            {"campaign_name": "ss_traffic_fitting_sep26", "objective": "OUTCOME_TRAFFIC",
             "current": {"spend": 59.0, "impressions": 3000, "reach": 2500, "clicks": 80},
             "previous": {"spend": 246.0, "impressions": 9000, "reach": 7000, "clicks": 300},
             "primary_result": {"primary_metric_label": "Landing page views", "primary_value": 26, "primary_cost_per_unit": 2.29}}]},
    }


def _extras():
    f = fx.swing_shack()["ads"]
    return {"tracking": {"totals": f["tracking"]["totals"], "ads": f["tracking"]["ads"], "summary": {}},
            "budget": dict(f["budget"], headline="used up", left=-1241.0), "changes": [], "guard_on": True, "paused_now": 4}


class Facts(unittest.TestCase):
    def test_facts_come_from_the_report_data_and_the_ads_extras(self):
        f = wr._cmo_facts("swing-shack", _v24(), PERIODS, _extras(), None)
        self.assertEqual(f["brand"], "Swing Shack")
        self.assertEqual(f["sessions"], {"cur": 607, "prev": 926})
        self.assertEqual(f["enquiries"]["cur"], 6)
        self.assertEqual(f["paid"]["spend"], {"cur": 112.0, "prev": 488.0})
        self.assertEqual(f["paid"]["campaigns"][0]["name"], "ss_leads_fitting_may26")
        self.assertFalse(f["bookings_linked"])
        self.assertEqual(f["ads"]["budget"]["budget"], 1000)
        self.assertTrue(f["ads"]["guard_on"])
        self.assertIn("19 Oct", f["week"]["current"])

    def test_works_without_the_ads_extras(self):
        f = wr._cmo_facts("swing-shack", _v24(), PERIODS, None, None)
        self.assertIsNone(f["ads"])
        self.assertTrue(wr._cmo("swing-shack", _v24(), {}, PERIODS, None)["verdict"]["headline"])


class Rendering(unittest.TestCase):
    def setUp(self):
        self.cmo = __import__("_lib.cmo_brief", fromlist=["build"]).build(fx.swing_shack())

    def test_html_leads_with_where_we_stand_and_the_decisions(self):
        html = wr._render_cmo(self.cmo)
        self.assertIn('id="sec-Executive"', html)
        self.assertIn("Where we stand", html)
        self.assertIn("Decisions for this week", html)
        self.assertIn("Recommendation", html)
        self.assertIn("What is working", html)
        self.assertIn("What is not", html)
        self.assertIn("Next week", html)
        self.assertIn("Herman:", html)

    def test_html_is_escaped(self):
        c = dict(self.cmo, verdict=dict(self.cmo["verdict"], headline="<script>x</script>"))
        html = wr._render_cmo(c)
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_markdown_has_the_same_story(self):
        md = "\n".join(wr._cmo_markdown(self.cmo))
        self.assertIn("## Where we stand", md)
        self.assertIn("### Decisions for this week", md)
        self.assertIn("Herman:", md)

    def test_the_executive_card_is_replaced_not_duplicated(self):
        html = wr._render_html("swing-shack", _v24(), {}, {}, {}, PERIODS)
        self.assertEqual(html.count('id="sec-Executive"'), 1)
        self.assertIn("Where we stand", html)
        self.assertNotIn("What happened this week", html.split("Where we stand")[0])

    def test_the_generic_actions_block_gives_way_to_next_week(self):
        html = wr._render_html("swing-shack", _v24(), {}, {}, {}, PERIODS)
        self.assertNotIn("Maximum three actions", html)

    def test_markdown_report_leads_with_it(self):
        md = wr._render_markdown("swing-shack", _v24(), {}, {}, {}, PERIODS)
        self.assertLess(md.index("## Where we stand"), md.index("## Website traffic"))

    def test_the_cmo_block_is_in_the_json_payload(self):
        import unittest.mock as m
        v24 = _v24()
        v24["__periods"] = PERIODS
        with m.patch.object(wr, "_read_v24", return_value=v24),                 m.patch.object(wr, "_validate_brand_isolation", return_value=(True, [])),                 m.patch.object(wr, "_read_organic_from_cache", return_value={}),                 m.patch.object(wr, "_read_seo_from_cache", return_value={}),                 m.patch.object(wr, "_read_seo_keywords", return_value={}),                 m.patch.object(wr, "_read_ads_extras", return_value=_extras()),                 m.patch.object(wr, "_read_ads_brief", return_value=None):
            out = wr.build_v36("swing-shack", fmt="json")
        cmo = out["raw_payload"]["cmo"]
        self.assertTrue(cmo["verdict"]["headline"])
        self.assertTrue(cmo["decisions"])


if __name__ == "__main__":
    unittest.main()
