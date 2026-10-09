"""Video ideas: the shipped idea files are usable, and the right idea lands on
the right test card."""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brief as bfx  # noqa: E402
import test_v2026_10_08_ads_creative as cfx  # noqa: E402
import test_v2026_10_09_ads_history as hfx  # noqa: E402
from _lib import ads_brief, ads_creative, ads_history, ads_ideas  # noqa: E402

BRAND_DIR = CAMPAIGN_OS.parent / "data" / "brand-directory"
BRANDS = ("stick", "swing-shack")
DAY = dt.date(2026, 10, 8)


def _bank(brand="swing-shack"):
    return ads_ideas.load_bank(brand, BRAND_DIR)


def _cards():
    cards, _ = cfx._plan()
    return cards


def _new_video(card):
    return next(c for c in card["challengers"] if c["kind"] == "NEW_VIDEO")


class ShippedBanks(unittest.TestCase):
    def test_both_brands_have_a_usable_file(self):
        for brand in BRANDS:
            raw = json.loads((BRAND_DIR / brand / "ads" / "video-ideas.json")
                             .read_text(encoding="utf-8"))
            self.assertEqual(ads_ideas.problems(raw), [], brand)
            self.assertEqual(raw["brand_id"], brand)
            self.assertGreaterEqual(len(_bank(brand)["ideas"]), 8, brand)

    def test_every_card_can_get_a_video_and_retail_can_get_a_still(self):
        for brand in BRANDS:
            ideas = _bank(brand)["ideas"]
            self.assertTrue([i for i in ideas if i["kind"] == "video" and "any" in i["themes"]],
                            brand)
            self.assertTrue([i for i in ideas if i["kind"] == "animated_still"
                             and set(i["themes"]) & ads_creative.RETAIL_THEMES], brand)

    def test_no_number_that_is_not_a_verified_fact(self):
        """The brand rule: any number not in knowledge.json is not allowed in copy."""
        for brand in BRANDS:
            facts = json.dumps(json.loads((BRAND_DIR / brand / "knowledge.json")
                                          .read_text(encoding="utf-8"))["verified_facts"])
            allowed = set(re.findall(r"\d+", facts))
            for idea in _bank(brand)["ideas"]:
                said = " ".join([idea["hook"]["say"], idea["hook"]["text"]] + idea["points"])
                for number in re.findall(r"\d+", said):
                    self.assertIn(number, allowed, f"{idea['id']}: {number}")

    def test_no_banned_phrases(self):
        banned = ("next level", "unlock your potential", "world-class", "game changer",
                  "bespoke", "journey", "click here", "learn more", "shop now", "buy now",
                  "—")
        for brand in BRANDS:
            text = json.dumps(_bank(brand), ensure_ascii=False).lower()
            for phrase in banned:
                self.assertNotIn(phrase, text, f"{brand}: {phrase}")
        # Stick does not sell membership and does not name its sister brand.
        stick = json.dumps(_bank("stick")).lower()
        self.assertNotIn("swing shack", stick)
        self.assertNotIn("join the club", stick)

    def test_a_broken_or_missing_file_is_an_empty_bank(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ads_ideas.load_bank("stick", d), {"ideas": []})
            path = Path(d) / "stick" / "ads"
            path.mkdir(parents=True)
            (path / "video-ideas.json").write_text("not json", encoding="utf-8")
            self.assertEqual(ads_ideas.load_bank("stick", d), {"ideas": []})
            (path / "video-ideas.json").write_text(
                json.dumps({"ideas": [{"id": "x", "kind": "video"}]}), encoding="utf-8")
            self.assertEqual(ads_ideas.load_bank("stick", d), {"ideas": []})

    def test_problems_names_what_is_wrong(self):
        good = dict(_bank()["ideas"][0])
        bad = [dict(good, id="a", angle="shouting"), dict(good, id="a", themes=["cricket"]),
               dict(good, id="b", hook={"say": "x"}), dict(good, id="c", points=["x — y"])]
        found = " | ".join(ads_ideas.problems({"ideas": bad}))
        for needle in ("unknown angle", "used twice", "unknown themes cricket",
                       "the hook needs say, show and text", "em dash"):
            self.assertIn(needle, found)


