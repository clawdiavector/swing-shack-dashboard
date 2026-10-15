"""A date on the yearly event spine, with no saved Calendar record, must
resolve for the Brief. The Plan alert banner lists spine dates, and its
"Make a plan" button died with "opportunity '...' not found" without this."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import campaign_brief as cb  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data"


class SpineResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Production: the volume holds a brand-planning/ with no events files in
        # it; the events live in the copy baked into the image (repo data/).
        os.makedirs(Path(self.tmp.name) / "brand-planning")
        self.patches = [
            patch.object(cb, "DATA_DIR_DEFAULT", self.tmp.name),
            patch.object(cb, "get_brief_opportunities", return_value=[]),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_spine_only_date_resolves(self):
        opp = cb._resolve_opportunity("stick", "black-friday-2026")
        self.assertEqual(opp["event_key"], "black-friday-2026")
        self.assertEqual(opp["name"], "Black Friday + Cyber Monday")
        self.assertEqual(opp["date"], "2026-10-12")
        self.assertEqual(opp["date_confidence"], "MEDIUM")  # LOW is a hard gate failure
        self.assertEqual(opp["source"], "spine")

    def test_unknown_date_still_not_found(self):
        self.assertEqual(cb._resolve_opportunity("stick", "nope-2026"), {})
        self.assertEqual(cb._resolve_opportunity("stick", ""), {})


if __name__ == "__main__":
    unittest.main()
