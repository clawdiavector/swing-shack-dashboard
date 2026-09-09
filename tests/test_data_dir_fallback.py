"""Tests for the data-dir fallback helpers + IG multi-source loader.

Covers:
  - _resolve_data_path: prefers runtime DATA_DIR, falls back to BUNDLED_DATA_DIR
  - _load_ig_posts: tries instagram.json → analytics/instagram-analytics.json → ig-analytics.json
  - Field normalisation across all three IG store shapes
  - get_top_instagram_posts returns real data when ANY IG store exists
  - get_ad_correlation_verdicts returns 'configured' when google-ads.json / meta-ads.json exist
  - get_content_traffic_correlations reports the right posts_scanned
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure we can import the app modules from anywhere
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "campaign-os"))

from _lib import insights_correlator as ic  # noqa: E402


@pytest.fixture
def tmp_data_dirs(monkeypatch):
    """Create empty runtime DATA_DIR + populated bundled DATA_DIR."""
    tmpdir = tempfile.mkdtemp(prefix="ig-test-")
    runtime = Path(tmpdir) / "runtime"
    bundled = Path(tmpdir) / "bundled"
    runtime.mkdir()
    bundled.mkdir()
    (bundled / "analytics").mkdir()
    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))
    yield runtime, bundled
    shutil.rmtree(tmpdir)


def _write_ig(path: Path, posts: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"posts": posts, "lastUpdated": "2026-08-10"}))


def _sample_posts() -> list:
    return [
        {
            "id": "123",
            "timestamp": "2026-08-01T10:00:00Z",
            "caption": "Test post",
            "engagementRate": 4.5,
            "permalink": "https://ig/p/123",
            "thumbnail_url": "https://cdn/123.jpg",
            "like_count": 100,
            "comments_count": 10,
            "reach": 5000,
        },
        {
            "id": "456",
            "timestamp": "2026-07-15T10:00:00Z",
            "captionPreview": "Older post",
            "engagementRate": 1.2,
            "permalink": "https://ig/p/456",
            "media_url": "https://cdn/456.jpg",
            "likes": 50,
            "comments": 5,
            "reach": 2000,
        },
    ]


def test_data_dir_fallback_to_bundled_when_runtime_empty(tmp_data_dirs):
    """Empty runtime dir + populated bundled dir → use bundled."""
    runtime, bundled = tmp_data_dirs
    _write_ig(bundled / "analytics" / "instagram-analytics.json", _sample_posts())
    resolved = ic._data_dir()
    assert resolved == bundled
    posts, source = ic._load_ig_posts()
    assert len(posts) == 2
    assert source == "analytics/instagram-analytics.json"


def test_data_dir_prefers_runtime_when_populated(tmp_data_dirs):
    """Runtime has its own copy → use runtime, not bundled."""
    runtime, bundled = tmp_data_dirs
    _write_ig(runtime / "analytics" / "instagram-analytics.json", _sample_posts()[:1])
    _write_ig(bundled / "analytics" / "instagram-analytics.json", _sample_posts())
    resolved = ic._data_dir()
    assert resolved == runtime
    posts, _ = ic._load_ig_posts()
    assert len(posts) == 1


def test_load_ig_posts_normalises_field_aliases(tmp_data_dirs):
    """Different IG stores have different field names — loader normalises them."""
    runtime, bundled = tmp_data_dirs
    posts_raw = _sample_posts()
    _write_ig(bundled / "analytics" / "instagram-analytics.json", posts_raw)
    posts, _ = ic._load_ig_posts()
    assert posts[0]["like_count"] == 100  # from 'like_count'
    assert posts[1]["like_count"] == 50   # from 'likes' alias
    assert posts[0]["engagementRate"] == 4.5
    assert posts[1]["engagementRate"] == 1.2
    # Both normalised to have thumbnail_url
    assert posts[0]["thumbnail_url"] == "https://cdn/123.jpg"
    assert posts[1]["thumbnail_url"] == "https://cdn/456.jpg"


def test_load_ig_posts_handles_ig_analytics_json(tmp_data_dirs):
    """The lightweight ig-analytics.json store also works."""
    runtime, bundled = tmp_data_dirs
    _write_ig(bundled / "ig-analytics.json", _sample_posts())
    posts, source = ic._load_ig_posts()
    assert len(posts) == 2
    assert source == "ig-analytics.json"


def test_get_top_instagram_posts_returns_real_posts(tmp_data_dirs):
    """End-to-end: empty runtime + bundled IG data → top posts appear."""
    runtime, bundled = tmp_data_dirs
    _write_ig(bundled / "analytics" / "instagram-analytics.json", _sample_posts())
    result = ic.get_top_instagram_posts(limit=5)
    assert result["ok"] is True
    assert len(result["posts"]) == 2
    assert result["posts"][0]["engagementRate"] == 4.5
    # 4.5 vs avg 2.85 → above-average (need 2x for top performer)
    assert result["posts"][0]["verdict"] == "Above average"
    # 1.2 vs avg 2.85 → below 50% threshold → Underperformer
    assert result["posts"][1]["verdict"] == "Underperformer"
    assert result["_meta"]["total_scanned"] == 2
    assert result["_meta"]["source"] == "analytics/instagram-analytics.json"


def test_get_top_instagram_posts_handles_missing_engagementrate(tmp_data_dirs):
    """Posts with None engagementRate shouldn't crash."""
    runtime, bundled = tmp_data_dirs
    posts_with_null = [
        {"id": "1", "engagementRate": None, "timestamp": "2026-08-01"},
        {"id": "2", "engagementRate": "0.5", "timestamp": "2026-08-02"},
    ]
    _write_ig(bundled / "ig-analytics.json", posts_with_null)
    result = ic.get_top_instagram_posts(limit=5)
    assert result["ok"] is True
    assert len(result["posts"]) == 2  # both posts count, no crash


