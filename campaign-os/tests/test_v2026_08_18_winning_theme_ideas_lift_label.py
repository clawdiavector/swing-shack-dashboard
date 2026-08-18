"""v2026_08_18: winning-theme-ideas "why" line sources the lift from data,
not a hard-coded "+267%" string. Catches the trap where the template ships
a literal number that drifts from the underlying post-conversion-score data.

Run: cd campaign-os && DATA_DIR=../data python3 -m pytest tests/test_v2026_08_18_winning_theme_ideas_lift_label.py -v
"""
import os
import sys
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ["DATA_DIR"] = str(HERE.parent / "data")
DATA_DIR = HERE.parent / "data"
os.environ["DATA_DIR"] = str(DATA_DIR)

from app import app


class WinningThemeIdeasLiftLabelTest(unittest.TestCase):
    """Ensure the booking-CTA template's "why" line sources the lift number
    from the actual post-conversion-score data, not a hard-coded literal."""

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.client.post("/login", data={"password": "swing-shack-dev-2026"})

    def _pcs_top_lift(self):
        with open(DATA_DIR / "post-conversion-score.json") as f:
            pcs = json.load(f)
        ranked = pcs.get("posts_ranked") or []
        if not ranked:
            return None
        v = ranked[0].get("lift_vs_baseline_pct")
        if isinstance(v, (int, float)) and v > 0:
            return round(float(v))
        return None

    def test_no_hardcoded_267_in_why_line(self):
        """The first template's why-line must NOT contain the literal
        '+267%' string that pre-fix shipped as a hard-coded literal."""
        r = self.client.get("/api/intel/winning_theme_ideas?n=5")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get("ok"))
        ideas = data["ideas"]
        self.assertGreater(len(ideas), 0)
        first_why = ideas[0]["why"]
        # The old hard-coded substring must be gone.
        self.assertNotIn("Booking-CTA posts historically drive +267%", first_why,
                         "Hard-coded '+267%' string leaked into the why line. "
                         "Source the number from post-conversion-score.json instead.")

    def test_why_line_carries_real_lift_from_data(self):
        """The why line should display the actual top-post lift value
        sourced from posts_ranked[0].lift_vs_baseline_pct."""
        top_lift = self._pcs_top_lift()
        if top_lift is None:
            self.skipTest("post-conversion-score.json has no top-post lift to source")
        r = self.client.get("/api/intel/winning_theme_ideas?n=5")
        data = r.get_json()
        first_why = data["ideas"][0]["why"]
        # The line should reference the actual lift number, not a fabricated one.
        expected_token = f"+{top_lift}%"
        self.assertIn(expected_token, first_why,
                      f"Expected the data-sourced lift number ({expected_token}) in the why line, "
                      f"got: {first_why!r}")

    def test_why_line_no_fabricated_lift_when_data_missing(self):
        """If posts_ranked[0] has no lift (or no posts_ranked), the line
        should fall back to a non-numeric phrasing — never invent a percent."""
        # Read the production source and check the fallback path is wired.
        import re
        src_path = HERE / "app.py"
        with open(src_path) as f:
            src = f.read()
        # Find the function body and assert the fallback message shape exists.
        self.assertIn("Top posts beat the /bookings/ baseline", src,
                      "Fallback non-numeric phrasing missing from the endpoint. "
                      "Add a fallback so an empty posts_ranked does not silently "
                      "fabricate a number.")
        # The fallback must be reachable (no early-return that bypasses it).
        self.assertIn("top_lift_pct = None", src,
                      "Lift-detection block missing; cannot confirm fallback wiring.")

    def test_em_dash_free_in_why_line(self):
        """Standing rule: no em-dashes in published copy."""
        em = chr(0x2014)
        r = self.client.get("/api/intel/winning_theme_ideas?n=5")
        data = r.get_json()
        for idea in data["ideas"]:
            self.assertNotIn(em, idea["why"], f"Em-dash in why: {idea['why'][:120]}")


if __name__ == "__main__":
    unittest.main()
