"""Re-arm the three GitHub schedules that have never fired (2026-11-03).

ads-budget-guard-hourly, mail-intake-cron and geo-observe-daily had zero runs ever.
#294 only changed the quote marks on each cron line, which GitHub reads as the same
schedule, so nothing re-registered. Each now has a different time, off the top of the
hour (GitHub drops or delays the most runs there).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

NEW_CRONS = {
    "ads-budget-guard-hourly.yml": "23 * * * *",
    "mail-intake-cron.yml": "11,41 * * * *",
    "geo-observe-daily.yml": "47 5 * * *",
}


def _crons(name: str) -> list[str]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return re.findall(r"cron:\s*[\"']([^\"']+)[\"']", text)


def test_dead_crons_have_a_new_schedule():
    for name, cron in NEW_CRONS.items():
        assert _crons(name) == [cron], name


def test_rearmed_crons_avoid_the_top_of_the_hour():
    for name in NEW_CRONS:
        for cron in _crons(name):
            minutes = cron.split()[0]
            assert not re.fullmatch(r"(\*/\d+|0(,.*)?)", minutes), (name, cron)


def test_rearmed_crons_keep_manual_trigger():
    for name in NEW_CRONS:
        assert "workflow_dispatch:" in (WORKFLOWS / name).read_text(encoding="utf-8"), name


def test_geo_observe_schedule_metadata_matches_new_time():
    from _lib.jobs.schedules import schedule_for

    assert schedule_for("geo_observe").get("cron_sast") == ["07:47"]
