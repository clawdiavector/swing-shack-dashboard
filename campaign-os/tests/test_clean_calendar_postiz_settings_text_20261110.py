"""Postiz now sends a post's `settings` as JSON text, and repeats every post once per
channel (checked on live, 10 Nov 2026: 890 Swing Shack rows = 178 posts x 5 channels,
all with text settings). The Plan calendar crashed on the text and showed no Postiz
posts at all, for both shops: the Swing Shack 2027 price posts were missing though all
were queued in Postiz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _row(pid, settings, provider="instagram", state="QUEUE", day="2026-11-12T10:00:00.000Z"):
    return {"id": pid, "state": state, "publishDate": day, "content": "<p>Loyalty pays off</p>",
            "settings": settings, "integration": {"id": "int-" + provider, "providerIdentifier": provider}}


def test_text_settings_are_read_not_crashed_on():
    from _lib import clean_calendar as cc

    rows = [_row("p1", json.dumps({"__type": "instagram", "post_type": "story"})),
            _row("p2", json.dumps({"post_type": "post", "__type": "facebook"}), provider="facebook")]
    out = cc.postiz_entries(rows, "swing-shack", linked_ids=set(), month="2026-11")
    by = {e["key"]: e for e in out}
    assert by["postiz:p1"]["format"] == "story"
    assert by["postiz:p1"]["what"] == "An Instagram story"
    assert by["postiz:p2"]["format"] == "feed"


def test_broken_or_odd_settings_do_not_drop_the_month():
    from _lib import clean_calendar as cc

    rows = [_row("p1", "not json"), _row("p2", None), _row("p3", "[1, 2]"),
            _row("p4", {"post_type": "story"})]
    out = cc.postiz_entries(rows, "swing-shack", linked_ids=set(), month="2026-11")
    assert sorted(e["key"] for e in out) == ["postiz:p1", "postiz:p2", "postiz:p3", "postiz:p4"]
    assert {e["key"]: e["format"] for e in out}["postiz:p4"] == "story"


def test_a_post_listed_once_per_channel_shows_once():
    from _lib import clean_calendar as cc

    row = _row("p1", json.dumps({"post_type": "post"}))
    out = cc.postiz_entries([row] * 5, "stick", linked_ids=set(), month="2026-11")
    assert [e["key"] for e in out] == ["postiz:p1"]


def test_failed_post_shows_for_checking():
    from _lib import clean_calendar as cc

    out = cc.postiz_entries([_row("p9", json.dumps({"post_type": "story"}), state="ERROR")],
                            "swing-shack", linked_ids=set(), month="2026-11")
    assert out[0]["status"].startswith("Did not send from Postiz")


class _FakePz:
    def __init__(self):
        self.created = None

    def create_post(self, integration, content, **kw):
        self.created = {"integration": integration, "content": content, **kw}
        return {"ok": True}, None

    def delete_post(self, pid, **kw):
        return {}, None


def test_approving_a_draft_keeps_text_settings():
    from _lib import clean_calendar as cc

    pz = _FakePz()
    row = _row("d1", json.dumps({"__type": "instagram", "post_type": "story"}), state="DRAFT",
               day="2026-12-20T10:00:00.000Z")
    ok, _ = cc.schedule_postiz_draft(pz, "swing-shack", row)
    assert ok is True
    assert (pz.created.get("platform_settings") or {}).get("post_type") == "story"
