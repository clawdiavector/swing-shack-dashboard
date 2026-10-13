"""Faded suggestions on the month calendar."""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import calendar_suggestions as cs  # noqa: E402

TODAY = date(2026, 10, 13)


def row(cid, title, d, **kw):
    return {"calendar_id": cid, "title": title, "public_peak": d, "status": "candidate", **kw}


def mine(r):
    return r.get("created_by") == "operator"


def items(pending=(), notes=(), decisions=None, names=(), month="2026-11", brand="stick"):
    return cs.month_items(brand, month, pending, mine, notes, decisions or {}, names, TODAY)


def test_month_bounds():
    assert cs.month_bounds("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    assert cs.month_bounds("2027-02")[1] == date(2027, 2, 28)
    with pytest.raises(ValueError):
        cs.month_bounds("nope")


def test_pending_rows_in_month_only_and_labelled():
    out = items(pending=[
        row("c1", "Yours", "2026-11-10", created_by="operator"),
        row("c2", "Scout find", "2026-11-12"),
        row("c3", "Other month", "2026-12-10", created_by="operator"),
    ])
    assert [(i["title"], i["source"]) for i in out] == [("Yours", "yours"), ("Scout find", "scout")]
    assert out[0]["key"] == "row:c1" and out[0]["calendar_id"] == "c1"


def test_scout_rows_drop_past_and_test_rows_but_yours_stay():
    out = items(month="2026-10", pending=[
        row("c1", "Past scout", "2026-10-02"),
        row("c2", "TEST — DO NOT RELEASE", "2026-10-20"),
        row("c3", "Past but typed by you", "2026-10-02", created_by="operator"),
    ])
    assert [i["title"] for i in out] == ["Past but typed by you"]


def test_important_dates_offered_until_decided():
    notes = [{"event_name": "Springbok test", "start_date": "2026-11-07", "notes": "Rugby. Tier B.",
              "event_type": "SA_SPORT"}]
    out = items(notes=notes)
    assert len(out) == 1 and out[0]["source"] == "date" and out[0]["tier"] == "B-PIN"
    assert items(notes=notes, decisions={out[0]["key"]: {"decision": "rejected"}}) == []


def test_date_already_on_the_calendar_is_not_offered_again():
    notes = [{"event_name": "Black Friday", "start_date": "2026-11-27"}]
    assert items(notes=notes, names=["Black Friday + Cyber Monday"]) == []


def test_other_brands_local_dates_are_left_off():
    notes = [{"event_name": "Cape Epic", "start_date": "2026-11-07", "notes": "Western Cape"}]
    assert items(notes=notes, brand="swing-shack") == []
    assert len(items(notes=notes, brand="stick")) == 1


def test_decisions_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert cs.read_decisions("stick") == {}
    cs.record_decision("stick", "note:x:2026-11-07", "rejected", "Christelle")
    assert cs.read_decisions("stick")["note:x:2026-11-07"]["decision"] == "rejected"
    assert cs.clear_decision("stick", "note:x:2026-11-07") is True
    assert cs.clear_decision("stick", "note:x:2026-11-07") is False
    assert cs.read_decisions("stick") == {}


def test_undo_tokens_work_once_and_lapse_after_a_day(tmp_path, monkeypatch):
    import datetime as dt
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    now = dt.datetime(2026, 10, 13, 12, 0, tzinfo=dt.timezone.utc)
    payload = {"kind": "approve", "key": "k", "calendar_id": "c1"}
    token = cs.issue_undo("stick", payload, now=now)
    assert cs.get_undo("stick", token, now=now + dt.timedelta(hours=1)) == payload
    assert cs.get_undo("stick", "und-made-up", now=now) is None
    assert cs.get_undo("stick", None, now=now) is None
    assert cs.get_undo("stick", token, now=now + dt.timedelta(hours=25)) is None   # lapsed
    cs.drop_undo("stick", token)
    assert cs.get_undo("stick", token, now=now) is None                            # used
    # issuing a new one sweeps out lapsed ones
    old = cs.issue_undo("stick", payload, now=now - dt.timedelta(hours=30))
    fresh = cs.issue_undo("stick", payload, now=now)
    assert cs.get_undo("stick", old, now=now - dt.timedelta(hours=29)) is None
    assert cs.get_undo("stick", fresh, now=now) == payload


def test_an_agent_find_already_on_the_calendar_is_hidden_but_an_operators_stays():
    rows = [row("c1", "Black Friday 2027 push", "2026-11-10"),
            row("c2", "Black Friday 2027 push", "2026-11-11", created_by="operator")]
    out = items(pending=rows, names=["Black Friday 2027 push"])
    assert [i["calendar_id"] for i in out] == ["c2"]
