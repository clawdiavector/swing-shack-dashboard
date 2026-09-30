"""
patch_review_fixture_cleanup_v211.py — V2.11 one-shot cleanup for
acceptance-test fixture artifacts that were ingested before the
fixture-* ingest guard shipped.

Run-once marker at DATA_DIR/.review-fixture-cleanup-v211-applied.
Deletes:
  - DATA_DIR/writer/<brand>/fixture-*.json       (writer artifacts)
  - DATA_DIR/review/<brand>/r_seo-brief-fixture-*  (review records)

This script is idempotent. After the first run it leaves the marker
file and never runs again.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")
MARKER = Path(DATA_DIR) / ".review-fixture-cleanup-v211-applied"

ALLOWED_BRANDS = ("stick", "swing-shack", "bag-drop")


def _delete_glob(pattern: str) -> int:
    n = 0
    for p in Path(DATA_DIR).glob(pattern):
        try:
            p.unlink()
            n += 1
            print(f"[v2.11/review-fixture-cleanup] deleted: {p}", flush=True)
        except Exception as e:
            print(f"[v2.11/review-fixture-cleanup] could not delete {p}: {e}", flush=True)
    return n


def main() -> int:
    if MARKER.exists():
        # cleanup already applied; no-op
        return 0
    deleted_writer = 0
    deleted_review = 0
    for brand in ALLOWED_BRANDS:
        deleted_writer += _delete_glob(f"writer/{brand}/fixture-*.json")
        deleted_review += _delete_glob(f"review/{brand}/r_seo-brief-fixture-*")
    try:
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(f"writer={deleted_writer} review={deleted_review}\n")
        print(
            f"[v2.11/review-fixture-cleanup] cleanup complete: "
            f"writer={deleted_writer} review={deleted_review} → {MARKER}",
            flush=True,
        )
    except Exception as e:
        print(f"[v2.11/review-fixture-cleanup] could not write marker: {e}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())