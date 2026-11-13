"""Staff leads message, and sending the staff messages to each facility's WhatsApp group.

Leads (Christelle, 13 Nov 2026): new since yesterday, and "check on these" (not contacted
for 3+ days), first names only. Sending: one Zernio WhatsApp group per facility, posted
with the staff key (ZERNIO_API_KEY_STAFF); nothing goes out until the groups are set up,
and one idempotency key per day, kind and facility so a retried run can't send twice.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import staff_messages as sm  # noqa: E402
from _lib import zernio_client as zc  # noqa: E402

NOW = dt.datetime(2026, 11, 13, 7, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))


def _lead(name, created, stage="new", ad="Free assessment Nov"):
    return {"id": name, "name": name, "created": created, "stage": stage, "ad_name": ad, "phone": "0820000000"}


LEADS = [
    _lead("Pieter van Wyk", "2026-11-12T19:30:00+02:00"),
    _lead("Sarah Jacobs", "2026-11-13T06:10:00+02:00", ad=""),
    _lead("Thandi Mokoena", "2026-11-12T09:00:00+02:00", stage="contacted"),  # new, already contacted
    _lead("Johan Botha", "2026-11-09T10:00:00+02:00"),                          # 4 days, never contacted
    _lead("Anna Smit", "2026-11-11T10:00:00+02:00"),                            # 2 days: not yet
    _lead("Old Lead", "2026-09-01T10:00:00+02:00"),                             # too old to chase
    _lead("Booked Person", "2026-11-05T10:00:00+02:00", stage="booked"),
    _lead("Lost Person", "2026-11-05T10:00:00+02:00", stage="lost"),
]


def test_the_leads_message_shows_new_leads_and_who_to_check_on():
    msg = sm.leads_message("stick", LEADS, NOW, "https://x/ads-brief?brand=stick")
    assert msg["send"]
    assert msg["text"] == (
        "Stick leads, Fri 13 Nov\n\n"
        "New since yesterday (3):\n"
        "• Sarah: from a Meta ad\n"
        "• Pieter: from the ad \"Free assessment Nov\"\n"
        "• Thandi: from the ad \"Free assessment Nov\" (contacted)\n\n"
        "Check on these (not contacted for 3+ days):\n"
        "• Johan: waiting since Mon 9 Nov\n\n"
        "Message them on WhatsApp or reply to their DM, then mark them in the Leads tab: "
        "https://x/ads-brief?brand=stick"
    )
    for hidden in ("van Wyk", "Jacobs", "0820000000", "Anna", "Old", "Booked", "Lost"):
        assert hidden not in msg["text"]


def test_no_leads_means_no_message():
    assert sm.leads_message("stick", [], NOW, "https://x")["send"] is False
    assert sm.leads_message("stick", [_lead("Anna", "2026-11-11T10:00:00+02:00")], NOW, "https://x")["send"] is False


def test_long_lead_lists_are_cut_with_a_pointer_to_the_tab():
    many = [_lead(f"Lead{i} X", "2026-11-13T05:00:00+02:00") for i in range(8)]
    text = sm.leads_message("swing-shack", many, NOW, "https://x")["text"]
    assert text.startswith("Swing Shack leads, Fri 13 Nov")
    assert text.count("• ") == sm.MAX_ITEMS
    assert "…and 3 more in the Leads tab" in text


def test_the_zernio_send_uses_the_staff_key_and_the_group_conversation(monkeypatch):
    calls = []
    monkeypatch.setattr(zc, "_request", lambda *a, **k: calls.append((a, k)) or ({"success": True}, None))
    monkeypatch.delenv("ZERNIO_API_KEY_STAFF", raising=False)
    out, err = zc.send_message("conv1", account_id="acc1", text="Hi", key="staff", idempotency_key="k1")
    assert out is None and "ZERNIO_API_KEY_STAFF" in err and not calls

    monkeypatch.setenv("ZERNIO_API_KEY_STAFF", "test-not-a-secret")
    out, err = zc.send_message("conv1", account_id="acc1", text="Hi", key="staff", idempotency_key="k1")
    assert err is None
    (method, path, brand), kw = calls[0][0][:3], calls[0][1]
    assert (method, path, brand) == ("POST", "/inbox/conversations/conv1/messages", "staff")
    assert calls[0][0][3] == {"accountId": "acc1", "message": "Hi"}
    assert kw["idempotency_key"] == "k1"


@pytest.fixture(scope="module")
def loaded_app(tmp_path_factory):
    base = tmp_path_factory.mktemp("cosdata")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(base))
    mp.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    sys.modules.pop("app", None)
    import app as app_module

    app_module._GIT_SYNC_DONE = True
    yield app_module
    mp.undo()


AUTH = {"Authorization": "Bearer test-job-token-not-a-secret"}


def _setup(loaded_app, monkeypatch):
    monkeypatch.setattr(loaded_app, "COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setattr(loaded_app, "_jhb_today", lambda: NOW.date())
    monkeypatch.setattr(loaded_app, "_jhb_now", lambda: NOW, raising=False)
    monkeypatch.setattr(loaded_app, "_staff_now", lambda: NOW)
    monkeypatch.setattr(loaded_app, "_ads_lane_load",
                        lambda b, rel: {"leads": LEADS} if rel == "ads-leads/leads.json" and b == "stick" else None)
    return loaded_app.app.test_client(cos_anon=True)


def test_the_leads_kind_reads_each_facilitys_lead_store(loaded_app, monkeypatch):
    anon = _setup(loaded_app, monkeypatch)
    r = anon.get("/api/jobs/staff-message?kind=leads&brand=stick", headers=AUTH).get_json()
    assert r["ok"] and r["send"] and "• Johan: waiting since Mon 9 Nov" in r["text"]
    assert "/ads-brief?brand=stick" in r["text"]
    r = anon.get("/api/jobs/staff-message?kind=leads&brand=swing-shack", headers=AUTH).get_json()
    assert r["ok"] and r["send"] is False


def test_sending_waits_until_the_groups_are_set_up(loaded_app, monkeypatch):
    anon = _setup(loaded_app, monkeypatch)
    monkeypatch.delenv("STAFF_WHATSAPP_GROUPS", raising=False)
    monkeypatch.delenv("STAFF_WHATSAPP_ACCOUNT_ID", raising=False)
    assert anon.post("/api/jobs/staff-whatsapp?kind=leads").status_code == 401
    assert anon.post("/api/jobs/staff-whatsapp?kind=gossip", headers=AUTH).status_code == 400
    r = anon.post("/api/jobs/staff-whatsapp?kind=leads", headers=AUTH).get_json()
    assert r["ok"] and r["sent"] == 0 and "not set up" in r["note"]


def test_sending_posts_once_per_facility_that_has_something_to_say(loaded_app, monkeypatch):
    anon = _setup(loaded_app, monkeypatch)
    monkeypatch.setenv("STAFF_WHATSAPP_ACCOUNT_ID", "acc1")
    monkeypatch.setenv("STAFF_WHATSAPP_GROUPS", json.dumps({"stick": "conv-stick", "swing-shack": "conv-ss"}))
    sent = []
    monkeypatch.setattr(zc, "send_message", lambda cid, **k: sent.append((cid, k)) or ({"success": True}, None))

    r = anon.post("/api/jobs/staff-whatsapp?kind=leads&dry_run=1", headers=AUTH).get_json()
    assert r["ok"] and r["sent"] == 0 and not sent
    assert r["results"]["stick"]["would_send"] and r["results"]["swing-shack"]["status"] == "nothing to send"

    r = anon.post("/api/jobs/staff-whatsapp?kind=leads", headers=AUTH).get_json()
    assert r["ok"] and r["sent"] == 1
    cid, k = sent[0]
    assert cid == "conv-stick" and k["account_id"] == "acc1" and k["key"] == "staff"
    assert k["idempotency_key"] == "staff-leads-stick-2026-11-13"
    assert k["text"].startswith("Stick leads, Fri 13 Nov")


def test_a_failed_send_is_reported_not_hidden(loaded_app, monkeypatch):
    anon = _setup(loaded_app, monkeypatch)
    monkeypatch.setenv("STAFF_WHATSAPP_ACCOUNT_ID", "acc1")
    monkeypatch.setenv("STAFF_WHATSAPP_GROUPS", json.dumps({"stick": "conv-stick"}))
    monkeypatch.setattr(zc, "send_message", lambda cid, **k: (None, "HTTP 400: not in group"))
    resp = anon.post("/api/jobs/staff-whatsapp?kind=leads&brand=stick", headers=AUTH)
    r = resp.get_json()
    assert resp.status_code == 502 and r["ok"] is False
    assert r["results"]["stick"]["error"] == "HTTP 400: not in group"
