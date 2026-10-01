"""Phase 1 creative one-shot — wire prompt, confidence gate, scoped negatives."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture(autouse=True)
def _bundled_data(monkeypatch):
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))


def test_stick_wire_prompt_has_measured_hex_no_section_headers():
    from _lib.creative_director import compose_prompt

    job = (
        "Flat navy gradient background plate for a Stick coaching poster, "
        "no people, no text"
    )
    result = compose_prompt(brand_id="stick", job=job)
    wire = result["wire_prompt"]
    assert "#073C52" in wire
    assert "[" not in wire
    assert "NEGATIVE" not in wire
    assert len(wire) <= 1200


def test_stick_background_negative_omits_anatomy_and_golf():
    from _lib.creative_director import build_negative_prompt, _load_brand_context

    ctx = _load_brand_context("stick")
    neg = build_negative_prompt(
        brand_id="stick",
        brand_ctx=ctx,
        job="Flat navy gradient background plate, no people",
        human_direction=None,
        subject_has_person=False,
        subject_has_gear=False,
    )
    low = neg.lower()
    assert "distorted hands" not in low
    assert "bent golf shaft" not in low
    assert "no text in the image" in low
    assert "stick" in low or "luxury aesthetic" in low or "soft pastel" in low


def test_draft_confidence_keywords_low_trust_prefix(tmp_path, monkeypatch):
    from _lib import brand_dna
    from _lib.creative_director import _build_brand_block

    brand_dir = tmp_path / "brand-directory" / "draft-brand"
    brand_dir.mkdir(parents=True)
    (brand_dir / "palette").mkdir()
    (brand_dir / "palette" / "brand.json").write_text(
        json.dumps(
            {
                "palette": {
                    "primary": {"hex": "#073C52", "name": "navy deep"},
                    "accent": {"hex": "#00B3BA", "name": "teal"},
                }
            }
        ),
        encoding="utf-8",
    )
    (brand_dir / "bible-visual.json").write_text(
        json.dumps(
            {
                "confidence": "draft",
                "philosophy": "Test brand",
                "look_and_feel_keywords": ["contradictory red accent"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(brand_dna, "_BRAND_DIR", tmp_path / "brand-directory")
    ctx = {
        "bible": json.loads((brand_dir / "bible-visual.json").read_text()),
        "palette": json.loads((brand_dir / "palette" / "brand.json").read_text())["palette"],
    }
    block = _build_brand_block(ctx, "draft-brand")
    assert "Unverified style notes" in block
    assert "Look + feel:" not in block

    bctx = brand_dna.load_brand_context("draft-brand", base_dir=tmp_path / "brand-directory")
    sys_msg = brand_dna.build_system_message(bctx)
    assert "Unverified style notes" in sys_msg


def test_krea_prompt_single_brand_block_no_system_prepend(monkeypatch):
    monkeypatch.setenv("KREA_MCP_TOKEN", "test-token")
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    captured: list[dict] = []

    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]

    from _lib import image_gen_router as router

    def _fake_krea(**kwargs):
        captured.append(kwargs)
        return {"job_id": "job-1", "structuredContent": {"job_id": "job-1"}}

    monkeypatch.setattr(router, "_krea_credentials_present", lambda: True)
    monkeypatch.setattr(router, "_call_krea_generate", _fake_krea)
    router.generate_image(
        "Flat navy gradient background plate, no people, no text",
        provider="krea",
        brand_id="stick",
        save=False,
    )

    assert captured
    prompt = captured[0]["prompt"]
    assert "#073C52" in prompt
    assert "USER REQUEST:" not in prompt
    assert "[" not in prompt.split("Avoid:")[0]
