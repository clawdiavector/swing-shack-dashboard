"""Tests for insights_reco job."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from _lib.jobs.layer1 import insights_reco
from _lib.jobs.layer1._io import read_json
from _lib.jobs.layer1._reco_steps import (
    empty_anomaly_alerts,
    empty_conversion_attribution,
    empty_funnel_leaks,
    empty_missed_opportunities,
    empty_recommendation_outcomes,
    empty_recommendation_scores,
    empty_retargeting_recommendations,
    empty_website_insights,
)

SEED_FILES = (
    "ig-analytics.json",
    "ig-business-analytics.json",
    "ga4-metrics.json",
    "seo-rankings.json",
    "hook-bank.json",
    "content-ideas.json",
    "website-insights.json",
    "reddit-trends.json",
    "youtube-trends.json",
    "post-plan.json",
    "sales-priority.json",
    "recommendation-outcomes.json",
    "geo-audit.json",
    "missed-opportunities.json",
    "funnel-leaks.json",
    "conversion-attribution.json",
    "retargeting-recommendations.json",
    "recommendation-scores.json",
)


@pytest.fixture()
def seed_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_data = Path(__file__).resolve().parents[2].parent / "data"
    for name in SEED_FILES:
        src = repo_data / name
        if src.is_file():
            shutil.copy(src, tmp_path / name)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def test_run_writes_all_eight_files(seed_data_dir: Path) -> None:
    result = insights_reco.run()
    assert result["ok"] is True
    assert result["rows"] >= 0

    for name in insights_reco.OUTPUT_FILES:
        path = seed_data_dir / name
        assert path.is_file(), f"missing {name}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)


def test_output_top_level_keys_match_seeds(seed_data_dir: Path) -> None:
    repo_data = Path(__file__).resolve().parents[2].parent / "data"
    insights_reco.run()

    for name in insights_reco.OUTPUT_FILES:
        seed_keys = set(json.loads((repo_data / name).read_text(encoding="utf-8")).keys())
        out_keys = set(read_json(name).keys())
        assert seed_keys <= out_keys, f"{name} missing keys: {seed_keys - out_keys}"


def test_empty_schemas(seed_data_dir: Path) -> None:
    empties = (
        empty_anomaly_alerts(),
        empty_missed_opportunities(),
        empty_funnel_leaks(),
        empty_conversion_attribution(),
        empty_retargeting_recommendations(),
        empty_recommendation_scores(),
        empty_recommendation_outcomes(),
        empty_website_insights(),
    )
    assert all(isinstance(e, dict) for e in empties)
    assert empty_recommendation_outcomes()["schema"].startswith("https://")
