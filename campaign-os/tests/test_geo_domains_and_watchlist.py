"""
GEO: Bag Drop must not be audited against the Swing Shack website, and the
default watchlists must be the ones we reviewed.

Background (2026-10-15): geo_audit and geo_routes both mapped bag-drop to
https://swingshack.co.za, so the Bag Drop GEO audit was checking the wrong
site. Bag Drop's real domain is not recorded in the repo, so it is now empty
and the audit says "no website set" instead.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib import geo_audit, geo_routes, geo_runner  # noqa: E402


def test_bag_drop_has_no_domain_so_audit_does_not_check_swing_shack():
    assert geo_audit._BRAND_DOMAINS["bag-drop"] == ""
    assert geo_routes._BRAND_DOMAINS["bag-drop"] == ""
    result = geo_audit.run_geo_audit("bag-drop")
    assert result["ok"] is False
    assert "no website" in result["error"]


def test_bag_drop_own_domain_is_not_swing_shack():
    assert not geo_runner._is_own_domain("https://swingshack.co.za/shop", "bag-drop")
    assert geo_runner._is_own_domain("https://bag-drop.example/bag", "bag-drop")


def test_stick_and_swing_shack_domains_unchanged():
    assert geo_audit._BRAND_DOMAINS["swing-shack"] == "https://swingshack.co.za"
    assert geo_audit._BRAND_DOMAINS["stick"] == "https://stickgolf.co.za"


def test_default_watchlists_have_no_duplicates():
    for brand, queries in geo_routes._DEFAULT_WATCHLIST.items():
        lowered = [q.lower() for q in queries]
        assert len(lowered) == len(set(lowered)), brand
