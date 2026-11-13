"""Review pack: a real calendar grid at the top of the client's page (2026-11-12).

Christelle, for Chantalle (MCM): the rollout calendar was a picture on a card. She wants it as
the first thing on the page, built in: a Monday-to-Saturday grid where each day shows its
posts, and a tap on a post jumps to that post's card to see it bigger. The cards follow below.

The pack keeps an optional `calendar`: groups (a name, the page it links to, a colour) and
slots (a date, a time, the post, which picture, a label, a group and a flag). Our side sets it
with the bearer token; the client's page only reads it. Slots that point at a post the client
cannot see are dropped, so a removed post never shows on the grid.

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
ITEMS = [{"id": "a", "title": "First car", "kind": "single"},
         {"id": "b", "title": "Family", "kind": "single"}]
CAL = {
    "groups": [{"name": "First car", "page": "/c/first-car-finds", "colour": "#9b3fec"},
               {"name": "Family", "page": "/c/family-first", "colour": "#3478f6"}],
    "slots": [{"date": "2026-11-16", "time": "12:30", "item": "a", "img": 0, "label": "Consumer", "group": 0, "flag": True},
              {"date": "2026-11-19", "time": "07:30", "item": "b", "img": 0, "label": "Dealer", "group": 1}],
}


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 50), (200, 30, 90)).save(buf, format="PNG")
    return buf.getvalue()


class CalendarModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-cal-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack
        self.pid = review_pack.create_pack("Posts", ITEMS)["id"]
        for i in ("a", "b"):
            review_pack.add_item_image(self.pid, i, _png())

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_calendar_means_no_calendar_on_the_page_data(self):
        v = self.rp.public_view(self.pid, "tok", "Chantalle")
        self.assertNotIn("calendar", v)

    def test_a_calendar_is_saved_and_shown_with_picture_links_that_carry_her_token(self):
        self.rp.set_calendar(self.pid, CAL)
        v = self.rp.public_view(self.pid, "tok", "Chantalle")
        cal = v["calendar"]
        self.assertEqual([g["name"] for g in cal["groups"]], ["First car", "Family"])
        self.assertEqual(len(cal["slots"]), 2)
        s = cal["slots"][0]
        self.assertEqual((s["date"], s["time"], s["item"]), ("2026-11-16", "12:30", "a"))
        self.assertEqual(s["src"], "/review-pack/tok/image/a/0")
        self.assertTrue(s["flag"])
        self.assertFalse(cal["slots"][1]["flag"])

    def test_bad_slots_are_refused(self):
        for bad in ({"date": "16 Nov", "time": "12:30", "item": "a"},
                    {"date": "2026-11-16", "time": "noon", "item": "a"},
                    {"date": "2026-11-16", "time": "12:30", "item": "nope"},
                    {"date": "2026-11-16", "time": "12:30", "item": "a", "img": 5}):
            with self.assertRaises(ValueError):
                self.rp.set_calendar(self.pid, {"groups": [], "slots": [bad]})

    def test_a_colour_must_be_a_hex_colour(self):
        with self.assertRaises(ValueError):
            self.rp.set_calendar(self.pid, {"groups": [{"name": "x", "colour": "red; background:url(x)"}], "slots": []})

    def test_a_removed_post_drops_off_the_grid(self):
        self.rp.set_calendar(self.pid, CAL)
        self.rp.remove_item(self.pid, "b")
        v = self.rp.public_view(self.pid, "tok", "Chantalle")
        self.assertEqual([s["item"] for s in v["calendar"]["slots"]], ["a"])

    def test_an_empty_calendar_clears_it(self):
        self.rp.set_calendar(self.pid, CAL)
        self.rp.set_calendar(self.pid, {})
        self.assertNotIn("calendar", self.rp.public_view(self.pid, "tok", "Chantalle"))

    def test_the_page_draws_the_grid_and_jumps_to_the_post(self):
        self.rp.set_calendar(self.pid, CAL)
        page = self.rp.render_page(self.rp.public_view(self.pid, "tok", "Chantalle"), token="tok")
        self.assertIn('id="calendar"', page)
        self.assertIn("function paintCalendar", page)
        self.assertIn("Tap a post to see it bigger", page)


class CalendarRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-cal-routes-"))
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
        for i in ("a", "b"):
            review_pack.add_item_image(self.pid, i, _png())

    def test_setting_the_calendar_needs_the_bearer_token(self):
        r = self.anon.post(f"/api/jobs/review-packs/{self.pid}/calendar", json=CAL)
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("calendar", self.rp.get_pack(self.pid))

    def test_setting_the_calendar_with_the_token_works(self):
        r = self.anon.post(f"/api/jobs/review-packs/{self.pid}/calendar", json=CAL, headers=self.bearer)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["slots"], 2)

    def test_a_bad_calendar_is_a_400(self):
        r = self.anon.post(f"/api/jobs/review-packs/{self.pid}/calendar",
                           json={"slots": [{"date": "x", "time": "y", "item": "a"}]}, headers=self.bearer)
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
