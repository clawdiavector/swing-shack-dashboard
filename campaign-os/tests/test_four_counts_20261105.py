"""One set of counts for every page (audit 3 Nov 2026).

Today, Create, Publish and Results counted from campaign-data.json asset statuses,
which are not updated when a post goes out through the shelf: Stick showed
"11 ready", "0 scheduled" and "0 shipped" while 4 were scheduled and 4 had gone out.
The four counts come from the lists that are right: Approve drafts, Inbox,
Scheduled, and the send queue.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import four_counts  # noqa: E402

THU = datetime(2026, 11, 5, 6, 0, tzinfo=timezone.utc)  # Thu 5 Nov, 08:00 SAST


def _row(asset, platform, status="dispatched", at="2026-11-03T12:07:19Z", brand="stick"):
    return {"brand_id": brand, "asset_id": asset, "platform": platform, "status": status, "dispatched_at": at}


def test_week_starts_monday_midnight_sast():
    assert four_counts.week_start(THU) == datetime(2026, 11, 1, 22, 0, tzinfo=timezone.utc)
    sunday_late = datetime(2026, 11, 1, 21, 30, tzinfo=timezone.utc)  # Sun 23:30 SAST
    assert four_counts.week_start(sunday_late) == datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc)


def test_sent_this_week_counts_each_post_once_across_platforms():
    rows = [
        _row("player-v", "instagram"), _row("player-v", "facebook"),
        _row("grip-drip", "instagram"),
        _row("pattern", "instagram", at="2026-11-05T06:12:44Z"),
    ]
    assert four_counts.sent_this_week(rows, "stick", now=THU) == 3


def test_sent_this_week_leaves_out_unsent_old_and_other_brands():
    rows = [
        _row("queued", "instagram", status="pending", at=None),
        _row("last-week", "instagram", at="2026-11-01T21:59:00Z"),
        _row("swing-shack-post", "instagram", brand="swing-shack"),
        _row("rejected", "facebook", status="rejected"),
    ]
    assert four_counts.sent_this_week(rows, "stick", now=THU) == 0


def test_brand_counts_reads_the_lists_that_are_right(monkeypatch):
    from _lib import unified_inbox

    def fake_list_items(*, brand=None, status="pending", item_type=None):
        n = {"draft_asset": 14, "calendar_candidate": 59}[item_type]
        return {"items": [{"type": item_type}] * n}

    monkeypatch.setattr(unified_inbox, "list_items", fake_list_items)
    monkeypatch.setattr(unified_inbox, "shelf_board", lambda **kw: {"counts": {"scheduled": 4}})
    monkeypatch.setattr(four_counts, "_queue_rows", lambda: [_row("a", "instagram"), _row("b", "facebook")])

    assert four_counts.brand_counts("stick", now=THU) == {
        "to_approve": 14, "dates_to_decide": 59, "scheduled": 4, "sent_this_week": 2,
    }


def test_all_brands_adds_up_each_brand(monkeypatch):
    per = {"stick": {"to_approve": 14, "dates_to_decide": 59, "scheduled": 4, "sent_this_week": 4},
           "swing-shack": {"to_approve": 11, "dates_to_decide": 28, "scheduled": 1, "sent_this_week": 0}}
    monkeypatch.setattr(four_counts, "brand_counts", lambda b, now=None: per.get(b, dict.fromkeys(per["stick"], 0)))

    out = four_counts.counts("all", now=THU)

    assert out["to_approve"] == 25 and out["dates_to_decide"] == 87
    assert out["scheduled"] == 5 and out["sent_this_week"] == 4
    assert set(out["brands"]) >= {"stick", "swing-shack"}
