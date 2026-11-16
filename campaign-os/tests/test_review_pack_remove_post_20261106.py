"""Review pack: take a post off a live pack, and put it back (2026-11-06).

Christelle asked to remove six MCM dealer posts from the pack Chantalle and Yolanda already
hold links to. There was no way to do it: posts could only be added. Now a signed-in teammate
who opens the same review link sees "Remove from pack" on each post and a "Removed posts" list
with "Put back". The client never sees either, and the client's link cannot remove anything.
A removed post is hidden, not deleted: its pictures and answers stay, so it can come back.

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
ITEMS = [{"id": "a", "title": "First post", "kind": "single"},
         {"id": "b", "title": "Second post", "kind": "single"},
         {"id": "c", "title": "Third post", "kind": "single"}]


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _fresh_module():
    for name in list(sys.modules):
        if name == "_lib.review_pack":
            del sys.modules[name]
    from _lib import review_pack

    return review_pack


class RemovePostModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-remove-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        self.rp = _fresh_module()
        self.pid = self.rp.create_pack("Posts", ITEMS)["id"]
        self.rp.add_item_image(self.pid, "b", _png())

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ids(self):
        return [i["id"] for i in self.rp.get_pack(self.pid)["items"]]

    def test_a_removed_post_leaves_the_pack_and_the_client_page(self):
        self.rp.remove_item(self.pid, "b")
        self.assertEqual(self.ids(), ["a", "c"])
        v = self.rp.public_view(self.pid, "tok", "Chantalle")
        self.assertEqual([i["id"] for i in v["pack"]["items"]], ["a", "c"])
        self.assertNotIn("removed", v)

    def test_a_removed_post_is_hidden_not_deleted(self):
        self.rp.record_decision(self.pid, "b", "hold", "Chantalle")
        self.rp.remove_item(self.pid, "b")
        removed = self.rp.removed_items(self.pid)
        self.assertEqual([r["id"] for r in removed], ["b"])
        self.assertEqual(removed[0]["title"], "Second post")
        self.assertTrue((self.tmp / "review-packs" / self.pid / "images" / "b-0-v1.png").is_file())
        self.assertEqual(self.rp.view(self.pid)["decisions"]["b"]["state"], "hold")

    def test_its_pictures_are_not_served_while_removed(self):
        self.rp.remove_item(self.pid, "b")
        self.assertIsNone(self.rp.image_path(self.pid, "b", 0))

    def test_put_back_returns_it_to_where_it_was(self):
        self.rp.remove_item(self.pid, "b")
        self.rp.restore_item(self.pid, "b")
        self.assertEqual(self.ids(), ["a", "b", "c"])
        self.assertEqual(self.rp.removed_items(self.pid), [])
        self.assertIsNotNone(self.rp.image_path(self.pid, "b", 0))

    def test_put_back_still_works_after_other_posts_moved(self):
        self.rp.remove_item(self.pid, "c")
        self.rp.remove_item(self.pid, "a")
        self.rp.restore_item(self.pid, "c")
        self.assertEqual(self.ids(), ["b", "c"])
        self.rp.restore_item(self.pid, "a")
        self.assertEqual(self.ids(), ["a", "b", "c"])

    def test_unknown_posts_are_not_found(self):
        with self.assertRaises(self.rp.NotFound):
            self.rp.remove_item(self.pid, "zzz")
        with self.assertRaises(self.rp.NotFound):
            self.rp.restore_item(self.pid, "a")
        with self.assertRaises(self.rp.NotFound):
            self.rp.remove_item("no-such-pack", "a")

    def test_the_client_page_has_no_remove_controls(self):
        page = self.rp.render_page(self.rp.public_view(self.pid, "tok", "Chantalle"), token="tok")
        self.assertIn('"staff": false', page)

    def test_the_team_view_lists_removed_posts(self):
        self.rp.remove_item(self.pid, "b")
        v = self.rp.public_view(self.pid, "tok", "Chantalle", staff=True)
        self.assertTrue(v["staff"])
        self.assertEqual([r["id"] for r in v["removed"]], ["b"])
        page = self.rp.render_page(v, token="tok")
        self.assertIn("Remove from pack", page)
        self.assertIn("Put back", page)


class RemovePostRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-remove-routes-"))
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
        self.rp = _fresh_module()
        self.pid = self.rp.create_pack("Posts", ITEMS)["id"]
        self.token = self.rp.mint_token(self.app_module._serializer, self.pid, who="Chantalle")
        self.anon = self.app_module.app.test_client(cos_anon=True)
        self.team = self.app_module.app.test_client()

    def ids(self):
        return [i["id"] for i in self.rp.get_pack(self.pid)["items"]]

    def test_removing_needs_a_signed_in_teammate(self):
        r = self.anon.post(f"/api/review-packs/{self.pid}/items/b/remove")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.ids(), ["a", "b", "c"])

    def test_the_client_link_cannot_remove(self):
        r = self.anon.post(f"/review-pack/{self.token}/remove", json={"item": "b"})
        self.assertIn(r.status_code, (404, 405))
        self.assertEqual(self.ids(), ["a", "b", "c"])

    def test_a_teammate_can_remove_and_put_back(self):
        r = self.team.post(f"/api/review-packs/{self.pid}/items/b/remove")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.ids(), ["a", "c"])
        data = self.anon.get(f"/review-pack/{self.token}/data").get_json()
        self.assertEqual([i["id"] for i in data["pack"]["items"]], ["a", "c"])
        r2 = self.team.post(f"/api/review-packs/{self.pid}/items/b/restore")
        self.assertEqual(r2.status_code, 200, r2.get_json())
        self.assertEqual(self.ids(), ["a", "b", "c"])

    def test_the_bearer_token_works_too(self):
        r = self.anon.post(f"/api/review-packs/{self.pid}/items/b/remove",
                           headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(r.status_code, 200, r.get_json())

    def test_unknown_post_is_a_404(self):
        r = self.team.post(f"/api/review-packs/{self.pid}/items/zzz/remove")
        self.assertEqual(r.status_code, 404)

    def test_the_page_shows_team_controls_only_when_signed_in(self):
        client_page = self.anon.get(f"/review-pack/{self.token}").get_data(as_text=True)
        self.assertIn('"staff": false', client_page)
        team_page = self.team.get(f"/review-pack/{self.token}").get_data(as_text=True)
        self.assertIn('"staff": true', team_page)

    def test_removed_list_never_reaches_the_client_data(self):
        self.team.post(f"/api/review-packs/{self.pid}/items/b/remove")
        data = self.anon.get(f"/review-pack/{self.token}/data").get_json()
        self.assertFalse(data["staff"])
        self.assertNotIn("removed", data)


if __name__ == "__main__":
    unittest.main()
