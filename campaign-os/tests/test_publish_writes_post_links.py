"""Publishing a post from an asset writes the post -> asset -> template link.

The link lands in meta-post-index.json (by_asset_id, and by_media_id when
Postiz returns the Instagram media id), so "make another like this" can
go from a published post back to the asset and template that made it.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _lib import post_links, publish_live, publish_sandbox

BRAND = "stick"
ASSET = "asset-abc123"
TEMPLATE = "tpl-fitting-headline"
MEDIA_ID = "17900000000000001"


class PublishWritesPostLinksTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._old_env = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_MODE")}
        os.environ["DATA_DIR"] = str(self._root)
        os.environ["PUBLISH_MODE"] = "live"
        publish_sandbox.ensure_sandbox_layout()
        sidecar_dir = self._root / "draft-assets"
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        (sidecar_dir / f"{ASSET}.json").write_text(
            json.dumps({"asset_id": ASSET, "template_id": TEMPLATE}), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _row(self) -> dict:
        return {
            "idempotency_key": f"qc-{ASSET}-instagram",
            "post_id": ASSET,
            "brand_id": BRAND,
            "platform": "instagram",
            "channel": "postiz",
            "caption_preview": "Better begins here.",
            "human_approved": True,
            "human_approved_at": "2026-10-19T09:00:00+00:00",
            "would_publish_at": None,
            "status": "pending",
        }

    def _dispatch(self, post_response: dict) -> tuple[dict, str | None]:
        cache = {BRAND: [{"id": "int-ig", "identifier": "instagram", "name": "Stick"}]}
        with mock.patch.object(publish_live, "create_post", return_value=(post_response, None)), \
                mock.patch.object(publish_live, "_media_for_row", return_value=[]):
            return publish_live._dispatch_row_live(self._row(), cache)

    def _index(self) -> dict:
        return json.loads((self._root / "meta-post-index.json").read_text(encoding="utf-8"))

    def test_publish_writes_asset_template_and_media_id(self) -> None:
        receipt, err = self._dispatch({"id": "postiz-999", "platformMediaId": MEDIA_ID})
        self.assertIsNone(err)
        self.assertEqual(receipt.get("postiz_post_id"), "postiz-999")

        index = self._index()
        by_asset = index["by_asset_id"][ASSET]
        self.assertEqual(by_asset["asset_id"], ASSET)
        self.assertEqual(by_asset["template_id"], TEMPLATE)
        self.assertEqual(by_asset["postiz_post_id"], "postiz-999")
        self.assertEqual(by_asset["platform_media_id"], MEDIA_ID)

        by_media = index["by_media_id"][MEDIA_ID]
        self.assertEqual(by_media["asset_id"], ASSET)
        self.assertEqual(by_media["template_id"], TEMPLATE)
        self.assertEqual(by_media["postiz_post_id"], "postiz-999")
        self.assertEqual(by_media["channel"], "instagram")
        self.assertEqual(index["count"], 1)

    def test_publish_without_media_id_still_links_asset_and_template(self) -> None:
        receipt, err = self._dispatch({"id": "postiz-1000"})
        self.assertIsNone(err)

        index = self._index()
        by_asset = index["by_asset_id"][ASSET]
        self.assertEqual(by_asset["template_id"], TEMPLATE)
        self.assertEqual(by_asset["postiz_post_id"], "postiz-1000")
        self.assertIsNone(by_asset["platform_media_id"])
        self.assertEqual(index["by_media_id"], {})

    def test_link_write_failure_does_not_fail_the_publish(self) -> None:
        with mock.patch.object(post_links, "record_publish_link", side_effect=OSError("disk full")):
            receipt, err = self._dispatch({"id": "postiz-1001", "platformMediaId": MEDIA_ID})
        self.assertIsNone(err)
        self.assertEqual(receipt.get("postiz_post_id"), "postiz-1001")


if __name__ == "__main__":
    unittest.main()
