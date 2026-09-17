"""Regression tests for prod route-health slices 1–4 (2026-09-16)."""

from __future__ import annotations

import json
from pathlib import Path

import app as app_module


def _auth_client():
    client = app_module.app.test_client()
    pw = getattr(app_module, "SHARED_PASSWORD", None)
    if pw:
        client.post("/login", data={"password": pw})
    return client


def test_clear_my_desk_no_name_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "decisions-swing-shack.json").write_text(
        json.dumps({"history": [], "queue": []})
    )
    client = _auth_client()
    resp = client.get("/api/decisions/clear-my-desk?brand=swing-shack")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    seq = body.get("sequence") or body
    assert "blocked_remaining" in seq


def test_spend_null_rands_do_not_500(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    spend = {
        "brand_id": "swing-shack",
        "campaigns": [{
            "campaign_id": "c1",
            "platform": "meta",
            "status": "active",
            "spend_rands": None,
            "strategy_link": {},
        }],
    }
    (tmp_path / "spend-swing-shack.json").write_text(json.dumps(spend))
    (tmp_path / "strategy-swing-shack.json").write_text(
        json.dumps({"brand_id": "swing-shack", "bets": [], "lessons": []})
    )
    client = _auth_client()
    for path in (
        "/api/spend/orphans?brand=swing-shack",
        "/api/spend/spend-vs-priority?brand=swing-shack",
        "/api/integrity/data-health?brand=swing-shack",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, (path, resp.get_json())


def test_lanes_calendar_requires_dates():
    client = _auth_client()
    resp = client.post("/api/lanes/calendar", json={"brand_id": "swing-shack"})
    assert resp.status_code == 400


def test_creative_from_reference_requires_ids():
    client = _auth_client()
    resp = client.post(
        "/api/creative/from-reference-and-product",
        json={"brand_id": "swing-shack"},
    )
    assert resp.status_code == 400
