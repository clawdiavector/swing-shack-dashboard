#!/usr/bin/env python3
"""One-shot live ClubLab pull for implement handoff evidence (counts only)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.layer2 import clublab_pull  # noqa: E402


def main() -> int:
    data_dir = os.environ.get("DATA_DIR")
    if not data_dir:
        scratch = Path("/tmp/cos-clublab-live-pull")
        scratch.mkdir(parents=True, exist_ok=True)
        os.environ["DATA_DIR"] = str(scratch)
    clublab_pull.load_clublab_env()
    result = clublab_pull.run()
    print(json.dumps({"ok": result.get("ok"), "rows": result.get("rows"), "totals": result.get("totals")}, indent=2))
    if not result.get("ok"):
        print(
            json.dumps(
                {
                    "error": result.get("error"),
                    "http_status": result.get("http_status"),
                    "endpoint": result.get("endpoint"),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    snap_path = Path(os.environ["DATA_DIR"]) / clublab_pull.SNAPSHOT_NAME
    with snap_path.open(encoding="utf-8") as fh:
        snap = json.load(fh)
    print(json.dumps({"facilities": clublab_pull.counts_summary(snap)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
