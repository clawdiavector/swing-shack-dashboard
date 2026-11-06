"""Visual Library: a folder filter and "Load more" paging.

Stick has ~880 photos and the grid shows 200 at a time, so the images route takes
`folder` (that folder and everything under it) and `offset`, and reports the
brand's folders plus whether more photos are waiting.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "campaign-os"))

import app as app_module  # noqa: E402
from itsdangerous import URLSafeTimedSerializer  # noqa: E402

SESSION_SECRET = "campaign-os-dev-secret-change-me"
BRAND = "zz-folder-paging-brand"
PHOTOS = (
    ["Shot List/Bags/Vessel/v%d.jpg" % i for i in range(3)]
    + ["Shot List/Putters/p%d.jpg" % i for i in range(2)]
    + ["Products/x%d.jpg" % i for i in range(4)]
)
VIEWER = Path(__file__).resolve().parent.parent / "visualizer.html"


class FolderPagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for rel in PHOTOS:
            img = self.tmp / "brand-directory" / BRAND / "images" / rel
            img.parent.mkdir(parents=True, exist_ok=True)
            img.write_bytes(b"\xff\xd8\xff\xe0fake")
            img.with_name(img.stem + ".visual-dna.json").write_text(json.dumps({}), encoding="utf-8")
        patcher = mock.patch.object(app_module, "DATA_DIR", str(self.tmp))
        patcher.start()
        self.addCleanup(patcher.stop)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.client.set_cookie("cos_session", URLSafeTimedSerializer(SESSION_SECRET).dumps({"v": 1}))

    def _get(self, query):
        resp = self.client.get(f"/api/visual-library/{BRAND}/images?{query}")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True)[:300])
        return resp.get_json()

    def test_folder_includes_its_subfolders(self):
        body = self._get("folder=Shot%20List&limit=500")
        self.assertEqual(sorted(i["filename"] for i in body["images"]),
                         sorted(p for p in PHOTOS if p.startswith("Shot List/")))

    def test_folder_list_counts_parents_and_children(self):
        folders = {f["path"]: f["count"] for f in self._get("limit=1")["folders"]}
        self.assertEqual(folders["Shot List"], 5)
        self.assertEqual(folders["Shot List/Bags"], 3)
        self.assertEqual(folders["Shot List/Bags/Vessel"], 3)
        self.assertEqual(folders["Shot List/Putters"], 2)
        self.assertEqual(folders["Products"], 4)

    def test_pages_cover_every_photo_once(self):
        first = self._get("sort=filename&limit=4")
        self.assertEqual(first["total_matching"], len(PHOTOS))
        self.assertTrue(first["has_more"])
        seen = [i["filename"] for i in first["images"]]
        offset = 4
        while True:
            page = self._get(f"sort=filename&limit=4&offset={offset}")
            seen += [i["filename"] for i in page["images"]]
            offset += 4
            if not page["has_more"]:
                break
        self.assertEqual(sorted(seen), sorted(PHOTOS))
        self.assertEqual(len(seen), len(set(seen)))

    def test_page_has_folder_picker_and_load_more(self):
        html = VIEWER.read_text(encoding="utf-8")
        self.assertIn('id="folder"', html)
        self.assertIn('id="load-more"', html)
        self.assertIn("params.offset", html)
        self.assertIn("params.folder", html)


if __name__ == "__main__":
    unittest.main()
