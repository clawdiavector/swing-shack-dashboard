"""Postiz never gets "now"; videos can be drafted or scheduled for a chosen time and land on the OS calendar (2026-10-20)."""
from __future__ import annotations

import datetime as dt
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from _lib import postiz_client as pz  # noqa: E402

READY = "2026-10-19__new-year-offer__reel-9x16__v1"
LISTING = [
    {"id": "v1abcdefghijkl", "name": READY + ".mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "t1", "name": READY + ".txt", "mime": "text/plain", "folder": "Video/2-ready-to-publish"},
]
INTEGRATIONS = [{"id": "ig1", "name": "Swing Shack", "identifier": "instagram"}]
UTC = dt.timezone.utc


def iso(d):
    return d.isoformat().replace("+00:00", "Z")


def parse(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


class MinLeadTests(unittest.TestCase):
    def test_no_date_or_a_close_or_past_date_becomes_five_minutes_from_now(self):
        now = dt.datetime.now(UTC)
        for given in (None, iso(now), iso(now + dt.timedelta(minutes=2)), "2020-01-01T00:00:00Z"):
            out, moved = pz.scheduled_at_least(given)
            self.assertTrue(moved, given)
            lead = (parse(out) - dt.datetime.now(UTC)).total_seconds()
            self.assertTrue(4 * 60 < lead <= 5 * 60 + 5, (given, lead))

    def test_a_later_date_is_kept_and_naive_times_read_as_utc(self):
        later = dt.datetime.now(UTC) + dt.timedelta(days=3)
        out, moved = pz.scheduled_at_least(iso(later))
        self.assertFalse(moved)
        self.assertEqual(parse(out), later.replace(microsecond=later.microsecond))
        out, moved = pz.scheduled_at_least((later.replace(tzinfo=None)).isoformat())
        self.assertFalse(moved)
        self.assertEqual(parse(out), later)

    def test_an_unreadable_date_is_passed_through(self):
        self.assertEqual(pz.scheduled_at_least("soon"), ("soon", False))

    def test_create_post_never_sends_now(self):
        with mock.patch.object(pz, "_request", return_value=({}, None)) as req:
            pz.create_post("ig1", "hi", [], brand_id="swing-shack")
            body = req.call_args.kwargs["json_body"]
        self.assertEqual(body["type"], "schedule")
        self.assertTrue(parse(body["date"]) > dt.datetime.now(UTC) + dt.timedelta(minutes=4))

    def test_the_release_job_path_is_pushed_back_too(self):
        from _lib import publish_live
        seen = {}

        def fake_create(**kw):
            seen.update(kw)
            return {"id": "p1"}, None

        row = {"brand_id": "swing-shack", "platform": "instagram", "caption": "hi",
               "would_publish_at": None, "human_approved": True, "idempotency_key": "k-never-sent"}
        with mock.patch.object(publish_live, "create_post", fake_create),                 mock.patch.object(publish_live.sandbox, "_receipt_index", return_value={}),                 mock.patch.object(publish_live, "_integrations_for_brand", return_value=([{"id": "ig1"}], None)),                 mock.patch.object(publish_live, "_integration_for_platform", return_value="ig1"),                 mock.patch.object(publish_live, "_media_for_row", return_value=[]):
            try:
                publish_live._dispatch_row_live(row, {})
            except Exception:
                pass  # the receipt step after the send is not under test
        self.assertTrue(seen, "create_post was not reached")
        self.assertTrue(parse(seen["publish_date"]) > dt.datetime.now(UTC) + dt.timedelta(minutes=4))


class RouteTests(unittest.TestCase):
    def setUp(self):
        import app as appmod
        from app import app as flask_app
        appmod._VIDEO_LIST_CACHE.clear()
        self.appmod = appmod
        self.env = mock.patch.dict(os.environ, {"POSTIZ_API_KEY_SWING_SHACK": "own"})
        self.env.start()
        self.items = []
        from _lib import google_drive as gd
        self.patches = [
            mock.patch("app._is_authed", lambda: True),
            mock.patch.object(appmod, "_drive_listing", lambda brand: LISTING),
            mock.patch.object(appmod, "_drive_text", lambda fid: "Happy new year." if fid == "t1" else None),
            mock.patch.object(pz, "list_integrations", return_value=(INTEGRATIONS, None)),
            mock.patch.object(gd, "download_public_file",
                              lambda fid, dest, **kw: (Path(dest).write_bytes(b"v"), Path(dest))[1]),
            mock.patch.object(pz, "upload_media", return_value=({"id": "m1", "path": "https://x/m.mp4"}, None)),
            mock.patch("_lib.marketing_lanes.add_content_item", lambda brand, item: self.items.append((brand, item)) or item),
        ]
        for p in self.patches:
            p.start()
        self.create = mock.patch.object(pz, "create_post", return_value=([{"postId": "pz1"}], None))
        self.create_mock = self.create.start()
        self.client = flask_app.test_client()

    def tearDown(self):
        self.create.stop()
        for p in self.patches:
            p.stop()
        self.env.stop()

    def send(self, **extra):
        body = {"brand_id": "swing-shack", "file_id": "v1abcdefghijkl", **extra}
        return self.client.post("/api/photos/videos/draft", json=body)

    def test_draft_default_saves_a_draft_five_minutes_out_and_lands_on_the_calendar(self):
        r = self.send()
        self.assertEqual(r.status_code, 200, r.get_json())
        kw = self.create_mock.call_args.kwargs
        self.assertIs(kw["draft"], True)
        self.assertTrue(parse(kw["publish_date"]) > dt.datetime.now(UTC) + dt.timedelta(minutes=4))
        brand, item = self.items[0]
        self.assertEqual((brand, item["status"], item["lane"], item["platform"]), ("swing-shack", "draft", "human", "instagram"))
        self.assertEqual((item["id"], item["format"], item["media_kind"]), ("vid-v1abcdefghij", "reel", "video"))
        self.assertEqual(item["caption"], "Happy new year.")
        self.assertEqual(r.get_json()["calendar_item"], "vid-v1abcdefghij")

    def test_schedule_uses_the_chosen_time_and_shows_it_in_south_african_time(self):
        when = dt.datetime.now(UTC).replace(microsecond=0) + dt.timedelta(days=12)
        r = self.send(mode="schedule", publish_at=iso(when))
        self.assertEqual(r.status_code, 200, r.get_json())
        kw = self.create_mock.call_args.kwargs
        self.assertIs(kw["draft"], False)
        self.assertEqual(parse(kw["publish_date"]), when)
        out = r.get_json()
        self.assertFalse(out["moved_to_minimum"])
        sast = when.astimezone(dt.timezone(dt.timedelta(hours=2)))
        _, item = self.items[0]
        self.assertEqual((item["status"], item["publish_date"], item["publish_time"]),
                         ("queued", sast.date().isoformat(), sast.strftime("%H:%M")))

    def test_a_time_that_is_too_soon_is_moved_to_five_minutes_from_now(self):
        soon = dt.datetime.now(UTC) + dt.timedelta(seconds=30)
        r = self.send(mode="schedule", publish_at=iso(soon))
        self.assertTrue(r.get_json()["moved_to_minimum"])
        self.assertTrue(parse(self.create_mock.call_args.kwargs["publish_date"]) > dt.datetime.now(UTC) + dt.timedelta(minutes=4))

    def test_asap_means_in_five_minutes_and_never_now(self):
        r = self.send(mode="schedule", asap=True)
        self.assertEqual(r.status_code, 200)
        self.assertIs(self.create_mock.call_args.kwargs["draft"], False)
        self.assertTrue(parse(self.create_mock.call_args.kwargs["publish_date"]) > dt.datetime.now(UTC) + dt.timedelta(minutes=4))

    def test_bad_requests_are_refused_before_anything_is_sent(self):
        self.assertEqual(self.send(mode="publish").status_code, 400)
        self.assertEqual(self.send(mode="schedule").status_code, 400)                          # no time
        self.assertEqual(self.send(mode="schedule", publish_at="2026-11-01T05:00:00").status_code, 400)  # no zone
        self.create_mock.assert_not_called()

    def test_a_calendar_failure_does_not_undo_the_postiz_draft(self):
        with mock.patch("_lib.marketing_lanes.add_content_item", side_effect=RuntimeError("disk")):
            r = self.send()
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.get_json()["calendar_item"])


if __name__ == "__main__":
    unittest.main()
