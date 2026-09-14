"""t31 Layer 1 contract tests — network stubbed; shape + failure paths.

CI subset: `python3 -m pytest campaign-os/tests/jobs/ -q`
A top-level key change in any JobSpec.writes artifact fails these tests.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.fixtures.layer1 import elem_keys, top_level_keys  # noqa: E402


@pytest.fixture()
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key in (
        "YOUTUBE_API_KEY",
        "GA4_PROPERTY_ID",
        "GA4_SERVICE_ACCOUNT_JSON_PATH",
        "UBERSUGGEST_TOKEN_FILE",
        "COS_JOB_CANCEL",
    ):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def _assert_ok_rows(result: dict) -> None:
    assert isinstance(result, dict)
    assert result.get("ok") is True
    assert isinstance(result.get("rows"), int)


def _assert_fail_no_raise(result: dict) -> None:
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("error")
    assert "rows" not in result or isinstance(result.get("rows"), (int, type(None)))


def _assert_writes(data_dir: Path, names: tuple[str, ...]) -> None:
    for name in names:
        path = data_dir / name
        assert path.is_file(), f"missing write {name}"
        obj = json.loads(path.read_text(encoding="utf-8"))
        assert set(obj.keys()) == top_level_keys(name), (
            f"{name} keys={sorted(obj.keys())} expected={sorted(top_level_keys(name))}"
        )


def _assert_array_elems(data_dir: Path, filename: str) -> None:
    expected = elem_keys(filename)
    if not expected:
        return
    meta = json.loads((HERE / "fixtures/layer1/golden_keys.json").read_text())[filename]
    arr_name = meta["array"]
    obj = json.loads((data_dir / filename).read_text(encoding="utf-8"))
    arr = obj.get(arr_name) or []
    assert arr, f"{filename}.{arr_name} empty — cannot assert element keys"
    assert set(arr[0].keys()) >= expected


# ── golf_news ───────────────────────────────────────────────────────────────

RSS = (
    b'<?xml version="1.0"?><rss><channel>'
    b"<item><title>SA Golf Open Winner Announced Today</title>"
    b"<link>https://example.com/a1</link>"
    b"<pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate>"
    b"<description>x</description></item>"
    b"</channel></rss>"
)


def test_golf_news_success_shape(data_dir):
    from _lib.jobs.layer1 import golf_news

    with patch.object(golf_news, "_fetch_url", return_value=RSS):
        result = golf_news.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("golf-news.json",))
    _assert_array_elems(data_dir, "golf-news.json")


def test_golf_news_failure_path(data_dir):
    from _lib.jobs.layer1 import golf_news

    with patch.object(golf_news, "_fetch_url", side_effect=RuntimeError("net down")):
        result = golf_news.run()
    _assert_fail_no_raise(result)


# ── reddit_trends ───────────────────────────────────────────────────────────

REDDIT_PAYLOAD = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "How to fix my slice on the range",
                    "score": 42,
                    "num_comments": 3,
                    "url": "https://reddit.com/r/golf/1",
                    "permalink": "/r/golf/comments/1/",
                    "created_utc": 1700000000,
                    "over_18": False,
                    "is_self": True,
                    "selftext": "help please",
                }
            }
        ]
    }
}


def test_reddit_trends_success_shape(data_dir):
    from _lib.jobs.layer1 import reddit_trends

    with patch.object(reddit_trends, "_fetch_json", return_value=REDDIT_PAYLOAD):
        result = reddit_trends.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("reddit-trends.json",))
    _assert_array_elems(data_dir, "reddit-trends.json")


def test_reddit_trends_failure_path(data_dir):
    from _lib.jobs.layer1 import reddit_trends

    with patch.object(reddit_trends, "_fetch_json", side_effect=RuntimeError("down")):
        result = reddit_trends.run()
    _assert_fail_no_raise(result)


# ── youtube_trends ──────────────────────────────────────────────────────────

YT_PAYLOAD = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "Fix your golf slice in 5 minutes",
                "channelTitle": "Coach",
                "publishedAt": "2026-01-01T00:00:00Z",
                "description": "slice fix drill",
            },
        }
    ]
}


def test_youtube_trends_success_shape(data_dir, monkeypatch):
    from _lib.jobs.layer1 import youtube_trends

    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    with patch.object(youtube_trends, "_youtube_search", return_value=YT_PAYLOAD):
        result = youtube_trends.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("youtube-trends.json",))
    _assert_array_elems(data_dir, "youtube-trends.json")


def test_youtube_trends_missing_cred(data_dir):
    from _lib.jobs.layer1 import youtube_trends

    result = youtube_trends.run()
    _assert_fail_no_raise(result)
    assert "YOUTUBE_API_KEY" in result["error"]


# ── seo_rankings ────────────────────────────────────────────────────────────

SEO_KEYS = (
    "seo-rankings.json",
    "ubersuggest-domain.json",
    "ubersuggest-competitors.json",
    "ubersuggest-backlinks.json",
)


def test_seo_rankings_no_token(data_dir):
    from _lib.jobs.layer1 import seo_rankings

    result = seo_rankings.run()
    _assert_fail_no_raise(result)
    assert result["error"] == "no ubersuggest token"


def test_seo_rankings_wrap_exit_zero(data_dir, monkeypatch):
    from _lib.jobs.layer1 import seo_rankings

    token = data_dir / "token.json"
    token.write_text(json.dumps({"access_token": "x"}), encoding="utf-8")
    monkeypatch.setenv("UBERSUGGEST_TOKEN_FILE", str(token))

    # Write the four artifacts the wrapper expects after a successful main().
    (data_dir / "seo-rankings.json").write_text(
        json.dumps(
            {
                "average_position_trend": [],
                "binned": {},
                "falling": [],
                "keywords": [{"keyword": "indoor golf"}],
                "metadata": {},
                "quick_wins": [],
                "rising": [],
                "summary": {},
            }
        ),
        encoding="utf-8",
    )
    for name, payload in (
        ("ubersuggest-domain.json", {"_meta": {}, "domain": "x", "backlinks": 0, "domainAuthority": 0, "domainTraffic": 0, "follow": 0, "noFollow": 0, "organic": 0, "organicKeywords": 0, "paidKeywords": 0, "paidTraffic": 0, "refDomains": 0, "serviceInfo": {}, "traffic": 0}),
        ("ubersuggest-competitors.json", {"_meta": {}, "competitors": []}),
        ("ubersuggest-backlinks.json", {"_meta": {}, "backlinks": [], "domainAuthority": 0, "follow": 0, "noFollow": 0, "refDomains": 0, "refDomainsGovEdu": 0}),
    ):
        (data_dir / name).write_text(json.dumps(payload), encoding="utf-8")

    mod = MagicMock()
    mod.main.return_value = 0
    with patch.object(seo_rankings, "_load_ubersuggest_module", return_value=mod):
        result = seo_rankings.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, SEO_KEYS)


# ── ga4_report ──────────────────────────────────────────────────────────────

GA4_REPORT = {
    "rows": [
        {
            "dimensionValues": [{"value": "/"}, {"value": "(direct)"}],
            "metricValues": [{"value": "10"}, {"value": "0.5"}, {"value": "30"}],
        }
    ]
}


def test_ga4_report_success_shape(data_dir, monkeypatch):
    from _lib.jobs.layer1 import ga4_report

    monkeypatch.setenv("GA4_PROPERTY_ID", "123")
    monkeypatch.setenv("GA4_SERVICE_ACCOUNT_JSON_PATH", str(data_dir / "sa.json"))
    (data_dir / "sa.json").write_text("{}", encoding="utf-8")
    with patch.object(ga4_report, "_get_ga4_bearer", return_value="tok"), patch.object(
        ga4_report, "_run_ga4_report", return_value=GA4_REPORT
    ):
        result = ga4_report.run()
    _assert_ok_rows(result)
    # Seed has _stale_reason / _fallback_used only when stale; success payload
    # must still cover the stable reader keys.
    obj = json.loads((data_dir / "ga4-metrics.json").read_text(encoding="utf-8"))
    required = {
        "updated",
        "fetched_at",
        "property_id",
        "data_window",
        "total_sessions",
        "pages",
        "sources",
        "insights",
        "top_pages_count",
        "insights_count",
        "_stale",
        "_auth_worked",
    }
    assert required <= set(obj.keys())
    assert isinstance(obj["total_sessions"], int)


def test_ga4_report_missing_cred(data_dir):
    from _lib.jobs.layer1 import ga4_report

    result = ga4_report.run()
    _assert_fail_no_raise(result)
    assert "GA4_PROPERTY_ID" in result["error"]


# ── site_audit ──────────────────────────────────────────────────────────────

HTML = (
    "<html><head><title>Swing Shack Indoor Golf Johannesburg Randburg Spot</title>"
    '<meta name="description" content="Indoor golf Trackman lessons and fittings in Johannesburg area">'
    "</head><body><h1>Swing Shack</h1><a href='/book'>Book Now</a> "
    "Johannesburg Randburg simulator Trackman</body></html>"
)


def test_site_audit_success_shape(data_dir):
    from _lib.jobs.layer1 import site_audit

    with patch.object(site_audit, "_fetch_page", return_value=HTML):
        result = site_audit.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("seo-audit.json", "geo-audit.json"))


def test_site_audit_failure_path(data_dir):
    from _lib.jobs.layer1 import site_audit

    with patch.object(site_audit, "_fetch_page", side_effect=RuntimeError("down")):
        result = site_audit.run()
    _assert_fail_no_raise(result)


# ── insights_hooks / insights_reco (Class A) ────────────────────────────────


def test_insights_hooks_empty_input(data_dir):
    from _lib.jobs.layer1 import insights_hooks

    result = insights_hooks.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("hook-bank.json", "youtube-hook-signals.json"))


def test_insights_hooks_with_seed_like_inputs(data_dir):
    from _lib.jobs.layer1 import insights_hooks

    (data_dir / "ig-analytics.json").write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "caption": "Stop slicing your driver TODAY",
                        "engagementRate": 4.2,
                        "saveRate": 1.1,
                        "shareRate": 0.4,
                        "reach": 500,
                        "likeCount": 40,
                        "commentsCount": 3,
                        "permalink": "https://instagram.com/p/1",
                    }
                ],
                "schema": "v1",
                "source": "test",
                "total_posts": 1,
                "updated": "2026-09-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "youtube-trends.json").write_text(
        json.dumps(
            {
                "articles_sourced": [],
                "data_source": "test",
                "hooks": [],
                "summary": {},
                "top_videos": [
                    {
                        "title": "How to fix a slice",
                        "description": "easy drill",
                        "videoId": "v1",
                        "channelTitle": "c",
                        "publishedAt": "2026-01-01T00:00:00Z",
                        "source": "youtube_api_v3",
                        "query": "slice",
                    }
                ],
                "trending_themes": {},
                "updated": "2026-09-01T00:00:00Z",
                "videos_found": 1,
            }
        ),
        encoding="utf-8",
    )
    result = insights_hooks.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("hook-bank.json", "youtube-hook-signals.json"))


def test_insights_reco_empty_input(data_dir):
    from _lib.jobs.layer1 import insights_reco

    result = insights_reco.run()
    _assert_ok_rows(result)
    _assert_writes(
        data_dir,
        (
            "anomaly-alerts.json",
            "missed-opportunities.json",
            "funnel-leaks.json",
            "conversion-attribution.json",
            "retargeting-recommendations.json",
            "recommendation-scores.json",
            "recommendation-outcomes.json",
            "website-insights.json",
        ),
    )


# ── registry wiring ─────────────────────────────────────────────────────────


def test_layer1_specs_registered():
    from _lib.jobs.layer1 import LAYER1_JOB_NAMES
    from _lib.jobs.registry import JOBS

    for name in LAYER1_JOB_NAMES:
        assert name in JOBS, f"{name} not registered"
        spec = JOBS[name]
        assert spec.fn is not None
        assert isinstance(spec.writes, tuple) and spec.writes
        assert isinstance(spec.reads, tuple)
        assert isinstance(spec.upstream, tuple)


def test_jobspec_reads_upstream_defaulted_on_meta():
    from _lib.jobs.registry import JOBS

    meta = JOBS["meta_refresh"]
    assert meta.reads == ()
    assert meta.upstream == ()
