"""Review pack: picking a design is not approving it (2026-11-03).

On a post with options A, B and C she taps the design she likes. That records her
choice but does NOT approve the post: the badge says which option she picked and the
post stays waiting until she presses Approve, Reject or Hold. Found by clicking
through the real page: the first version approved on the first tap.

Requirement-Owner: Christelle
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

ITEMS = [
    {"id": "first-car", "title": "Your first car, matched.", "kind": "choice"},
    {"id": "day-1", "title": "Day 1. Day 40.", "kind": "single"},
]


class ChoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-choice-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack
        self.pack = review_pack.create_pack("Choice", ITEMS)["id"]

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_picking_a_design_keeps_the_post_waiting(self):
        row = self.rp.record_choice(self.pack, "first-car", "B", "Chantalle")
        self.assertEqual((row["state"], row["choice"]), ("pending", "B"))
        self.assertEqual(self.rp.view(self.pack)["decisions"]["first-car"]["state"], "pending")

    def test_the_choice_survives_the_decision_and_can_be_changed(self):
        self.rp.record_choice(self.pack, "first-car", "B", "Chantalle")
        self.rp.record_decision(self.pack, "first-car", "approve", "Chantalle")
        d = self.rp.view(self.pack)["decisions"]["first-car"]
        self.assertEqual((d["state"], d["choice"]), ("approve", "B"))
        self.rp.record_choice(self.pack, "first-car", "C", "Chantalle")
        d = self.rp.view(self.pack)["decisions"]["first-car"]
        self.assertEqual((d["state"], d["choice"]), ("approve", "C"))

    def test_only_a_choice_post_takes_a_choice_and_only_a_b_or_c(self):
        with self.assertRaises(ValueError):
            self.rp.record_choice(self.pack, "day-1", "A", "Chantalle")
        with self.assertRaises(ValueError):
            self.rp.record_choice(self.pack, "first-car", "Z", "Chantalle")
        with self.assertRaises(self.rp.NotFound):
            self.rp.record_choice(self.pack, "no-such-item", "A", "Chantalle")


class ChoiceRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-choice-routes-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        import app as app_module

        cls.app_module = app_module

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        self.app_module.DATA_DIR = str(self.tmpdir)
        for child in self.tmpdir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack
        self.pack = review_pack.create_pack("Choice", ITEMS)["id"]
        token = review_pack.mint_token(self.app_module._serializer, self.pack, who="Chantalle")
        self.base = f"/review-pack/{token}"
        self.anon = self.app_module.app.test_client(cos_anon=True)

    def test_a_tap_on_a_design_sends_only_the_choice_and_does_not_approve(self):
        r = self.anon.post(self.base + "/act", json={"item": "first-car", "choice": "B"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["decision"]["state"], "pending")
        self.assertEqual(self.rp.view(self.pack)["decisions"]["first-car"]["choice"], "B")

    def test_a_post_with_neither_a_state_nor_a_choice_is_a_400(self):
        self.assertEqual(self.anon.post(self.base + "/act", json={"item": "first-car"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
