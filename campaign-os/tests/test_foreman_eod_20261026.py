"""T11 — Foreman end-of-day Telegram report (2026-10-26)."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import pytest

CAMPAIGN_OS = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, CAMPAIGN_OS)

from _lib import foreman_eod as feod  # noqa: E402

TODAY = dt.date(2026, 10, 26)  # Sunday
BASE = "https://example.test"


def _section(**overrides):
    base = {
        "brand_id": "stick",
        "counts": {"created": 3, "approved": 2, "released": 2, "on_social": 1},
        "rest_of_week": [
            {"weekday": "Mon", "ready": 1, "planned": 1, "gap": False},
            {"weekday": "Tue", "ready": 0, "planned": 1, "gap": True},
        ],
        "pending": ["Vice irons", "Wed fitting"],
        "approve_url": f"{BASE}/?page=review&brand=stick",
    }
    base.update(overrides)
    return base


def test_eod_text_matches_the_spec_shape():
    text = feod.eod_text({"stick": _section()}, TODAY)
    assert text.startswith("Stick, today")
    assert "Created 3 · Approved 2 · Released 2 · On social 1" in text
    assert "Rest of week: Mon 1/1 · Tue 0/1 (gap)" in text
    assert "Waiting for approval (2):" in text
    assert "• Vice irons" in text
    assert f"Approve drafts: {BASE}/?page=review&brand=stick" in text


def test_rest_line_when_nothing_scheduled():
    assert feod._rest_line([]) == "Rest of week: nothing scheduled."


def test_created_today_counts_sidecars_for_brand(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    draft_dir = tmp_path / "draft-assets"
    draft_dir.mkdir()
    ts = "2026-10-26T10:00:00Z"
    for brand, n in (("stick", 2), ("swing-shack", 1)):
        for i in range(n):
            (draft_dir / f"{brand}-{i}.json").write_text(
                json.dumps({"brand_id": brand, "created_at": ts}),
                encoding="utf-8",
            )
    (draft_dir / "old.json").write_text(
        json.dumps({"brand_id": "stick", "created_at": "2026-10-25T10:00:00Z"}),
        encoding="utf-8",
    )
    assert feod.created_today("stick", TODAY) == 2
    assert feod.created_today("swing-shack", TODAY) == 1


def test_human_edit_actions_count_per_brand_and_day(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    edits = tmp_path / "human-edits.jsonl"
    rows = [
        {"action": "approve", "brand_id": "stick", "ts": "2026-10-26T08:00:00Z"},
        {"action": "approve", "brand_id": "stick", "ts": "2026-10-26T09:00:00Z"},
        {"action": "approve", "brand_id": "swing-shack", "ts": "2026-10-26T09:00:00Z"},
        {"action": "release", "brand_id": "stick", "ts": "2026-10-26T11:00:00Z"},
        {"action": "approve", "brand_id": "stick", "ts": "2026-10-25T09:00:00Z"},
    ]
    edits.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert feod.approved_today("stick", TODAY) == 2
    assert feod.released_today("stick", TODAY) == 1
    assert feod.approved_today("swing-shack", TODAY) == 1


@pytest.fixture(scope="module")
def evening_app(tmp_path_factory):
    base = tmp_path_factory.mktemp("feod-route")
    (base / "important-dates").mkdir(parents=True)
    (base / "important-dates" / "2027.json").write_text('{"dates": []}', encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(base))
    mp.setenv("BUNDLED_DATA_DIR", str(os.path.join(CAMPAIGN_OS, "..", "data")))
    mp.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    sys.modules.pop("app", None)
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    yield app_module
    mp.undo()


def test_evening_message_route_requires_job_bearer(evening_app):
    anon = evening_app.app.test_client(cos_anon=True)
    assert anon.get("/api/jobs/evening-message?brand=stick").status_code == 401
    r = anon.get(
        "/api/jobs/evening-message?brand=stick",
        headers={"Authorization": "Bearer test-job-token-not-a-secret"},
    )
    d = r.get_json()
    assert r.status_code == 200 and d["ok"]
    assert d["text"].startswith("Stick, today")
    assert "counts" in d and "pending_approval" in d
    authed = evening_app.app.test_client()
    assert authed.get("/api/jobs/evening-message?brand=nope").status_code == 400
