"""Mail from Herman is filed as a Do now or an Idea, and Christelle is told.

Pure logic plus a small store; the AgentMail calls are injected.
"""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import mail_intake as mi  # noqa: E402

TODAY = date(2026, 10, 26)
HERMAN = "herman@example.test"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)
    monkeypatch.setenv("MAIL_INTAKE_NOTIFY_TO", "christelle@example.test")


def msg(mid="m1", subject="Hi", text="", sender=f"Herman <{HERMAN}>"):
    return {"message_id": mid, "from": sender, "subject": subject, "text": text,
            "timestamp": "2026-10-26T07:00:00Z"}


# ── classify ──────────────────────────────────────────────────────────

def test_explicit_tag_wins():
    assert mi.classify("IDEA: golf trip", "please do this today")[0] == "idea"
    assert mi.classify("DO: fix the banner", "maybe an idea too")[0] == "do_now"
    assert mi.classify("Idee: ouma se dag", "")[0] == "idea"


def test_idea_words_in_english_and_afrikaans():
    assert mi.classify("Thought", "What if we ran a ladies' day campaign?")[0] == "idea"
    assert mi.classify("Voorstel", "Wat as ons 'n vrouens dag het?")[0] == "idea"


def test_request_words_are_do_now():
    assert mi.classify("Banner", "Please change the banner today, it is urgent")[0] == "do_now"
    assert mi.classify("Kan jy asseblief", "die prys verander vandag")[0] == "do_now"


def test_unsure_goes_to_do_now_so_nothing_is_buried():
    assert mi.classify("Hello", "ok")[0] == "do_now"


# ── brand and date ────────────────────────────────────────────────────

def test_brand_only_when_one_is_named():
    assert mi.detect_brand("new driver at Stick Paarl") == "stick"
    assert mi.detect_brand("Swing Shack Johannesburg bay hire") == "swing-shack"
    assert mi.detect_brand("Stick and Swing Shack both") is None   # two brands: ask
    assert mi.detect_brand("nothing here") is None                 # never default a brand


def test_dates_in_english_afrikaans_and_iso():
    assert mi.extract_date("launch on 27 November", TODAY) == date(2026, 11, 27)
    assert mi.extract_date("Op 3 Desember 2026 is dit", TODAY) == date(2026, 12, 3)
    assert mi.extract_date("on 2026-12-24", TODAY) == date(2026, 12, 24)
    assert mi.extract_date("November 27", TODAY) == date(2026, 11, 27)


def test_past_or_missing_dates_are_none():
    assert mi.extract_date("it was on 2026-10-01", TODAY) is None
    assert mi.extract_date("some time soon", TODAY) is None


def test_a_day_that_already_passed_this_year_means_next_year():
    assert mi.extract_date("on 5 March", TODAY) == date(2027, 3, 5)


# ── filing ────────────────────────────────────────────────────────────

def test_only_allowed_senders_are_filed():
    assert mi.file_message(msg(sender="Stranger <x@evil.test>"), TODAY) is None
    assert mi.list_items() == []


def test_filing_is_idempotent_by_message_id():
    a = mi.file_message(msg("m1", "Please fix", "urgent"), TODAY)
    b = mi.file_message(msg("m1", "Please fix", "urgent"), TODAY)
    assert a and b is None and len(mi.list_items()) == 1


def test_idea_without_brand_or_date_says_what_it_needs():
    it = mi.file_message(msg("m2", "Idea", "What if we did a ladies day"), TODAY)
    assert it["kind"] == "idea" and set(it["needs"]) == {"brand", "date"}


def test_idea_with_brand_and_date_is_ready_for_the_calendar():
    it = mi.file_message(msg("m3", "Idea", "What if Stick ran a demo day on 14 November"), TODAY)
    assert it["brand"] == "stick" and it["date"] == "2026-11-14" and it["needs"] == []


def test_mail_text_is_kept_as_data_and_trimmed():
    it = mi.file_message(msg("m4", "Hi", "x" * 5000), TODAY)
    assert len(it["summary"]) <= mi.SUMMARY_MAX


def test_set_status_done_and_flip_kind():
    it = mi.file_message(msg("m5", "Please", "urgent"), TODAY)
    assert mi.set_status(it["id"], "done")["status"] == "done"
    assert mi.list_items(status="open") == []
    it2 = mi.file_message(msg("m6", "Hello", "ok"), TODAY)
    assert mi.set_kind(it2["id"], "idea")["kind"] == "idea"


# ── the job ───────────────────────────────────────────────────────────

def test_run_intake_files_notifies_and_adds_ready_ideas_to_the_calendar():
    inbox = [
        msg("a", "Please", "urgent: change the banner"),
        msg("b", "Idea", "What if Stick ran a demo day on 14 November"),
        msg("c", "spam", "buy now", sender="Bot <bot@evil.test>"),
    ]
    sent, added = [], []
    out = mi.run_intake(
        fetch=lambda: inbox,
        notify=lambda to, subject, text: sent.append((to, subject, text)),
        add_suggestion=lambda brand, item: added.append((brand, item["date"])) or "cal-1",
        today=TODAY,
    )
    assert out["ok"] and out["filed"] == 2 and out["do_now"] == 1 and out["ideas"] == 1
    assert added == [("stick", "2026-11-14")]
    assert len(sent) == 1 and sent[0][0] == "christelle@example.test"
    assert "Do now" in sent[0][2] and "Idea" in sent[0][2]
    assert "evil" not in sent[0][2]


def test_run_intake_second_run_is_quiet():
    inbox = [msg("a", "Please", "urgent")]
    sent = []
    kw = dict(fetch=lambda: inbox, notify=lambda *a: sent.append(a),
              add_suggestion=lambda b, i: "x", today=TODAY)
    mi.run_intake(**kw)
    out = mi.run_intake(**kw)
    assert out["filed"] == 0 and len(sent) == 1


def test_not_configured_is_reported_not_raised(monkeypatch):
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    monkeypatch.delenv("AGENTMAIL_INBOX", raising=False)
    out = mi.run_intake_live(today=TODAY)
    assert out["ok"] is False and "AGENTMAIL" in out["error"]


def test_a_failed_notice_does_not_lose_the_item():
    def boom(*a):
        raise RuntimeError("smtp down")
    out = mi.run_intake(fetch=lambda: [msg("a", "Please", "urgent")], notify=boom,
                        add_suggestion=lambda b, i: "x", today=TODAY)
    assert out["filed"] == 1 and out["notice_failed"] is True
    assert len(mi.list_items()) == 1
