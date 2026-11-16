"""The Scheduled list must not redo the whole calendar and drafts folder per post (6 Nov 2026).

shelf_board took 8 s on a quiet server and 14 s for All brands. For every calendar
record, visual_gate.decide looked the record up again (a full calendar load),
archetypes._moment_context loaded the calendar again, draft_assets._sidecar_for_moment
read through the drafts folder and campaign-data.json was read twice; decide runs twice
per record. The work grew with the square of the number of posts. Here it must stay flat:
the calendar loads a fixed number of times, and how often each draft file is read does
not change when the number of posts doubles.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def make_board(tmp_path, monkeypatch):
    """Build a Stick board of n approved posts, each with its approved draft; count the work."""
    from _lib import archetypes, marketing_calendar, unified_inbox

    calls = {"calendar": 0, "reads": {}}
    real_read = Path.read_text
    state = {"records": [], "drafts": None}

    def counted_records(brand_id, status_filter=None):
        calls["calendar"] += 1
        return [dict(r) for r in state["records"]]

    def counted_read(self, *a, **kw):
        if state["drafts"] is not None and self.parent == state["drafts"]:
            calls["reads"][self.name] = calls["reads"].get(self.name, 0) + 1
        return real_read(self, *a, **kw)

    monkeypatch.setattr(marketing_calendar, "canonical_records", counted_records)
    # A vetted, pinned layout, so decide goes as far as the draft's composed image.
    monkeypatch.setattr(
        archetypes,
        "select_archetype_explained",
        lambda brand_id, item_id, *, record=None: ({"id": "photo-post", "vetted": True}, "pinned"),
    )
    monkeypatch.setattr(Path, "read_text", counted_read)

    def build(n: int):
        root = tmp_path / f"n{n}"
        drafts = root / "draft-assets"
        drafts.mkdir(parents=True)
        monkeypatch.setenv("DATA_DIR", str(root))
        assets = {}
        for i in range(n):
            (drafts / f"asset-{i}.json").write_text(
                json.dumps({
                    "asset_id": f"asset-{i}",
                    "brand_id": "stick",
                    "campaign_id": "stick-calendar",
                    "source_inbox_item_id": f"calendar_candidate:stick:cal-{i}",
                    "composed": {"instagram": f"/brand-images/stick/composed-asset-{i}.png"},
                }),
                encoding="utf-8",
            )
            assets[f"asset-{i}"] = {
                "approvalStatus": "approved",
                "caption": f"Post {i}. Better begins here.",
                "visualUrl": f"/brand-images/stick/composed-asset-{i}.png",
            }
        (root / "campaign-data.json").write_text(
            json.dumps({"campaigns": {"stick-calendar": {"brand": "stick", "assets": assets}}}),
            encoding="utf-8",
        )
        state["drafts"] = drafts
        state["records"] = [
            {
                "calendar_id": f"cal-{i}",
                "event_key": f"cal-{i}",
                "title": f"Post {i}",
                "status": "approved",
                "event_date": "2026-11-20",
                "source_type": "operator",
            }
            for i in range(n)
        ]
        calls["calendar"] = 0
        calls["reads"] = {}
        out = unified_inbox.shelf_board(brand_id="stick")
        worst = max(calls["reads"].values()) if calls["reads"] else 0
        return out, calls["calendar"], worst

    return build


def test_the_calendar_loads_a_fixed_number_of_times(make_board):
    _, calendar_loads, _ = make_board(40)
    assert calendar_loads <= 3, f"calendar loaded {calendar_loads} times for 40 posts"


def test_draft_reads_do_not_grow_with_the_number_of_posts(make_board):
    _, _, worst_20 = make_board(20)
    _, _, worst_40 = make_board(40)
    assert worst_40 == worst_20, f"reads per draft grew from {worst_20} to {worst_40} when posts doubled"


def test_the_board_still_lists_every_approved_post_with_its_draft(make_board):
    out, _, _ = make_board(40)
    posts = [p for g in out.get("date_groups") or [] for p in g.get("posts") or []] + list(out.get("undated") or [])
    assert out.get("ok") is not False
    assert len(posts) == 40, f"expected 40 approved posts on the board, got {len(posts)}"
    assert {p.get("asset_id") for p in posts} == {f"asset-{i}" for i in range(40)}
