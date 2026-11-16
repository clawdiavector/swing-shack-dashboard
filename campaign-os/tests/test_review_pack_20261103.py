"""The review pack (2026-11-03): a no-login page where a client approves, rejects,
comments and uploads her own photos.

Christelle's ask, from Chantalle (MCM, a separate client): she cannot sign in to
Claude, so she needs a plain web link. Herman's calendar link is the pattern, with
three differences: it is not tied to one of our brands, Approve and Reject only
record a decision (nothing is ever scheduled or sent), and she can upload photos
and tag a comment as a copy edit or a design edit.

Requirement-Owner: Christelle
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from itsdangerous import URLSafeTimedSerializer

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

TOKEN = "test-job-token-not-a-secret"


def _jpeg(colour=(20, 90, 60)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (600, 750), colour).save(buf, format="JPEG")
    return buf.getvalue()


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (80, 80), (200, 30, 90)).save(buf, format="PNG")
    return buf.getvalue()


ITEMS = [
    {"id": "first-car", "title": "Your first car, matched.", "kind": "choice",
     "caption": "Tell us your budget.", "channels": "Instagram, Facebook",
     "when": "Mon 2 Nov, 17:30", "audience": "Consumer"},
    {"id": "day-1-day-40", "title": "Day 1. Day 40. Same exposure.", "kind": "single",
     "caption": "Your aged stock keeps earning its place.", "channels": "LinkedIn",
     "when": "Mon 2 Nov, 07:30", "audience": "Dealer"},
]


class _TmpData(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-pack-"))
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

    def _pack(self, items=None):
        return self.rp.create_pack("MCM, 2 to 13 Nov", items or ITEMS, client="Chantalle")


# ── the module on its own ────────────────────────────────────────────────────


class TokenTests(_TmpData):
    def test_a_link_names_one_pack_and_the_person_it_is_for(self):
        pack = self._pack()
        token = self.rp.mint_token(self.ser, pack["id"], who="Chantalle")
        self.assertEqual(self.rp.read_token(self.ser, token), {"pack": pack["id"], "who": "Chantalle"})

    def test_a_tampered_expired_or_foreign_link_is_refused(self):
        from _lib import clean_calendar as cc

        pack = self._pack()
        token = self.rp.mint_token(self.ser, pack["id"])
        self.assertIsNone(self.rp.read_token(self.ser, token + "x"))
        self.assertIsNone(self.rp.read_token(self.ser, ""))
        time.sleep(1.1)
        self.assertIsNone(self.rp.read_token(self.ser, token, max_age=0))
        # Herman's calendar link must not open a review pack.
        herman = cc.mint_share_token(self.ser, "stick")
        self.assertIsNone(self.rp.read_token(self.ser, herman))

    def test_a_link_for_a_pack_that_is_gone_is_refused(self):
        pack = self._pack()
        token = self.rp.mint_token(self.ser, pack["id"])
        shutil.rmtree(self.tmp / "review-packs" / pack["id"])
        self.assertIsNone(self.rp.read_token(self.ser, token))


class PackTests(_TmpData):
    def test_a_pack_needs_a_title_and_at_least_one_item(self):
        with self.assertRaises(ValueError):
            self.rp.create_pack("", ITEMS)
        with self.assertRaises(ValueError):
            self.rp.create_pack("Empty", [])

    def test_item_ids_are_unique_and_kinds_are_known(self):
        with self.assertRaises(ValueError):
            self.rp.create_pack("Dupes", [ITEMS[0], dict(ITEMS[0])])
        with self.assertRaises(ValueError):
            self.rp.create_pack("Odd", [{"id": "x", "title": "X", "kind": "banana"}])

    def test_a_pack_is_saved_and_read_back(self):
        pack = self._pack()
        again = self.rp.get_pack(pack["id"])
        self.assertEqual([i["id"] for i in again["items"]], ["first-car", "day-1-day-40"])
        self.assertIsNone(self.rp.get_pack("no-such-pack"))

    def test_a_pack_id_cannot_climb_out_of_the_data_folder(self):
        self.assertIsNone(self.rp.get_pack("../etc"))
        self.assertIsNone(self.rp.get_pack("a/b"))


class ImageTests(_TmpData):
    def test_a_real_image_is_accepted_and_a_text_file_is_not(self):
        pack = self._pack()
        out = self.rp.add_item_image(pack["id"], "first-car", _jpeg())
        self.assertEqual(out["index"], 0)
        with self.assertRaises(ValueError):
            self.rp.add_item_image(pack["id"], "first-car", b"<html>not an image</html>")

    def test_an_oversize_image_is_refused(self):
        pack = self._pack()
        with mock.patch.object(self.rp, "MAX_PACK_IMAGE_BYTES", 100):
            with self.assertRaises(ValueError):
                self.rp.add_item_image(pack["id"], "first-car", _jpeg())

    def test_replacing_an_image_resets_that_items_decision(self):
        pack = self._pack()
        self.rp.add_item_image(pack["id"], "day-1-day-40", _jpeg())
        self.rp.record_decision(pack["id"], "day-1-day-40", "approve", "Chantalle")
        self.assertEqual(self.rp.view(pack["id"])["decisions"]["day-1-day-40"]["state"], "approve")
        self.rp.add_item_image(pack["id"], "day-1-day-40", _jpeg((90, 20, 20)), replace=True)
        self.assertNotIn("day-1-day-40", self.rp.view(pack["id"])["decisions"])
        self.assertEqual(self.rp.get_pack(pack["id"])["items"][1]["version"], 2)


class DecisionAndCommentTests(_TmpData):
    def test_approve_reject_and_hold_are_recorded_with_who_and_when(self):
        pack = self._pack()
        for state in ("approve", "reject", "hold"):
            self.rp.record_decision(pack["id"], "day-1-day-40", state, "Chantalle")
            d = self.rp.view(pack["id"])["decisions"]["day-1-day-40"]
            self.assertEqual((d["state"], d["by"]), (state, "Chantalle"))
            self.assertTrue(d["at"].endswith("Z"))

    def test_anything_else_is_refused_and_a_choice_must_be_a_b_or_c(self):
        pack = self._pack()
        with self.assertRaises(ValueError):
            self.rp.record_decision(pack["id"], "day-1-day-40", "send", "Chantalle")
        with self.assertRaises(ValueError):
            self.rp.record_decision(pack["id"], "no-such-item", "approve", "Chantalle")
        with self.assertRaises(ValueError):
            self.rp.record_decision(pack["id"], "first-car", "approve", "Chantalle", choice="Z")
        self.rp.record_decision(pack["id"], "first-car", "approve", "Chantalle", choice="B")
        self.assertEqual(self.rp.view(pack["id"])["decisions"]["first-car"]["choice"], "B")

    def test_a_comment_keeps_its_tag_and_both_sides_share_one_thread(self):
        pack = self._pack()
        self.rp.add_comment(pack["id"], "first-car", "Chantalle", "Change the word first.", tag="copy edit")
        self.rp.add_comment(pack["id"], "first-car", "Christelle", "Done.", role="us")
        thread = self.rp.view(pack["id"])["comments"]["first-car"]
        self.assertEqual([c["role"] for c in thread], ["client", "us"])
        self.assertEqual(thread[0]["tag"], "copy edit")

    def test_an_empty_comment_or_unknown_tag_is_refused(self):
        pack = self._pack()
        with self.assertRaises(ValueError):
            self.rp.add_comment(pack["id"], "first-car", "Chantalle", "   ")
        with self.assertRaises(ValueError):
            self.rp.add_comment(pack["id"], "first-car", "Chantalle", "Hi", tag="shout")


class UploadTests(_TmpData):
    def test_a_photo_is_saved_under_a_random_name_with_where_it_came_from(self):
        pack = self._pack()
        up = self.rp.save_upload(pack["id"], "first-car", _png(), original_name="../../my photo.PNG",
                                 source="Taken by Michelle", rights=True, who="Chantalle")
        self.assertNotIn("photo", up["file"])
        self.assertTrue(up["file"].endswith(".png"))
        self.assertEqual((up["source"], up["rights"]), ("Taken by Michelle", True))
        self.assertTrue(self.rp.upload_path(pack["id"], up["file"]).is_file())

    def test_a_non_image_an_oversize_file_and_a_bad_item_are_refused(self):
        pack = self._pack()
        with self.assertRaises(ValueError):
            self.rp.save_upload(pack["id"], "first-car", b"MZ\x90\x00 an exe", original_name="a.png",
                                source="", rights=False, who="x")
        with mock.patch.object(self.rp, "MAX_UPLOAD_BYTES", 100):
            with self.assertRaises(ValueError):
                self.rp.save_upload(pack["id"], "first-car", _png(), original_name="a.png",
                                    source="", rights=False, who="x")
        with self.assertRaises(ValueError):
            self.rp.save_upload(pack["id"], "no-such-item", _png(), original_name="a.png",
                                source="", rights=False, who="x")

    def test_a_week_level_upload_is_allowed(self):
        pack = self._pack()
        up = self.rp.save_upload(pack["id"], "", _png(), original_name="a.png", source="", rights=False, who="x")
        self.assertEqual(up["item"], "")

    def test_an_upload_path_cannot_climb_out(self):
        pack = self._pack()
        self.assertIsNone(self.rp.upload_path(pack["id"], "../pack.json"))


# ── the routes ───────────────────────────────────────────────────────────────


class ReviewPackRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-review-pack-routes-"))
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
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack
        self.app = self.app_module.app
        self.anon = self.app.test_client(cos_anon=True)
        self.bearer = {"Authorization": f"Bearer {TOKEN}"}
        self.pack = self.rp.create_pack("MCM, 2 to 13 Nov", ITEMS, client="Chantalle")
        self.rp.add_item_image(self.pack["id"], "first-car", _jpeg())
        self.rp.add_item_image(self.pack["id"], "day-1-day-40", _jpeg((90, 20, 20)))
        self.token = self.rp.mint_token(self.app_module._serializer, self.pack["id"], who="Chantalle")
        self.base = f"/review-pack/{self.token}"

    # -- who can open it
    def test_a_good_link_opens_with_no_login_and_is_not_indexed(self):
        r = self.anon.get(self.base)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Your first car, matched.", r.get_data(as_text=True))
        self.assertIn("noindex", r.headers.get("X-Robots-Tag", ""))

    def test_a_bad_link_is_a_plain_404_page(self):
        for bad in ("/review-pack/not-a-token", self.base + "x"):
            r = self.anon.get(bad)
            self.assertEqual(r.status_code, 404, bad)
            self.assertNotIn("Your first car", r.get_data(as_text=True))

    def test_the_page_never_shows_another_packs_items(self):
        other = self.rp.create_pack("Other client", [{"id": "secret", "title": "Secret launch", "kind": "single"}])
        self.assertNotIn("Secret launch", self.anon.get(self.base).get_data(as_text=True))
        self.assertEqual(self.anon.post(self.base + "/act", json={"item": "secret", "state": "approve"}).status_code, 404)
        self.assertNotIn("secret", self.rp.view(self.pack["id"])["decisions"])
        self.assertIsNotNone(other)

    # -- Approve and Reject only record
    def test_approve_records_a_decision_and_never_schedules_or_sends(self):
        with mock.patch("_lib.unified_inbox.approve_item", side_effect=AssertionError("approve_item must not run")):
            r = self.anon.post(self.base + "/act", json={"item": "day-1-day-40", "state": "approve"})
        self.assertEqual(r.status_code, 200, r.get_json())
        d = self.rp.view(self.pack["id"])["decisions"]["day-1-day-40"]
        self.assertEqual((d["state"], d["by"]), ("approve", "Chantalle"))

    def test_an_unknown_state_is_a_400(self):
        r = self.anon.post(self.base + "/act", json={"item": "day-1-day-40", "state": "send"})
        self.assertEqual(r.status_code, 400)

    # -- comments
    def test_a_comment_is_saved_with_its_tag_as_the_client(self):
        r = self.anon.post(self.base + "/comment", json={"item": "first-car", "text": "Wrong word.", "tag": "copy edit"})
        self.assertEqual(r.status_code, 200, r.get_json())
        c = self.rp.view(self.pack["id"])["comments"]["first-car"][0]
        self.assertEqual((c["tag"], c["role"], c["who"]), ("copy edit", "client", "Chantalle"))

    def test_an_empty_comment_is_a_400(self):
        self.assertEqual(self.anon.post(self.base + "/comment", json={"item": "first-car", "text": " "}).status_code, 400)

    # -- images and uploads
    def test_the_pictures_are_served_only_with_the_link(self):
        ok = self.anon.get(self.base + "/image/first-car/0")
        self.assertEqual((ok.status_code, ok.mimetype), (200, "image/jpeg"))
        self.assertEqual(self.anon.get(f"/review-pack/{self.token}x/image/first-car/0").status_code, 404)

    def _files(self, n, data=None):
        return [(io.BytesIO(data or _png()), f"p{i}.png") for i in range(n)]

    def test_up_to_twenty_photos_upload_in_one_go(self):
        r = self.anon.post(self.base + "/upload", data={"item": "first-car", "source": "Michelle", "rights": "1",
                                                        "files": self._files(2)}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(len(r.get_json()["uploads"]), 2)
        self.assertEqual(len(self.rp.view(self.pack["id"])["uploads"]), 2)

    def test_the_twenty_first_photo_is_refused_and_nothing_is_saved(self):
        r = self.anon.post(self.base + "/upload", data={"item": "first-car", "files": self._files(21)},
                           content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.rp.view(self.pack["id"])["uploads"], [])

    def test_a_non_image_upload_is_refused(self):
        r = self.anon.post(self.base + "/upload", data={"item": "first-car", "files": [(io.BytesIO(b"MZ exe"), "a.png")]},
                           content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.rp.view(self.pack["id"])["uploads"], [])

    def test_an_uploaded_file_cannot_be_fetched_without_the_link_or_a_login(self):
        up = self.rp.save_upload(self.pack["id"], "first-car", _png(), original_name="a.png", source="", rights=False, who="x")
        self.assertEqual(self.anon.get(self.base + f"/file/{up['file']}").status_code, 200)
        self.assertEqual(self.anon.get(f"/review-pack/{self.token}x/file/{up['file']}").status_code, 404)
        self.assertEqual(self.anon.get(f"/api/jobs/review-packs/{self.pack['id']}/file/{up['file']}").status_code, 401)

    def test_a_flood_of_actions_is_slowed_down(self):
        with mock.patch.object(self.app_module, "_REVIEW_PACK_LIMIT_PER_MIN", 3, create=True):
            codes = [self.anon.post(self.base + "/act", json={"item": "first-car", "state": "hold"}).status_code
                     for _ in range(6)]
        self.assertIn(429, codes)

    # -- our side, with the bearer token
    def test_our_api_needs_the_bearer_token(self):
        body = {"title": "Anyone", "items": [{"id": "a", "title": "A", "kind": "single"}]}
        self.assertEqual(self.anon.post("/api/jobs/review-packs", json=body).status_code, 401)
        r = self.anon.post("/api/jobs/review-packs", json=body, headers=self.bearer)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertTrue(r.get_json()["pack_id"])

    def test_we_can_add_a_picture_share_the_pack_and_read_what_she_did(self):
        r = self.anon.post("/api/jobs/review-packs", headers=self.bearer,
                           json={"title": "Fresh", "client": "Chantalle", "items": [{"id": "a", "title": "A", "kind": "single"}]})
        pid = r.get_json()["pack_id"]
        img = self.anon.post(f"/api/jobs/review-packs/{pid}/items/a/image", headers=self.bearer,
                             data={"file": (io.BytesIO(_jpeg()), "a.jpg")}, content_type="multipart/form-data")
        self.assertEqual(img.status_code, 200, img.get_json())
        share = self.anon.post(f"/api/jobs/review-packs/{pid}/share", headers=self.bearer, json={"who": "Chantalle"})
        url = share.get_json()["share_url"]
        self.assertIn("/review-pack/", url)
        path = url[url.index("/review-pack/"):]
        self.anon.post(path + "/act", json={"item": "a", "state": "reject"})
        seen = self.anon.get(f"/api/jobs/review-packs/{pid}", headers=self.bearer).get_json()
        self.assertEqual(seen["decisions"]["a"]["state"], "reject")

    def test_our_reply_lands_in_the_same_thread_as_us(self):
        self.anon.post(self.base + "/comment", json={"item": "first-car", "text": "Hi", "tag": "general"})
        r = self.anon.post(f"/api/jobs/review-packs/{self.pack['id']}/reply", headers=self.bearer,
                           json={"item": "first-car", "text": "Fixed.", "who": "Christelle"})
        self.assertEqual(r.status_code, 200, r.get_json())
        roles = [c["role"] for c in self.rp.view(self.pack["id"])["comments"]["first-car"]]
        self.assertEqual(roles, ["client", "us"])

    def test_replacing_a_picture_through_the_api_resets_the_decision(self):
        self.anon.post(self.base + "/act", json={"item": "day-1-day-40", "state": "approve"})
        r = self.anon.post(f"/api/jobs/review-packs/{self.pack['id']}/items/day-1-day-40/image?replace=1", headers=self.bearer,
                           data={"file": (io.BytesIO(_jpeg((1, 2, 3))), "b.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertNotIn("day-1-day-40", self.rp.view(self.pack["id"])["decisions"])


if __name__ == "__main__":
    unittest.main()
