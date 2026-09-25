"""Unit tests for public Google Drive folder listing (embedded HTML fixture)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from _lib import google_drive as gd

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "drive_embedded_folder_services.html"
)
SERVICES_FOLDER_ID = "1FYeac0rVLezYFcS_02Yqsn7fOw1ecghd"


def test_parse_embedded_folder_services_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    entries = gd.parse_embedded_folder_html(html)
    assert len(entries) == 34
    assert all(not e["folder"] for e in entries)
    names = {e["name"] for e in entries}
    assert "apparelend.jpg" in names
    assert "swingsasses_story2.jpg" in names
    first = next(e for e in entries if e["name"] == "apparelend.jpg")
    assert first["id"] == "1aUgX38Rjjo9bmoyMaIkNdQjW5Wo2VRuX"
    assert "jpeg" in first["mime"].lower() or first["mime"] == "image/jpeg"


def test_list_public_folder_uses_fetch_injection():
    html = FIXTURE.read_text(encoding="utf-8")

    def _fetch(folder_id: str) -> str:
        assert folder_id == SERVICES_FOLDER_ID
        return html

    listed = gd.list_public_folder(
        SERVICES_FOLDER_ID,
        rel_folder="Services",
        _fetch_html=_fetch,
    )
    assert len(listed) == 34
    assert all(item["folder"] == "Services" for item in listed)


def test_is_public_drive_image_skips_ai():
    assert not gd.is_public_drive_image(
        {"name": "foo.ai", "mime": "application/postscript"}
    )
    assert gd.is_public_drive_image({"name": "bar.jpg", "mime": "image/jpeg"})


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
def test_fixture_is_real_embedded_page():
    html = FIXTURE.read_text(encoding="utf-8")
    assert "embeddedfolderview" in html or "flip-entry" in html
    assert "<title>Services</title>" in html
