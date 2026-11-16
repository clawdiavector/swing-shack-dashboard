"""Bag Drop posts go out through its own Zernio account when approved (3 Nov 2026).

Christelle chose Zernio for Bag Drop's weekly deals: Bag Drop has no Postiz key, and its
Facebook page and Instagram are connected to the bagdropmarketing Zernio account. Approving a
Bag Drop row must schedule it there, as a story on both channels, never "now" (her 5-minute
rule), and never through another brand's key. Stick and Swing Shack keep using Postiz.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from _lib import postiz_on_approve, publish_sandbox, zernio_client
from _lib.jobs import auto_release

ENV_KEYS = (
    "DATA_DIR",
    "PUBLISH_MODE",
    "CAMPAIGN_OS_POSTIZ_ON_APPROVE",
    "POSTIZ_API_KEY_STICK",
    "POSTIZ_API_KEY_BAG_DROP",
    "POSTIZ_API_KEY",
    "ZERNIO_API_KEY",
    "ZERNIO_API_KEY_BAG_DROP",
    "ZERNIO_MEDIA_BASE_URL",
)


class _Resp:
    def __init__(self, body: dict, status: int = 201):
        self._body = json.dumps(body).encode()
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ZernioBagDropTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._old = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        os.environ["DATA_DIR"] = str(self._root)
        os.environ["PUBLISH_MODE"] = "live"
        os.environ["CAMPAIGN_OS_POSTIZ_ON_APPROVE"] = "1"
        os.environ["ZERNIO_API_KEY_BAG_DROP"] = "zk-test-bag-drop"
        os.environ["ZERNIO_MEDIA_BASE_URL"] = "https://cos.example.test"
        publish_sandbox.ensure_sandbox_layout()
        self.image = self._root / "deal.png"
        self.image.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    def tearDown(self) -> None:
        self._tmp.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _row(self, *, brand: str = "bag-drop", platform: str = "instagram_story", when: str | None = None,
             key: str = "bd-deal-1") -> dict:
        when = when or _iso(datetime.now(timezone.utc) + timedelta(days=2))
        publish_sandbox.enqueue_item(
            brand_id=brand,
            platform=platform,
            caption_preview="20% off putters this week. Shop the drop. Link in bio.",
            human_approved=True,
            would_publish_at=when,
            idempotency_key=key,
            image_url="",
            image_path=str(self.image),
            event_date=when[:10],
        )
        rows = publish_sandbox._read_jsonl(publish_sandbox._queue_path())
        return next(r for r in rows if r["idempotency_key"] == key)

    # -- the client ---------------------------------------------------------------

    def test_own_key_only_no_shared_fallback(self):
        self.assertTrue(zernio_client.has_brand_key("bag-drop"))
        self.assertFalse(zernio_client.has_brand_key("stick"))
        os.environ.pop("ZERNIO_API_KEY_BAG_DROP")
        os.environ["ZERNIO_API_KEY"] = "shared"
        self.assertFalse(zernio_client.has_brand_key("bag-drop"))

    def test_story_request_shape(self):
        sent = {}

        def fake_urlopen(req, timeout=0):
            sent["url"] = req.full_url
            sent["auth"] = req.get_header("Authorization")
            sent["body"] = json.loads(req.data)
            return _Resp({"post": {"_id": "zp-1", "status": "scheduled"}})

        soon = _iso(datetime.now(timezone.utc))  # "now" must be moved 5 minutes ahead
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            post, err = zernio_client.create_post(
                brand_id="bag-drop", content="caption", image_url="https://cos.example.test/asset-media/a.jpg",
                publish_date=soon, story=True, idempotency_key="bd-deal-1",
            )
        self.assertIsNone(err)
        self.assertEqual(post["_id"], "zp-1")
        self.assertEqual(sent["url"], "https://zernio.com/api/v1/posts")
        self.assertEqual(sent["auth"], "Bearer zk-test-bag-drop")
        body = sent["body"]
        self.assertEqual(body["mediaItems"], [{"type": "image", "url": "https://cos.example.test/asset-media/a.jpg"}])
        plats = {p["platform"]: p for p in body["platforms"]}
        self.assertEqual(set(plats), {"instagram", "facebook"})
        self.assertEqual(plats["instagram"]["accountId"], zernio_client.ACCOUNTS["bag-drop"]["instagram"])
        self.assertEqual(plats["facebook"]["accountId"], zernio_client.ACCOUNTS["bag-drop"]["facebook"])
        for p in plats.values():
            self.assertEqual(p["platformSpecificData"], {"contentType": "story"})
        when = datetime.fromisoformat(body["scheduledFor"].replace("Z", "+00:00"))
        self.assertGreaterEqual(when, datetime.now(timezone.utc) + timedelta(minutes=4, seconds=30))
        self.assertNotIn("publishNow", body)

    def test_refuses_brand_without_its_own_key(self):
        with mock.patch("urllib.request.urlopen") as op:
            post, err = zernio_client.create_post(
                brand_id="stick", content="x", image_url="https://x/a.jpg", publish_date=None, story=True,
            )
        self.assertIsNone(post)
        self.assertIn("ZERNIO_API_KEY_STICK", err)
        op.assert_not_called()

    def test_public_media_url_serves_from_asset_media(self):
        url = zernio_client.public_media_url(self.image)
        self.assertTrue(url.startswith("https://cos.example.test/asset-media/"))
        name = url.rsplit("/", 1)[1]
        self.assertTrue((self._root / "asset-media" / name).is_file())

    # -- approve ------------------------------------------------------------------

    def test_approve_bag_drop_schedules_on_zernio_not_postiz(self):
        row = self._row()
        with mock.patch.object(zernio_client, "create_post", return_value=({"_id": "zp-9"}, None)) as zc, \
                mock.patch.object(postiz_on_approve, "create_post") as pc:
            receipt, err = postiz_on_approve.schedule_row_on_approve(row)
        self.assertIsNone(err)
        pc.assert_not_called()
        kwargs = zc.call_args.kwargs
        self.assertEqual(kwargs["brand_id"], "bag-drop")
        self.assertTrue(kwargs["story"])
        self.assertTrue(kwargs["image_url"].startswith("https://cos.example.test/asset-media/"))
        self.assertEqual(receipt["zernio_post_id"], "zp-9")
        self.assertEqual(receipt["channel"], "zernio")
        rows = publish_sandbox._read_jsonl(publish_sandbox._receipts_path())
        self.assertEqual([r["zernio_post_id"] for r in rows], ["zp-9"])

    def test_feed_row_is_not_sent_as_story(self):
        row = self._row(platform="instagram", key="bd-feed-1")
        with mock.patch.object(zernio_client, "create_post", return_value=({"_id": "zp-2"}, None)) as zc:
            _r, err = postiz_on_approve.schedule_row_on_approve(row)
        self.assertIsNone(err)
        self.assertFalse(zc.call_args.kwargs["story"])

    def test_approve_twice_sends_once(self):
        row = self._row()
        with mock.patch.object(zernio_client, "create_post", return_value=({"_id": "zp-3"}, None)) as zc:
            postiz_on_approve.schedule_row_on_approve(row)
            postiz_on_approve.schedule_row_on_approve(row)
        self.assertEqual(zc.call_count, 1)

    def test_bag_drop_without_any_key_is_refused(self):
        os.environ.pop("ZERNIO_API_KEY_BAG_DROP")
        row = self._row()
        with mock.patch.object(zernio_client, "create_post") as zc, \
                mock.patch.object(postiz_on_approve, "create_post") as pc:
            receipt, err = postiz_on_approve.schedule_row_on_approve(row)
        self.assertEqual(receipt, {})
        self.assertTrue(err)
        zc.assert_not_called()
        pc.assert_not_called()

    def test_stick_still_goes_to_postiz(self):
        os.environ["POSTIZ_API_KEY_STICK"] = "pk-stick"
        row = self._row(brand="stick", platform="instagram", key="stick-1")
        with mock.patch.object(zernio_client, "create_post") as zc, \
                mock.patch.object(publish_sandbox, "preflight_queue_row", return_value=(True, "")), \
                mock.patch.object(postiz_on_approve.publish_live, "_integrations_for_brand",
                                  return_value=([{"id": "i1", "identifier": "instagram"}], None)), \
                mock.patch.object(postiz_on_approve.publish_live, "_media_for_row", return_value=[]), \
                mock.patch.object(postiz_on_approve, "create_post", return_value=({"id": "p1"}, None)) as pc:
            _r, err = postiz_on_approve.schedule_row_on_approve(row)
        self.assertIsNone(err)
        zc.assert_not_called()
        pc.assert_called_once()

    # -- un-approve ---------------------------------------------------------------

    def test_unapprove_cancels_future_zernio_post(self):
        row = self._row()
        with mock.patch.object(zernio_client, "create_post", return_value=({"_id": "zp-5"}, None)):
            postiz_on_approve.schedule_row_on_approve(row)
        with mock.patch.object(zernio_client, "unpublish_post", return_value=({}, None)) as up:
            out, err = postiz_on_approve.clear_postiz_on_unapprove(row["idempotency_key"])
        self.assertIsNone(err)
        up.assert_called_once_with("zp-5", brand_id="bag-drop")
        self.assertEqual(publish_sandbox._read_jsonl(publish_sandbox._receipts_path()), [])

    def test_unapprove_refused_once_it_is_about_to_go(self):
        row = self._row(when=_iso(datetime.now(timezone.utc)), key="bd-now")
        with mock.patch.object(zernio_client, "create_post", return_value=({"_id": "zp-6"}, None)):
            postiz_on_approve.schedule_row_on_approve(row)
        rows = publish_sandbox._read_jsonl(publish_sandbox._receipts_path())
        rows[0]["postiz_scheduled_at"] = _iso(datetime.now(timezone.utc) + timedelta(minutes=1))
        publish_sandbox._rewrite_jsonl(publish_sandbox._receipts_path(), rows)
        with mock.patch.object(zernio_client, "unpublish_post") as up:
            _out, err = postiz_on_approve.clear_postiz_on_unapprove("bd-now")
        self.assertTrue(err)
        up.assert_not_called()

    # -- auto release -------------------------------------------------------------

    def test_auto_release_does_not_hold_bag_drop_with_zernio_key(self):
        self.assertFalse(auto_release._held_without_own_key("bag-drop"))
        os.environ.pop("ZERNIO_API_KEY_BAG_DROP")
        self.assertTrue(auto_release._held_without_own_key("bag-drop"))


if __name__ == "__main__":
    unittest.main()
