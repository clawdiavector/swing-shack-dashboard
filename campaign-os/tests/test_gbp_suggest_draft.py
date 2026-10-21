"""
The Today card suggests the best unapproved Google Business draft when none is
approved: ready drafts only, most-searched phrase first, then oldest waiting.

Run: python -m pytest campaign-os/tests/test_gbp_suggest_draft.py
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_gbp_reviewed_drafts import TodayCardRouteTests, _draft, _write, gbp  # noqa: E402


class SuggestDraftTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_picks_the_draft_whose_search_term_is_asked_most(self):
        _write(self.root, _draft("quiet", targetQuery="ball fitting", body="A ball fitting shows your ball.",
                                 createdAt="2026-10-01T08:00:00Z"))
        _write(self.root, _draft("busy", targetQuery="club fitting", body="Club fitting starts here.",
                                 createdAt="2026-10-10T08:00:00Z"))
        terms = [{"query": "club fitting", "impressions": 90}, {"query": "ball fitting", "impressions": 4}]
        found = gbp.suggest_draft("swing-shack", drafts_dir=self.root, terms=terms)
        self.assertEqual(found["draft"]["id"], "busy")
        self.assertIn("90", found["why"])
        self.assertEqual(found["ready_count"], 2)

    def test_oldest_ready_draft_wins_without_search_data(self):
        _write(self.root, _draft("new", createdAt="2026-10-10T08:00:00Z"))
        _write(self.root, _draft("old", createdAt="2026-10-01T08:00:00Z"))
        found = gbp.suggest_draft("swing-shack", drafts_dir=self.root, terms=[])
        self.assertEqual(found["draft"]["id"], "old")

    def test_drafts_that_cannot_be_approved_are_never_suggested(self):
        _write(self.root, _draft("nophoto", imageUrl=""))
        _write(self.root, _draft("done", status="approved"))
        _write(self.root, _draft("other-brand", brand="stick", link="https://stickgolf.co.za/"))
        found = gbp.suggest_draft("swing-shack", drafts_dir=self.root, terms=[])
        self.assertIsNone(found["draft"])
        self.assertEqual(found["blocked_count"], 1)


class SuggestionRouteTests(TodayCardRouteTests):
    def test_pending_offers_the_best_unapproved_draft_when_none_is_approved(self):
        (self.root / "card-draft.json").unlink()
        _write(self.root, _draft("waiting", imageUrl=str(self.media / "card.jpg")))
        with mock.patch.object(self.app_module._gdp, "search_terms", return_value={"terms": []}):
            res = self.client.get("/api/gbp/daily-poster/pending?brand_id=swing-shack")
        body = res.get_json()
        self.assertIsNone(body["post"])
        self.assertEqual(body["suggestion"]["post"]["draft_id"], "waiting")
        self.assertEqual(body["suggestion"]["post"]["photo_url"], "/api/intel/gmb/draft/waiting/photo-file")


# Only the new route test belongs here; the inherited ones already run in their own file.
for _name in ("test_pending_names_the_draft_and_its_photo", "test_approve_refuses_a_post_that_is_no_longer_the_one_shown"):
    setattr(SuggestionRouteTests, _name, None)


if __name__ == "__main__":
    unittest.main()
