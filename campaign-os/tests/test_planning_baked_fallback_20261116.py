"""Bag Drop's calendar said "no planning data" on prod (2026-11-16).

The volume held swing-shack.json and stick.json but no bag-drop.json, and the
reader only looked in one folder. It must fall back to the baked copy per file.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

import app as cos_app  # noqa: E402


class PlanningBakedFallbackTests(unittest.TestCase):
    def setUp(self):
        self.vol = tempfile.TemporaryDirectory()
        self.baked = tempfile.TemporaryDirectory()
        self.addCleanup(self.vol.cleanup)
        self.addCleanup(self.baked.cleanup)
        Path(self.vol.name, "stick.json").write_text(json.dumps({"from": "volume"}))
        Path(self.baked.name, "stick.json").write_text(json.dumps({"from": "baked"}))
        Path(self.baked.name, "bag-drop.json").write_text(json.dumps({"from": "baked"}))
        p1 = mock.patch.object(cos_app, "PLANNING_DIR", self.vol.name)
        p2 = mock.patch.object(cos_app, "PLANNING_DIR_BAKED", self.baked.name)
        p1.start(), p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def test_brand_missing_on_volume_reads_baked_copy(self):
        self.assertEqual(cos_app._read_planning("bag-drop"), {"from": "baked"})

    def test_volume_copy_still_wins(self):
        self.assertEqual(cos_app._read_planning("stick"), {"from": "volume"})

    def test_unknown_brand_is_none(self):
        self.assertIsNone(cos_app._read_planning("nope"))

    def test_broken_volume_file_falls_back(self):
        Path(self.vol.name, "bag-drop.json").write_text("{not json")
        self.assertEqual(cos_app._read_planning("bag-drop"), {"from": "baked"})

    def test_repo_ships_a_bag_drop_planning_file(self):
        repo = Path(__file__).resolve().parents[2] / "data" / "brand-planning" / "bag-drop.json"
        self.assertIn("lane_system", json.loads(repo.read_text()))


if __name__ == "__main__":
    unittest.main()
