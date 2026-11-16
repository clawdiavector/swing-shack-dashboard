"""Space out posts that go out together (audit, 3 Nov 2026).

Due and Publish-now rows were all handed to Postiz as now + 5 minutes, so three Stick
posts went out at 14:12 on 3 Nov. Posts of one brand sent together now get their own
time, GAP apart; a post's platforms (IG + FB) share one time; nothing after LATEST SAST.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import post_spacing as ps  # noqa: E402

NOON = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)  # 10:00 SAST


def test_three_posts_of_one_brand_get_their_own_times():
    out = ps.spaced_times([("stick", "a"), ("stick", "b"), ("stick", "c")], now=NOON)
    assert out == {
        ("stick", "a"): "2026-11-05T08:05:00Z",
        ("stick", "b"): "2026-11-05T11:05:00Z",
        ("stick", "c"): "2026-11-05T14:05:00Z",
    }


def test_each_brand_starts_on_its_own():
    out = ps.spaced_times([("stick", "a"), ("swing-shack", "b")], now=NOON)
    assert out[("stick", "a")] == out[("swing-shack", "b")] == "2026-11-05T08:05:00Z"


def test_a_post_listed_twice_keeps_one_time():
    out = ps.spaced_times([("stick", "a"), ("stick", "a"), ("stick", "b")], now=NOON)
    assert out[("stick", "a")] == "2026-11-05T08:05:00Z"
    assert out[("stick", "b")] == "2026-11-05T11:05:00Z"


def test_waits_a_gap_after_a_post_that_already_went_out_today():
    out = ps.spaced_times([("stick", "a")], now=NOON, last_today={"stick": "2026-11-05T07:30:00Z"})
    assert out[("stick", "a")] == "2026-11-05T10:30:00Z"


def test_a_slot_after_the_latest_time_moves_to_nine_the_next_morning():
    late = datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)  # 16:00 SAST
    out = ps.spaced_times([("stick", "a"), ("stick", "b"), ("stick", "c")], now=late)
    assert out[("stick", "a")] == "2026-11-05T14:05:00Z"  # 16:05 SAST
    assert out[("stick", "b")] == "2026-11-05T17:05:00Z"  # 19:05 SAST, before 19:30
    assert out[("stick", "c")] == "2026-11-06T07:00:00Z"  # next day 09:00 SAST
