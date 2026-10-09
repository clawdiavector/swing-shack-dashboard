"""The Ad Library read, the charts, and the Trends and What works pages."""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brief as bfx  # noqa: E402
import test_v2026_10_09_ads_history as hfx  # noqa: E402
from _lib import ads_brief, ads_charts, ads_history, ads_library  # noqa: E402

TODAY = dt.date(2026, 10, 9)
TOKEN = "secret-token"


def _lib_ad(i, page, started, body="Opening line. More."):
    return {"id": str(i), "page_id": "p-" + page, "page_name": page,
            "ad_delivery_start_time": started, "ad_creative_bodies": [body] if body else [],
            "ad_creative_link_titles": ["Book a fitting"], "publisher_platforms": ["facebook"]}


def _archive(params):
    if params["search_terms"] != "golf club fitting":
        return {"data": []}, None
    return {"data": [
        _lib_ad(1, "Fitters UK", "2026-09-01"),
        _lib_ad(2, "Old Hand Golf", "2025-01-10", "Still guessing your shaft flex?\nBook in."),
        _lib_ad(3, "Old Hand Golf", "2025-06-01"),
        _lib_ad(4, "No Words Ltd", "2024-01-01", body=None),
        _lib_ad(5, "Mid Golf", "2026-03-01"),
    ]}, None


def _fetch(archive=_archive, themes=("fitting", "coaching", "nonsense")):
    get = hfx.fake_get(archive=archive)
    return ads_library.fetch(themes, TOKEN, get=get, today=TODAY), get


class Library(unittest.TestCase):
    def test_longest_running_first_one_per_advertiser(self):
        out, get = _fetch()
        self.assertEqual(out["status"], "OK")
        self.assertEqual([t["theme"] for t in out["themes"]], ["coaching", "fitting"])
        fitting = out["themes"][1]
        self.assertEqual([a["page_name"] for a in fitting["ads"]],
                         ["Old Hand Golf", "Mid Golf", "Fitters UK"])
        first = fitting["ads"][0]
        self.assertEqual((first["days_running"], first["opening"], first["started"]),
                         (637, "Still guessing your shaft flex?", "2025-01-10"))
        self.assertEqual(fitting["seen"], 5)
        asked = next(p for path, p in get.calls if p.get("search_terms") == "golf club fitting")
        self.assertEqual((asked["media_type"], asked["ad_active_status"], asked["ad_type"]),
                         ("VIDEO", "ACTIVE", "ALL"))
        self.assertEqual(json.loads(asked["ad_reached_countries"]), ["GB", "IE"])

    def test_the_token_never_reaches_the_output(self):
        out, get = _fetch()
        # The API's own snapshot link carries the access token, so it is never asked for.
        self.assertTrue(all("ad_snapshot_url" not in p.get("fields", "") for _, p in get.calls))
        self.assertNotIn(TOKEN, json.dumps(out))
        self.assertEqual(out["themes"][1]["ads"][0]["link"],
                         "https://www.facebook.com/ads/library/?id=2")

    def test_every_subject_links_to_the_south_african_library(self):
        out, _ = _fetch()
        link = out["themes"][1]["home_link"]
        self.assertTrue(link.startswith("https://www.facebook.com/ads/library/?"))
        for part in ("country=ZA", "media_type=video", "q=golf+club+fitting",
                     "active_status=active"):
            self.assertIn(part, link)

    def test_a_refusal_stops_asking_and_still_gives_the_links(self):
        out, get = _fetch(archive=None)
        self.assertEqual(out["status"], "NO_ACCESS")
        self.assertEqual(len([1 for path, _ in get.calls if path.endswith("/ads_archive")]), 1)
        self.assertEqual(len(out["themes"]), 2)
        self.assertTrue(all(t["home_link"] and not t["ads"] for t in out["themes"]))

    def test_nothing_found_is_empty_and_a_failure_is_an_error(self):
        self.assertEqual(_fetch(archive=lambda p: ({"data": []}, None))[0]["status"], "EMPTY")
        self.assertEqual(_fetch(archive=lambda p: (None, "HTTP 500: later"))[0]["status"], "ERROR")

    def test_reread_weekly_or_when_a_new_subject_appears(self):
        out, _ = _fetch()
        self.assertTrue(ads_library.is_stale(None, TODAY, ["fitting"]))
        self.assertFalse(ads_library.is_stale(out, TODAY + dt.timedelta(days=6), ["fitting"]))
        self.assertTrue(ads_library.is_stale(out, TODAY + dt.timedelta(days=7), ["fitting"]))
        self.assertTrue(ads_library.is_stale(out, TODAY, ["fitting", "putter"]))


