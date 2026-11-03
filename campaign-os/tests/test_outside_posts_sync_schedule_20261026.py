"""outside_posts_sync — GitHub Actions schedule registration (T9 fix)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))
WF = REPO_ROOT / ".github" / "workflows" / "outside-posts-sync-4h.yml"


def test_outside_posts_sync_workflow_exists_with_four_hour_cron():
    assert WF.is_file(), "missing outside-posts-sync-4h.yml workflow"
    text = WF.read_text(encoding="utf-8")
    assert "outside_posts_sync?brand=" in text
    assert re.search(r"cron:\s*'0 4,8,12,16,20 \* \* \*'", text)


def test_outside_posts_sync_schedule_metadata_registered():
    from _lib.jobs.schedules import schedule_for

    sched = schedule_for("outside_posts_sync")
    assert sched.get("cadence") == "every 4h"
    assert "outside-posts-sync-4h.yml" in sched.get("scheduler", "")
    assert sched.get("cron_sast") == ["06:00", "10:00", "14:00", "18:00", "22:00"]
