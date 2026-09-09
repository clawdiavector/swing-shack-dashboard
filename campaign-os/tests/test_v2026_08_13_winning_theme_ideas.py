"""Tests for the winning-theme ideas endpoint + reels-vs-images awareness.

v2026-08-13: validates:
  - /api/intel/winning_theme_ideas returns the expected shape
  - Format is decided from data (auto) or override
  - Reel-only mode returns reel caption examples
  - Theme labels in titles are human-readable, not raw slugs
  - booking_cta is never rendered literally in a title

Run: cd campaign-os && DATA_DIR=./data python3 -m pytest tests/test_v2026_08_13_winning_theme_ideas.py -v
"""
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

# Make the campaign-os dir importable so 'from app import app' works
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("DATA_DIR", str(HERE.parent / "data"))

# Set DATA_DIR to the real data directory for the test
DATA_DIR = HERE.parent / "data"
os.environ["DATA_DIR"] = str(DATA_DIR)

from app import app  # noqa: E402


class WinningThemeIdeasTest(unittest.TestCase):
    """Test /api/intel/winning_theme_ideas endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        # Auth gate is enforced; login first with the dev password
        cls.client.post("/login", data={"password": "swing-shack-dev-2026"})

    def test_endpoint_returns_ok(self):
        r = self.client.get("/api/intel/winning_theme_ideas?n=5")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("ideas", data)
        self.assertIn("themes_used", data)
        self.assertIn("format_used", data)

    def test_ideas_have_required_fields(self):
        r = self.client.get("/api/intel/winning_theme_ideas?n=5")
        data = r.get_json()
        ideas = data["ideas"]
        self.assertGreater(len(ideas), 0, "Expected at least 1 idea")
        for idea in ideas:
            self.assertIn("title", idea)
            self.assertIn("caption_hook", idea)
            self.assertIn("format", idea)
            self.assertIn("themes", idea)
            self.assertIn("why", idea)
            self.assertIn("source", idea)

    def test_booking_cta_not_in_title(self):
        """booking_cta theme must never appear as a literal token in titles."""
        r = self.client.get("/api/intel/winning_theme_ideas?n=10")
        data = r.get_json()
        for idea in data["ideas"]:
            title = idea["title"].lower()
            self.assertNotIn("booking_cta", title,
                             f"Title contains literal 'booking_cta': {idea['title']}")
            self.assertNotIn("booking cta", title,
                             f"Title contains literal 'booking cta': {idea['title']}")

    def test_format_auto_picks_winning_format_from_data(self):
        r = self.client.get("/api/intel/winning_theme_ideas?n=5&format=auto")
        data = r.get_json()
        self.assertIn(data["format_used"], ("reel", "image"))

    def test_format_override_image(self):
        r = self.client.get("/api/intel/winning_theme_ideas?n=5&format=image")
        data = r.get_json()
        self.assertEqual(data["format_used"], "image")
        for idea in data["ideas"]:
            self.assertEqual(idea["format"], "image")

    def test_format_override_reel(self):
        r = self.client.get("/api/intel/winning_theme_ideas?n=5&format=reel")
        data = r.get_json()
        self.assertEqual(data["format_used"], "reel")
        for idea in data["ideas"]:
            self.assertEqual(idea["format"], "reel")

    def test_themes_override(self):
        r = self.client.get(
            "/api/intel/winning_theme_ideas?n=3&themes_override=club_fitting,golf_lessons"
        )
        data = r.get_json()
        self.assertEqual(data["themes_used"], ["club_fitting", "golf_lessons"])
        for idea in data["ideas"]:
            self.assertEqual(idea["themes"], ["club_fitting", "golf_lessons"])

    def test_n_limits_to_max_10(self):
        r = self.client.get("/api/intel/winning_theme_ideas?n=20")
        data = r.get_json()
        # The endpoint clamps to max 10. Inspiration examples can extend it
        # by 2. So we expect <= 12 ideas.
        self.assertLessEqual(len(data["ideas"]), 12)

    def test_em_dash_free_in_user_facing_fields(self):
        """No em-dashes in titles or hooks (standing rule)."""
        r = self.client.get("/api/intel/winning_theme_ideas?n=5")
        data = r.get_json()
        em = chr(0x2014)
        for idea in data["ideas"]:
            for fld in ("title", "caption_hook", "why"):
                self.assertNotIn(em, idea[fld],
                                 f"Em-dash in {fld}: {idea[fld][:80]}")


class PostConversionScoreReelsTest(unittest.TestCase):
    """Test that the post-conversion-score JSON includes reels + images."""

    def test_post_conversion_score_json_has_reels_and_images(self):
        pcs_path = DATA_DIR / "post-conversion-score.json"
        self.assertTrue(pcs_path.exists(), "post-conversion-score.json not found")
        with open(pcs_path) as f:
            pcs = json.load(f)
        summary = pcs.get("summary", {})
        self.assertIn("reel_count", summary)
        self.assertIn("image_count", summary)
        self.assertIn("winning_format", summary)
        self.assertGreater(summary["reel_count"] + summary["image_count"], 0)

    def test_posts_ranked_include_format_type(self):
        pcs_path = DATA_DIR / "post-conversion-score.json"
        with open(pcs_path) as f:
            pcs = json.load(f)
        ranked = pcs["posts_ranked"]
        self.assertGreater(len(ranked), 0)
        for p in ranked:
            self.assertIn("format_type", p)
            self.assertIn(p["format_type"], ("reel", "image"),
                          f"Unknown format_type: {p['format_type']}")

    def test_recommendation_includes_next_post_format(self):
        pcs_path = DATA_DIR / "post-conversion-score.json"
        with open(pcs_path) as f:
            pcs = json.load(f)
        rec = pcs["recommendation"]
        self.assertIn("next_post_format", rec)
        self.assertIn(rec["next_post_format"], ("reel", "image"))
        # Should also have separate reel/image buckets
        self.assertIn("reel_themes", rec)
        self.assertIn("image_themes", rec)


if __name__ == "__main__":
    unittest.main()
