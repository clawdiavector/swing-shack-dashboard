"""The build preview and result pages: plain words, the confirm form only when writes are on, undo afterwards."""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_11_13_ads_build as bt  # noqa: E402
from _lib import ads_build  # noqa: E402


def _preview(monkeypatch, on):
    if on:
        monkeypatch.setenv("ADS_WRITES_ENABLED", "1")
    else:
        monkeypatch.delenv("ADS_WRITES_ENABLED", raising=False)
    return ads_build.preview("stick", bt._suggestion(), graph=bt.FakeMeta(), token="tok", account_id=bt.ACCOUNT,
                             signer=bt.Signer())


def test_preview_page_lists_each_part_and_confirms_only_when_writes_are_on(monkeypatch):
    html = ads_build.render_preview(_preview(monkeypatch, True))
    for word in ("Lead form", "Campaign", "Ad set", "Creative", "Ad"):
        assert word in html
    assert "switched off" in html.lower()
    assert 'action="/ads-brief/build/confirm"' in html
    off = ads_build.render_preview(_preview(monkeypatch, False))
    assert 'action="/ads-brief/build/confirm"' not in off
    assert "ADS_WRITES_ENABLED" not in off  # no settings talk on a page for people


def test_done_page_links_ads_manager_and_offers_undo():
    entry = {"id": "abc", "kind": "build_ad", "names": {"campaign": "stick_leads_fitting_nov26", "adset": "x",
                                                       "ad": "fitting_reel_v1"},
             "created": {"campaign": "102", "ad": "105"}, "status": "PAUSED"}
    html = ads_build.render_done("stick", entry, account_id="act_123")
    assert "adsmanager" in html and "act=123" in html
    assert 'action="/ads-brief/build/undo"' in html and 'value="abc"' in html
