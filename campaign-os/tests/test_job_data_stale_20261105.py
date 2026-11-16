"""Flag jobs that say OK while the data they write is old (audit, 3 Nov 2026).

ga4_report and meta_refresh showed OK while Reach said GA4 was 46 days old and
Instagram 14. A job's data age is the newest timestamp inside the files it writes
(the file's own date when there is none).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs import data_freshness as df  # noqa: E402

NOW = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)


def test_newest_timestamp_across_the_files_a_job_writes(tmp_path):
    (tmp_path / "ga4-metrics.json").write_text(json.dumps({"fetched_at": "2026-09-20T10:00:00Z"}), encoding="utf-8")
    (tmp_path / "other.json").write_text(json.dumps({"generated": "2026-11-04T08:00:00Z"}), encoding="utf-8")

    ga4 = df.newest_data(("ga4-metrics.json",), tmp_path, now=NOW)
    both = df.newest_data(("ga4-metrics.json", "other.json"), tmp_path, now=NOW)

    assert ga4["file"] == "ga4-metrics.json" and ga4["age_days"] == 45.9
    assert both["file"] == "other.json" and both["age_days"] == 1.0


def test_a_file_without_timestamps_uses_its_own_date(tmp_path):
    p = tmp_path / "static.json"
    p.write_text(json.dumps({"rows": [1, 2]}), encoding="utf-8")
    when = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc).timestamp()
    os.utime(p, (when, when))
    assert df.newest_data(("static.json",), tmp_path, now=NOW)["age_days"] == 2.0


def test_no_files_means_nothing_to_judge(tmp_path):
    assert df.newest_data(("missing.json",), tmp_path, now=NOW) is None
    assert df.newest_data((), tmp_path, now=NOW) is None


def test_ok_with_old_data_is_flagged():
    assert df.is_data_stale("OK", 86400, {"age_days": 45.9}) is True
    assert df.is_data_stale("OK", 43200, {"age_days": 14.0}) is True


def test_recent_data_or_a_job_already_in_trouble_is_not_flagged():
    assert df.is_data_stale("OK", 86400, {"age_days": 1.5}) is False  # under the 2-day floor
    assert df.is_data_stale("OK", 7 * 86400, {"age_days": 10}) is False  # weekly job, within 3 runs
    assert df.is_data_stale("LATE", 86400, {"age_days": 45}) is False  # already shown as a problem
    assert df.is_data_stale("OK", 86400, None) is False
