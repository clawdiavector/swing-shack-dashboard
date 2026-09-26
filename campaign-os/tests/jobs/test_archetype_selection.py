"""Archetype selection — pillar token matching (stick-coaching → coaching)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from _lib.archetypes import _pillar_match_tokens, _rule_matches  # noqa: E402


def test_pillar_token_suffix_matches_rule():
    ctx = {"pillar_in": ["stick-coaching"], "has_product_item": False, "subject": ""}
    when = {"pillar_in": ["coaching"], "has_product_item": False}
    assert _rule_matches(when, ctx) is True


def test_pillar_full_id_matches():
    ctx = {"pillar_in": ["ss-fitting"], "has_product_item": False, "subject": ""}
    when = {"pillar_in": ["fitting"], "has_product_item": False}
    assert _rule_matches(when, ctx) is True


def test_pillar_tokens_helper():
    assert "coaching" in _pillar_match_tokens("stick-coaching")
    assert "fitting" in _pillar_match_tokens("ss-fitting")
