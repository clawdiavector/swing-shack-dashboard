"""Review pack: a deal pack looks nothing like a post pack, and never says "lesson" (2026-11-13).

Christelle, 13 Nov 2026: Herman was sent the Christmas deals on the same review page we use
for posts. Each deal was a picture card with Feed/Story/Google tabs and "Next post", so he
read them as posts ("It still feels like I'm the intern doing very basic checking on these
posts"). A deal pack must say plainly that it holds deals, not posts, and look different.

Her second rule, same day: the word "lesson" must never appear in front of Herman. Both brand
bibles say "Coaching, never lesson" (data/brand-directory/stick/north_stars.json,
data/brand-planning/swing-shack.json: use_coaching_never_lesson). The pack refuses the word in
anything we write onto it; what the client writes himself is his.

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
DEALS = [
    {"id": "how", "title": "How to answer", "kind": "note", "caption": "Yes or no on each deal."},
    {"id": "deal-01", "title": "1. Putter + free fitting (Stick)", "kind": "single",
     "caption": "Buy a L.A.B. putter, get the putter fitting free.", "when": "18 Nov - 31 Dec",
     "audience": "Stick"},
]
POSTS = [{"id": "a", "title": "A post", "kind": "single"}]


class _Module(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-deals-"))
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


class DealPackLooksDifferent(_Module):
    def test_a_pack_can_be_made_as_deals_and_posts_stay_the_default(self):
        deals = self.rp.create_pack("Christmas deals", DEALS, kind="deals")
        self.assertEqual(self.rp.get_pack(deals["id"])["kind"], "deals")
        posts = self.rp.create_pack("Posts", POSTS)
        self.assertNotEqual(self.rp.get_pack(posts["id"]).get("kind"), "deals")

    def test_an_unknown_pack_kind_is_refused(self):
        with self.assertRaises(ValueError):
            self.rp.create_pack("Odd", POSTS, kind="banana")

    def test_the_deal_view_speaks_of_deals_not_posts(self):
        pack = self.rp.create_pack("Christmas deals", DEALS, kind="deals")
        data = self.rp.public_view(pack["id"], "tok")
        self.assertEqual(data["mode"], "deals")
        self.assertEqual(data["words"], {"one": "deal", "many": "deals"})
        self.assertIn("not posts", data["intro"].lower())
        self.assertNotIn("post", data["intro"].lower().replace("not posts", ""))
        self.assertEqual(data["labels"]["approve"], "Yes, run it")
        self.assertEqual(data["labels"]["hold"], "Change it")

    def test_a_post_view_keeps_its_post_words(self):
        pack = self.rp.create_pack("Posts", POSTS)
        data = self.rp.public_view(pack["id"], "tok")
        self.assertEqual(data.get("mode", "posts"), "posts")
        self.assertEqual(data["words"], {"one": "post", "many": "posts"})

    def test_the_deal_page_has_a_deals_banner_and_the_post_page_does_not(self):
        deals = self.rp.create_pack("Christmas deals", DEALS, kind="deals")
        page = self.rp.render_page(self.rp.public_view(deals["id"], "tok"), token="tok")
        self.assertIn('class="mode-deals"', page)
        self.assertIn("Deals, not posts", page)
        posts = self.rp.create_pack("Posts", POSTS)
        page = self.rp.render_page(self.rp.public_view(posts["id"], "tok"), token="tok")
        self.assertNotIn('class="mode-deals"', page)
        self.assertNotIn("Deals, not posts", page)


class NeverLesson(_Module):
    def test_lesson_in_an_item_is_refused_with_the_bible_rule(self):
        for field in ("title", "caption", "note", "when", "channels", "audience"):
            item = {"id": "x", "title": "A deal", "kind": "single", field: "Free 30-min Lesson"}
            if field == "title":
                item["title"] = "Free junior lessons"
            with self.assertRaises(ValueError) as cm:
                self.rp.create_pack("Deals", [item], kind="deals")
            self.assertIn("coaching", str(cm.exception).lower(), field)

    def test_lesson_in_the_pack_title_or_notice_is_refused(self):
        with self.assertRaises(ValueError):
            self.rp.create_pack("Lesson deals", POSTS)
        with self.assertRaises(ValueError):
            self.rp.create_pack("Deals", POSTS, notice="Includes a LESSON")

    def test_lesson_is_refused_on_post_packs_too(self):
        with self.assertRaises(ValueError):
            self.rp.create_pack("Posts", [{"id": "a", "title": "A", "caption": "Book a lesson"}])

    def test_lesson_is_refused_when_adding_or_editing_an_item(self):
        pack = self.rp.create_pack("Deals", DEALS, kind="deals")
        with self.assertRaises(ValueError):
            self.rp.add_item(pack["id"], {"id": "y", "title": "Gift a lesson"})
        with self.assertRaises(ValueError):
            self.rp.update_item_fields(pack["id"], "deal-01", {"caption": "50% off a lesson"})
        self.assertNotIn("lesson", self.rp.get_pack(pack["id"])["items"][1]["caption"].lower())

    def test_our_replies_cannot_say_lesson_but_the_clients_words_are_his(self):
        pack = self.rp.create_pack("Deals", DEALS, kind="deals")
        with self.assertRaises(ValueError):
            self.rp.add_comment(pack["id"], "deal-01", "Christelle", "Swapped the lesson", role="us")
        self.rp.add_comment(pack["id"], "deal-01", "Herman", "Lesson not allowed", role="client")

    def test_words_that_only_contain_the_letters_pass(self):
        self.rp.create_pack("Deals", [{"id": "a", "title": "Lessen the wait", "caption": "Coaching, 4 sessions"}])


class DealRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-deals-routes-"))
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

    def test_our_api_makes_a_deal_pack_and_his_page_says_deals(self):
        r = self.anon.post("/api/jobs/review-packs", headers=self.bearer,
                           json={"title": "Christmas deals", "kind": "deals", "items": DEALS})
        self.assertEqual(r.status_code, 200, r.get_json())
        pid = r.get_json()["pack_id"]
        share = self.anon.post(f"/api/jobs/review-packs/{pid}/share", headers=self.bearer,
                               json={"who": "Herman"}).get_json()
        path = share["share_url"][share["share_url"].index("/review-pack/"):]
        page = self.anon.get(path).get_data(as_text=True)
        self.assertIn("Deals, not posts", page)

    def test_our_api_refuses_lesson(self):
        r = self.anon.post("/api/jobs/review-packs", headers=self.bearer,
                           json={"title": "Christmas deals", "kind": "deals",
                                 "items": [{"id": "a", "title": "Junior set + 5 lessons"}]})
        self.assertEqual(r.status_code, 400, r.get_json())
        self.assertIn("coaching", r.get_json()["error"].lower())


if __name__ == "__main__":
    unittest.main()
