"""Review pack: deleting a pack (2026-11-03).

Loading the real MCM pack onto the live site dropped its connection partway and left
a half-loaded pack behind with no way to remove it. Our API can now delete a pack.
Deleting is final, so a pack the client has already answered (a decision, a comment
or an upload) is refused unless the caller says force.

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

from itsdangerous import URLSafeTimedSerializer

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TOKEN = "test-job-token-not-a-secret"
ITEMS = [{"id": "a", "title": "A post", "kind": "single"}]


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 90)).save(buf, format="PNG")
    return buf.getvalue()


class DeleteModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-delete-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack
        self.ser = URLSafeTimedSerializer("not-a-real-secret")

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_an_untouched_pack_is_deleted_and_its_link_stops_working(self):
        pid = self.rp.create_pack("Half loaded", ITEMS)["id"]
        token = self.rp.mint_token(self.ser, pid)
        self.assertTrue(self.rp.delete_pack(pid))
        self.assertIsNone(self.rp.get_pack(pid))
        self.assertIsNone(self.rp.read_token(self.ser, token))
        self.assertEqual(self.rp.list_packs(), [])

    def test_deleting_a_pack_that_is_not_there_says_so(self):
        self.assertFalse(self.rp.delete_pack("no-such-pack"))
        self.assertFalse(self.rp.delete_pack("../etc"))

    def test_a_pack_she_has_answered_is_refused_unless_forced(self):
        for act in (
            lambda pid: self.rp.record_decision(pid, "a", "approve", "Chantalle"),
            lambda pid: self.rp.add_comment(pid, "a", "Chantalle", "Hello"),
            lambda pid: self.rp.save_upload(pid, "a", _png(), original_name="a.png", source="", rights=False, who="x"),
        ):
            pid = self.rp.create_pack("Answered " + str(id(act)), ITEMS)["id"]
            act(pid)
            self.assertTrue(self.rp.has_activity(pid))
            with self.assertRaises(ValueError):
                self.rp.delete_pack(pid)
            self.assertIsNotNone(self.rp.get_pack(pid))
            self.assertTrue(self.rp.delete_pack(pid, force=True))
            self.assertIsNone(self.rp.get_pack(pid))

    def test_a_reply_from_us_does_not_count_as_her_answering(self):
        pid = self.rp.create_pack("Ours only", ITEMS)["id"]
        self.rp.add_comment(pid, "a", "Christelle", "Hi", role="us")
        self.assertFalse(self.rp.has_activity(pid))


class DeleteRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-delete-routes-"))
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
        self.pid = review_pack.create_pack("Delete me", ITEMS)["id"]

    def test_delete_needs_the_bearer_token(self):
        self.assertEqual(self.anon.delete(f"/api/jobs/review-packs/{self.pid}").status_code, 401)
        self.assertIsNotNone(self.rp.get_pack(self.pid))

    def test_an_untouched_pack_is_deleted_and_leaves_the_list(self):
        r = self.anon.delete(f"/api/jobs/review-packs/{self.pid}", headers=self.bearer)
        self.assertEqual(r.status_code, 200, r.get_json())
        listed = self.anon.get("/api/jobs/review-packs", headers=self.bearer).get_json()["packs"]
        self.assertEqual(listed, [])

    def test_a_pack_with_an_answer_in_it_is_a_409_with_plain_words_until_forced(self):
        self.rp.record_decision(self.pid, "a", "approve", "Chantalle")
        r = self.anon.delete(f"/api/jobs/review-packs/{self.pid}", headers=self.bearer)
        self.assertEqual(r.status_code, 409)
        self.assertIn("answered", r.get_json()["error"])
        self.assertIsNotNone(self.rp.get_pack(self.pid))
        r2 = self.anon.delete(f"/api/jobs/review-packs/{self.pid}?force=1", headers=self.bearer)
        self.assertEqual(r2.status_code, 200)
        self.assertIsNone(self.rp.get_pack(self.pid))

    def test_a_pack_that_is_not_there_is_a_404(self):
        self.assertEqual(self.anon.delete("/api/jobs/review-packs/no-such-pack", headers=self.bearer).status_code, 404)


if __name__ == "__main__":
    unittest.main()
