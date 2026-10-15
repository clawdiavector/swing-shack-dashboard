"""The caption hook pool holds hooks, for the right brand, used whole.

On 2026-10-15 generate_captions() built its variants from
generate_hooks(20, _skip_dedup=True), and with the repo's data/ about half
that pool was to-do text from missed-opportunities.json, wrapped as
"You're losing bookings because: Create IG content targeting "/customer-portal/"
· 92 session". The pool was the same for every voice, so Swing Shack's
TrackMan and booking angles reached Stick and Bag Drop (an online gear store
at thebagdrop.co.za). Four body templates used only the hook's first word,
producing "Forget what you heard about The."
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from _lib import intelligence

REPO_DATA = Path(__file__).resolve().parents[2] / "data"
VOICES = ("swing-shack", "stick", "bag-drop")

# Recommendation / to-do text: what someone should do, not a line a golfer reads.
RECOMMENDATION = re.compile(
    r"you're losing bookings"
    r"|^\s*(create|schedule|post|publish|add|write|fix|update|target|launch|run)\b"
    r"|\bIG (post|content)\b"
    r"|\bsessions? with no\b"
    r"|\btrending videos\b"
    r"|\"/[^\"]*\"",
    re.I,
)

# Swing Shack's own business: a studio with bays, bookings and TrackMan in JHB.
SWING_SHACK_ONLY = re.compile(r"trackman|booking|\bbays?\b|johannesburg|swingshack", re.I)


@pytest.fixture()
def repo_data(monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(REPO_DATA))


@pytest.mark.parametrize("voice", VOICES)
def test_real_pool_holds_no_recommendation_text(voice, repo_data):
    result = intelligence.generate_captions(n=20, voice=voice)
    assert result["variants"]
    bad = [v["hook"] for v in result["variants"] if RECOMMENDATION.search(v["hook"])]
    assert bad == []


def test_hook_generator_holds_no_recommendation_text(repo_data):
    hooks = intelligence.generate_hooks(20, _skip_dedup=True)["generated"]
    assert hooks
    assert [h["hook"] for h in hooks if RECOMMENDATION.search(h["hook"])] == []


def test_hook_pool_has_no_duplicates(repo_data):
    hooks = [h["hook"] for h in intelligence.generate_hooks(20, _skip_dedup=True)["generated"]]
    assert len(hooks) == len(set(hooks))


@pytest.mark.parametrize("voice", ("stick", "bag-drop"))
def test_real_pool_carries_no_swing_shack_angles(voice, repo_data):
    result = intelligence.generate_captions(n=20, voice=voice)
    assert result["variants"]
    bad = [v["hook"] for v in result["variants"] if SWING_SHACK_ONLY.search(v["hook"])]
    assert bad == []


@pytest.fixture()
def marked_data(tmp_path, monkeypatch):
    """Flat signal files (the default brand's) and one per-brand file for Stick."""
    def write(rel, angle):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"opportunities": [{"suggested_angle": angle}]}), encoding="utf-8")

    write("reddit-opportunities.json", "FLATMARKER angle for the default brand")
    write("brands/stick/reddit-opportunities.json", "STICKMARKER angle for Stick")
    monkeypatch.setattr(intelligence, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def _hooks(voice):
    return " | ".join(v["hook"] for v in intelligence.generate_captions(n=20, voice=voice)["variants"])


def test_default_brand_reads_the_flat_signal_files(marked_data):
    assert "FLATMARKER" in _hooks("swing-shack")


def test_other_brand_reads_its_own_signal_files(marked_data):
    hooks = _hooks("stick")
    assert "STICKMARKER" in hooks
    assert "FLATMARKER" not in hooks


def test_brand_without_signal_files_gets_none_of_the_default_brands(marked_data):
    hooks = _hooks("bag-drop")
    assert hooks
    assert "FLATMARKER" not in hooks and "STICKMARKER" not in hooks


SAMPLE_HOOKS = [
    "The lie every golfer believes about the range.",
    "Why your slice won't fix itself",
    "What fitting actually fixes?",
]


@pytest.mark.parametrize("voice", VOICES)
def test_every_mechanism_uses_the_whole_hook(voice, repo_data, monkeypatch):
    n = len(intelligence._VARIANT_MECHANISMS)
    pool = [{"hook": SAMPLE_HOOKS[i % len(SAMPLE_HOOKS)] + ("" if i < 3 else f" {i}")} for i in range(n)]
    monkeypatch.setattr(intelligence, "generate_hooks", lambda *a, **k: {"generated": list(pool)})
    result = intelligence.generate_captions(n=n, voice=voice)
    assert {v["mechanism"] for v in result["variants"]} == set(intelligence._VARIANT_MECHANISMS)
    for v in result["variants"]:
        core = v["hook"].rstrip(".?! ")
        assert core in v["body"], f"{v['mechanism']} dropped the hook: {v['body']}"
        assert not re.search(r"about (The|Why|What)\b", v["body"]), v["body"]
        assert not re.search(r"[.?!]\s*[.?]", v["body"].replace("...", "")), f"{v['mechanism']}: {v['body']}"
