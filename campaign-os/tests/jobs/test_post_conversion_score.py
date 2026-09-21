"""Regression tests for post_conversion_score field mapping."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.layer1.post_conversion_score import _score_posts  # noqa: E402

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
