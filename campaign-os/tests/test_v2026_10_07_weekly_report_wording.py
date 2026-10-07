"""Weekly report v3 wording bugs found reading the 2026-10-07 reports.

- "indoor golf" (#2 -> #3) was listed under Biggest gains and Biggest drops.
- A rise in GA4 "Unassigned" traffic was listed under What worked.
- The Meta leads tile showed "from lead campaigns" where the week-on-week
  change goes.

Run: cd campaign-os && python3 -m pytest tests/test_v2026_10_07_weekly_report_wording.py -v
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from _lib import weekly_report_v3 as wr3  # noqa: E402


def _kw(keyword, prev, cur):
    return {"keyword": keyword, "previous_position": prev,
            "current_position": cur,
            "delta": (prev - cur) if prev else None}


def _channel(name, prev, cur):
    return {"channel": name, "previous_sessions": prev, "current_sessions": cur,
            "comparison_status": "improving", "share_of_sessions": 20.0}


class RankGainsTests(unittest.TestCase):

    def test_slipped_keyword_is_not_a_gain(self):
        seo_kw = {"winning": [_kw("indoor golf", 2, 3), _kw("golf fitting", 9, 4)]}
        self.assertEqual([k["keyword"] for k in wr3._rank_gains(seo_kw)],
                         ["golf fitting"])

    def test_unchanged_and_new_keywords_are_not_gains(self):
        seo_kw = {"winning": [_kw("holding", 5, 5), _kw("new", None, 7)]}
        self.assertEqual(wr3._rank_gains(seo_kw), [])

    def test_biggest_move_first(self):
        seo_kw = {"winning": [_kw("small", 4, 3), _kw("big", 10, 2)]}
        self.assertEqual([k["keyword"] for k in wr3._rank_gains(seo_kw)],
                         ["big", "small"])

    def test_empty_input(self):
        self.assertEqual(wr3._rank_gains(None), [])
        self.assertEqual(wr3._rank_gains({}), [])


class WorkedSectionTests(unittest.TestCase):

    def _html(self, rows):
        v24 = {"sections": {"channel_mix": {"rows": rows}}}
        return wr3._render_worked_attention(v24, "#000000")

    def test_unassigned_rise_is_not_listed_as_worked(self):
        html = self._html([_channel("Unassigned", 40, 90)])
        self.assertNotIn("Unassigned brought more visitors", html)

    def test_real_channel_rise_is_still_listed(self):
        html = self._html([_channel("Organic Search", 40, 90)])
        self.assertIn("Organic Search brought more visitors", html)


class LeadCardTests(unittest.TestCase):

    def test_caption_is_not_rendered_in_the_change_slot(self):
        card = {"label": "Meta leads", "value": "12", "change_pct": None,
                "change_text": None, "trend": "neutral",
                "secondary": "from lead campaigns · bookings not yet linked"}
        html = wr3._render_kpi_cards([card], "#000000")
        change_slot = html.split('class="kpi-change')[1].split("</div>")[0]
        self.assertNotIn("from lead campaigns", change_slot)
        self.assertIn("from lead campaigns", html)


if __name__ == "__main__":
    unittest.main()
