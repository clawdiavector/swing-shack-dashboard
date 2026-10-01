"""One-shot sub-cap vs global image cap."""

from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def test_oneshot_cap_and_global(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from _lib.image_submit_quota import (
        check_brand_image_submit,
        check_brand_oneshot_submit,
        record_brand_image_submit,
        record_brand_oneshot_submit,
    )

    ok, _ = check_brand_oneshot_submit("stick")
    assert ok
    record_brand_oneshot_submit("stick")
    record_brand_image_submit("stick")
    ok2, reason = check_brand_oneshot_submit("stick")
    assert not ok2
    assert "cap" in reason.lower()
    ok3, _ = check_brand_image_submit("stick")
    assert ok3


def test_old_day_file_without_oneshot_key(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    path = tmp_path / "image-submit-count"
    path.mkdir()
    (path / "2026-10-01.json").write_text(
        '{"schema": "campaign-os/image-submit-count/v1", "date": "2026-10-01", "brands": {}}',
        encoding="utf-8",
    )
    from _lib.image_submit_quota import oneshot_count_for_brand

    assert oneshot_count_for_brand("stick", day="2026-10-01") == 0
