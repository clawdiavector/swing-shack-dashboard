"""Connected Accounts catalog helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.connected_accounts_catalog import (  # noqa: E402
    build_brand_integrations,
    build_catalog_extras,
    infer_postiz_provider,
)


@pytest.fixture()
def brands_env(monkeypatch):
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()
    for mod in list(sys.modules):
        if mod == "_lib.connected_accounts_catalog" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    yield
    clear_brands_cache()


def test_infer_postiz_provider_from_identifier():
    assert infer_postiz_provider({"providerIdentifier": "instagram", "name": "Swing Shack"}) == "instagram"


def test_infer_postiz_provider_name_is_platform():
    assert infer_postiz_provider({"name": "gmb"}) == "gmb"


def test_infer_postiz_provider_fallback_channel():
    assert infer_postiz_provider({"name": "Swing Shack"}) == "channel"


def test_build_catalog_extras_shape():
    out = build_catalog_extras()
    assert "categories" in out
    assert "summary" in out
    assert isinstance(out["integrations"], list)
    ids = {x["id"] for x in out["integrations"]}
    assert "ga4" in ids
    assert "publish_mode" in ids
    assert "windsor" not in ids


def test_integration_state_swing_shack_unsuffixed_ga4_gsc(brands_env, monkeypatch):
    from _lib.jobs.brand_lanes import integration_state

    monkeypatch.delenv("GA4_PROPERTY_SWING_SHACK", raising=False)
    monkeypatch.delenv("GA4_CREDENTIALS_JSON_SWING_SHACK", raising=False)
    monkeypatch.delenv("GSC_SITE_URL_SWING_SHACK", raising=False)
    monkeypatch.setenv("GA4_PROPERTY_ID", "123456789")
    monkeypatch.setenv("GA4_CREDENTIALS_JSON", '{"type":"service_account","client_email":"x@y.z"}')
    monkeypatch.setenv("GSC_SITE_URL", "https://swingshack.co.za/")

    assert integration_state("swing-shack", "ga4") == "connected"
    assert integration_state("swing-shack", "gsc") == "connected"


def test_stick_gsc_skipped_job_demotes_to_partial(monkeypatch):
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    monkeypatch.setenv("GSC_SITE_URL_STICK", "https://stickgolf.co.za/")
    monkeypatch.setenv(
        "GA4_CREDENTIALS_JSON_STICK",
        '{"type":"service_account","client_email":"stick@example.com"}',
    )
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()
    for mod in list(sys.modules):
        if mod == "_lib.connected_accounts_catalog" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import _lib.connected_accounts_catalog as cat

    fake_activity = {"last_success_at": "2026-01-01T00:00:00Z", "job_verdict": "SKIPPED"}

    with patch.object(cat, "_job_activity_for_brand", return_value=fake_activity):
        out = cat.build_brand_integrations("stick")
    gsc = next(it for it in out["integrations"] if it["id"] == "gsc")
    assert gsc["state"] == "partial"
    assert gsc["connect"]["url"] == "/api/gsc/oauth/login?brand=stick"


def test_windsor_absent_from_brand_integrations(brands_env):
    for brand_id in ("swing-shack", "stick"):
        out = build_brand_integrations(brand_id)
        ids = {it["id"] for it in out["integrations"]}
        assert "windsor" not in ids


def test_gbp_oauth_file_connected_without_location_env(brands_env, monkeypatch):
    from _lib.jobs import brand_lanes as bl

    monkeypatch.delenv("GBP_LOCATION_ID_SWING_SHACK", raising=False)
    monkeypatch.delenv("GBP_LOCATION_ID", raising=False)
    with patch.object(bl, "_credential_file_exists", return_value=True):
        assert bl.integration_state("swing-shack", "gbp") == "connected"


def test_ubersuggest_token_file_only_connected(brands_env, monkeypatch, tmp_path):
    from _lib.jobs.brand_lanes import integration_state

    monkeypatch.delenv("UBERSUGGEST_ACCESS", raising=False)
    monkeypatch.delenv("UBERSUGGEST_REFRESH_TOKEN", raising=False)
    tok = tmp_path / "uber.json"
    tok.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("UBERSUGGEST_TOKEN_FILE", str(tok))
    assert integration_state("swing-shack", "ubersuggest") == "connected"


def test_stick_meta_shared_token_not_missing(brands_env, monkeypatch):
    from _lib.jobs.brand_lanes import integration_state

    monkeypatch.delenv("META_SYSTEM_USER_TOKEN_STICK_PAARL", raising=False)
    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", "shared-tok")
    monkeypatch.setenv("META_PAGE_ID_STICK", "123")
    monkeypatch.setenv("META_INSTAGRAM_BUSINESS_ACCOUNT_ID_STICK", "456")
    assert integration_state("stick", "meta") == "connected"


def test_late_job_verdict_does_not_demote_connected(brands_env, monkeypatch):
    import _lib.connected_accounts_catalog as cat

    monkeypatch.setenv("UBERSUGGEST_ACCESS", "tok")
    fake = {"last_success_at": "2026-01-01T00:00:00Z", "job_verdict": "LATE", "last_status": "OK"}
    with patch.object(cat, "_job_activity_for_brand", return_value=fake):
        out = cat.build_brand_integrations("swing-shack")
    uber = next(it for it in out["integrations"] if it["id"] == "ubersuggest")
    assert uber["state"] == "connected"


def test_stuck_overall_ok_brand_stays_connected(brands_env, monkeypatch):
    import _lib.connected_accounts_catalog as cat

    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", "tok")
    monkeypatch.setenv("META_PAGE_ID_SWING_SHACK", "1")
    monkeypatch.setenv("META_INSTAGRAM_BUSINESS_ACCOUNT_ID_SWING_SHACK", "2")
    fake = {
        "last_success_at": "2026-01-01T00:00:00Z",
        "job_verdict": "OK",
        "last_status": "OK",
    }
    with patch.object(cat, "_job_activity_for_brand", return_value=fake):
        out = cat.build_brand_integrations("swing-shack")
    meta = next(it for it in out["integrations"] if it["id"] == "meta")
    assert meta["state"] == "connected"
    fake_stuck = {**fake, "job_verdict": "STUCK"}
    with patch.object(cat, "_job_activity_for_brand", return_value=fake_stuck):
        out2 = cat.build_brand_integrations("swing-shack")
    meta2 = next(it for it in out2["integrations"] if it["id"] == "meta")
    assert meta2["state"] == "connected"


def test_connected_html_skips_env_tags_for_connected():
    html = (CAMPAIGN_OS / "connected-accounts.html").read_text(encoding="utf-8")
    assert "item.state !== 'connected'" in html
    assert "env_unsatisfied" in html