class Choose(unittest.TestCase):
    def test_on_the_subject_first_then_a_different_kind_of_video(self):
        picked = ads_ideas.choose(_bank(), "video", {"coaching"}, "Statement.", set())
        self.assertEqual([i["id"] for i in picked], ["ss-three-feels", "ss-your-normal-swing"])
        self.assertEqual(len({i["angle"] for i in picked}), 2)

    def test_does_not_open_on_a_question_against_an_ad_that_does(self):
        asks = "Missing the hole by that little bit? Get the specs right."
        first = ads_ideas.choose(_bank(), "video", {"fitting"}, asks, set())[0]
        self.assertNotEqual(first["angle"], "question")
        # Against a statement the question is fair game, and it is on the subject.
        ids = [i["id"] for i in ads_ideas.choose(_bank(), "video", {"fitting"}, "A fact.", set())]
        self.assertIn("ss-when-last-measured", ids)

    def test_skips_ideas_already_on_another_card(self):
        first = ads_ideas.choose(_bank(), "video", {"fitting"}, None, set())
        again = ads_ideas.choose(_bank(), "video", {"fitting"}, None, {i["id"] for i in first})
        self.assertFalse({i["id"] for i in first} & {i["id"] for i in again})

    def test_a_campaign_with_no_subject_still_gets_a_general_idea(self):
        picked = ads_ideas.choose(_bank("stick"), "video", set(), None, set())
        self.assertEqual([i["id"] for i in picked], ["stick-in-their-words"])

    def test_stills_and_videos_do_not_mix(self):
        still = ads_ideas.choose(_bank(), "animated_still", {"retail"}, None, set())
        self.assertEqual([i["kind"] for i in still], ["animated_still"])
        self.assertFalse(ads_ideas.choose(_bank(), "animated_still", {"fitting"}, None, set()))
        self.assertTrue(all(i["kind"] == "video"
                            for i in ads_ideas.choose(_bank(), "video", {"retail"}, None, set())))


