"""A failed GSC token refresh must not hand back the dead cached access token (2026-11-02 fleet tick:
gsc_report 401 for 19 days because the expired token kept being reused)."""

from __future__ import annotations


def test_refresh_failure_returns_none(tmp_path, monkeypatch):
    from _lib import gsc_oauth as gsc

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    gsc.save_token({"access_token": "dead", "refresh_token": "r"}, brand="stick")
    monkeypatch.setattr(gsc, "refresh_access_token", lambda _r: (None, ("400", {"error": "invalid_grant"})))
    assert gsc.get_access_token(brand="stick") is None


def test_refresh_success_returns_new_token(tmp_path, monkeypatch):
    from _lib import gsc_oauth as gsc

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    gsc.save_token({"access_token": "old", "refresh_token": "r"}, brand="stick")
    monkeypatch.setattr(gsc, "refresh_access_token", lambda _r: ({"access_token": "new", "expires_in": 3600}, None))
    assert gsc.get_access_token(brand="stick") == "new"


def test_no_refresh_token_keeps_access_token(tmp_path, monkeypatch):
    from _lib import gsc_oauth as gsc

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    gsc.save_token({"access_token": "only"}, brand="stick")
    assert gsc.get_access_token(brand="stick") == "only"
