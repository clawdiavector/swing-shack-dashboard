"""The working list from the plans, and the morning message."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import plan_todo as pt  # noqa: E402

TODAY = dt.date(2026, 10, 14)   # a Wednesday


def item(i, kind, due, title="A step", status="kept", **kw):
    return {"item_id": i, "kind": kind, "due": due, "title": title, "status": status, **kw}


def plan(items, pid="pln-1", status="proposed", name="Valentine's Day"):
    return {"plan_id": pid, "status": status, "event_name": name, "event_date": "2027-02-14",
            "event_kind": "retail_push", "items": items}


def steps(items, **kw):
    return pt.todo_steps("stick", [plan(items, **kw)], TODAY)


def test_buckets_by_how_far_off_a_step_is():
    assert pt.bucket_for(dt.date(2026, 10, 13), TODAY) == "overdue"
    assert pt.bucket_for(TODAY, TODAY) == "today"
    assert pt.bucket_for(dt.date(2026, 10, 21), TODAY) == "this_week"
    assert pt.bucket_for(dt.date(2026, 10, 22), TODAY) == "later"
    assert pt.bucket_for(dt.date(2026, 11, 13), TODAY) == "later"
    assert pt.bucket_for(dt.date(2026, 11, 14), TODAY) is None


def test_the_list_skips_done_removed_superseded_and_far_off_steps_and_is_ordered():
    s = steps([
        item("a", "post", "2026-10-20", "This week"),
        item("b", "post", "2026-10-10", "Overdue one"),
        item("c", "post", "2026-10-14", "Today one"),
        item("d", "post", "2026-10-11", "Done", status="done"),
        item("e", "post", "2026-10-12", "Removed", status="removed"),
        item("f", "post", "2027-02-01", "Far off"),
        item("g", "post", "2026-10-30", "Later"),
        item("h", "post", "not a date"),
    ])
    assert [x["title"] for x in s] == ["Overdue one", "Today one", "This week", "Later"]
    assert [x["bucket"] for x in s] == ["overdue", "today", "this_week", "later"]
    assert pt.todo_steps("stick", [plan([item("a", "post", "2026-10-14")], status="superseded")], TODAY) == []


def test_each_step_says_what_it_still_needs():
    s = steps([
        item("a", "shoot", "2026-10-14", "Shoot photos"),
        item("b", "shoot", "2026-10-15", "Shoot video", shots=["A clip"], asked={"to": "Pieter", "at": "x"}),
        item("c", "boost", "2026-10-16", "Boost"),
        item("d", "boost", "2026-10-17", "Boost two", budget=500),
        item("e", "post", "2026-10-18", "A post"),
    ])
    by = {x["item_id"]: x["needs"] for x in s}
    assert by["a"] == ["no shot list yet", "nobody asked yet"]
    assert by["b"] == []
    assert by["c"] == ["no budget yet"] and by["d"] == [] and by["e"] == []


def test_group_by_bucket_keeps_every_bucket():
    g = pt.group_by_bucket(steps([item("a", "post", "2026-10-14")]))
    assert list(g) == list(pt.BUCKETS) and len(g["today"]) == 1 and g["overdue"] == []


def alert(msg, level="scream"):
    return {"message": msg, "level": level}


def test_the_morning_message_leads_with_what_is_close_and_not_ready():
    s = steps([item("a", "shoot", "2026-10-10", "Shoot photos"), item("b", "post", "2026-10-14", "Teaser")])
    text = pt.morning_text({"stick": {"alerts": [alert("Black Friday is on now and has no plan."),
                                                  alert("Festive Gifting is in 34 days and has no plan.", "warn")],
                                      "steps": s}}, TODAY)
    assert text.startswith("Good morning. Calendar check, Wed 14 Oct.")
    assert "Close and not ready:\n• Black Friday is on now and has no plan." in text
    assert "Festive Gifting" not in text                      # a warning is not for the morning message
    assert "Overdue (1):" in text and "was due 4 days ago" in text and "no shot list yet" in text
    assert "Due today (1):\n• Post: Teaser — Valentine's Day" in text
    assert text.index("Close and not ready") < text.index("Overdue") < text.index("Due today")


def test_the_message_is_short_when_there_is_a_lot_and_says_so_when_there_is_nothing():
    many = steps([item(str(n), "post", "2026-10-10", f"Step {n}") for n in range(8)])
    text = pt.morning_text({"stick": {"alerts": [], "steps": many}}, TODAY)
    assert text.count("• Post:") == pt.MAX_LINES and "…and 3 more" in text
    assert pt.morning_text({"stick": {"alerts": [], "steps": []}}, TODAY).endswith("Nothing needs you today.")


def test_several_brands_get_their_own_heading_and_one_brand_does_not():
    s = steps([item("a", "post", "2026-10-14", "Teaser")])
    both = pt.morning_text({"stick": {"alerts": [], "steps": s}, "swing-shack": {"alerts": [], "steps": s}}, TODAY)
    assert "— Stick —" in both and "— Swing Shack —" in both
    assert "— Stick —" not in pt.morning_text({"stick": {"alerts": [], "steps": s}}, TODAY)


def test_an_approved_placed_post_with_no_draft_says_so_until_one_is_asked_for():
    base = {"plan_id": "pln-1", "status": "approved", "event_name": "X", "event_date": "2027-02-14", "items": [
        item("a", "post", "2026-10-15", "Teaser", calendar_id="cal-1"),
        item("b", "post", "2026-10-16", "Reminder", calendar_id="cal-2", draft={"requested_at": "x"}),
        item("c", "post", "2026-10-17", "Not placed yet"),
        item("d", "story", "2026-10-18", "A story", calendar_id="cal-4"),
    ]}
    by = {s["item_id"]: s["needs"] for s in pt.todo_steps("stick", [base], TODAY)}
    assert by["a"] == ["no draft yet"] and by["b"] == [] and by["c"] == [] and by["d"] == []
    draft_plan = dict(base, status="proposed")
    assert all(s["needs"] == [] for s in pt.todo_steps("stick", [draft_plan], TODAY))
