"""Tests for layer1/_io helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from _lib.jobs.layer1._io import atomic_write, data_dir, empty_hook_bank, read_json, utc_date, utc_now_iso


@pytest.fixture()
def scratch_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def test_data_dir_from_env(scratch_data_dir: Path) -> None:
    assert data_dir() == scratch_data_dir


def test_read_json_missing_returns_none(scratch_data_dir: Path) -> None:
    assert read_json("missing.json") is None


def test_atomic_write_and_read(scratch_data_dir: Path) -> None:
    assert atomic_write("sample.json", {"a": 1}) is True
    assert read_json("sample.json") == {"a": 1}


def test_atomic_write_skips_on_cancel(scratch_data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COS_JOB_CANCEL", "1")
    assert atomic_write("cancelled.json", {"x": 1}) is False
    assert not (scratch_data_dir / "cancelled.json").exists()


def test_empty_hook_bank_schema_keys() -> None:
    keys = set(empty_hook_bank().keys())
    expected = {
        "updated",
        "total_hooks",
        "cross_signal_sources",
        "output_buckets",
        "watched_and_worked",
        "hook_formulas",
        "ab_winners",
        "youtube_signals_summary",
    }
    assert expected <= keys


def test_utc_helpers() -> None:
    assert "T" in utc_now_iso()
    assert len(utc_date()) == 10
