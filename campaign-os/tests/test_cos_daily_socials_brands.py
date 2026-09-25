"""Daily social links — brands.json socials[] + social_history ingest helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

BRANDS_FILE = REPO_ROOT / "data" / "brands.json"


def _brand(bid: str) -> dict:
    reg = json.loads(BRANDS_FILE.read_text(encoding="utf-8"))
    return (reg.get("brands") or {})[bid]


def test_stick_socials_five_platform_links():
    socials = _brand("stick")["socials"]
    assert len(socials) == 5
    platforms = {s["platform"] for s in socials}
    assert platforms == {"instagram", "facebook", "youtube", "tiktok", "google"}
    for item in socials:
        assert item["label"]
        assert item["url"].startswith("http")


def test_swing_shack_socials_and_people_policy():
    b = _brand("swing-shack")
    assert b["image_rules"]["people_allowed"] is True
    assert len(b["socials"]) == 2
    assert {s["platform"] for s in b["socials"]} == {"instagram", "youtube"}


def test_ingest_skips_meta_when_token_missing(monkeypatch):
    monkeypatch.delenv("META_SYSTEM_USER_TOKEN", raising=False)
    monkeypatch.delenv("META_PAGE_ID", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", raising=False)
    from _lib import social_history

    out = social_history.ingest_social_history("swing-shack", download_thumbnails=False)
    assert out["platforms"]["instagram"]["status"] == "skipped"
    assert out["platforms"]["facebook"]["status"] == "skipped"
    assert "reason" in out["platforms"]["instagram"]


def test_ingest_skips_tiktok_when_token_missing(monkeypatch):
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN_SWING_SHACK", raising=False)
    from _lib import social_history

    out = social_history.ingest_social_history("swing-shack", download_thumbnails=False)
    assert out["platforms"]["tiktok"]["status"] == "skipped"
