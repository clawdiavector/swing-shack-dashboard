"""Image scout: quality gate, size-parameter stripping, saving with provenance."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cos-scout-"))

from PIL import Image  # noqa: E402

from _lib import image_scout as sc  # noqa: E402
from _lib import photo_map as pm  # noqa: E402


def png(w, h):
    buf = io.BytesIO()
    Image.effect_noise((w, h), 80).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


class ScoutTests(unittest.TestCase):
    def setUp(self):
        self.brand = "sc-" + next(tempfile._get_candidate_names())
        self.dir = Path(tempfile.mkdtemp(prefix="cos-scout-imgs-"))

    def test_size_parameters_are_dropped_but_the_version_stays(self):
        u = "https://x.com/cdn/shop/files/a.png?v=12&width=533&crop=center"
        self.assertEqual(sc.full_size(u), "https://x.com/cdn/shop/files/a.png?v=12")

    def test_gate_rejects_non_images_thumbnails_and_tiny_files(self):
        self.assertIn("not an image", sc.check(b"<html>" * 5000, "text/html")["reason"])
        self.assertIn("under", sc.check(png(300, 300), "image/png")["reason"])
        self.assertIn("too small", sc.check(b"x" * 100, "image/png")["reason"])
        self.assertTrue(sc.check(png(1200, 800), "image/png")["ok"])

    def test_good_candidate_is_saved_named_by_sku_and_waits_for_a_check(self):
        row = sc.add(self.brand, "TS001", "Takomo SF002 wedge", "https://t.com/p", "https://t.com/i.png?width=500")
        with mock.patch.object(sc, "_get", return_value={"status": 200, "type": "image/png", "data": png(1200, 1200)}):
            out = sc.fetch(self.brand, row, self.dir)
        self.assertTrue(out["ok"])
        self.assertTrue((self.dir / "Products" / "TS001__front.png").exists())
        e = pm.load(self.brand)[0]
        self.assertEqual((e["status"], e["source"], e["source_url"]), ("needs-check", "official-site", "https://t.com/p"))
        self.assertTrue(e["exact_build"])

    def test_bad_candidate_saves_nothing(self):
        row = sc.add(self.brand, "TS002", "Thumb", "https://t.com/p", "https://t.com/i.png")
        with mock.patch.object(sc, "_get", return_value={"status": 200, "type": "image/png", "data": png(300, 300)}):
            out = sc.fetch(self.brand, row, self.dir)
        self.assertFalse(out["ok"])
        self.assertFalse((self.dir / "Products").exists() and any((self.dir / "Products").iterdir()))
        self.assertEqual(pm.load(self.brand), [])

    def test_existing_file_is_never_overwritten(self):
        (self.dir / "Products").mkdir()
        (self.dir / "Products" / "TS003__front.png").write_bytes(b"mine")
        row = sc.add(self.brand, "TS003", "X", "https://t.com/p", "https://t.com/i.png")
        with mock.patch.object(sc, "_get", return_value={"status": 200, "type": "image/png", "data": png(1200, 1200)}):
            out = sc.fetch(self.brand, row, self.dir)
        self.assertFalse(out["ok"])
        self.assertEqual((self.dir / "Products" / "TS003__front.png").read_bytes(), b"mine")

    def test_adding_the_same_candidate_twice_keeps_one(self):
        sc.add(self.brand, "TS004", "X", "https://t.com/p", "https://t.com/i.png?width=1")
        sc.add(self.brand, "TS004", "X", "https://t.com/p", "https://t.com/i.png?width=900")
        self.assertEqual(len(sc.load(self.brand)), 1)

    def test_standard_image_for_a_custom_build_is_marked(self):
        row = sc.add(self.brand, "LO1", "L.A.B O.Z.1I CUSTOM ACCRA", "https://l.com/p", "https://l.com/i.png",
                     note="standard black model image; custom shaft and colour not shown", exact_build=False)
        with mock.patch.object(sc, "_get", return_value={"status": 200, "type": "image/png", "data": png(1200, 1200)}):
            sc.fetch(self.brand, row, self.dir)
        self.assertFalse(pm.load(self.brand)[0]["exact_build"])


if __name__ == "__main__":
    unittest.main()
