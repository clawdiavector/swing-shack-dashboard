"""caption_lint: a caption is checked against the brand bible's Part 4 rules.

The golden and rejected captions below are the ones printed in each brand's
`BRAND-BIBLE.md` (section 15). If a bible's example stops passing or failing as
described, either the bible or the linter has drifted, and this test says which.
"""
from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

import caption_lint as L  # noqa: E402

BRAND_DIR = CAMPAIGN_OS.parent / "data" / "brand-directory"
HAVE_BIBLES = all((BRAND_DIR / b / "BRAND-BIBLE.md").exists() for b in L.BRANDS)

GOLD = {
    "stick": [
        "You can be fit for a golf ball without being a low-handicap golfer.\nFitting is not a reward for being good at golf.\nIt is simply a better way to choose equipment.\nBook a fitting at Stick.\nBetter begins here.",
        "A lesson should leave you knowing what to do next.\nNot carrying twelve swing thoughts to the first tee.\nBook coaching at Stick.\nBetter begins here.",
        "Why it’s here: Sausage Putters.\nDifferent is only interesting if it still does the job. Sausage Putters brings a distinct point of view to the putting floor at Stick.\nCome roll one at Stick.\nBetter begins here.",
        "Bring your current clubs.\nIf the new option cannot beat what you already own in a meaningful way, that tells us something useful.\nBook a fitting at Stick.\nBetter begins here.",
        "Titleist T250 iron set available at Stick.\nS300 shafts. 4-PW.\nFast face. Cleaner shape. More help than it lets on.\nDM us for price and details.\nBetter begins here.",
        "The Limited Edition Srixon US Open Stand Bag is here.\nIncludes three matching headcovers.\nR7,999.\nOnly two available.\nDM us to secure yours.",
        "There’s a new golf spot in Paarl.\nYou’ll find us at Winelands Square.\nLook for the Stick sign.\nWalk in.\nTry not to leave with something.\nNo promises.\nBetter begins here.",
        "The Bunny has landed.\nA little too good at looking good.\nPsycho Bunny available at Stick.\nBetter begins here.",
    ],
    "swing-shack": [
        "Off-the-rack is fine for groceries.\nFor clubs, let’s aim a little higher.\nBook your fitting at Swing Shack.",
        "The woods are lovely this time of year.\nStill, probably better to stay out of them.\nBook your coaching session.",
        "A few small changes can save a lot of golf balls.\nBook your coaching session now.",
        "Golf is easier when the club is built around your swing, not someone else’s spec sheet.\nBook your fitting.",
        "Your driver can feel fine.\nBut TrackMan shows what ball flight hides: spin rate, launch angle, strike pattern and dispersion.\nThat is the difference between guessing and fitting properly.\nBook a club fitting. Link in bio.",
        "This one will not sit quietly in the corner.\nLimited Edition Srixon US Open Stand Bag.\nThree matching headcovers included.\nR7,999.\nOnly two available.\nDM us to secure yours.",
        "Camo has entered the chat.\nNew Herschel golf bags are now at Swing Shack.\nPlenty of character. Plenty of storage.\nDM us for pricing and stock.",
    ],
    "bag-drop": [
        "Old balls do old-ball things.\nScuffs, damaged covers and tired dimples can cost distance, spin and feel.\nShop balls. Link in bio.",
        "Old wedges cost shots.\nFresh grooves give you more control where it matters most.\nShop the drop. Link in bio.",
        "Callaway Ai Smoke Triple Diamond driver head.\nLoft: 11°. Condition: B. Price: R5,000.\nLow-spin.\nShop the drop. Link in bio.",
        "Putters are personal.\nShop putters. Link in bio.",
        "The hardest club to fit in your bag is the 3-wood.\nBuying off the rack rarely works.\nStop guessing and fix your gaps with our demo fairway metals and hybrid heads.\nShop the drop. Link in bio.",
    ],
}

