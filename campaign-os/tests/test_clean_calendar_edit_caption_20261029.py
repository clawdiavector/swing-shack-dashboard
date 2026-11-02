"""Christelle can edit a post's caption from the clean calendar while it waits for a yes.
Herman's share link cannot edit, and an approved or sent post is not edited here."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402

WAITING = {"calendar_id": "c1", "state": "draft_ready", "go_live_date": "2099-01-05", "primary_channel": "instagram"}
SCHEDULED = {**WAITING, "state": "scheduled"}
BODY = {"key": "c1", "kind": "post", "action": "edit", "text": "New caption.\nBetter begins here."}


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app

    return app


@pytest.fixture
def edits(monkeypatch):
    from _lib import unified_inbox as ui

    calls: list = []
    monkeypatch.setattr(ui, "edit_item", lambda item_id, editor="operator", fields=None:
                        calls.append((item_id, editor, fields)) or {"ok": True, "changed": ["caption"]})
    monkeypatch.setattr(cc, "add_comment", lambda *a, **k: None)
    return calls


def _with_row(monkeypatch, row):
    monkeypatch.setattr(cc, "find_post", lambda brand, key: (row, {"inbox_item_id": "draft_asset:camp:a1", "caption": "Old"}))


def test_only_a_post_waiting_for_a_yes_is_editable():
    assert cc.post_entry(WAITING, "stick")["editable"] is True
    assert cc.post_entry(SCHEDULED, "stick")["editable"] is False
    assert cc.post_entry({**WAITING, "state": "posted"}, "stick")["editable"] is False
    assert cc.post_entry({**WAITING, "plan_item_kind": "shoot"}, "stick")["editable"] is False


def test_edit_saves_the_caption_through_the_inbox(app_module, monkeypatch, edits):
    _with_row(monkeypatch, WAITING)
    with app_module.app.test_request_context():
        out, code = app_module._clean_cal_act("stick", BODY, "Christelle")
    assert code == 200, out
    assert edits == [("draft_asset:camp:a1", "Christelle", {"caption": BODY["text"]})]


def test_an_empty_caption_is_refused(app_module, monkeypatch, edits):
    _with_row(monkeypatch, WAITING)
    with app_module.app.test_request_context():
        out, code = app_module._clean_cal_act("stick", {**BODY, "text": "  "}, "Christelle")
    assert code == 400 and edits == []


def test_an_approved_post_is_not_edited_here(app_module, monkeypatch, edits):
    _with_row(monkeypatch, SCHEDULED)
    with app_module.app.test_request_context():
        out, code = app_module._clean_cal_act("stick", BODY, "Christelle")
    assert code == 409 and edits == []


def test_the_share_link_cannot_edit(app_module, monkeypatch, edits):
    from flask import g

    _with_row(monkeypatch, WAITING)
    with app_module.app.test_request_context():
        g.calendar_share_authed = True
        out, code = app_module._clean_cal_act("stick", BODY, "Herman")
    assert code == 403 and edits == []
