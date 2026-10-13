"""Plan from a date: dated checklist, editing, approval rules."""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import campaign_plan as cp  # noqa: E402

TODAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def brief(status="approved", d="2026-12-05", bid="brf-test0001"):
    return {"brief_id": bid, "status": status,
            "source_opportunity": {"name": "Black Friday", "date": d}}


def test_items_work_backwards_from_event():
    items = cp.build_items(date(2026, 12, 5), TODAY)
    by = {(i["kind"], i["days_before_event"]): i for i in items}
    assert by[("review", 7)]["due"] == "2026-11-28"
    assert by[("post", 0)]["due"] == "2026-12-05"
    assert [i["due"] for i in items] == sorted(i["due"] for i in items)


def test_boost_comes_with_real_video_shoot():
    items = cp.build_items(date(2026, 12, 5), TODAY)
    assert any(i["kind"] == "boost" for i in items)
    assert any(i["kind"] == "shoot" and i["needs_real_video"] for i in items)


def test_short_lead_has_no_boost():
    items = cp.build_items(date(2026, 10, 20), TODAY)
    assert not any(i["kind"] == "boost" for i in items)


def test_past_dates_flagged_late_not_moved():
    items = cp.build_items(date(2026, 10, 20), TODAY)
    research = next(i for i in items if i["kind"] == "research")
    assert research["due"] == "2026-09-29" and research["late"] is True


def test_propose_refuses_rejected_and_undated():
    assert not cp.propose_plan("stick", brief("rejected"), today=TODAY)["ok"]
    assert not cp.propose_plan("stick", brief(d=""), today=TODAY)["ok"]


def test_one_plan_per_brief_and_force_supersedes():
    a = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    again = cp.propose_plan("stick", brief(), today=TODAY)
    assert again["existing"] and again["plan"]["plan_id"] == a["plan_id"]
    b = cp.propose_plan("stick", brief(), force=True, today=TODAY)["plan"]
    assert b["plan_id"] != a["plan_id"]
    assert cp.get_plan("stick", a["plan_id"])["status"] == "superseded"


def test_edit_change_date_and_remove_and_add():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    it = p["items"][0]
    r = cp.edit_item("stick", p["plan_id"], it["item_id"],
                     {"due": "2026-11-20", "title": "New idea"})
    assert r["item"]["due"] == "2026-11-20" and r["item"]["source"] == "operator"
    assert not cp.edit_item("stick", p["plan_id"], it["item_id"],
                            {"kind": "nope"})["ok"]
    assert not cp.edit_item("stick", p["plan_id"], it["item_id"],
                            {"item_id": "x"})["ok"]
    cp.edit_item("stick", p["plan_id"], it["item_id"], {"status": "removed"})
    a = cp.add_item("stick", p["plan_id"],
                    {"title": "Email list", "due": "2026-11-30", "kind": "post"})
    assert a["ok"] and len(a["plan"]["items"]) == len(p["items"]) + 1


def test_approve_needs_approved_brief():
    p = cp.propose_plan("stick", brief("draft"), today=TODAY)["plan"]
    assert not cp.approve_plan("stick", p["plan_id"])["ok"]


def test_approve_locks_then_reopen():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    assert cp.approve_plan("stick", p["plan_id"])["ok"]
    first = p["items"][0]["item_id"]
    assert not cp.edit_item("stick", p["plan_id"], first, {"title": "x"})["ok"]
    assert cp.edit_item("stick", p["plan_id"], first, {"status": "done"})["ok"]
    assert cp.reopen_plan("stick", p["plan_id"])["ok"]
    assert cp.edit_item("stick", p["plan_id"], first, {"title": "x"})["ok"]


def test_boost_without_video_blocks_approval():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    for i in p["items"]:
        if i["kind"] == "shoot" and i["needs_real_video"]:
            cp.edit_item("stick", p["plan_id"], i["item_id"],
                         {"status": "removed"})
    r = cp.approve_plan("stick", p["plan_id"])
    assert not r["ok"] and "real human video" in r["error"]