# (brand, caption, codes that must fire)
BAD = [
    ("stick", "Ever wonder why your clubs feel more like a punishment than a partner? Spoiler alert: it might be because they’re not fitted to you. Get the gear that actually fits your game.\nBetter begins here.", {"banned-brand", "hook-length"}),
    ("stick", "Come experience the latest Sub 70 range at Stick.\n✔ Professional fitting\n✔ Premium shafts\nBook your fitting today.\nBetter begins today.", {"name-wrong", "banned-brand"}),
    ("stick", "20% off full bag fittings\nFirst 30 people to tag someone who blames the wind.\nSTICK is coming to Paarl.\nDM us for bookings", {"banned-universal"}),
    ("stick", "Meet Jared.\nClub fitter. Gear nerd.\nHe looks at the numbers, the build, the flight, the strike — then helps you find what actually belongs in your bag.\nBetter begins here.", {"em-dash"}),
    ("stick", "Better begins here\nBook a fitting at Stick.", {"signoff-variant"}),
    ("stick", "Rush Naidoo new iron build started with the fitting.\nBook a fitting at Stick.\nBetter begins here.\n#customgolfclubs #golfclubfitting", {"hashtag-allowed"}),
    ("swing-shack", "87% of golfers who get fit lower their handicap. That’s fact, not opinion. Your game deserves equipment that performs to your potential. Book your fitting today.", {"banned-brand"}),
    ("swing-shack", "Fitted clubs can take up to 5 shots off your game guaranteed!", {"banned-brand", "exclamation"}),
    ("swing-shack", "FROM CONFUSED GOLFER TO CONFIDENT STRIKER.\nReal South African results:\nClub speed: 142km/h\nR820 full TrackMan coaching session.\nSwing Shack - Johannesburg’s indoor golf studio.", {"caps", "banned-brand"}),
    ("swing-shack", "Is your budget looking a lil tight \U0001F62D We’ve got u covered with discounts on your golfing needs.", {"text-speak", "banned-universal"}),
    ("swing-shack", "Built to preform.\nAvoda now at Swing Shack.\nCome get fitted.", {"typo"}),
    ("swing-shack", "Srixon Stand Bags Available \U0001F3CC️‍♂️\nR7999.00\nOnly Two left \U0001F4E2\nCall/whatsapp us on 066 542 1522\nDont Miss Out \U0001FAF5", {"currency", "emoji-count"}),
    ("swing-shack", "Want to elevate your golfing game with something cool\U0001F60E", {"banned-universal"}),
    ("swing-shack", "\U0001D5E5\U0001D7EE\U0001D7EF\U0001D7ED\U0001D7EC Golfers who improve consistently have one thing in common.\nDM us for details.", {"unicode-styled"}),
    ("bag-drop", "The Mizuno STG driver head is seriously underrated and packs a massive punch \U0001F4A5 Maximum adjustability and pure ball speed. Don’t sleep on this one. Grab it before it’s gone! \U0001F680 Link in bio.", {"banned-brand", "emoji-count"}),
    ("bag-drop", "Demo head does not mean damaged \U0001F4A5\nThese heads are inspected, checked and in mint condition before they go up for sale.\nVisit the online store or DM⛳️", {"banned-brand", "emoji-count"}),
    ("bag-drop", "Bag Drop stocks demo clubs, second-hand clubs and useful golf essentials at better price points.\nMessage us to check what’s available.", {"banned-brand", "hook-opener"}),
    ("bag-drop", "Buy from The Bag Drop and get R500 off a fitting at SwingShack or Stick.paarl\nShop now: www.thebagdrop.co.za", {"banned-brand", "link"}),
    ("bag-drop", "Odyssey Ai-ONE Seven T putter. Condition: New Price: R8 500\nClean shape.", {"currency"}),
    ("bag-drop", "Callaway driver head.\nLoft: 11°. Condition: Demo. Price: R5,000.", {"condition-grade"}),
]


def codes(res: dict, level: str | None = None) -> set[str]:
    return {f["code"] for f in res["findings"] if level is None or f["level"] == level}


@unittest.skipUnless(HAVE_BIBLES, "the brand bibles are not on this branch")
class BibleExamples(unittest.TestCase):
    def test_every_golden_example_has_no_hard_fail(self):
        for brand, caps in GOLD.items():
            for cap in caps:
                with self.subTest(brand=brand, caption=cap.splitlines()[0][:50]):
                    res = L.lint(brand, cap, cross_brand=False)
                    self.assertEqual(res["hard"], 0, [f["message"] for f in res["findings"] if f["level"] == L.HARD])

    def test_every_rejected_example_fails_for_the_cited_reason(self):
        for brand, cap, want in BAD:
            with self.subTest(brand=brand, caption=cap.splitlines()[0][:50]):
                res = L.lint(brand, cap, cross_brand=False)
                self.assertTrue(want <= codes(res), f"wanted {sorted(want)}, got {sorted(codes(res))}")
                self.assertGreater(res["hard"], 0)


