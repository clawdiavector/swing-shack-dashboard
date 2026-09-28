"""Publish image resolution + JPEG export."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from _lib import publish_image


class PublishImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        os.environ["DATA_DIR"] = str(self._root)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.pop("DATA_DIR", None)

    def test_prefers_composed_publish_jpeg_over_krea_path(self) -> None:
        brand = "stick"
        out = self._root / "draft-assets" / "images" / brand
        out.mkdir(parents=True)
        png = out / "composed-draft-abc-instagram.png"
        jpg = out / "composed-draft-abc-instagram-publish.jpg"
        png.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x04\x00\x01\x5c\xcd\xff_\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        jpg.write_bytes(b"fake-jpeg")

        row = {
            "brand_id": brand,
            "image_url": "/brand-images/stick/composed-draft-abc-instagram.png",
            "image_path": str(self._root / "draft-assets/images/stick/images/krea-stick-x.png"),
        }
        resolved = publish_image.resolve_queue_upload_path(row)
        self.assertEqual(resolved, jpg)

    def test_write_publish_jpeg_from_png(self) -> None:
        from PIL import Image
        import io

        buf = io.BytesIO()
        Image.new("RGB", (4, 4), (0, 128, 128)).save(buf, format="PNG")
        dest = self._root / "out-publish.jpg"
        publish_image.write_publish_jpeg_from_png_bytes(buf.getvalue(), dest)
        self.assertTrue(dest.is_file())
        self.assertGreater(dest.stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
