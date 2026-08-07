"""
test_v2026_08_07_brand_images_fallback.py

Regression: /brand-images/<brand>/<filename> falls back to other brand
directories when the file is not under the requested brand. Closes the
"takomo.png 404 under swing-shack" hole (DNA indexed under swing-shack
but the actual PNG lives under takomo/).

Coverage:
  - /brand-images/swing-shack/takomo.png returns 200 (fell back to takomo/)
  - /brand-images/swing-shack/blackfriday%20copy%203.jpg returns 200 (file is
    actually under swing-shack — exercises the fast branch)
  - /brand-images/nonexistent-brand/foo.png returns 404 (no false positive)
  - /brand-images/<brand>/../../etc/passwd still 403 / 302 (traversal still
    blocked)
  - /api/visual-library/swing-shack/images still returns 200 with images[]
    including the takomo record (index intact, not silently dropped)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent


class BrandImagesFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # DATA_DIR shadow so app boot doesn't fail on /data read-only
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-brand-fb-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app
        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        cls.module.init_repo = lambda: None
        cls.client.post("/login", data={"password": cls.module.SHARED_PASSWORD})

    def test_swing_shack_takomo_falls_back_to_takomo_brand(self):
        """The orphan DNA case: file lives under takomo/, requested under
        swing-shack/. Before the fix this 404'd in the browser."""
        r = self.client.get("/brand-images/swing-shack/takomo.png")
        self.assertEqual(r.status_code, 200, f"got {r.status_code} body={r.data[:200]!r}")
        self.assertEqual(r.mimetype, "image/png")
        self.assertGreater(len(r.data), 1000, "served image should be non-trivial")

    def test_native_swing_shack_image_still_serves(self):
        """A file that genuinely lives under swing-shack still serves via
        the primary path (no regression on the fast branch)."""
        # blackfriday copy 3.jpg is bundled under swing-shack/
        r = self.client.get("/brand-images/swing-shack/blackfriday%20copy%203.jpg")
        self.assertEqual(r.status_code, 200)
        self.assertIn("jpeg", r.mimetype)

    def test_unknown_brand_unknown_file_returns_404(self):
        """No brand has the file → 404 (no false positive from the fallback)."""
        r = self.client.get("/brand-images/totally-fake-brand/nope.png")
        self.assertEqual(r.status_code, 404)

    def test_traversal_still_blocked(self):
        """Path-traversal protection is intact (fallback must not bypass it)."""
        # The fallback scans sibling brand dirs; traversal would try to
        # escape brand-directory/ entirely. Test by attempting a path with ..
        r = self.client.get("/brand-images/swing-shack/..%2F..%2Fetc%2Fpasswd")
        # Either 403 (path traversal denied) or 302 (auth) is fine — must NOT 200
        self.assertIn(r.status_code, (302, 403, 404),
                      f"unexpected status {r.status_code}")

    def test_visual_library_index_intact(self):
        """The takomo record is still surfaced in the index — we are NOT
        silently dropping it, only healing the broken thumbnail URL."""
        r = self.client.get("/api/visual-library/swing-shack/images?limit=200")
        self.assertEqual(r.status_code, 200)
        body = r.get_json() or {}
        rows = body.get("images", []) or []
        filenames = [row.get("filename") for row in rows]
        self.assertIn("takomo.png", filenames, "takomo.png should still be in the library roster")
        takomo_row = next(r for r in rows if r["filename"] == "takomo.png")
        self.assertIn("url", takomo_row)
        self.assertEqual(takomo_row["url"], "/brand-images/swing-shack/takomo.png",
                         "URL contract unchanged — fix is server-side fallback only")


if __name__ == "__main__":
    unittest.main()