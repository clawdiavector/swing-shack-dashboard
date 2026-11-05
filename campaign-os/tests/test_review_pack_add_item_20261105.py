"""Review pack: add a post to a pack that is already live (2026-11-05).

Christelle wants a new design added to the MCM pack Chantalle and Yolanda already hold links
to. A pack's posts were fixed when it was created, so the only way was a new pack and new
links, which confuses the client. Our API can now add a post to an existing pack.

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
ITEMS = [{"id": "a", "title": "First post", "kind": "single"}]
NEW = {"id": "b1", "title": "Find the car that says yes back", "kind": "single", "caption": "Hello",
       "channels": "Instagram, Facebook", "when": "Not yet scheduled", "audience": "Consumers"}


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 90)).save(buf, format="PNG")
    return buf.getvalue()


class AddItemModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-additem-"))
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

    def test_a_new_post_joins_the_end_of_the_pack(self):
        item = self.rp.add_item(self.pid, NEW)
        self.assertEqual(item["id"], "b1")
        self.assertEqual(item["version"], 1)
        self.assertEqual(item["images"], [])
        ids = [i["id"] for i in self.rp.get_pack(self.pid)["items"]]
        self.assertEqual(ids, ["a", "b1"])

    def test_a_picture_can_be_added_to_the_new_post_afterwards(self):
        self.rp.add_item(self.pid, NEW)
        self.rp.add_item_image(self.pid, "b1", _png())
        self.assertEqual(len(self.rp.get_pack(self.pid)["items"][1]["images"]), 1)

    def test_answers_already_given_stay_put(self):
        self.rp.record_decision(self.pid, "a", "approve", "Chantalle")
        self.rp.add_item(self.pid, NEW)
        self.assertEqual(self.rp.view(self.pid)["decisions"]["a"]["state"], "approve")

    def test_the_client_page_data_includes_the_new_post(self):
        self.rp.add_item(self.pid, NEW)
        v = self.rp.public_view(self.pid, "tok", "Chantalle")
        self.assertEqual([i["id"] for i in v["pack"]["items"]], ["a", "b1"])

    def test_a_clash_of_ids_is_refused(self):
        with self.assertRaises(ValueError):
            self.rp.add_item(self.pid, {**NEW, "id": "a"})

    def test_a_post_needs_a_title_and_a_known_kind(self):
        with self.assertRaises(ValueError):
            self.rp.add_item(self.pid, {"id": "x"})
        with self.assertRaises(ValueError):
            self.rp.add_item(self.pid, {**NEW, "kind": "nonsense"})

    def test_a_missing_pack_is_not_found(self):
        with self.assertRaises(self.rp.NotFound):
            self.rp.add_item("no-such-pack", NEW)

    def test_the_page_tells_a_client_with_the_page_open_that_a_post_was_added(self):
        page = self.rp.render_page(self.rp.public_view(self.pid, "tok", "Chantalle"), token="tok")
        self.assertIn("A new post was added", page)


class AddItemRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-additem-routes-"))
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

    def test_adding_a_post_needs_the_bearer_token(self):
        r = self.anon.post(f"/api/jobs/review-packs/{self.pid}/items", json=NEW)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(len(self.rp.get_pack(self.pid)["items"]), 1)

    def test_adding_a_post_works_and_the_picture_route_then_accepts_it(self):
        r = self.anon.post(f"/api/jobs/review-packs/{self.pid}/items", json=NEW, headers=self.bearer)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["item_id"], "b1")
        r2 = self.anon.post(f"/api/jobs/review-packs/{self.pid}/items/b1/image", headers=self.bearer,
                            data={"file": (io.BytesIO(_png()), "b1.png")}, content_type="multipart/form-data")
        self.assertEqual(r2.status_code, 200, r2.get_json())

    def test_a_clash_is_a_400_and_a_missing_pack_a_404(self):
        self.anon.post(f"/api/jobs/review-packs/{self.pid}/items", json=NEW, headers=self.bearer)
        again = self.anon.post(f"/api/jobs/review-packs/{self.pid}/items", json=NEW, headers=self.bearer)
        self.assertEqual(again.status_code, 400)
        gone = self.anon.post("/api/jobs/review-packs/no-such-pack/items", json=NEW, headers=self.bearer)
        self.assertEqual(gone.status_code, 404)


if __name__ == "__main__":
    unittest.main()
