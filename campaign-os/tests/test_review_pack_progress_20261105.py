"""Review pack: a progress line and an "I'm done" button (2026-11-05).

Chantalle gets lost easily and nothing tells us when she has finished. The page now says
"6 of 20 answered" with a jump to the next post, and an "I'm done" button that records that
she has finished. Done is a note for us: it shows in the news (so the watcher can ping) and
counts as her having answered. It never schedules, sends or posts anything.

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
ITEMS = [
    {"id": "a", "title": "Dealer post", "kind": "single"},
    {"id": "b", "title": "Consumer post", "kind": "single"},
]


class DoneModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-done-"))
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

    def test_marking_done_records_who_and_when(self):
        row = self.rp.mark_done(self.pid, "Chantalle")
        self.assertEqual(row["by"], "Chantalle")
        self.assertTrue(row["at"].endswith("Z"))

    def test_the_page_data_says_who_is_done_and_which_one_is_you(self):
        self.rp.mark_done(self.pid, "Chantalle")
        v = self.rp.public_view(self.pid, "tok", "chantalle ")
        self.assertEqual(len(v["done"]), 1)
        self.assertTrue(v["done"][0]["mine"])
        self.assertRegex(v["done"][0]["colour"], r"^#[0-9a-f]{6}$")
        other = self.rp.public_view(self.pid, "tok", "Yolanda")
        self.assertFalse(other["done"][0]["mine"])

    def test_nobody_done_means_an_empty_list(self):
        self.assertEqual(self.rp.public_view(self.pid, "tok", "Yolanda")["done"], [])

    def test_done_is_news_and_names_who(self):
        self.rp.mark_done(self.pid, "Chantalle")
        n = self.rp.news(self.pid, "")
        self.assertFalse(n["empty"])
        self.assertEqual(n["done"], ["Chantalle"])
        self.assertIn("Chantalle", n["text"])
        self.assertIn("done", n["text"].lower())

    def test_done_before_since_is_not_news_again(self):
        self.rp.mark_done(self.pid, "Chantalle")
        n = self.rp.news(self.pid, "9999-01-01T00:00:00Z")
        self.assertTrue(n["empty"])
        self.assertEqual(n["done"], [])

    def test_pressing_done_again_is_news_again(self):
        first = self.rp.mark_done(self.pid, "Chantalle")
        again = self.rp.news(self.pid, first["at"])
        self.assertTrue(again["empty"])
        import json
        d = self.rp._pack_dir(self.pid)
        rows = json.loads((d / "done.json").read_text())
        key = next(iter(rows))
        rows[key]["at"] = "2999-01-01T00:00:00Z"
        (d / "done.json").write_text(json.dumps(rows))
        self.assertEqual(self.rp.news(self.pid, first["at"])["done"], ["Chantalle"])

    def test_done_counts_as_her_having_answered_so_delete_is_refused(self):
        self.assertFalse(self.rp.has_activity(self.pid))
        self.rp.mark_done(self.pid, "Chantalle")
        self.assertTrue(self.rp.has_activity(self.pid))
        with self.assertRaises(ValueError):
            self.rp.delete_pack(self.pid)

    def test_the_page_has_a_progress_line_a_next_button_and_a_done_button(self):
        page = self.rp.render_page(self.rp.public_view(self.pid, "tok", "Chantalle"), token="tok")
        self.assertIn("answered", page)
        self.assertIn("Next post", page)
        self.assertIn("I'm done", page)
        self.assertIn("/done", page)


class DoneRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-done-routes-"))
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
        self.token = review_pack.mint_token(self.app_module._serializer, self.pid, "Chantalle")

    def test_done_with_a_good_link_is_recorded_under_her_name(self):
        r = self.anon.post(f"/review-pack/{self.token}/done")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["done"]["by"], "Chantalle")
        data = self.anon.get(f"/review-pack/{self.token}/data").get_json()
        self.assertTrue(data["done"][0]["mine"])

    def test_done_with_a_bad_link_is_a_404_and_records_nothing(self):
        r = self.anon.post("/review-pack/not-a-real-token/done")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(self.rp.has_activity(self.pid))

    def test_the_bearer_news_route_reports_done(self):
        self.anon.post(f"/review-pack/{self.token}/done")
        j = self.anon.get(f"/api/jobs/review-packs/{self.pid}/news", headers=self.bearer).get_json()
        self.assertEqual(j["done"], ["Chantalle"])
        self.assertFalse(j["empty"])


if __name__ == "__main__":
    unittest.main()
