"""The caption tool must not run without a brand.

Christelle, 2026-10-15: "Caption tool must have brand selected in order to
work. Everything must run through brand." Without one, generate_captions fell
back to Swing Shack wording and swingshack.co.za for whoever asked.

Caption Studio v2 (/api/captions/v2/generate) already refuses an empty
brand_id via build_generation_context. These cover the older routes and the
/api/intel/captions_generate view.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from _lib import intelligence

REPO_DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    shutil.copy(REPO_DATA / "voice_bible.json", tmp_path / "voice_bible.json")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(intelligence, "generate_hooks", lambda *a, **k: {"generated": [{"hook": "Neutral hook"}] * 3})
    from app import app

    return app.test_client()


def _refused(rv):
    body = json.loads(rv.data)
    return rv.status_code == 400 and body.get("ok") is False and not body.get("variants")


def test_captions_generate_without_brand_is_refused(client):
    assert _refused(client.post("/api/captions/generate", json={"n": 3}))


def test_captions_generate_with_brand_still_works(client):
    rv = client.post("/api/captions/generate", json={"n": 3, "voice": "stick"})
    body = json.loads(rv.data)
    assert rv.status_code == 200 and body["ok"] is True and body["_voice"] == "stick"


def test_intel_generate_captions_without_brand_is_refused(client):
    assert _refused(client.get("/api/intel/generate/captions/no-such-asset?n=3"))


def test_intel_generate_captions_with_brand_still_works(client):
    rv = client.get("/api/intel/generate/captions/no-such-asset?n=3&voice=bag-drop")
    body = json.loads(rv.data)
    assert rv.status_code == 200 and body["_voice"] == "bag-drop"


@pytest.mark.parametrize("brand", ["swing-shack", "stick", "bag-drop"])
def test_captions_view_uses_the_active_brand(brand, client):
    # Called the way app._intel calls it. Not through the route: in the full CI
    # run other tests re-import app, and the route answered with another
    # test's brand.
    fn = intelligence.INTELLIGENCE_FUNCS["captions_generate"]
    intelligence.set_request_brand(brand)
    try:
        body = fn()
    finally:
        intelligence.clear_request_brand()
    assert body.get("_voice") == brand


def test_captions_view_without_a_voice_is_refused(client):
    fn = intelligence.INTELLIGENCE_FUNCS["captions_generate"]
    intelligence.set_request_brand("takomo")
    try:
        body = fn()
    finally:
        intelligence.clear_request_brand()
    assert body.get("ok") is False and not body.get("variants")
