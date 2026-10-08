"""DELETE /api/campaigns/<id> — archive-then-remove.

Runs the real Flask route against an isolated DATA_DIR. The bundled
campaign-data.json is never modified.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


CAMPAIGN_OS = Path(__file__).resolve().parents[1]


def _fixture():
    return {
        "activeCampaignId": "old-one",
        "campaigns": {
            "old-one": {
                "brand_id": "swing-shack",
                "identity": {"name": "Old One"},
                "assets": {"a1": {"approvalStatus": "review"}, "a2": {"approvalStatus": "published"}},
            },
            "old-two": {"brand_id": "swing-shack", "identity": {"name": "Old Two"}, "assets": {}},
            "other-brand": {"brand_id": "stick", "identity": {"name": "Other"}, "assets": {}},
        },
    }


class CampaignArchiveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-archive-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app

        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        cls.module.init_repo = lambda: None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        shutil.rmtree(self.tmpdir / "archive", ignore_errors=True)
        (self.tmpdir / "campaign-data.json").write_text(json.dumps(_fixture()), encoding="utf-8")

    def _data(self):
        return json.loads((self.tmpdir / "campaign-data.json").read_text(encoding="utf-8"))

    def _archives(self):
        d = self.tmpdir / "archive" / "campaigns"
        return sorted(d.glob("*.json")) if d.is_dir() else []

    def test_archives_then_removes(self):
        res = self.client.delete("/api/campaigns/old-one")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["assetsRemoved"], 2)

        data = self._data()
        self.assertNotIn("old-one", data["campaigns"])
        self.assertIn("old-two", data["campaigns"])
        self.assertIn("other-brand", data["campaigns"])

        archives = self._archives()
        self.assertEqual([p.name for p in archives], [body["archivedAs"]])
        archived = json.loads(archives[0].read_text(encoding="utf-8"))
        self.assertEqual(archived["campaignId"], "old-one")
        self.assertTrue(archived["wasActive"])
        self.assertEqual(set(archived["campaign"]["assets"]), {"a1", "a2"})

    def test_active_campaign_moves_to_same_brand(self):
        body = self.client.delete("/api/campaigns/old-one").get_json()
        self.assertEqual(body["activeCampaignId"], "old-two")
        self.assertEqual(self._data()["activeCampaignId"], "old-two")

    def test_non_active_delete_leaves_active_alone(self):
        self.client.delete("/api/campaigns/old-two")
        self.assertEqual(self._data()["activeCampaignId"], "old-one")

    def test_removing_every_campaign_clears_active(self):
        for cid in ("old-one", "old-two", "other-brand"):
            self.assertEqual(self.client.delete(f"/api/campaigns/{cid}").status_code, 200)
        data = self._data()
        self.assertEqual(data["campaigns"], {})
        self.assertIsNone(data["activeCampaignId"])
        self.assertEqual(len(self._archives()), 3)

    def test_unknown_campaign_is_404_and_writes_nothing(self):
        res = self.client.delete("/api/campaigns/nope")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self._archives(), [])
        self.assertEqual(len(self._data()["campaigns"]), 3)

    def test_failed_archive_keeps_the_campaign(self):
        with patch.object(self.module.os, "makedirs", side_effect=OSError("disk full")):
            res = self.client.delete("/api/campaigns/old-one")
        self.assertEqual(res.status_code, 500)
        self.assertIn("old-one", self._data()["campaigns"])

    def test_requires_login(self):
        anon = self.flask_app.test_client(cos_anon=True)
        res = anon.delete("/api/campaigns/old-one")
        self.assertIn(res.status_code, (302, 401))
        self.assertIn("old-one", self._data()["campaigns"])


if __name__ == "__main__":
    unittest.main()
