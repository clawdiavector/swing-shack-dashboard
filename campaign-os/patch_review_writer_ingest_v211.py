"""
patch_review_writer_ingest_v211.py — V2.11 startup patch to ingest the
canonical Writer artifact onto the Railway volume.

The Campaign OS Writer (heidi skill campaign-os-writer) writes the
draft artifact to the LOCAL heidi outbox:

  ~/.hermes/profiles/heidi/outbox/<brand>-writer-draft-<slug>.json

On Railway, that path does not exist. The Review routes
(_lib/review.py::_writer_artifact_candidates) already fall back to
DATA_DIR/writer/<brand>/<slug>.json — so we just need to copy the
artifact there on each deploy's boot.

This script:
  - Reads the local heidi outbox (if reachable — Railway container will
    not have it, that's fine).
  - Reads the in-repo data/writer-artifacts/<brand>/<slug>.json which is
    baked into the Docker image (canonical "shipped with the OS" path).
  - For each <brand>-writer-draft-<slug>.json that exists, copies it
    into DATA_DIR/writer/<brand>/<slug>.json on the volume.

Idempotent. Boot-block bootstrap runs even if the v2.11 marker is set.
"""
from __future__ import annotations
import json
import os
import shutil
import sys
from pathlib import Path

DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")
HEIDI_OUTBOX = Path(os.path.expanduser("~/.hermes/profiles/heidi/outbox"))
LOCAL_REPO = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard")
LOCAL_OUTBOX = LOCAL_REPO / "outbox"

ALLOWED_BRANDS = ("stick", "swing-shack", "bag-drop")

# On Railway, the local heidi outbox is not present. The Writer artifact
# is shipped inside the Docker image at:
#   - /app/data/writer-artifacts/<brand>/<slug>.json (baked in)
#   - /app/outbox/<brand>-writer-draft-<slug>.json (legacy fallback)
SHIPPED_REPO_OUTBOX = Path("/app/outbox")
SHIPPED_REPO_WRITER_ARTIFACTS = Path("/app/data/writer-artifacts")
BAKED_DATA_WRITER_ARTIFACTS = Path("/app/data/writer-artifacts")


def _copy_artifact(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def main() -> int:
    written = 0

    # 1. Try the heidi outbox (Mac dev environment)
    if HEIDI_OUTBOX.exists():
        for src in HEIDI_OUTBOX.glob("*-writer-draft-*.json"):
            fn = src.name
            for brand in ALLOWED_BRANDS:
                if fn.startswith(f"{brand}-writer-draft-"):
                    slug = fn[len(f"{brand}-writer-draft-"):-len(".json")]
                    dst = Path(DATA_DIR) / "writer" / brand / f"{slug}.json"
                    if _copy_artifact(src, dst):
                        written += 1
                    break

    # 2. Try the local repo outbox (Mac dev / Railway has no local repo)
    if LOCAL_OUTBOX.exists() and LOCAL_OUTBOX != HEIDI_OUTBOX:
        for src in LOCAL_OUTBOX.glob("*-writer-draft-*.json"):
            fn = src.name
            for brand in ALLOWED_BRANDS:
                if fn.startswith(f"{brand}-writer-draft-"):
                    slug = fn[len(f"{brand}-writer-draft-"):-len(".json")]
                    dst = Path(DATA_DIR) / "writer" / brand / f"{slug}.json"
                    if _copy_artifact(src, dst):
                        written += 1
                    break

    # 3. Try the shipped-in-image outbox (legacy fallback)
    if os.path.isdir(SHIPPED_REPO_OUTBOX):
        for src in SHIPPED_REPO_OUTBOX.glob("*-writer-draft-*.json"):
            fn = src.name
            for brand in ALLOWED_BRANDS:
                if fn.startswith(f"{brand}-writer-draft-"):
                    slug = fn[len(f"{brand}-writer-draft-"):-len(".json")]
                    dst = Path(DATA_DIR) / "writer" / brand / f"{slug}.json"
                    if _copy_artifact(src, dst):
                        written += 1
                    break

    # 4. Try the canonical in-repo writer-artifacts dir (baked into the
    #    Docker image at /app/data/writer-artifacts/<brand>/<slug>.json).
    if os.path.isdir(SHIPPED_REPO_WRITER_ARTIFACTS):
        for brand in ALLOWED_BRANDS:
            bdir = SHIPPED_REPO_WRITER_ARTIFACTS / brand
            if not bdir.is_dir():
                continue
            for src in bdir.glob("*.json"):
                slug = src.stem
                dst = Path(DATA_DIR) / "writer" / brand / f"{slug}.json"
                if _copy_artifact(src, dst):
                    written += 1

    if written:
        print(f"[v2.11/review-ingest] copied {written} writer artifact(s) onto volume", flush=True)
    else:
        print("[v2.11/review-ingest] no writer artifacts found to ingest (volume clean)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())