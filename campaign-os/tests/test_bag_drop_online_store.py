"""Bag Drop is the online store thebagdrop.co.za, not a bag-storage service at Swing Shack.

Christelle confirmed this on 2026-10-21 (wiki decisions/owner-answers-d1-d2-2026-10-21).
The brand files written before that described members leaving their bag at Swing Shack, a
Thursday member social and swingshack.co.za as the booking link. Anything generated from
them talked about a service that does not exist and sent customers to the wrong website.
BRAND-BIBLE.md is the source; these checks keep the files that feed generation in line
with it, and keep Bag Drop off auto-release until it has its own Postiz key (bible
decision 17: without one, a post would go out through another brand's channel).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
BAG_DROP = REPO / "data" / "brand-directory" / "bag-drop"
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

import caption_lint as L  # noqa: E402

OLD_SERVICE = [
    "thursday",
    "member social",
    "drop your bag",
    "leave your bag",
    "play lighter",
    "bag that lives",
    "swingshack.co.za",
    "sub-brand of swing shack",
    "community-first",
    "travel bags",
]

# Files that feed generation. BRAND-BIBLE.md names the old phrases in order to ban
# them, and feedback/instagram-audit.json holds real captions, so neither is checked.
GENERATION_FILES = [
    "README.md",
    "knowledge.json",
    "calendar_config.json",
    "bible-visual.json",
    "voice/do-say-dont-say.md",
    "voice/punctuation-rules.md",
    "voice/tone-rules.md",
    "copy/ctas.md",
    "copy/headlines.md",
    "examples/good.md",
    "examples/bad.md",
]


def _voice_bible_entry() -> dict:
    doc = json.loads((REPO / "data" / "voice_bible.json").read_text(encoding="utf-8"))
    return doc["voices"]["bag-drop"]


@pytest.mark.parametrize("rel", GENERATION_FILES)
def test_brand_file_does_not_describe_a_bag_storage_service(rel):
    text = (BAG_DROP / rel).read_text(encoding="utf-8").lower()
    found = [p for p in OLD_SERVICE if p in text]
    assert not found, f"{rel} still describes the old bag-storage service: {found}"


def test_voice_bible_entry_is_the_store_voice():
    text = json.dumps(_voice_bible_entry(), ensure_ascii=False).lower()
    found = [p for p in OLD_SERVICE + ["community", "warm"] if p in text]
    assert not found, f"voice_bible.json bag-drop still has the old voice: {found}"


def test_knowledge_points_at_the_store():
    know = json.loads((BAG_DROP / "knowledge.json").read_text(encoding="utf-8"))
    assert "thebagdrop.co.za" in json.dumps(know)
    assert not [s for s in know.get("services", []) if "storage" in json.dumps(s).lower()]


def _ctas_in_use() -> list[str]:
    know = json.loads((BAG_DROP / "knowledge.json").read_text(encoding="utf-8"))
    rules = know["cta_rules"]
    vb = _voice_bible_entry()
    return [rules["default_cta"], *rules.get("hard_ctas", []), *rules.get("soft_ctas", []),
            vb["cta_default"], *vb.get("cta_alternatives", [])]


@pytest.mark.parametrize("cta", _ctas_in_use())
def test_every_cta_in_use_is_one_the_bible_allows(cta):
    rules = L.load_rules("bag-drop")
    listed, unlisted = L.find_ctas(cta, rules["ctas_allowed"])
    assert listed and not unlisted, f"{cta!r} is not in the bible's ctas_allowed"
    banned = [b for b in rules["banned_brand"] if b.lower() in cta.lower()]
    assert not banned, f"{cta!r} uses banned phrases {banned}"


def test_gbp_poster_uses_the_store_domain():
    from _lib.gbp_daily_poster import BRANDS

    bd = BRANDS["bag-drop"]
    assert bd["domain"] == "thebagdrop.co.za"
    assert "swingshack" not in json.dumps(bd).lower()


@pytest.fixture
def release_env(monkeypatch, tmp_path):
    """auto_release with one scheduled Bag Drop post going live today, release_moment recorded."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLISH_SANDBOX_DIR", str(tmp_path / "publish-sandbox"))
    monkeypatch.setenv("CAMPAIGN_OS_AUTO_RELEASE", "1")
    for k in list(os.environ):
        if k.startswith("POSTIZ_API_KEY"):
            monkeypatch.delenv(k)
    from _lib import marketing_calendar, publish_sandbox, unified_inbox
    from _lib.jobs import auto_release

    today = datetime.now(ZoneInfo("Africa/Johannesburg")).date().isoformat()
    monkeypatch.setattr(auto_release, "_brand_release_hour", lambda b: 0)
    monkeypatch.setattr(marketing_calendar, "canonical_records",
                        lambda b: [{"calendar_id": "cal-bd-1", "brand_id": b}])
    monkeypatch.setattr(unified_inbox, "build_post_index", lambda brand_id: {})
    monkeypatch.setattr(unified_inbox, "post_state", lambda r, index, now: {
        "state": "scheduled", "go_live_date": today, "calendar_id": r["calendar_id"]})
    calls: list[dict] = []
    monkeypatch.setattr(publish_sandbox, "release_moment",
                        lambda **kw: calls.append(kw) or {"ok": True})
    return auto_release, calls


def test_auto_release_holds_bag_drop_without_its_own_postiz_key(release_env, monkeypatch):
    auto_release, calls = release_env
    monkeypatch.setenv("POSTIZ_API_KEY", "shared-key-belongs-to-another-brand")
    out = auto_release.run(brand="bag-drop")
    assert calls == []
    assert out["released"] == 0
    assert "bag-drop" in out["held"]


def test_auto_release_releases_bag_drop_once_it_has_its_own_key(release_env, monkeypatch):
    auto_release, calls = release_env
    monkeypatch.setenv("POSTIZ_API_KEY_BAG_DROP", "its-own-key")
    out = auto_release.run(brand="bag-drop")
    assert [c["brand_id"] for c in calls] == ["bag-drop"]
    assert out["released"] == 1
    assert "bag-drop" not in out["held"]
