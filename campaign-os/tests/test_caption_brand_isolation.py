"""No voice's captions may name another brand.

Swing Shack, Stick and Bag Drop are separate businesses. On 2026-10-14
generate_captions(voice='stick') returned "A golfer walked into Swing Shack
and said: ..." because the story template hard-coded the name, and the
bag-drop voice's CTAs all pointed at swingshack.co.za. The live caption
pipeline (Caption Studio, the draft_caption job) reads the same CTAs from
data/voice_bible.json, so the voice file is checked too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from _lib import intelligence

REPO_DATA = Path(__file__).resolve().parents[2] / "data"

BRAND_NAMES = {
    "swing-shack": re.compile(r"swing\s*shack", re.I),
    # Case-sensitive: "stick" is also an ordinary golf word.
    "stick": re.compile(r"\bStick\b|stickgolf|stick\.paarl"),
    "bag-drop": re.compile(r"bag\s*drop", re.I),
}
VOICES = list(BRAND_NAMES)

# Brand-neutral hooks, one per caption mechanism, so every body template runs.
NEUTRAL_HOOKS = [{"hook": f"Neutral hook number {i}"} for i in range(len(intelligence._VARIANT_MECHANISMS))]


def _other_brands(text: str, voice: str) -> list[str]:
    return [b for b, pat in BRAND_NAMES.items() if b != voice and pat.search(text)]


def _leaks(result: dict, voice: str) -> list[str]:
    out = []
    for v in result["variants"]:
        text = " | ".join(str(v.get(f) or "") for f in ("hook", "body", "cta"))
        bad = _other_brands(text, voice)
        if bad:
            out.append(f"{v.get('mechanism')}: names {bad}: {text[:200]}")
    return out


@pytest.fixture()
def repo_data(monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(REPO_DATA))


@pytest.mark.parametrize("voice", VOICES)
def test_every_template_stays_in_its_own_brand(voice, repo_data, monkeypatch):
    monkeypatch.setattr(intelligence, "generate_hooks", lambda *a, **k: {"generated": list(NEUTRAL_HOOKS)})
    result = intelligence.generate_captions(n=len(NEUTRAL_HOOKS), voice=voice)
    assert result["_voice"] == voice
    assert {v["mechanism"] for v in result["variants"]} == set(intelligence._VARIANT_MECHANISMS)
    assert _leaks(result, voice) == []


@pytest.mark.parametrize("voice", VOICES)
def test_fallback_hooks_stay_in_their_own_brand(voice, repo_data, monkeypatch):
    monkeypatch.setattr(intelligence, "generate_hooks", lambda *a, **k: {"generated": []})
    result = intelligence.generate_captions(n=20, voice=voice)
    assert result["variants"]
    assert _leaks(result, voice) == []


@pytest.mark.parametrize("voice", VOICES)
def test_real_hook_pool_stays_in_its_own_brand(voice, repo_data):
    """The reported reproduction: repo data, no stubs."""
    result = intelligence.generate_captions(n=20, voice=voice)
    assert _leaks(result, voice) == []


@pytest.mark.parametrize("voice", VOICES)
def test_voice_bible_names_no_other_brand(voice):
    """Fields the live caption pipeline copies into prompts or appends to captions."""
    vb = json.loads((REPO_DATA / "voice_bible.json").read_text(encoding="utf-8"))
    entry = vb["voices"][voice]
    fields = ("template_prefix", "template_suffix", "cta_default", "cta_alternatives",
              "example_caption", "hashtag_suggestions")
    leaks = {}
    for f in fields:
        val = entry.get(f)
        text = " ".join(val) if isinstance(val, list) else str(val or "")
        bad = _other_brands(text, voice)
        if bad:
            leaks[f] = (bad, text)
    assert leaks == {}
