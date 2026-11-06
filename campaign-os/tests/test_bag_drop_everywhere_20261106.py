"""Bag Drop gets every Campaign OS feature that fits an online store (2026-11-06).

Christelle: "every usability should now also be available for Bag Drop. All things we do
for Swing Shack and Stick should now also be done for The Bag Drop." The audit
(wiki research/bag-drop-activation-audit-and-brand-parity-2026-11-06) found ~45 places
hard-coded to ("swing-shack", "stick"). This pins the switch-on:

- one shared list of the three businesses, and a separate list of the two venues
  (Google Business Profile, bookings and services only apply to a place people visit);
- Bag Drop's own facts in data/brands.json (it still described a Thursday social at
  Swing Shack, with Swing Shack's website and Instagram);
- Meta numbers on (connected 2026-10-30), Instagram and Facebook as its channels;
- reports, daily target, calendar-moment drafts, story ideas, SEO, site audit, GEO;
- ads stay on brands with a Meta ad account, and say so plainly for Bag Drop;
- the right website for every brand.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _brands() -> dict:
    return json.loads((REPO_ROOT / "data" / "brands.json").read_text(encoding="utf-8"))["brands"]


# ── one shared list ─────────────────────────────────────────────────────────

def test_one_shared_list_of_businesses_and_venues():
    from _lib import brand_scope as bs

    assert bs.OPERATING_BRANDS == ("swing-shack", "stick", "bag-drop")
    assert bs.VENUE_BRANDS == ("swing-shack", "stick")
    assert bs.BRAND_DOMAINS == {
        "swing-shack": "swingshack.co.za",
        "stick": "stickgolf.co.za",
        "bag-drop": "thebagdrop.co.za",
    }


# ── data/brands.json says what Bag Drop really is ───────────────────────────

def test_bag_drop_entry_describes_the_online_store():
    bd = _brands()["bag-drop"]
    assert bd["website"] == "https://thebagdrop.co.za"
    assert bd["instagram_handle"] == "@the_bagdrop_za"
    text = json.dumps({k: bd.get(k) for k in ("tagline", "positioning", "audience", "pillar_defaults")}).lower()
    for wrong in ("thursday", "swing shack", "member", "social"):
        assert wrong not in text, wrong
    assert bd["tagline"] == "Good gear doesn't need to be new."


def test_bag_drop_posts_to_instagram_and_facebook():
    assert _brands()["bag-drop"]["publish_channels"] == ["instagram", "facebook"]
    from _lib import publish_sandbox

    assert publish_sandbox.INTENDED_CHANNELS_FALLBACK["bag-drop"] == ["instagram", "facebook"]


def test_bag_drop_meta_numbers_are_switched_on():
    meta = _brands()["bag-drop"]["integration_scope"]["meta"]
    assert meta["applies"] is True
    assert "META_PAGE_ID_BAG_DROP" in meta["env"]
    assert "META_INSTAGRAM_BUSINESS_ACCOUNT_ID_BAG_DROP" in meta["env"]


def test_bag_drop_google_reasons_are_not_about_swing_shack():
    scope = _brands()["bag-drop"]["integration_scope"]
    for key in ("ga4", "gsc"):
        assert "swingshack" not in json.dumps(scope[key]).lower(), key
        assert "swing-shack" not in json.dumps(scope[key]).lower(), key
    assert scope["ubersuggest"]["applies"] is True


def test_venue_only_integrations_stay_off_for_bag_drop():
    scope = _brands()["bag-drop"]["integration_scope"]
    assert scope["gbp"]["applies"] is False


# ── reports ─────────────────────────────────────────────────────────────────

def test_report_engine_knows_bag_drop():
    from _lib import reporting_intelligence as ri

    cfg = ri.BRAND_CONFIG["bag-drop"]
    assert cfg["domain"] == "thebagdrop.co.za"
    assert cfg["facebook_page_id"] == "1216761101518231"
    assert cfg["instagram_business_account_id"] == "17841425356549616"


def test_portfolio_pages_list_every_brand_they_are_given():
    from _lib import reporting_intelligence as ri

    reports = {b: {"brand_name": b.upper()} for b in ("stick", "swing-shack", "bag-drop")}
    for render in (ri.render_portfolio_summary_html,):
        assert "<code>bag-drop</code>" in render(reports)


# ── daily target, calendar moments ──────────────────────────────────────────

def test_bag_drop_has_a_daily_target_without_google():
    from _lib import daily_target as dt

    split = dt.target_for("bag-drop")
    assert split, "Bag Drop has a target"
    assert "google" not in split
    assert sum(split.values()) > 0


def test_bag_drop_daily_push_never_offers_fittings():
    from _lib import daily_target as dt

    leads = dt.day_leads("bag-drop", date(2026, 11, 9), date(2026, 11, 12), 17)
    for day in leads.values():
        for name in day["push"]:
            assert "fitting" not in name.lower()
            assert "coaching" not in name.lower()


def test_calendar_moment_drafts_include_bag_drop():
    from _lib import moments

    assert "bag-drop" in moments.DRAFT_BRANDS
    assert "bag-drop" in moments.VOICE_SYSTEM
    out = moments.parse_draft(json.dumps({
        "angle": "a",
        "swing-shack": "one", "stick": "two", "bag-drop": "three",
        "headlines": {"bag-drop": "Three"},
    }))
    assert out["lines"]["bag-drop"] == "three"
    assert out["headlines"]["bag-drop"] == "Three"


# ── SEO, site audit, GEO ────────────────────────────────────────────────────

def test_bag_drop_domain_resolves_without_an_env_var(monkeypatch):
    monkeypatch.delenv("BRAND_DOMAIN_BAG_DROP", raising=False)
    from _lib.jobs.layer1._io import resolve_brand_domain

    assert resolve_brand_domain("bag-drop") == ("thebagdrop.co.za", None)


def test_site_audit_has_bag_drop_store_pages():
    from _lib.jobs.layer1 import site_audit
    from _lib import seo_fix_queue

    suffixes = [p["url_suffix"] for p in site_audit.pages_for("bag-drop")]
    assert suffixes[0] == ""
    assert all(not s.startswith("/membership") and "fitting" not in s for s in suffixes)
    assert "bag-drop" in seo_fix_queue.QUEUE_BRANDS


def test_layer1_jobs_run_for_bag_drop_where_they_fit():
    from _lib.jobs.layer1 import layer1_specs

    specs = {s.name: s for s in layer1_specs()}
    for name in ("seo_rankings", "site_audit", "geo_observe"):
        assert "bag-drop" in specs[name].brands, name
    assert "bag-drop" not in specs["booking_truth"].brands


def test_geo_watches_bag_drop():
    from _lib import geo_routes, geo_runner_routes

    assert "bag-drop" in geo_runner_routes.ACTIVE_BRANDS
    qs = [q.lower() for q in geo_routes._DEFAULT_WATCHLIST["bag-drop"]]
    assert 10 <= len(qs) <= 35
    assert "second hand golf clubs" in qs
    wf = (REPO_ROOT / ".github" / "workflows" / "geo-observe-daily.yml").read_text(encoding="utf-8")
    assert "geo_observe?brand=bag-drop" in wf


# ── the app's routes ────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    for mod in list(sys.modules):
        if mod == "app":
            del sys.modules[mod]
    import app as app_module

    monkeypatch.setattr(app_module, "_is_authed", lambda: True)
    return app_module, app_module.app.test_client()


def test_report_v1_accepts_bag_drop(client, monkeypatch):
    app_module, c = client
    monkeypatch.setattr(app_module._ri, "build_brand_report", lambda b, d, cookie=None: {"brand_id": b})
    r = c.get("/api/reports/v1/bag-drop?format=json")
    assert r.status_code == 200
    assert r.get_json()["report"]["brand_id"] == "bag-drop"
    r = c.get("/api/reports/v1/portfolio?format=json")
    assert set(r.get_json()["reports"]) == {"swing-shack", "stick", "bag-drop"}


def test_story_ideas_cover_all_three_brands_by_default(client, monkeypatch):
    app_module, c = client
    from _lib import story_suggestion

    seen = []
    monkeypatch.setattr(story_suggestion, "suggest", lambda b, day, settings: seen.append(b) or [])
    monkeypatch.setattr(story_suggestion, "stock_stories", lambda *a, **k: [])
    r = c.get("/api/stories/suggestion")
    assert r.status_code == 200
    assert seen == ["swing-shack", "stick", "bag-drop"]


def test_ads_say_plainly_that_bag_drop_has_no_ad_account(client):
    app_module, c = client
    r = c.get("/api/meta/ads/cache/bag-drop")
    assert r.status_code == 404
    assert "no meta ad account" in r.get_json()["error"].lower()
    r = c.get("/api/meta/ads/cache/not-a-brand")
    assert r.status_code == 400


def test_ad_brands_follow_the_ad_accounts(client):
    app_module, _ = client
    assert set(app_module._ADS_BRIEF_BRANDS) == set(app_module._META_ADS_ACCOUNT_FOR_BRAND)


def test_channel_prompts_use_each_brands_real_website(client):
    app_module, _ = client
    for brand, domain in (("stick", "stickgolf.co.za"), ("bag-drop", "thebagdrop.co.za")):
        out = app_module._per_channel_prompts("Idea", brand_id=brand, voice=brand, tone="", pillar=None,
                                              neighbourhood=None, goal="")
        text = json.dumps(out)
        assert domain in text, brand
        assert "Westcliff" not in text and "Swing Shack" not in text, brand
