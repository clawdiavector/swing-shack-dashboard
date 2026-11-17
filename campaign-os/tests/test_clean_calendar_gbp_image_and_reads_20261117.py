"""Calendar fixes (17 Nov 2026).

1. Google post thumbnails were broken: the draft keeps a server file path
   (/data/campaign-os/asset-media/x.jpg) and the calendar sent it to the browser.
2. The month took ~7 s on live: campaign-data.json, the drafts folder and the
   post index were read again for every piece of the page.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402
from _lib import unified_inbox as ui  # noqa: E402


def test_a_server_path_becomes_the_web_address():
    assert cc.gbp_image_url("/data/campaign-os/asset-media/gbp-a-1.jpg") == "/asset-media/gbp-a-1.jpg"


def test_web_addresses_and_empty_stay_as_they_are():
    for image in ("", "https://cdn.example.test/a.jpg", "/asset-media/a.jpg", "/static/a.png"):
        assert cc.gbp_image_url(image) == image


def test_google_entries_carry_the_web_address():
    drafts = [{"id": "d1", "status": "approved", "approvedAt": "2026-11-01", "title": "Gloves",
               "imageUrl": "/data/campaign-os/asset-media/gbp-gloves.jpg"}]
    [entry] = cc.gbp_entries(drafts, "swing-shack", first_slot=date(2026, 11, 18))
    assert entry["image"] == "/asset-media/gbp-gloves.jpg"
    assert entry["has_image"] is True


def test_one_post_index_per_brand_inside_a_board(monkeypatch):
    built = []
    monkeypatch.setattr(ui, "_build_post_index", lambda *, brand_id: built.append(brand_id) or object())
    monkeypatch.setattr(ui, "_load_campaign_data", lambda: {"campaigns": {}})
    with ui._board_reads():
        a = ui.build_post_index(brand_id="stick")
        assert ui.build_post_index(brand_id="stick") is a
        ui.build_post_index(brand_id="swing-shack")
    assert built == ["stick", "swing-shack"]
    ui.build_post_index(brand_id="stick")  # outside a board: fresh every time
    assert built == ["stick", "swing-shack", "stick"]


def test_a_nested_board_reuses_the_outer_read(monkeypatch):
    loads = []
    real = ui._load_campaign_data
    monkeypatch.setattr(ui, "_load_campaign_data", lambda: loads.append(1) or real())
    with ui._board_reads():
        with ui._board_reads():
            pass
    assert len(loads) == 1


def test_section_times_add_up_and_format_for_the_header():
    with cc.timings() as took:
        with cc.timed("posts"):
            pass
        with cc.timed("posts"):
            pass
        with cc.timed("google"):
            pass
    assert set(took) == {"posts", "google"}
    header = cc.server_timing(took)
    assert header.startswith("posts;dur=") and ", google;dur=" in header


def test_timed_outside_a_build_records_nothing():
    with cc.timed("posts"):
        pass  # no error, nothing collected
