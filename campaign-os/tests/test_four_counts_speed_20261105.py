"""/api/counts on live (5 Nov 2026): Stick showed Sent this week 8 for 4 posts, and the
call took 8 s quiet and 42 s alongside Today's other requests.

Real queue rows have no asset_id field: the post is in the idempotency key
(qc-<asset>-<platform>). Counts are kept for a short while per brand.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import four_counts  # noqa: E402

THU = datetime(2026, 11, 5, 6, 0, tzinfo=timezone.utc)


def _live_row(asset, platform, at="2026-11-03T12:07:19Z"):
    return {"brand_id": "stick", "platform": platform, "status": "dispatched", "dispatched_at": at,
            "idempotency_key": f"qc-{asset}-{platform}"}


def test_a_post_sent_to_two_platforms_counts_once_without_asset_id():
    rows = []
    for asset in ("stick-stick-vessel-v-stand-shadow-v2", "stick-stick-grip-drip-drip-word",
                  "stick-stick-vice-pro-air-editorial", "stick-stick-grip-drip-staircase"):
        rows += [_live_row(asset, "instagram"), _live_row(asset, "facebook")]
    assert four_counts.sent_this_week(rows, "stick", now=THU) == 4


def test_counts_are_kept_for_a_short_while_per_brand(monkeypatch):
    calls = []

    def slow(brand_id, *, now=None):
        calls.append(brand_id)
        return dict.fromkeys(four_counts.KEYS, len(calls))

    monkeypatch.setattr(four_counts, "_fresh_brand_counts", slow)
    four_counts.clear_cache()

    first = four_counts.brand_counts("stick", now=THU)
    again = four_counts.brand_counts("stick", now=THU)
    other = four_counts.brand_counts("swing-shack", now=THU)

    assert first == again and calls == ["stick", "swing-shack"]
    assert other["to_approve"] == 2


def test_kept_counts_expire(monkeypatch):
    calls = []
    monkeypatch.setattr(four_counts, "_fresh_brand_counts",
                        lambda b, now=None: calls.append(b) or dict.fromkeys(four_counts.KEYS, 0))
    clock = iter([1000.0, 1000.0 + four_counts.CACHE_SECONDS + 1])
    monkeypatch.setattr(four_counts, "_clock", lambda: next(clock))
    four_counts.clear_cache()

    four_counts.brand_counts("stick", now=THU)
    four_counts.brand_counts("stick", now=THU)

    assert calls == ["stick", "stick"]