def test_sync_brief_status_unsticks_a_plan():
    p = cp.propose_plan("stick", brief("draft"), today=TODAY)["plan"]
    assert not cp.approve_plan("stick", p["plan_id"])["ok"]
    cp.sync_brief_status(cp.get_plan("stick", p["plan_id"]), brief("approved"))
    assert cp.get_plan("stick", p["plan_id"])["brief_status"] == "approved"
    assert cp.approve_plan("stick", p["plan_id"])["ok"]


def _approved_plan():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    assert cp.approve_plan("stick", p["plan_id"])["ok"]
    return p["plan_id"]


class FakeCalendar:
    def __init__(self):
        self.rows, self.moved = [], []

    def add(self, brand, record, status):
        rec = dict(record, calendar_id=f"cal-{len(self.rows)}", status=status)
        self.rows.append(rec)
        return rec

    def transition(self, brand, cid, status, reason=""):
        self.moved.append((cid, status))


def test_place_needs_approved_plan():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    r = cp.place_on_calendar("stick", p["plan_id"], add_record=FakeCalendar().add)
    assert not r["ok"] and "approve" in r["error"]


def test_place_creates_content_and_reminders_once():
    pid = _approved_plan()
    cal = FakeCalendar()
    r = cp.place_on_calendar("stick", pid, add_record=cal.add)
    assert r["ok"] and r["placed"] == len(cal.rows) > 0
    types = {row["plan_item_kind"]: row["type"] for row in cal.rows}
    assert types["post"] == "content" and types["story"] == "content"
    assert types["shoot"] == "reminder" and types["boost"] == "reminder"
    assert all(row["status"] == "approved" for row in cal.rows)
    again = cp.place_on_calendar("stick", pid, add_record=cal.add)
    assert again["placed"] == 0 and len(cal.rows) == r["placed"]


def test_removed_steps_are_not_placed():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    gone = p["items"][0]
    cp.edit_item("stick", p["plan_id"], gone["item_id"], {"status": "removed"})
    cp.approve_plan("stick", p["plan_id"])
    cal = FakeCalendar()
    cp.place_on_calendar("stick", p["plan_id"], add_record=cal.add)
    assert all(row["plan_item_id"] != gone["item_id"] for row in cal.rows)


def test_take_off_undoes_and_unblocks_reopen():
    pid = _approved_plan()
    cal = FakeCalendar()
    cp.place_on_calendar("stick", pid, add_record=cal.add)
    assert not cp.reopen_plan("stick", pid)["ok"]
    r = cp.take_off_calendar("stick", pid, transition=cal.transition)
    assert r["ok"] and r["removed"] == len(cal.rows)
    assert all(status == "ignored" for _, status in cal.moved)
    assert cp.get_plan("stick", pid)["placed_at"] is None
    assert cp.reopen_plan("stick", pid)["ok"]


def test_one_failed_step_is_reported_not_hidden():
    pid = _approved_plan()
    cal = FakeCalendar()

    def flaky(brand, record, status):
        if record["plan_item_kind"] == "boost":
            raise ValueError("no")
        return cal.add(brand, record, status)

    r = cp.place_on_calendar("stick", pid, add_record=flaky)
    assert not r["ok"] and len(r["failed"]) == 1 and r["placed"] > 0
    retry = cp.place_on_calendar("stick", pid, add_record=cal.add)
    assert retry["placed"] == 1


def test_latest_revisions_lets_an_undo_hide_the_old_row():
    from _lib.marketing_calendar import latest_revisions
    rows = [
        {"calendar_id": "a", "status": "approved"},
        {"calendar_id": "b", "status": "approved"},
        {"calendar_id": "a", "status": "ignored"},
        {"status": "approved", "title": "no id"},
    ]
    kept = latest_revisions(rows)
    assert [(r.get("calendar_id"), r["status"]) for r in kept] == [
        ("b", "approved"), ("a", "ignored"), (None, "approved")]
