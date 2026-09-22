"""Google Drive integration_state via oauth_status (shared token, per-brand folder)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from _lib.jobs.brand_lanes import clear_brands_cache, integration_state


def _drive_status(*, has_token: bool, connected: bool, auth_error: str | None = None):
    return {
        "has_token": has_token,
        "connected": connected,
        "auth_error": auth_error,
        "has_oauth_client": True,
    }


@pytest.fixture(autouse=True)
def _fresh_brands_cache():
    clear_brands_cache()
    yield
    clear_brands_cache()


@pytest.mark.parametrize("brand_id", ["stick", "swing-shack"])
def test_integration_state_connected_when_drive_oauth_live(brand_id):
    mock_status = _drive_status(has_token=True, connected=True)
    with patch("_lib.google_drive.status", return_value=mock_status):
        assert integration_state(brand_id, "google_drive") == "connected"


@pytest.mark.parametrize("brand_id", ["stick", "swing-shack"])
def test_build_brand_integrations_drive_row_connected(brand_id):
    from _lib.connected_accounts_catalog import build_brand_integrations

    mock_status = _drive_status(has_token=True, connected=True)
    with patch("_lib.google_drive.status", return_value=mock_status):
        data = build_brand_integrations(brand_id)
    by_id = {it["id"]: it for it in data["integrations"]}
    drive = by_id["google_drive"]
    assert drive["state"] == "connected"
    assert drive.get("folder_name")


@pytest.mark.parametrize("brand_id", ["stick", "swing-shack"])
def test_integration_state_missing_without_token(brand_id):
    mock_status = _drive_status(has_token=False, connected=False)
    with patch("_lib.google_drive.status", return_value=mock_status):
        assert integration_state(brand_id, "google_drive") == "missing"


def test_integration_state_partial_when_folder_name_empty():
    mock_status = _drive_status(has_token=True, connected=True)
    with patch("_lib.google_drive.status", return_value=mock_status):
        with patch(
            "_lib.jobs.brand_lanes.load_brands_registry",
        ) as load_reg:
            load_reg.return_value = {
                "integrations": {
                    "google_drive": {
                        "state_source": "oauth_status",
                        "scope_class": "shared_credential_per_brand_config",
                    }
                },
                "brands": {
                    "stick": {
                        "integration_scope": {
                            "google_drive": {"applies": True, "config": {"folder_name": ""}}
                        }
                    }
                },
            }
            assert integration_state("stick", "google_drive") == "partial"


def test_integration_state_partial_on_auth_error():
    mock_status = _drive_status(
        has_token=True, connected=False, auth_error="Token has been expired or revoked"
    )
    with patch("_lib.google_drive.status", return_value=mock_status):
        assert integration_state("swing-shack", "google_drive") == "partial"
