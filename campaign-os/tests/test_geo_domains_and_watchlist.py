"""
GEO: Bag Drop must be audited against its own website, not the Swing Shack
site, and the default watchlists must be the ones we reviewed.

Background (2026-10-15): geo_audit and geo_routes both mapped bag-drop to
https://swingshack.co.za, so the Bag Drop GEO audit was checking the wrong
site. Bag Drop's site is https://thebagdrop.co.za (confirmed by Christelle).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib import geo_audit, geo_routes, geo_runner  # noqa: E402


def test_bag_drop_domain_is_its_own_site():
    assert geo_audit._BRAND_DOMAINS["bag-drop"] == "https://thebagdrop.co.za"
    assert geo_routes._BRAND_DOMAINS["bag-drop"] == "https://thebagdrop.co.za"


def test_audit_reports_missing_domain_instead_of_guessing(monkeypatch):
    monkeypatch.setitem(geo_audit._BRAND_DOMAINS, "bag-drop", "")
    result = geo_audit.run_geo_audit("bag-drop")
    assert result["ok"] is False
    assert "no website" in result["error"]


def test_bag_drop_own_domain_is_not_swing_shack():
    assert not geo_runner._is_own_domain("https://swingshack.co.za/shop", "bag-drop")
    assert geo_runner._is_own_domain("https://thebagdrop.co.za/product/x", "bag-drop")


def test_stick_and_swing_shack_domains_unchanged():
    assert geo_audit._BRAND_DOMAINS["swing-shack"] == "https://swingshack.co.za"
    assert geo_audit._BRAND_DOMAINS["stick"] == "https://stickgolf.co.za"


def test_default_watchlists_have_no_duplicates():
    for brand, queries in geo_routes._DEFAULT_WATCHLIST.items():
        lowered = [q.lower() for q in queries]
        assert len(lowered) == len(set(lowered)), brand


def test_swing_shack_and_stick_watchlists_are_about_thirty():
    for brand in ("swing-shack", "stick"):
        assert 25 <= len(geo_routes._DEFAULT_WATCHLIST[brand]) <= 35, brand
