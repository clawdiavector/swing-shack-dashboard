"""meta_live_fetch must write to DATA_DIR when set (Railway volume)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def test_resolve_data_dir_prefers_runtime(monkeypatch, tmp_path):
    runtime = tmp_path / "volume"
    runtime.mkdir()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "post-conversion-score.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))

    from _lib import meta_live_fetch as mlf

    assert mlf._resolve_data_dir() == runtime
    assert mlf._live_data_dir() == runtime
