"""What an ad is about, checked against the text of the ads that were live on
2026-10-09. The first prod run of the video ideas showed the old matching was
too loose: hashtags made nearly every Swing Shack ad a coaching ad, a new
"member" of staff made one a membership ad, and a grip listed in a build spec
made an iron-fitting ad about grips.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import ads_creative  # noqa: E402

RUSH = ("Rush Naidoo new iron build started with the fitting, not the catalogue.\n\n"
        "Srixon ZXi7 heads.\nAerotech SteelFiber i110 shafts.\nRipit Stripe Green grips.\n\n"
        "The build followed the data.\nThat is the point of a fitting.\n\nBetter begins here.\n\n"
        "#customgolfclubs #golfclubfitting #paarlgolf #golfersofsouthafrica #newirons")

# (campaign, ad, headline, text) -> subject. Text as Meta returned it.
LIVE = [
    (("Rush web traffic campaign 30/07/2026 Campaign", "Rush web traffic campaign 30/07/2026 Ad",
      None, RUSH), {"fitting", "irons"}),
    (("Tip Of The Week - Grip - Web Traffic", "New Traffic Ad with recommended settings", None,
      "Tip of the week.\nOne useful change beats ten clever observations.\n"
      "Better begins with clarity.\nBook a lesson at Stick."), {"coaching"}),
    (("Tailored web traffic campaign 14/07/2026 Campaign",
      "Tailored web traffic campaign 14/07/2026 Ad", None,
      "Book a Club Assessment on us. \nBring in your current set, and we’ll take a look at "
      "the important stuff: length, lie, shafts, grips, gapping and set make-up."), {"fitting"}),
    (("Fit Fact leads Campaign", "50+km Paarl", "Better begins here.",
      "Your clubs need to suit your swing, not fight it. \nGet measured at Stick."), {"fitting"}),
    (("Coaching Web Push", "New Traffic Ad with recommended settings", None,
      "A lesson should leave you knowing what to do next. \nBook coaching at Stick."),
     {"coaching"}),
    (("Bags messages campaign 23/07/2026 Campaign", "Tailored messages campaign 23/07/2026 Ad",
      "Bags available at Stick", "New bag day is always a good idea."), {"bags", "retail"}),
    (("FitFacts", "FItFacts – 2", None,
      "Not sure about your clubs? We got you sorted \U0001faf5\n"
      "#golf #coach #golfaddict #golffitting #build"), {"fitting"}),
    (("Coaching Cat", "Coaching Cat 2", None,
      "A sneak peak into a lesson with our newest member Dawid! Dawid is available for "
      "coaching.\n#golf #coach #trackman #indoorgolf #swingshack"), {"coaching"}),
    (("Welcome David Traffic Campaign with recommended settings",
      "Welcome David Traffic Ad with recommended settings", None,
      "Let’s welcome Dawid to the team!! Ready to improve? He will be available for "
      "coaching. Visit our site or pop us a DM to get started\n"
      "#golf #golflife #coach #trackman #indoorgolf"), {"coaching"}),
    (("Putter Traffic Campaign with recommended settings",
      "New Traffic Ad with recommended settings", None,
      "If you’ve played golf..you know how annoying missing the hole by just that little "
      "bit is \U0001f62d Let us help you get the specs right to drop more putts \U0001f64c\n"
      "#golf #golflife #coach #clubfitting #keepgoing"), {"fitting", "putter"}),
    # No subject is better than a wrong one.
    (("Avoda web traffic campaign 28/07/2026 Campaign", "Avoda web traffic campaign 28/07/2026 Ad",
      None, "Tired of the same old setup \U0001f971 try Avoda today! \n"
            "#golf #coach #fitter #equipment #golfaddict"), set()),
    (("Web Traffic  Campaign", "Web Traffic  Ad", None,
      "Life’s hard, why make golf hard too\U0001f979\n#golf #golﬂife #data #coach #coaching"),
     set()),
]


class LiveAds(unittest.TestCase):
    def test_each_live_ad_is_about_what_a_person_would_say(self):
        for (campaign, ad, title, body), expected in LIVE:
            self.assertEqual(ads_creative.subject(campaign, ad, title, body), expected,
                             f"{campaign} / {ad}")


class Rules(unittest.TestCase):
    def test_hashtags_do_not_name_a_subject(self):
        self.assertEqual(ads_creative.themes_of("New in store #coach #golffitting #putter"),
                         {"retail"})
        self.assertEqual(ads_creative.themes_of("#coaching"), set())

    def test_the_rest_of_the_text_counts_only_when_the_top_names_nothing(self):
        # The opening names fitting, so the grips in the spec list are not the subject.
        self.assertEqual(ads_creative.subject(None, None, None, RUSH), {"fitting", "irons"})
        # Nothing up top: fall back to the whole text.
        self.assertEqual(ads_creative.subject("Campaign 7", "Ad 7", None,
                                              "Come and see us.\nWe regrip while you wait."),
                         {"grip"})
        self.assertEqual(ads_creative.subject(None, None, None, None), set())

    def test_grip_and_member_mean_the_service_and_the_membership(self):
        self.assertEqual(ads_creative.themes_of("Regrip special this week"), {"grip"})
        self.assertEqual(ads_creative.themes_of("Fresh grips fitted"), {"fitting", "grip"})
        self.assertEqual(ads_creative.themes_of("Tip of the week: grip pressure"), set())
        self.assertEqual(ads_creative.themes_of("Become a member today"), {"membership"})
        self.assertEqual(ads_creative.themes_of("Membership is open"), {"membership"})
        self.assertEqual(ads_creative.themes_of("Meet our newest member of staff"), set())

    def test_the_fitting_campaigns_are_fitting(self):
        self.assertEqual(ads_creative.themes_of("FitFacts"), {"fitting"})
        self.assertEqual(ads_creative.themes_of("Fit Fact leads Campaign"), {"fitting"})
        self.assertEqual(ads_creative.themes_of("Book a Club Assessment on us."), {"fitting"})


if __name__ == "__main__":
    unittest.main()
