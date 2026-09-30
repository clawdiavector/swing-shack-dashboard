"""P11 copy package + draft_assets sidecar persistence (LLM patched)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import (  # noqa: E402
    _seed_approved_proposal,
    _seed_brands,
    _seed_queue_row,
    l5_app,
)


def test_parse_copy_package_valid():
    from _lib.p11_context_engine import _parse_copy_package

    raw = json.dumps(
        {"caption_body": "Body text", "poster_hook": "HOOK", "cta_line": "Book now"}
    )
    pkg = _parse_copy_package(raw)
    assert pkg["caption_body"] == "Body text"
    assert pkg["poster_hook"] == "HOOK"


def test_parse_copy_package_with_prose_prefix():
    from _lib.p11_context_engine import _parse_copy_package

    inner = json.dumps({"caption_body": "Only body", "poster_hook": "", "cta_line": ""})
    pkg = _parse_copy_package(f"Here is the JSON:\n{inner}")
    assert pkg["caption_body"] == "Only body"


def test_parse_copy_package_invalid_json_returns_none():
    from _lib.p11_context_engine import _parse_copy_package

    assert _parse_copy_package("not json at all") is None


def test_generate_candidate_structured():
    from _lib.p11_context_engine import _generate_candidate

    blob = json.dumps(
        {
            "caption_body": "TrackMan helps tempo.",
            "poster_hook": "FIND YOUR TEMPO",
            "cta_line": "Book assessment",
        }
    )
    ctx = {
        "brand_id": "stick",
        "brand": {"label": "stick", "brand_id": "stick", "cta_default": "Visit stick.co.za", "hashtag_suggestions": [], "banned_terms": [], "personality": "dry", "voice_description": "plain", "allowed_tones": ["dry"]},
        "context_id": "ctx-1",
        "copy_caps": {"poster_hook_cap": 64, "poster_cta_cap": 48},
        "product_service": {},
        "channel": {"channel": "instagram", "rules": {"voice_notes": ""}},
        "restrictions": {},
        "user_brief": "Coaching",
    }
    route = {"route_id": "r1", "mechanism": "observation", "brand_fit": 4, "rhetorical_structure_suggestion": "q", "rationale": "test"}
    with patch("_lib.p11_context_engine._call_llm_chat_completions", return_value=blob):
        c = _generate_candidate(ctx, route)
    assert "Visit stick.co.za" in c["body"]
    assert c["copy_package"]["source"] == "llm"
    assert c["copy_package"]["poster_hook"] == "FIND YOUR TEMPO"


def test_generate_candidate_unstructured_fallback():
    from _lib.p11_context_engine import _generate_candidate

    ctx = {
        "brand_id": "stick",
        "brand": {"label": "stick", "brand_id": "stick", "cta_default": "", "hashtag_suggestions": [], "banned_terms": [], "personality": "dry", "voice_description": "plain", "allowed_tones": ["dry"]},
        "context_id": "ctx-2",
        "copy_caps": {"poster_hook_cap": 72, "poster_cta_cap": 48},
        "product_service": {},
        "channel": {"channel": "instagram", "rules": {"voice_notes": ""}},
        "restrictions": {},
        "user_brief": "Brief",
    }
    route = {"route_id": "r2", "mechanism": "observation", "brand_fit": 4, "rhetorical_structure_suggestion": "q", "rationale": "test"}
    with patch("_lib.p11_context_engine._call_llm_chat_completions", return_value="Plain caption prose."):
        c = _generate_candidate(ctx, route)
    assert c["body"] == "Plain caption prose."
    assert c["copy_package"]["source"] == "fallback"


def test_check_locale_rejects_us_spelling():
    from _lib.p11_context_engine import _check_locale

    r = _check_locale({"caption_body": "personalized fitting", "poster_hook": "", "cta_line": ""})
    assert r["passed"] is False


def test_check_locale_rejects_us_hype():
    from _lib.p11_context_engine import _check_locale

    r = _check_locale({"caption_body": "Spoiler alert: clubs matter", "poster_hook": "", "cta_line": ""})
    assert r["passed"] is False


def test_check_locale_warns_on_length():
    from _lib.p11_context_engine import _check_locale

    long_body = "x" * 400
    r = _check_locale({"caption_body": long_body, "poster_hook": "", "cta_line": ""})
    assert r["passed"] is True
    assert "caption_body_over_320" in r["warnings"]


def test_en_za_block_in_system_prompt():
    from _lib.p11_context_engine import _build_llm_prompt

    ctx = {
        "brand": {
            "label": "stick",
            "brand_id": "stick",
            "personality": "dry",
            "voice_description": "plain",
            "allowed_tones": ["dry"],
            "cta_default": "CTA",
            "hashtag_suggestions": [],
            "banned_terms": [],
        },
        "restrictions": {"internal_agents_banned": [], "cross_brand_text_banned": False},
        "product_service": {},
        "channel": {"channel": "instagram", "rules": {"voice_notes": "short"}},
        "user_brief": "fitting",
        "semantic_history": {},
        "structural_history": {},
        "copy_caps": {"poster_hook_cap": 64, "poster_cta_cap": 48},
    }
    route = {
        "mechanism": "observation",
        "brand_fit": 4,
        "rhetorical_structure_suggestion": "question",
        "rationale": "test",
    }
    system, _user = _build_llm_prompt(ctx, route)
    assert "en-ZA" in system
    assert "personalised" in system
    assert "NEVER use US spellings" in system


def test_sidecar_carries_copy_package_and_compose_fields(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path, brand="swing-shack", campaign_id="camp-ss")
    item_id = _seed_approved_proposal(tmp_path, brand="swing-shack", pid="prop-ss")
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id, brand="swing-shack")
    mock_result = {
        "ok": True,
        "survivors": [
            {
                "body": "Feed caption\n\nCTA",
                "copy_package": {
                    "caption_body": "Feed caption",
                    "poster_hook": "SHOULD NOT WIN",
                    "cta_line": "Book online",
                    "locale": "en-ZA",
                    "source": "llm",
                },
            }
        ],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        draft_assets.run(brand="swing-shack")

    sidecar = json.loads(next((tmp_path / "draft-assets").glob("*.json")).read_text(encoding="utf-8"))
    assert sidecar.get("copy_package")
    assert sidecar.get("compose_cta") == "Book online"
    assert sidecar.get("compose_body") == "Feed caption"
    assert sidecar.get("poster_copy_mode")


def test_legacy_pipeline_result_without_copy_package(l5_app, tmp_path):
    from _lib.jobs.layer5 import draft_assets

    _seed_brands(tmp_path)
    item_id = _seed_approved_proposal(tmp_path)
    _seed_queue_row(tmp_path, action="draft_caption", item_id=item_id)
    mock_result = {
        "ok": True,
        "survivors": [{"body": "Legacy body only"}],
        "observability": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    with patch("_lib.p11_context_engine.run_caption_pipeline", return_value=mock_result):
        out = draft_assets.run()
    assert out.get("drafted") == 1
    sidecar = json.loads(next((tmp_path / "draft-assets").glob("*.json")).read_text(encoding="utf-8"))
    assert "compose_headline" not in sidecar or not sidecar.get("compose_headline")
