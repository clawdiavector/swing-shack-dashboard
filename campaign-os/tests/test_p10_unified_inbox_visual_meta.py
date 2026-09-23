"""P10 — unified inbox resolves camelCase asset paths onto meta.image_url."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class UnifiedInboxVisualMetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-inbox-thumb-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        from _lib import unified_inbox

        cls.unified_inbox = unified_inbox

    def test_asset_image_meta_from_file_path_only(self):
        path, url = self.unified_inbox._asset_image_meta(
            {"filePath": "assets/campaigns/trackman/takomo-101t-hero-a.png"},
        )
        self.assertEqual(path, "assets/campaigns/trackman/takomo-101t-hero-a.png")
        self.assertEqual(url, "assets/campaigns/trackman/takomo-101t-hero-a.png")

    def test_asset_image_meta_camel_case_precedence(self):
        path, url = self.unified_inbox._asset_image_meta(
            {
                "visualUrl": "/assets/campaigns/a.png",
                "filePath": "assets/campaigns/b.png",
            },
        )
        self.assertEqual(url, "/assets/campaigns/a.png")
        self.assertEqual(path, "assets/campaigns/b.png")


if __name__ == "__main__":
    unittest.main()
