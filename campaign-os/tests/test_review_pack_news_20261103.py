"""Review pack: what is new since the last look (2026-11-03).

Nothing tells Christelle when the client answers a pack. The Mac watcher (like the
morning message) needs a bearer route that returns ready-to-send plain text plus
counts for "what happened since <time>", and sends nothing itself. Stateless: the
caller keeps the time it last looked.

Requirement-Owner: Christelle
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TOKEN = "test-job-token-not-a-secret"
ITEMS = [
    {"id": "a", "title": "Dealer post", "kind": "single"},
    {"id": "b", "title": "Consumer post", "kind": "single"},
]


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 90)).save(buf, format="PNG")
    return buf.getvalue()


class NewsModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-news-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack
        self.pid = review_pack.create_pack("Posts", ITEMS)["id"]

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_quiet_pack_is_empty_and_says_nothing(self):
        n = self.rp.news(self.pid, "")
        self.assertTrue(n["empty"])
        self.assertEqual(n["text"], "")
        self.assertEqual(n["counts"], {"approved": 0, "rejected": 0, "held": 0, "picked": 0, "comments": 0, "uploads": 0})

    def test_everything_she_did_is_counted_and_named(self):
        self.rp.record_decision(self.pid, "a", "approve", "Chantalle")
        self.rp.record_decision(self.pid, "b", "reject", "Chantalle")
        self.rp.add_comment(self.pid, "a", "Chantalle", "Change the headline", tag="copy edit")
        self.rp.save_upload(self.pid, "a", _png(), original_name="x.png", source="mine", rights=True, who="Chantalle")
        n = self.rp.news(self.pid, "")
        self.assertFalse(n["empty"])
        self.assertEqual(n["counts"]["approved"], 1)
        self.assertEqual(n["counts"]["rejected"], 1)
        self.assertEqual(n["counts"]["comments"], 1)
        self.assertEqual(n["counts"]["uploads"], 1)
        for word in ("Chantalle", "Dealer post", "Consumer post", "copy edit"):
            self.assertIn(word, n["text"])

    def test_only_what_happened_after_since_is_reported(self):
        self.rp.record_decision(self.pid, "a", "approve", "Chantalle")
        first = self.rp.news(self.pid, "")
        later = "9999-01-01T00:00:00Z"
        self.assertTrue(self.rp.news(self.pid, later)["empty"])
        self.assertTrue(first["now"] > "2000")
        self.assertTrue(self.rp.news(self.pid, "2000-01-01T00:00:00Z")["counts"]["approved"] == 1)

    def test_our_own_replies_are_not_news(self):
        self.rp.add_comment(self.pid, "a", "Christelle", "Thanks", role="us")
        self.assertTrue(self.rp.news(self.pid, "")["empty"])

    def test_a_design_pick_that_is_not_yet_approved_counts_as_picked(self):
        pid = self.rp.create_pack("Choice", [{"id": "c", "title": "Pick", "kind": "choice"}])["id"]
        # a pack with a choice item needs pictures; record the pick directly on the stored row
        import json
        d = self.rp._pack_dir(pid)
        (d / "decisions.json").write_text(json.dumps({"c": {"state": "pending", "by": "Chantalle", "at": "2026-11-03T10:00:00Z", "choice": "B"}}))
        n = self.rp.news(pid, "")
        self.assertEqual(n["counts"]["picked"], 1)
        self.assertEqual(n["counts"]["approved"], 0)

    def test_a_missing_pack_is_not_found(self):
        with self.assertRaises(self.rp.NotFound):
            self.rp.news("no-such-pack", "")


class NewsRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-news-routes-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        os.environ["COS_JOB_TOKEN"] = TOKEN
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
        self.app_module.COS_JOB_TOKEN = TOKEN
        for child in self.tmpdir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack
        self.anon = self.app_module.app.test_client(cos_anon=True)
        self.bearer = {"Authorization": f"Bearer {TOKEN}"}
        self.pid = review_pack.create_pack("Posts", ITEMS)["id"]

    def test_news_needs_the_bearer_token(self):
        self.assertEqual(self.anon.get(f"/api/jobs/review-packs/{self.pid}/news").status_code, 401)

    def test_news_returns_text_and_counts_and_a_time_to_ask_from_next(self):
        self.rp.record_decision(self.pid, "a", "approve", "Chantalle")
        r = self.anon.get(f"/api/jobs/review-packs/{self.pid}/news", headers=self.bearer)
        self.assertEqual(r.status_code, 200, r.get_json())
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertFalse(j["empty"])
        self.assertEqual(j["counts"]["approved"], 1)
        self.assertIn("Dealer post", j["text"])
        self.assertTrue(j["now"])
        again = self.anon.get(f"/api/jobs/review-packs/{self.pid}/news?since={j['now']}", headers=self.bearer).get_json()
        self.assertTrue(again["empty"])

    def test_news_for_a_missing_pack_is_a_404(self):
        self.assertEqual(self.anon.get("/api/jobs/review-packs/no-such-pack/news", headers=self.bearer).status_code, 404)


if __name__ == "__main__":
    unittest.main()