def test_get_ad_correlation_verdicts_when_files_exist(tmp_data_dirs):
    """When google-ads.json + meta-ads.json exist, configured=True with verdicts."""
    runtime, bundled = tmp_data_dirs
    (bundled / "google-ads.json").write_text(json.dumps({
        "campaigns": [
            {"id": "c1", "name": "Test campaign", "spend": 100, "clicks": 50,
             "impressions": 1000, "start_date": "2026-08-01", "end_date": "2026-08-07",
             "landing_page": "/"}
        ]
    }))
    (bundled / "meta-ads.json").write_text(json.dumps({
        "campaigns": [
            {"id": "m1", "name": "Meta campaign", "spend": 50, "clicks": 30,
             "impressions": 500, "start_date": "2026-08-02", "end_date": "2026-08-08",
             "landing_page": "/"}
        ]
    }))
    result = ic.get_ad_correlation_verdicts()
    assert result["configured"] is True
    assert result["google_ads"]["configured"] is True
    assert len(result["google_ads"]["campaigns"]) == 1
    assert result["meta_ads"]["configured"] is True
    assert len(result["meta_ads"]["campaigns"]) == 1


def test_get_ad_correlation_verdicts_returns_not_configured_when_missing(tmp_data_dirs):
    """When ad files don't exist, configured=False but with helpful reason."""
    result = ic.get_ad_correlation_verdicts()
    assert result["configured"] is False
    assert result["google_ads"]["configured"] is False
    assert "google-ads.json" in result["google_ads"]["reason"].lower()
    assert result["meta_ads"]["configured"] is False
    assert "meta-ads.json" in result["meta_ads"]["reason"].lower()


def test_get_content_traffic_correlations_with_real_posts(tmp_data_dirs):
    """When posts exist, _meta shows the right scanned count."""
    runtime, bundled = tmp_data_dirs
    _write_ig(bundled / "analytics" / "instagram-analytics.json", _sample_posts())
    (bundled / "ga4-metrics.json").write_text(json.dumps({
        "total_sessions": 1008,
        "data_window": "2026-08-01 to 2026-08-07",
        "pages": [{"path": "/", "sessions": 500, "engRate": 0.45}]
    }))
    result = ic.get_content_traffic_correlations(days=30)
    assert result["ok"] is True
    assert result["_meta"]["posts_scanned"] == 2
    assert result["_meta"]["ga4_total_sessions"] == 1008
    assert len(result["_meta"]["top_instagram_posts"]) == 2