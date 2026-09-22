"""Regression tests for post_conversion_score field mapping and source merge."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.layer1 import post_conversion_score  # noqa: E402
from _lib.jobs.layer1.post_conversion_score import (  # noqa: E402
    _merge_sources,
    _score_posts,
)

# Prod ig-business-analytics.json shape (camelCase, top-level engagement, no metrics).
PROD_CAMEL_MEDIA_ROW = {
    "id": "17988987897030897",
    "hook_id": "too-many-swing-thoughts-lets-lessen-that-book-your",
    "captionPreview": (
        "Too many swing thoughts? Lets lessen that 🫵 Book your coaching session @swingshack "
        "\n#golf #coach #golflife #trackman #indoorgolf"
    ),
    "format_type": "reel",
    "likes": 17,
    "comments": 0,
    "saves": 0,
    "shares": 1,
    "engagement_rate_pct": 1.09,
    "reach": 548,
    "timestamp": "2026-08-19T08:57:13+0000",
}


def _analytics_posts(n: int) -> list[dict]:
    return [{"id": f"a{i}", "timestamp": "2026-08-01T00:00:00+0000"} for i in range(n)]


def _business_media(n: int, *, start_id: int = 0) -> list[dict]:
    return [
        {
            "id": f"b{start_id + i}",
            "timestamp": "2026-08-01T00:00:00+0000",
            "hook_id": f"hook-b{start_id + i}",
            "permalink": f"https://example.com/{i}",
        }
        for i in range(n)
    ]


def test_score_posts_camelcase_prod_media_row():
    scored = _score_posts({"media": [PROD_CAMEL_MEDIA_ROW]}, {}, {}, 0.0)
    assert len(scored) == 1
    post = scored[0]
    assert post["caption_preview"]
    assert post["format_type"] == "reel"
    assert post["likes"] == 17
    assert "golf_lessons" in post["themes"] or "trackman_stats" in post["themes"]


def test_score_posts_snake_case_graph_row():
    snake_row = {
        "id": "18098215292347008",
        "hook_id": "sub-70-clubs-are-now-available-for-fitting-at-swin",
        "caption_preview": "Book your coaching session with trackman data",
        "media_type": "VIDEO",
        "metrics": {
            "likes": 10,
            "comments": 2,
            "saved": 3,
            "shares": 1,
            "reach": 222,
        },
        "permalink": "https://www.instagram.com/reel/DbpcjRwG4Tx/",
        "timestamp": "2026-08-05T06:01:11+0000",
    }
    scored = _score_posts({"media": [snake_row]}, {}, {}, 0.0)
    assert len(scored) == 1
    post = scored[0]
    assert post["format_type"] == "reel"
    assert post["likes"] == 10
    assert post["comments"] == 2
    assert post["saves"] == 3
    assert post["shares"] == 1
    assert post["permalink"] == "https://www.instagram.com/reel/DbpcjRwG4Tx/"


def test_merge_prefers_analytics_roster():
    analytics = {"posts": _analytics_posts(30)}
    overlap = [{"id": f"a{i}", "timestamp": "2026-08-01T00:00:00+0000", "hook_id": f"h{i}"} for i in range(14)]
    business = {"media": overlap}
    assert len(_merge_sources(analytics, business)) == 30


def test_merge_business_fields_win_on_overlap():
    shared_id = "17988987897030897"
    analytics = {
        "posts": [
            {
                "id": shared_id,
                "timestamp": "2026-08-19T08:57:13+0000",
                "topic_cluster": "coaching",
                "engagementRate": "0.50",
            }
        ]
    }
    business = {
        "media": [
            {
                "id": shared_id,
                "timestamp": "2026-08-19T08:57:13+0000",
                "hook_id": "too-many-swing-thoughts-lets-lessen-that-book-your",
                "engagement_rate_pct": 1.09,
                "permalink": "https://www.instagram.com/reel/DcNzhsjsClp/",
            }
        ]
    }
    merged = _merge_sources(analytics, business)
    assert len(merged) == 1
    row = merged[0]
    assert row["permalink"] == "https://www.instagram.com/reel/DcNzhsjsClp/"
    assert row["engagement_rate_pct"] == 1.09
    assert row["hook_id"] == "too-many-swing-thoughts-lets-lessen-that-book-your"
    assert row["topic_cluster"] == "coaching"


def test_merge_appends_business_only_ids():
    analytics = {"posts": [{"id": "only-analytics", "timestamp": "2026-08-01T00:00:00+0000"}]}
    business = {
        "media": [
            {"id": "only-analytics", "timestamp": "2026-08-01T00:00:00+0000"},
            {"id": "only-business", "timestamp": "2026-08-02T00:00:00+0000", "hook_id": "biz-only"},
        ]
    }
    merged = _merge_sources(analytics, business)
    ids = {str(r["id"]) for r in merged}
    assert ids == {"only-analytics", "only-business"}


def test_merge_falls_back_to_business_media():
    business = {"media": _business_media(3)}
    assert _merge_sources({}, business) == business["media"]
    assert _merge_sources({"posts": []}, business) == business["media"]


def test_run_errors_when_both_sources_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with patch.object(post_conversion_score.ga4_report, "_missing_env_error", return_value=None):
        result = post_conversion_score.run()
    assert result.get("ok") is False
    err = result.get("error") or ""
    assert "ig-analytics.json" in err
    assert "ig-business-analytics.json" in err


def test_engagement_rate_from_camelcase_string():
    row = {
        "id": "1",
        "hook_id": "slug-here",
        "captionPreview": "hello world",
        "engagementRate": "0.93",
        "timestamp": "2026-08-01T00:00:00+0000",
        "reach": 100,
    }
    scored = _score_posts([row], {}, {}, 0.0)
    assert scored[0]["engagement_rate_pct"] == 0.93


def test_media_type_derived_from_format_type():
    reel_row = {
        "id": "1",
        "hook_id": "slug",
        "format_type": "reel",
        "captionPreview": "test",
        "timestamp": "2026-08-01T00:00:00+0000",
        "reach": 10,
    }
    scored = _score_posts([reel_row], {}, {}, 0.0)
    assert scored[0]["media_type"] == "VIDEO"
    assert scored[0]["format_type"] == "reel"

    carousel_row = {
        **reel_row,
        "id": "2",
        "format_type": "carousel",
    }
    scored_c = _score_posts([carousel_row], {}, {}, 0.0)
    assert scored_c[0]["media_type"] == "CAROUSEL_ALBUM"
    assert scored_c[0]["format_type"] == "image"


def test_hook_id_derived_when_numeric():
    row = {
        "id": "17988987897030897",
        "hook_id": "17988987897030897",
        "captionPreview": (
            "Too many swing thoughts? Lets lessen that Book your coaching session @swingshack"
        ),
        "timestamp": "2026-08-19T08:57:13+0000",
        "reach": 100,
    }
    scored = _score_posts([row], {}, {}, 0.0)
    assert scored[0]["hook_id"] == "too-many-swing-thoughts-lets-lessen-that-book-your"


def test_hook_id_preserved_when_slug():
    row = {
        "id": "18098215292347008",
        "hook_id": "sub-70-clubs-are-now-available-for-fitting-at-swin",
        "caption_preview": "Sub 70 clubs",
        "timestamp": "2026-08-05T06:01:11+0000",
        "reach": 222,
    }
    scored = _score_posts([row], {}, {}, 0.0)
    assert scored[0]["hook_id"] == "sub-70-clubs-are-now-available-for-fitting-at-swin"


def test_hook_id_empty_for_unicode_caption():
    row = {
        "id": "18241808092308155",
        "hook_id": "18241808092308155",
        "captionPreview": "𝗦𝘂𝗯 𝟳𝟬 𝗵𝗮𝘀 𝗮𝗋𝗋𝗂𝘃𝖾𝖽 𝗮𝘁 𝗦𝘄𝗶𝗻𝗴 𝗦𝗵𝗮𝗰𝗸.",
        "timestamp": "2026-07-30T14:13:21+0000",
        "reach": 137,
    }
    scored = _score_posts([row], {}, {}, 0.0)
    assert scored[0]["hook_id"] == ""
    assert scored[0]["raw_score"] >= 0


def test_permalink_blank_without_source():
    row = {
        "id": "999",
        "hook_id": "999",
        "captionPreview": "Only analytics row",
        "timestamp": "2026-08-01T00:00:00+0000",
        "reach": 50,
    }
    scored = _score_posts([row], {}, {}, 0.0)
    assert "permalink" in scored[0]
    assert scored[0]["permalink"] == ""


def test_scoring_math_unchanged():
    row = {
        "id": "math-1",
        "hook_id": "plain-test-hook",
        "caption_preview": "random topic no themes here",
        "timestamp": "2026-08-01T00:00:00+0000",
        "reach": 1000,
        "engagement_rate_pct": 0,
    }
    ig_daily = {"2026-08-01": 3, "2026-08-02": 3, "2026-08-03": 3}
    ga_by_hook = {"plain-test-hook": 5}
    scored = _score_posts([row], ga_by_hook, ig_daily, 0.0)
    assert scored[0]["raw_score"] == 60.0
