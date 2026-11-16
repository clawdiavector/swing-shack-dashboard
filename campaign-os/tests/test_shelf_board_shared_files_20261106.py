"""The Scheduled list reads brands.json and the layouts file once per board (6 Nov 2026).

After PR #340, Stick's Scheduled list still took 4 s on live. Per post it read brands.json
8 times (publish_sandbox._load_brands_registry, for channels) and the brand's
archetypes.json 4 times (archetypes.load_archetypes_doc). How often each file is read
must not change when the number of posts doubles.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

WATCHED = ("brands.json", "archetypes.json")


@pytest.fixture()
def make_board(tmp_path, monkeypatch):
    from _lib import marketing_calendar, unified_inbox

    state = {"records": []}
    reads: dict[str, int] = {}
    real_read = Path.read_text

    def counted_read(self, *a, **kw):
        if self.name in WATCHED and str(tmp_path) in str(self):
            reads[self.name] = reads.get(self.name, 0) + 1
        return real_read(self, *a, **kw)

    monkeypatch.setattr(marketing_calendar, "canonical_records", lambda brand_id, status_filter=None: [dict(r) for r in state["records"]])
    monkeypatch.setattr(Path, "read_text", counted_read)

    def build(n: int):
        root = tmp_path / f"n{n}"
        drafts = root / "draft-assets"
        drafts.mkdir(parents=True)
        spec = root / "brand-directory" / "stick" / "visual-spec"
        spec.mkdir(parents=True)
        spec.joinpath("archetypes.json").write_text(
            json.dumps({"selection": {}, "archetypes": [{"id": "photo-post", "vetted": True}]}), encoding="utf-8"
        )
        root.joinpath("brands.json").write_text(
            json.dumps({"brands": {"stick": {"publish_channels": ["instagram", "facebook"]}}}), encoding="utf-8"
        )
        monkeypatch.setenv("DATA_DIR", str(root))
        assets = {}
        for i in range(n):
            drafts.joinpath(f"asset-{i}.json").write_text(
                json.dumps({
                    "asset_id": f"asset-{i}",
                    "brand_id": "stick",
                    "campaign_id": "stick-calendar",
                    "source_inbox_item_id": f"calendar_candidate:stick:cal-{i}",
                    "composed": {"instagram": f"/brand-images/stick/composed-asset-{i}.png"},
                }),
                encoding="utf-8",
            )
            assets[f"asset-{i}"] = {"approvalStatus": "approved", "caption": f"Post {i}."}
        root.joinpath("campaign-data.json").write_text(
            json.dumps({"campaigns": {"stick-calendar": {"brand": "stick", "assets": assets}}}), encoding="utf-8"
        )
        state["records"] = [
            {"calendar_id": f"cal-{i}", "event_key": f"cal-{i}", "title": f"Post {i}", "status": "approved",
             "event_date": "2026-11-20", "source_type": "operator", "template_id": "photo-post"}
            for i in range(n)
        ]
        reads.clear()
        out = unified_inbox.shelf_board(brand_id="stick")
        return out, dict(reads)

    return build


def test_brands_and_layout_reads_do_not_grow_with_the_number_of_posts(make_board):
    _, reads_20 = make_board(20)
    _, reads_40 = make_board(40)
    for name in WATCHED:
        assert reads_40.get(name, 0) == reads_20.get(name, 0), (
            f"{name} read {reads_20.get(name, 0)} times for 20 posts, {reads_40.get(name, 0)} for 40"
        )


def test_the_board_still_lists_every_approved_post(make_board):
    out, _ = make_board(40)
    posts = [p for g in out.get("date_groups") or [] for p in g.get("posts") or []] + list(out.get("undated") or [])
    assert len(posts) == 40
