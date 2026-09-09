"""v2026-08-13: postiz_overview dedup invariant.

publish-queue.json was historically never cleaned up when items shipped.
Every `published_dry` item also sat in `queued`, so the Publish page
rendered the same items in both "Drafts" and "Published" columns. This
test pins the invariant: no item_id may appear in both `queue` and
`published` slices of the postiz_overview() response.
"""
import json
import os
import sys
import tempfile
import unittest
from typing import Any, Dict, List


def _collect_ids(items: List[Dict[str, Any]]) -> set:
    """Same key order as production dedup logic."""
    out = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        for k in ("id", "item_id", "asset_id", "assetId", "publish_id", "publishId"):
            v = it.get(k)
            if v:
                out.add(str(v))
                break
    return out


class PostizDedupInvariantTests(unittest.TestCase):
    """Test against the real on-disk data files. These are the production
    invariant tests - they fail loudly if someone re-introduces a writer
    that doesn't clean publish-queue.json when items ship.
    """

    @classmethod
    def setUpClass(cls):
        # Find repo root by walking up from this file.
        here = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.normpath(os.path.join(here, "..", ".."))
        cls.repo_root = repo_root
        cls.data_dir = os.path.join(repo_root, "data")

    def _load(self, name):
        path = os.path.join(self.data_dir, name)
        if not os.path.exists(path):
            self.skipTest(f"missing fixture: {path}")
        with open(path) as f:
            return json.load(f)

    def test_no_overlap_between_published_and_queue(self):
        queue = self._load("publish-queue.json") or {}
        published = self._load("published-items.json") or {}
        q_items = queue.get("queued", []) if isinstance(queue, dict) else []
        p_items = published.get("published", []) if isinstance(published, dict) else []
        q_ids = _collect_ids(q_items)
        p_ids = _collect_ids(p_items)
        overlap = q_ids & p_ids
        self.assertEqual(
            overlap, set(),
            f"publish-queue.json still contains {len(overlap)} item_ids that "
            f"already shipped - these leak into the Drafts column and "
            f"duplicate Published. Sample: {sorted(overlap)[:3]}",
        )

    def test_no_overlap_between_published_and_scheduled(self):
        scheduled = self._load("scheduled-items.json") or {}
        published = self._load("published-items.json") or {}
        s_items = scheduled.get("scheduled", []) if isinstance(scheduled, dict) else []
        p_items = published.get("published", []) if isinstance(published, dict) else []
        s_ids = _collect_ids(s_items)
        p_ids = _collect_ids(p_items)
        overlap = s_ids & p_ids
        self.assertEqual(
            overlap, set(),
            f"scheduled-items.json still contains {len(overlap)} shipped item_ids",
        )


class PostizOverviewFunctionDedupTests(unittest.TestCase):
    """Unit tests for the in-memory dedup logic in postiz_overview.

    These don't touch the network or the Flask app - they construct fake
    data files in a tempdir and call the function directly so the invariant
    works regardless of current on-disk state.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        # Build minimal data files: 5 shipped + 3 still-in-queue + 2 scheduled.
        shipped_ids = ["cap-A", "cap-B", "cap-C", "cap-D", "cap-E"]
        queue_ids = ["cap-A", "cap-B", "cap-C", "cap-F", "cap-G", "cap-H"]  # 3 dupes
        sched_ids = ["cap-D", "cap-E", "cap-I", "cap-J"]  # 2 dupes
        with open(os.path.join(self._tmp, "published-items.json"), "w") as f:
            json.dump({"published": [{"id": i} for i in shipped_ids], "total": 5}, f)
        with open(os.path.join(self._tmp, "publish-queue.json"), "w") as f:
            json.dump({"queued": [{"id": i} for i in queue_ids]}, f)
        with open(os.path.join(self._tmp, "scheduled-items.json"), "w") as f:
            json.dump({"scheduled": [{"id": i} for i in sched_ids]}, f)
        with open(os.path.join(self._tmp, "publishing-references.json"), "w") as f:
            json.dump({"count": 1}, f)
        # Make the intel module see this tmpdir as DATA_DIR.
        os.environ["DATA_DIR"] = self._tmp
        # Import intel with DATA_DIR set.
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        # Force reload so DATA_DIR picks up.
        if "campaign_os._lib.intelligence" in sys.modules:
            del sys.modules["campaign_os._lib.intelligence"]
        # The app's DATA_DIR is computed at import time, so re-import is required.
        try:
            from campaign_os._lib import intelligence as intel_mod  # type: ignore
        except Exception:
            # Fallback: the app likely runs from the workspace root, so try
            # the package layout used in production.
            from _lib import intelligence as intel_mod  # type: ignore
        self.intel_mod = intel_mod

    def tearDown(self):
        os.environ.pop("DATA_DIR", None)
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_overview_partitions_items_by_terminal_state(self):
        out = self.intel_mod.postiz_overview()
        self.assertTrue(out.get("ok"))
        q_ids = _collect_ids(out.get("queue", []))
        s_ids = _collect_ids(out.get("scheduled", []))
        p_ids = _collect_ids(out.get("published", []))
        # Each id appears in exactly one of the three buckets.
        union = q_ids | s_ids | p_ids
        intersection_qp = q_ids & p_ids
        intersection_sp = s_ids & p_ids
        intersection_qs = q_ids & s_ids
        self.assertEqual(intersection_qp, set(), "queue overlaps published")
        self.assertEqual(intersection_sp, set(), "scheduled overlaps published")
        self.assertEqual(intersection_qs, set(), "queue overlaps scheduled")
        # All 10 unique ids (A-J minus cap-A which appears in both queue and
        # published and should be hidden from queue) accounted for.
        expected = {f"cap-{c}" for c in "ABCDEFGHIJ"}
        # cap-A,B,C were shipped - should not be in queue. cap-D,E also shipped.
        # cap-F,G,H are pending queue. cap-I,J are pending scheduled.
        # After dedup queue should hold F,G,H only (3 items).
        # After dedup scheduled should hold I,J only (2 items).
        # After slice(20) published holds A,B,C,D,E (5 items).
        self.assertEqual(q_ids, {"cap-F", "cap-G", "cap-H"})
        self.assertEqual(s_ids, {"cap-I", "cap-J"})
        self.assertEqual(p_ids, {"cap-A", "cap-B", "cap-C", "cap-D", "cap-E"})

    def test_overview_exposes_dedup_audit_trail(self):
        out = self.intel_mod.postiz_overview()
        dedup = out.get("dedup")
        self.assertIsNotNone(dedup, "missing dedup audit block")
        self.assertEqual(dedup.get("queue_raw"), 6)
        self.assertEqual(dedup.get("queue_visible"), 3)
        self.assertEqual(dedup.get("queue_hidden_shipped"), 3)

    def test_overview_summary_uses_deduped_count(self):
        out = self.intel_mod.postiz_overview()
        summary = out.get("summary", "")
        # 3 unique queue items, 2 unique scheduled items, 5 published.
        self.assertIn("Queue: 3", summary)
        self.assertIn("Scheduled: 2", summary)
        self.assertIn("Published: 5", summary)


if __name__ == "__main__":
    unittest.main()
