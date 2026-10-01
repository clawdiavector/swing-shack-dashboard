"""One-shot prompt sections and negatives."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture(autouse=True)
def _bundled(monkeypatch):
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))


def test_literal_in_wire_and_negatives():
    from _lib.creative_director import build_negative_prompt, compose_prompt

    line = "Stick coaching wins"
    result = compose_prompt(
        brand_id="stick",
        job="Photoreal indoor golf bay",
        literal_text=line,
        render_text=True,
    )
    assert "LITERAL TEXT" in result["master_prompt"]
    assert f'"{line}"' in result["wire_prompt"]
    neg = result["negative_prompt"].lower()
    assert "no text in the image" not in neg
    assert "no fake logos" in neg
    assert "no text other than the quoted line" in neg


def test_default_compose_unchanged_negatives():
    from _lib.creative_director import build_negative_prompt, compose_prompt, _load_brand_context

    job = "Flat navy gradient background plate, no people, no text"
    before = compose_prompt(brand_id="stick", job=job)
    ctx = _load_brand_context("stick")
    neg_alone = build_negative_prompt(
        brand_id="stick",
        brand_ctx=ctx,
        job=job,
        human_direction=None,
        subject_has_person=False,
        subject_has_gear=False,
        render_text=False,
    )
    assert "no text in the image" in neg_alone
    assert before["negative_prompt"] == neg_alone
