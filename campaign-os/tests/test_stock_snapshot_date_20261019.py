"""Stock import can date its snapshot, so a re-import replaces the week it belongs to (2026-10-19)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

HEADER = "Location,Product Name,Variant Choices,SKU,Movement Type,Quantity,Alert Level\n"
CSV = HEADER + ",Callaway Chrome Tour,Chrome Tour X,CTX,,15,3\n,Ball A,,A1,,8,2\n"

_SAVED = os.environ.get("DATA_DIR")


def setUpModule():
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cos-snapshot-date-")


def tearDownModule():
    if _SAVED is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = _SAVED


class SnapshotDateTests(unittest.TestCase):
    def test_import_with_a_date_saves_that_days_snapshot(self):
        from _lib import stock_pulse as sp
        from _lib.stock_importer import commit_smart_import
        out = commit_smart_import(CSV, store_brand="stick", snapshot_date="2026-10-16")
        self.assertEqual([s["date"] for s in sp.load_snapshots("stick")], ["2026-10-16"])
        self.assertEqual(out["stock_pulse"]["snapshots"], 1)

    def test_same_date_again_replaces_it_not_adds(self):
        from _lib import stock_pulse as sp
        from _lib.stock_importer import commit_smart_import
        commit_smart_import(CSV, store_brand="swing-shack", snapshot_date="2026-10-16")
        out = commit_smart_import(CSV, store_brand="swing-shack", snapshot_date="2026-10-16")
        self.assertEqual(out["stock_pulse"]["snapshots"], 1)

    def test_route_refuses_a_bad_or_future_date(self):
        os.environ.setdefault("COS_JOB_TOKEN", "t")
        import app as m
        c = m.app.test_client()
        c.set_cookie(m.SESSION_COOKIE, m._serializer.dumps({"u": "test"}))
        for bad in ("not-a-date", "2999-01-01"):
            r = c.post("/api/lanes/stock/smart-commit",
                       json={"brand_id": "stick", "csv_content": CSV, "snapshot_date": bad})
            self.assertEqual(r.status_code, 400, bad)


if __name__ == "__main__":
    unittest.main()