class Charts(unittest.TestCase):
    POINTS = [("2026-08-31", 0), ("2026-09-07", 120.0), ("2026-09-14", None),
              ("2026-09-21", 80.0), ("2026-09-28", 200.0)]

    def test_axis_tops_out_on_a_clean_number(self):
        for value, top in ((0, 2), (0.5, 0.6), (3, 4), (18, 20), (100, 100), (101, 200),
                           (950, 1000), (2400, 4000)):
            self.assertEqual(ads_charts.nice_max(value), top)

    def test_columns_one_bar_per_week_with_a_value_and_a_hit_area_for_every_week(self):
        svg = ads_charts.columns("Spend per week", self.POINTS, lambda v: f"R{v:,.0f}",
                                 noun="spend")
        self.assertEqual(svg.count('class="bar"'), 3)
        self.assertEqual(svg.count('class="hit"'), 5)
        self.assertIn("<title>Week of 28 Sep: R200</title>", svg)
        self.assertIn("<title>Week of 14 Sep: no spend</title>", svg)
        self.assertIn('aria-label="Spend per week, 5 weeks. Latest, week of 28 Sep: R200. '
                      'Highest, week of 28 Sep: R200."', svg)
        # Ticks at nothing, half and the top; one month label per month.
        for tick in (">R0<", ">R100<", ">R200<", ">Aug<", ">Sep<"):
            self.assertIn(tick, svg)

    def test_line_breaks_where_a_week_has_no_value(self):
        svg = ads_charts.line("Cost per lead", self.POINTS, lambda v: f"R{v:,.0f}", noun="leads")
        # Weeks one and two join; week four and five join; nothing bridges the gap.
        self.assertEqual(svg.count('class="ln"'), 2)
        self.assertEqual(svg.count('class="dot"'), 1)
        lonely = ads_charts.line("x", [("2026-09-07", 5.0), ("2026-09-14", None),
                                       ("2026-09-21", None)], str)
        self.assertEqual((lonely.count('class="ln"'), lonely.count('class="dot"')), (0, 2))

    def test_empty_series_still_draws_a_frame(self):
        svg = ads_charts.columns("Leads", [("2026-09-28", 0)], str, integer=True)
        self.assertIn('aria-label="Leads, 1 week. Latest, week of 28 Sep: 0.', svg)
        self.assertEqual(svg.count('class="bar"'), 0)
        # A count's axis never shows half a lead.
        self.assertIn(">1.0<", svg)
        svg = ads_charts.line("Cost per lead", [("2026-09-28", None)], str, noun="leads")
        self.assertIn('aria-label="Cost per lead: nothing in this period."', svg)
        self.assertIn("<title>Week of 28 Sep: no leads</title>", svg)


def _history_doc(brand="swing-shack"):
    h = hfx.history()[0]
    return {"schema": ads_history.SCHEMA, "brand_id": brand, "date": "2026-10-08",
            "period": h["period"], "trends": ads_history.trends(h),
            "winners": ads_history.winners(h), "errors": h["errors"]}


class TrendsPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = ads_brief.render_trends_html([_history_doc()], missing=["stick"])

    def test_four_charts_tiles_and_the_table_behind_them(self):
        self.assertEqual(self.page.count("<svg"), 4)
        for needle in ("<h1>Ads trends</h1>", "<h2>Swing Shack</h2>", "Last 4 weeks",
                       "Spend per week", "Leads per week", "Cost per lead",
                       "Page visits per week", "The numbers behind the charts",
                       "23 whole weeks, Monday to Sunday, up to 4 Oct 2026",
                       "vs the 4 weeks before", "Latest week: R365"):
            self.assertIn(needle, self.page)
        # Most recent week first in the table.
        self.assertRegex(self.page, r"<tr><td>28 Sep</td><td>R365</td><td>3</td><td>R41\.67</td>")

    def test_a_brand_with_no_history_says_so(self):
        self.assertIn("<h2>Stick</h2>", self.page)
        self.assertIn("No history yet", self.page)
        empty = ads_brief.render_trends_html(
            [{"brand_id": "stick", "trends": {"weeks": []}, "errors": ["weeks x: HTTP 500"]}])
        self.assertIn("Meta returned no weekly history", empty)
        self.assertIn("HTTP 500", empty)

    def test_tabs_on_every_view(self):
        self.assertIn('href="/ads-brief?kind=trends" class="on"', self.page)
        self.assertIn('href="/ads-brief?kind=research" class=""', self.page)
        self.assertIn('href="/ads-brief" class=""', self.page)
        research = ads_brief.render_research_html(["swing-shack"], {}, {})
        self.assertIn('href="/ads-brief?kind=research" class="on"', research)

    def test_plain_page_no_script_no_em_dash(self):
        self.assertNotIn("<script", self.page)
        self.assertNotIn("—", self.page)
        self.assertIn("--series:#2a78d6", self.page)
        self.assertIn("--series:#3987e5", self.page)


class ResearchPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = _fetch()[0]
        cls.page = ads_brief.render_research_html(
            ["swing-shack", "stick"], {"swing-shack": _history_doc()},
            {"swing-shack": cls.lib})

    def test_own_winners_with_cost_run_and_opening(self):
        for needle in (
                "<h1>What works</h1>", "Cheapest leads", "Cheapest page visits",
                "<b>FItFacts</b> (video): 24 leads at R30.00 each, R720 spent, ran 12 weeks, "
                "13 Jul to 28 Sep, still running.",
                "Opened with: &ldquo;Get your clubs checked, see the numbers, and find what "
                "suits your swing.&rdquo;",
                "30% of the times it was shown, it was watched for three seconds; 25% of those "
                "watched it through; average watch 4 seconds.",
                "Leads by subject", "Openings that held attention",
                "Your own ads, 52 weeks to 4 Oct 2026. 6 ads ran."):
            self.assertIn(needle, self.page)
        self.assertEqual(self.page.count('class="tag good">proven'), 2)  # FItFacts, Putter
        self.assertEqual(self.page.count("too few to judge"), 2)  # Coaching Cat, Driver day
        self.assertNotIn("Cheapest chats", self.page)

    def test_other_advertisers_and_the_south_african_link(self):
        self.assertIn("<b>Old Hand Golf</b>, running 637 days: &ldquo;Still guessing your shaft "
                      "flex?&rdquo;", self.page)
        self.assertIn('href="https://www.facebook.com/ads/library/?id=2"', self.page)
        self.assertIn("See South African video ads on this subject", self.page)
        self.assertIn("country=ZA", self.page)
        self.assertIn("Nothing long-running found.", self.page)  # coaching came back empty
        self.assertNotIn(TOKEN, self.page)

    def test_states_before_any_read_and_after_a_refusal(self):
        self.assertIn("No history yet", self.page)  # Stick has no file
        self.assertIn("has not been checked yet", self.page)
        self.assertIn('href="/ads-brief?kind=research&amp;refresh=1"', self.page)
        refused = ads_brief.render_research_html(
            ["swing-shack"], {}, {"swing-shack": _fetch(archive=None)[0]})
        self.assertIn("Meta refused the Ad Library read", refused)
        self.assertIn("See South African video ads on this subject", refused)
        self.assertIn("(#10) no permission", refused)

    def test_an_image_ad_says_so_and_claims_no_watch_time(self):
        doc = _history_doc()
        ad = doc["winners"]["ranked"]["leads"]["ads"][0]
        ad["format"] = "image"
        page = ads_brief.render_research_html(["swing-shack"], {"swing-shack": doc}, {})
        self.assertIn("<b>FItFacts</b> (image): 24 leads", page)
        self.assertNotIn("25% of those watched it through", page)

    def test_names_from_meta_are_escaped(self):
        doc = _history_doc()
        doc["winners"]["ranked"]["leads"]["ads"][0]["ad_name"] = "<script>x</script>"
        lib = json.loads(json.dumps(self.lib))
        lib["themes"][1]["ads"][0]["page_name"] = "<img src=x>"
        page = ads_brief.render_research_html(["swing-shack"], {"swing-shack": doc},
                                              {"swing-shack": lib})
        self.assertNotIn("<script>x", page)
        self.assertNotIn("<img src=x>", page)
        self.assertNotIn("—", page)


class Job(bfx._JobCase):
    def test_writes_the_history_beside_the_brief(self):
        out = self.job.run(brand="stick", today=bfx.DAY,
                           get=self._get(), get_as=bfx.fx._fake_get_as(bfx.fx.STICK))
        self.assertTrue(out["ok"])
        lane = self.lane.parent / "ads-history"
        latest = json.loads((lane / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(latest["period"]["weeks"], 52)
        self.assertEqual(len(latest["trends"]["weeks"]), 23)
        self.assertEqual(latest["winners"]["ranked"]["leads"]["ads"][0]["ad_name"], "FItFacts")
        self.assertTrue((lane / "weekly.json").exists())
        self.assertEqual(out["history"], {"weeks_with_delivery": 16, "ads": 6, "errors": []})
        self.assertIn("<svg", ads_brief.render_trends_html([latest]))

    def test_a_meta_refusal_of_the_history_does_not_cost_the_brief(self):
        out = self.job.run(brand="stick", today=bfx.DAY, get=self._get(history_fails=True),
                           get_as=bfx.fx._fake_get_as(bfx.fx.STICK))
        self.assertTrue(out["ok"])
        self.assertTrue((self.lane / "latest.json").exists())
        self.assertEqual(out["history"]["weeks_with_delivery"], 0)
        self.assertEqual(len(out["history"]["errors"]), 3)

    def _get(self, history_fails=False):
        """Weekly requests get the history fixtures; everything else the brief's own."""
        brief = bfx._get(bfx.fx.STICK, bfx.RECENT["stick"])
        weekly = hfx.fake_get()

        def get(path, params):
            if "time_increment" in params:
                return (None, "HTTP 500: later") if history_fails else weekly(path, params)
            return brief(path, params)
        return get


if __name__ == "__main__":
    unittest.main()