@unittest.skipUnless(HAVE_BIBLES, "the brand bibles are not on this branch")
class Rules(unittest.TestCase):
    def test_every_bible_has_a_parsable_part_4(self):
        for brand in L.BRANDS:
            rules = L.load_rules(brand)
            self.assertEqual(rules["brand"], brand)
            self.assertTrue(rules.get("ctas_allowed"))
            self.assertIn("banned_brand", rules)

    def test_missing_bible_is_a_clear_error(self):
        with self.assertRaises(FileNotFoundError):
            L.load_rules("stick", Path("/nope/BRAND-BIBLE.md"))

    def test_em_dash_and_en_dash_are_hard_fails(self):
        for ch in ("—", "–"):
            res = L.lint("stick", f"Fitting first {ch} then buying.\nBook a fitting at Stick.\nBetter begins here.", cross_brand=False)
            self.assertIn("em-dash", codes(res, L.HARD))

    def test_stick_signoff_must_be_exact_and_last(self):
        ok = "Fit first.\nBook a fitting at Stick.\nBetter begins here."
        self.assertEqual(L.lint("stick", ok, cross_brand=False)["hard"], 0)
        wrong_place = "Better begins here.\nBook a fitting at Stick."
        self.assertIn("signoff-place", codes(L.lint("stick", wrong_place, cross_brand=False), L.HARD))
        for variant in ("Better Begins Here.", "Better begins here", "Better begins here ⛳️"):
            res = L.lint("stick", f"Fit first.\nBook a fitting at Stick.\n{variant}", cross_brand=False)
            self.assertIn("signoff-variant", codes(res, L.HARD), variant)

    def test_hashtags_and_credit_line_may_follow_the_signoff(self):
        cap = "Fit first.\nBook a fitting at Stick.\nBetter begins here.\n\nPhoto credit: @shante.hutton.photography\n#PaarlGolf"
        res = L.lint("stick", cap, cross_brand=False)
        self.assertNotIn("signoff-place", codes(res))
        self.assertNotIn("credit-format", codes(res))

    def test_one_cta_only(self):
        res = L.lint("stick", "Fit first.\nBook a fitting at Stick.\nDM us for price and details.\nBetter begins here.", cross_brand=False)
        self.assertIn("cta-multiple", codes(res, L.HARD))

    def test_wildcard_cta_patterns(self):
        self.assertTrue(L._matches_pattern("dm us to secure yours", "DM us to *."))
        self.assertTrue(L._matches_pattern("book a lesson at stick", "Book a * at Stick."))
        self.assertTrue(L._matches_pattern("shop balls link in bio", "Shop *. Link in bio."))
        self.assertFalse(L._matches_pattern("message us for current stock", "Message us to order."))
        self.assertFalse(L._matches_pattern("book a lesson at swing shack", "Book a * at Stick."))

    def test_vague_bag_drop_cta_is_not_listed(self):
        res = L.lint("bag-drop", "Putters are personal.\nMessage us for current stock.", cross_brand=False)
        self.assertIn("cta-unlisted", codes(res, L.HARD))

    def test_the_word_stick_is_left_alone_but_the_brand_is_checked(self):
        self.assertNotIn("name-case", codes(L.lint("stick", "Big stick attitude. Slightly better manners.\nBook coaching at Stick.\nBetter begins here.", cross_brand=False)))
        self.assertIn("name-case", codes(L.lint("stick", "Vice available at stick.\nBook coaching at Stick.\nBetter begins here.", cross_brand=False), L.HARD))

    def test_swing_shack_may_not_mention_stick_but_may_say_stick(self):
        self.assertIn("banned-brand", codes(L.lint("swing-shack", "Ask the team at Stick.\nBook your fitting today.", cross_brand=False), L.HARD))
        self.assertNotIn("banned-brand", codes(L.lint("swing-shack", "Stick with the plan.\nBook your fitting today.", cross_brand=False)))

    def test_up_to_is_only_a_claim_before_a_performance_unit(self):
        self.assertIn("banned-brand", codes(L.lint("swing-shack", "A fitting can add up to 19 metres.\nBook your fitting today.", cross_brand=False), L.HARD))
        self.assertNotIn("banned-brand", codes(L.lint("swing-shack", "Payouts up to 10th place.\nBook your fitting today.", cross_brand=False)))

    def test_a_capitalised_word_inside_a_proper_noun_is_not_banned(self):
        res = L.lint("swing-shack", "Sean won the BSI Premier Division title.\nBook your fitting today.", cross_brand=False)
        self.assertNotIn("banned-brand", codes(res))

    def test_initialisms_are_not_shouting_but_shouting_is(self):
        self.assertNotIn("caps", codes(L.lint("swing-shack", "Coach Dave is a PGA professional.\nBook your coaching session.", cross_brand=False)))
        self.assertIn("caps", codes(L.lint("swing-shack", "NEW ARRIVAL ALERT\nBook your fitting today.", cross_brand=False), L.HARD))

    def test_one_emoji_cluster_counts_once(self):
        res = L.lint("swing-shack", "Camo has entered the chat.\nDM us for price and details. \U0001F3CC️‍♂️", cross_brand=False)
        self.assertNotIn("emoji-count", codes(res))
        res = L.lint("swing-shack", "Camo has entered the chat.\nDM us for price and details. ⛳⛳", cross_brand=False)
        self.assertIn("emoji-count", codes(res, L.HARD))

    def test_stick_allows_no_emoji_except_the_pin(self):
        self.assertIn("emoji-allowed", codes(L.lint("stick", "Fit first.\nBook a fitting at Stick.\nBetter begins here.\n\U0001F3CC️", cross_brand=False), L.HARD))
        self.assertNotIn("emoji-allowed", codes(L.lint("stick", "Fit first.\nWe are at Winelands Square.\n\U0001F4CD Paarl\nVisit us at Winelands Square.\nBetter begins here.", cross_brand=False)))

    def test_currency_format(self):
        for bad in ("R5000", "R8 500", "R 6,500.00", "R7999.00"):
            res = L.lint("stick", f"A bag for {bad}.\nDM us to secure yours.\nBetter begins here.", cross_brand=False)
            self.assertIn("currency", codes(res, L.HARD), bad)
        for good in ("R500", "R7,999", "R101"):
            res = L.lint("stick", f"A bag for {good}.\nDM us to secure yours.\nBetter begins here.", cross_brand=False)
            self.assertNotIn("currency", codes(res), good)

    def test_figures_and_stock_claims_are_flagged_for_a_person_not_failed(self):
        res = L.lint("swing-shack", "Titleist GTS is now available for fitting at Swing Shack.\nA fitting measures 3 things.\nDM us for fitting details.", cross_brand=False)
        self.assertEqual(res["hard"], 0)
        self.assertIn("stock-claim", codes(res, L.CHECK))

    def test_lane_word_band(self):
        res = L.lint("stick", "Short.\nBook a fitting at Stick.\nBetter begins here.", lane="why-its-here", cross_brand=False)
        self.assertIn("lane-length", codes(res, L.WARN))

    def test_cross_brand_line_inside_the_window(self):
        audit = BRAND_DIR / "stick" / "feedback" / "instagram-audit.json"
        if not audit.exists():
            self.skipTest("no Stick audit")
        line = "Titleist T250 iron set available at Swing Shack."
        res = L.lint("swing-shack", f"{line}\nDM us for price and details.", when=dt.date(2026, 6, 19))
        self.assertIn("cross-brand-line", codes(res, L.HARD))
        far = L.lint("swing-shack", f"{line}\nDM us for price and details.", when=dt.date(2027, 6, 19))
        self.assertNotIn("cross-brand-line", codes(far))

    def test_a_shared_call_to_action_is_not_a_shared_line(self):
        # "Book your fitting today." runs on both feeds and is meant to.
        res = L.lint("swing-shack", "Golf is easier with a fit.\nBook your fitting today.", when=dt.date(2026, 8, 15))
        self.assertNotIn("cross-brand-line", codes(res))


@unittest.skipUnless(HAVE_BIBLES, "the brand bibles are not on this branch")
class Cli(unittest.TestCase):
    def test_exit_status_follows_hard_fails(self):
        good = GOLD["stick"][0]
        self.assertEqual(L.main(["stick", "--text", good]), 0)
        self.assertEqual(L.main(["stick", "--text", "Unlock your potential.\nClick here."]), 1)

    def test_list_rules(self):
        self.assertEqual(L.main(["--list-rules"]), 0)

    def test_audit_runs_over_a_real_feed(self):
        if not (BRAND_DIR / "stick" / "feedback" / "instagram-audit.json").exists():
            self.skipTest("no Stick audit")
        self.assertEqual(L.main(["stick", "--audit", "--since", "2026-09-01"]), 0)

    def test_audit_with_no_captions_in_range_is_a_usage_error(self):
        if not (BRAND_DIR / "stick" / "feedback" / "instagram-audit.json").exists():
            self.skipTest("no Stick audit")
        self.assertEqual(L.main(["stick", "--audit", "--since", "2099-01-01"]), 2)


if __name__ == "__main__":
    unittest.main()
