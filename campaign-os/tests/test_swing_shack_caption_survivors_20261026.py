"""Swing Shack draft_assets — brief fidelity must not trap on lodge-title fragments."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def test_rack_is_not_trackman_session_subject():
    from _lib.p11_context_engine import _detect_brief_subject, _related_service_keywords

    subject = _detect_brief_subject(
        "Off-the-rack is for groceries | service promo",
        lodge_title="Off-the-rack is for groceries",
    )
    assert "rack" in subject.split()
    assert "groceries" in subject.split()
    assert _related_service_keywords("rack") == []


def test_brief_fidelity_accepts_lodge_title_word_in_caption():
    from _lib.p11_context_engine import _check_brief_fidelity, build_generation_context

    ctx = build_generation_context(
        brand_id="swing-shack",
        user_brief="Off-the-rack is for groceries | service promo",
        lodge_title="Off-the-rack is for groceries",
        template_id="ss-service-promo",
        post_type="service_promo",
    )
    body = (
        "Groceries belong in aisles, not your bag. "
        "Book a fitting and match the clubs to your swing."
    )
    result = _check_brief_fidelity(body, ctx)
    assert result["passed"] is True
    assert result["reason"] == "lodge_title_word_match"


def test_caption_pipeline_survives_off_the_rack_lodge_title():
    from _lib.p11_context_engine import run_caption_pipeline

    def mock_llm(system, user, **kw):
        return json.dumps(
            {
                "caption_body": (
                    "Groceries belong in aisles. Your irons belong in a fitting bay."
                ),
                "poster_hook": "OFF THE RACK",
                "cta_line": "Book online",
            }
        )

    req = {
        "brand_id": "swing-shack",
        "user_brief": "Off-the-rack is for groceries | service promo",
        "channel": "instagram",
        "n_survivors": 3,
        "n_candidates": 12,
        "lodge_title": "Off-the-rack is for groceries",
        "template_id": "ss-service-promo",
        "post_type": "service_promo",
    }
    with patch("_lib.p11_context_engine._call_llm_chat_completions", side_effect=mock_llm):
        result = run_caption_pipeline(req)
    assert result.get("ok") is True
    assert len(result.get("survivors") or []) >= 1


@pytest.fixture()
def inbox_env(monkeypatch, tmp_path):
    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    yield tmp_path
    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]


def test_draft_assets_lodge_title_when_pipeline_empty_survivors(l5_app, inbox_env, tmp_path):
    from _lib.jobs.layer5 import draft_assets
    from tests.jobs.test_layer5_create import (
        _seed_approved_proposal,
        _seed_brands,
        _seed_queue_row,
    )

    _seed_brands(tmp_path, brand="swing-shack", campaign_id="camp-ss")
    item_id = _seed_approved_proposal(tmp_path, brand="swing-shack", pid="prop-ss-surv")
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id, brand="swing-shack")
    mock_result = {
        "ok": True,
        "survivors": [],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        out = draft_assets.run(brand="swing-shack")
    assert out.get("drafted") == 1
    sidecar = json.loads(next((tmp_path / "draft-assets").glob("*.json")).read_text(encoding="utf-8"))
    assert sidecar.get("action") == "draft_caption"
