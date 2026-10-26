"""
Google Business drafts must sit on the permanent volume (DATA_DIR), not inside
the app folder that every deploy replaces.

Run: python -m pytest campaign-os/tests/test_gbp_drafts_dir.py
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "campaign-os"))

from _lib import gbp_daily_poster as gbp  # noqa: E402


class DraftsDirTests(unittest.TestCase):
    def test_uses_the_data_volume_when_data_dir_is_set(self):
        self.assertEqual(gbp.resolve_drafts_dir({"DATA_DIR": "/data/campaign-os"}), Path("/data/campaign-os/gmb-drafts"))

    def test_falls_back_to_the_app_folder_without_data_dir(self):
        self.assertEqual(gbp.resolve_drafts_dir({}).parts[-3:], ("campaign-os", "data", "gmb-drafts"))

    def test_the_app_uses_the_same_folder_as_the_daily_poster(self):
        import app as app_module  # noqa: PLC0415

        self.assertEqual(Path(app_module.GMB_DRAFTS_DIR), gbp.GMB_DRAFTS_DIR)


if __name__ == "__main__":
    unittest.main()
