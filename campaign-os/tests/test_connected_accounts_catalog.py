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
