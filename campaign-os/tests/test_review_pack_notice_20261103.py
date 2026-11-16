"""Review pack: a notice at the top of the page (2026-11-03).

Christelle's rule (2026-10-28): confirm the rights before any sourced image is used.
The 20 MCM designs use carmaker photos whose licence is not confirmed, so the pack
page must say so plainly at the top, in words the client reads before she approves.

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

TOKEN = "test-job-token-not-a-secret"
ITEMS = [{"id": "a", "title": "A post", "kind": "single"}]
NOTICE = "The car photos are the carmakers' own and are examples until we have permission."


class NoticeModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-notice-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_notice_is_saved_with_the_pack_and_defaults_to_none(self):
        pack = self.rp.create_pack("With notice", ITEMS, notice=NOTICE)
        self.assertEqual(self.rp.get_pack(pack["id"])["notice"], NOTICE)
        self.assertEqual(self.rp.create_pack("Without", ITEMS)["notice"], "")

    def test_a_very_long_notice_is_cut_short(self):
        pack = self.rp.create_pack("Long", ITEMS, notice="x" * 5000)
        self.assertLessEqual(len(pack["notice"]), 800)

    def test_the_notice_reaches_the_page_and_cannot_inject_markup(self):
        pack = self.rp.create_pack("Safe", ITEMS, notice="<script>alert(1)</script> " + NOTICE)
        data = self.rp.public_view(pack["id"], "tok")
        self.assertIn(NOTICE, data["pack"]["notice"])
        page = self.rp.render_page(data, token="tok")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn('id="notice"', page)


class NoticeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-notice-routes-"))
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
        self.anon = self.app_module.app.test_client(cos_anon=True)
        self.bearer = {"Authorization": f"Bearer {TOKEN}"}

    def test_our_api_takes_a_notice_and_her_page_shows_it(self):
        r = self.anon.post("/api/jobs/review-packs", headers=self.bearer,
                           json={"title": "Fresh", "client": "Chantalle", "notice": NOTICE, "items": ITEMS})
        self.assertEqual(r.status_code, 200, r.get_json())
        pid = r.get_json()["pack_id"]
        share = self.anon.post(f"/api/jobs/review-packs/{pid}/share", headers=self.bearer, json={}).get_json()
        path = share["share_url"][share["share_url"].index("/review-pack/"):]
        page = self.anon.get(path).get_data(as_text=True)
        self.assertIn("carmakers", page)


if __name__ == "__main__":
    unittest.main()
