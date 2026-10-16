"""The plan banner alerts only on dates approved on the Main Calendar.

The event spine lists every date for the year, approved or not. An unapproved
spine date must not show up as "approved and not ready", and a date that has
been approved must still show up.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app as app_module  # noqa: E402
from _lib import campaign_plan as cp  # noqa: E402
from _lib import marketing_calendar as mc  # noqa: E402


def _soon(days):
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def _spine(*events):
    return lambda brand_id, yr: ({"events": list(events)}, "test")


def _setup(monkeypatch, spine_events, calendar_rows):
    monkeypatch.setattr(app_module, "_load_events_for_year", _spine(*spine_events))
    monkeypatch.setattr(app_module, "_brief_ids_by_event", lambda brand_id: {})
    monkeypatch.setattr(mc, "list_records", lambda brand_id, status_filter=None: calendar_rows)
    monkeypatch.setattr(cp, "list_plans", lambda brand_id: [])


def test_unapproved_spine_date_is_not_alerted(monkeypatch):
    spine = {"id": "black-friday-2026", "name": "Black Friday", "tier": "A-PIN",
             "start": _soon(5), "end": _soon(40)}
    _setup(monkeypatch, [spine], calendar_rows=[])
    assert app_module._alerts_for_brand("swing-shack") == []


def test_approved_calendar_date_is_alerted(monkeypatch):
    row = {"calendar_id": "cal-1", "event_key": "heritage-day", "type": "moment",
           "status": "approved", "title": "Heritage Day", "event_start": _soon(7),
           "event_end": _soon(7), "tier": "A-PIN", "revision": 1}
    _setup(monkeypatch, [], calendar_rows=[row])
    alerts = app_module._alerts_for_brand("swing-shack")
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Heritage Day" and alerts[0]["level"] == "scream"


def test_only_the_approved_date_is_alerted_when_both_exist(monkeypatch):
    spine = [{"id": "black-friday-2026", "name": "Black Friday", "tier": "A-PIN",
              "start": _soon(5), "end": _soon(40)}]
    row = {"calendar_id": "cal-1", "event_key": "heritage-day", "type": "moment",
           "status": "approved", "title": "Heritage Day", "event_start": _soon(7),
           "event_end": _soon(7), "tier": "A-PIN", "revision": 1}
    _setup(monkeypatch, spine, calendar_rows=[row])
    names = [a["name"] for a in app_module._alerts_for_brand("swing-shack")]
    assert names == ["Heritage Day"]