class Attach(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win = ads_history.winners(hfx.history()[0])
        cls.cards = ads_ideas.attach(_cards(), _bank(), cls.win)
        cls.by = {c["control"]["ad_id"]: c for c in cls.cards}

    def test_every_proposed_card_says_what_to_film(self):
        for card in self.cards:
            ideas = _new_video(card)["ideas"]
            self.assertEqual(len(ideas), 2, card["campaign_name"])
            for idea in ideas:
                self.assertTrue(idea["hook"]["say"] and idea["points"] and idea["shots"])
                self.assertEqual(idea["sign_off"], "Real Golf, Indoors.")

    def test_two_cards_never_share_an_idea(self):
        ids = [i["id"] for c in self.cards for i in _new_video(c)["ideas"]]
        self.assertEqual(len(ids), len(set(ids)))
        # Both coaching campaigns get a coaching idea first, a different one each.
        self.assertEqual(_new_video(self.by["cat"])["ideas"][0]["id"], "ss-three-feels")
        self.assertEqual(_new_video(self.by["david"])["ideas"][0]["id"], "ss-your-normal-swing")

    def test_the_ending_matches_what_the_ad_is_bought_for(self):
        self.assertIn("short form", _new_video(self.by["ff1"])["ideas"][0]["end"])
        self.assertIn("tap through", _new_video(self.by["david"])["ideas"][0]["end"])

    def test_why_points_at_the_brands_own_proven_ad(self):
        # FItFacts is the proven fitting lead ad, and it is the ad being tested against.
        self.assertIn("already your cheapest lead ad", _new_video(self.by["ff1"])["ideas"][0]["why"])
        # Nothing has ten leads on coaching yet.
        self.assertIn("No ad on this subject has enough leads",
                      _new_video(self.by["cat"])["ideas"][0]["why"])
        other = dict(self.by["ff1"], control=dict(self.by["ff1"]["control"], ad_id="ff9"),
                     challengers=[{"kind": "NEW_VIDEO"}])
        why = _new_video(ads_ideas.attach([other], _bank(), self.win)[0])["ideas"][0]["why"]
        self.assertIn("FItFacts, opened with", why)
        self.assertIn("24 leads at R30.00 each", why)

    def test_a_card_keeps_its_ideas_and_picks_up_edits_to_the_file(self):
        again = ads_ideas.attach(self.cards, _bank(), self.win)
        self.assertEqual([[i["id"] for i in _new_video(c)["ideas"]] for c in again],
                         [[i["id"] for i in _new_video(c)["ideas"]] for c in self.cards])
        edited = json.loads(json.dumps(_bank()))
        next(i for i in edited["ideas"] if i["id"] == "ss-three-feels")["title"] = "Just three"
        again = ads_ideas.attach(self.cards, edited, self.win)
        cat = next(c for c in again if c["control"]["ad_id"] == "cat")
        self.assertEqual(_new_video(cat)["ideas"][0]["title"], "Just three")

    def test_only_proposed_cards_are_touched(self):
        running = dict(_cards()[0], status="RUNNING")
        out = ads_ideas.attach([running], _bank(), self.win)
        self.assertNotIn("ideas", _new_video(out[0]))
        self.assertEqual(ads_ideas.attach(_cards(), {"ideas": []}, self.win), _cards())

    def test_a_closed_test_gives_its_ideas_back(self):
        closed = [dict(c, status="EXPIRED") for c in self.cards]
        fresh = ads_ideas.attach(closed + _cards(), _bank(), self.win)[len(closed):]
        self.assertEqual(_new_video(fresh[0])["ideas"][0]["id"], "ss-three-feels")
        # While it is still open, a new card for another campaign does not reuse it.
        other = dict(_cards()[0], id="x", campaign_id="c-x")
        fresh = ads_ideas.attach(self.cards[:1] + [other], _bank(), self.win)[-1]
        self.assertEqual(_new_video(fresh)["ideas"][0]["id"], "ss-your-normal-swing")

    def test_when_the_file_runs_out_a_card_repeats_an_idea_rather_than_go_empty(self):
        other = dict(_cards()[0], id="x", campaign_id="c-x")
        fresh = ads_ideas.attach(self.cards + [other], _bank(), self.win)[-1]
        self.assertEqual([i["id"] for i in _new_video(fresh)["ideas"]], ["ss-three-feels"])

    def test_the_card_on_the_page_reads_as_a_shoot(self):
        page = ads_brief._creative_section(ads_creative.summarise(self.cards, DAY))
        for needle in ("Film this: The ball tells the truth", "First three seconds",
                       "<b>Say:</b> The swing may lie, but the ball tells the truth.",
                       "Then say", "Shots to get", "Sign off: Real Golf, Indoors.",
                       "Or this instead:", "Why this one:"):
            self.assertIn(needle, page)
        self.assertNotIn("—", page)


class Job(bfx._JobCase):
    def test_the_morning_job_puts_ideas_on_the_cards_it_writes(self):
        out = self.run_job(bfx.fx.STICK, DAY)
        self.assertTrue(out["ok"])
        tests = json.loads((self.lane.parent / "ads-creative" / "tests.json")
                           .read_text(encoding="utf-8"))
        self.assertTrue(tests)
        for t in tests:
            self.assertTrue(_new_video(t)["ideas"][0]["id"].startswith("stick-"))
        self.assertIn("Film this:", ads_brief.render_html([self.read("latest.json")], "daily"))
        # The same cards the next day: same ideas, nothing reshuffled.
        self.run_job(bfx.fx.STICK, DAY + dt.timedelta(days=1))
        after = json.loads((self.lane.parent / "ads-creative" / "tests.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual([[i["id"] for i in _new_video(t)["ideas"]] for t in after],
                         [[i["id"] for i in _new_video(t)["ideas"]] for t in tests])


if __name__ == "__main__":
    unittest.main()
