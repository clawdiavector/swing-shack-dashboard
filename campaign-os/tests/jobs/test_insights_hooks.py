"""Tests for insights_hooks job."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from _lib.jobs.layer1 import insights_hooks
from _lib.jobs.layer1._io import read_json


@pytest.fixture()
def seed_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_data = Path(__file__).resolve().parents[2].parent / "data"
    for name in (
        "ig-analytics.json",
        "youtube-trends.json",
        "youtube-hook-signals.json",
        "reddit-trends.json",
        "golf-news.json",
        "hook-bank.json",
        "ab-tests.json",
    ):
        src = repo_data / name
        if src.is_file():
            shutil.copy(src, tmp_path / name)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def test_run_with_seed_data(seed_data_dir: Path) -> None:
    result = insights_hooks.run()
    assert result["ok"] is True
    assert result["rows"] >= 0

    hook_bank = read_json("hook-bank.json")
    assert isinstance(hook_bank, dict)
    assert "total_hooks" in hook_bank
    assert "output_buckets" in hook_bank

    yt_signals = read_json("youtube-hook-signals.json")
    assert isinstance(yt_signals, dict)
    assert "signals" in yt_signals
    assert "summary" in yt_signals


def test_run_empty_inputs_writes_valid_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = insights_hooks.run()
    assert result["ok"] is True

    hook_bank = json.loads((tmp_path / "hook-bank.json").read_text(encoding="utf-8"))
    assert hook_bank["total_hooks"] == 0
    assert hook_bank["output_buckets"]["proven_and_trending"] == []

    yt = json.loads((tmp_path / "youtube-hook-signals.json").read_text(encoding="utf-8"))
    assert yt["videos_analyzed"] == 0
    assert yt["top_videos"] == []
