"""Weekly report v3 must not show one brand's Facebook/Instagram numbers
under another brand.

On 2026-10-07 the Stick report showed "Page fans: 450" — Swing Shack's page —
because fb-page-analytics.json was read flat with no brand check.

Run: cd campaign-os && python3 -m pytest tests/test_v2026_10_07_organic_brand_isolation.py -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from _lib import weekly_report_v3 as wr3  # noqa: E402

SS_FB = {"brand": "swing-shack",
         "page": {"id": "198859063301219", "name": "Swing Shack", "fan_count": 450}}
SS_IG = {"account": {"username": "swingshack", "followers_count": 2496}}
STICK_FB = {"brand": "stick",
            "page": {"id": "1051565264705239", "name": "Stick", "fan_count": 77}}
STICK_IG = {"account": {"username": "stick.paarl", "followers_count": 912}}


def _write(root: Path, rel: str, doc: dict) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


class OrganicBrandIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env = mock.patch.dict(
            os.environ, {"CAMPAIGN_OS_DATA_DIR": str(self.root)})
        self._env.start()
        _write(self.root, "fb-page-analytics.json", SS_FB)
        _write(self.root, "ig-business-analytics.json", SS_IG)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_stick_does_not_inherit_swing_shack_flat_files(self):
        out = wr3._read_organic_from_cache("stick")
        self.assertIsNone(out["fb"])
        self.assertIsNone(out["ig"])

    def test_swing_shack_still_reads_flat_files(self):
        out = wr3._read_organic_from_cache("swing-shack")
        self.assertEqual(out["fb"]["fans"], 450)
        self.assertEqual(out["ig"]["followers"], 2496)

    def test_flat_fb_file_without_brand_key_is_matched_on_page_name(self):
        _write(self.root, "fb-page-analytics.json",
               {"page": {"name": "Swing Shack", "fan_count": 450}})
        self.assertIsNone(wr3._read_organic_from_cache("stick")["fb"])
        self.assertEqual(
            wr3._read_organic_from_cache("swing-shack")["fb"]["fans"], 450)

    def test_brand_lane_files_win(self):
        _write(self.root, "brands/stick/fb-page-analytics.json", STICK_FB)
        _write(self.root, "brands/stick/ig-business-analytics.json", STICK_IG)
        out = wr3._read_organic_from_cache("stick")
        self.assertEqual(out["fb"]["fans"], 77)
        self.assertEqual(out["fb"]["page_name"], "Stick")
        self.assertEqual(out["ig"]["followers"], 912)
        ss = wr3._read_organic_from_cache("swing-shack")
        self.assertEqual(ss["fb"]["fans"], 450)


if __name__ == "__main__":
    unittest.main()
