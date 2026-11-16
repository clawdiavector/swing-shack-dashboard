"""Approving a Postiz draft from the Plan calendar keeps its settings when Postiz sends
them as JSON text (10 Nov 2026). create_post takes them as `platform_settings`; the
draft test in test_clean_calendar_postiz_settings_text_20261110.py asks for `settings`,
which create_post does not take, so that one assertion is wrong and needs fixing by
whoever may edit committed tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


class _FakePz:
    def __init__(self):
        self.created = None

    def create_post(self, integration, content, **kw):
        self.created = {"integration": integration, "content": content, **kw}
        return {"ok": True}, None

    def delete_post(self, pid, **kw):
        return {}, None


def test_approving_a_draft_passes_text_settings_to_postiz():
    from _lib import clean_calendar as cc

    pz = _FakePz()
    row = {"id": "d2", "state": "DRAFT", "publishDate": "2026-12-20T10:00:00.000Z",
           "content": "Story", "settings": json.dumps({"__type": "instagram", "post_type": "story"}),
           "integration": {"id": "int-ig", "providerIdentifier": "instagram"}}
    ok, _ = cc.schedule_postiz_draft(pz, "swing-shack", row)
    assert ok is True
    assert (pz.created.get("platform_settings") or {}).get("post_type") == "story"
