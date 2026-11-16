"""A poster that fails to build must say why (G4 test, 2026-11-16).

Approved Stick and Bag Drop items got a caption and then sat at
compose_post = pending with no note, while the run reported OK.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

FAKE_CAPTION = {
    "ok": True,
    "survivors": [
        {
            "body": "Fit first. Buy second.\n\nBook a fitting",
            "copy_package": {
                "caption_body": "Fit first. Buy second.",
                "poster_hook": "THE FITTING COMES FIRST",
                "cta_line": "Book a fitting",
                "locale": "en-ZA",
                "source": "llm",
            },
            "candidate_id": "c-1",
            "route": "r1",
            "mechanism": "m",
            "rhetorical_structure": "s",
            "checks": {},
        }
    ],
    "observability": {"provider": "openai", "model": "x"},
    "rejects": {},
}


def _queue_rows(data_dir: str, cal_id: str) -> list[dict]:
    doc = json.loads((Path(data_dir) / "agent-queue.json").read_text())
    rows = doc.get("rows", doc) if isinstance(doc, dict) else doc
    return [r for r in rows if cal_id in json.dumps(r)]


def test_failed_compose_leaves_a_note_and_is_reported():
    with tempfile.TemporaryDirectory() as data_dir, mock.patch.dict(os.environ, {"DATA_DIR": data_dir}):
        import app as cos_app
        from _lib import p11_context_engine as p11
        from _lib.jobs.layer5 import create_photo_compose as cpc
        from _lib.jobs.layer5 import draft_assets as da

        client = cos_app.app.test_client()
        with mock.patch.object(cos_app, "_is_job_authed", lambda *a, **k: True), mock.patch.object(
            cos_app, "_is_authed", lambda *a, **k: True
        ), mock.patch.object(p11, "run_caption_pipeline", lambda req: FAKE_CAPTION), mock.patch(
            "_lib.llm_spend.check", lambda *a, **k: (True, "")
        ), mock.patch.object(
            cpc, "process_compose_post_row", lambda *a, **k: (None, "missing asset images/x.png")
        ):
            made = client.post(
                "/api/calendar/candidates",
                json={
                    "brand_id": "stick",
                    "type": "moment",
                    "title": "THE FITTING COMES FIRST",
                    "post_type": "brand_statement",
                    "event_date": "2027-06-15",
                    "event_start": "2027-06-15",
                    "event_end": "2027-06-15",
                    "primary_channel": "instagram",
                    "created_by": "kyle",
                    "source_type": "manual",
                },
            ).get_json()
            cal_id = made["record"]["calendar_id"]
            ok = client.post(
                f"/api/inbox/unified/calendar_candidate:stick:{cal_id}/approve",
                json={"editor": "kyle", "mode": "lodge"},
            ).get_json()
            assert ok["ok"], ok
            out = da.run("stick")

        compose = [r for r in _queue_rows(data_dir, cal_id) if r.get("action") == "compose_post"]
        assert compose, "compose_post should be queued after the caption"
        assert compose[0]["status"] == "pending"
        assert compose[0].get("note") == "compose: missing asset images/x.png"
        assert any("missing asset images/x.png" in e for e in out.get("compose_errors", []))
