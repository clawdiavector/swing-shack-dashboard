"""The seo_rankings job must tell fetch_ubersuggest which brand it is running for.

Regression: the job passes --domain stickgolf.co.za for Stick, but
fetch_ubersuggest picks its output file names from STRATEGY_BRAND. The job
never set it, so Stick's pull overwrote Swing Shack's unsuffixed
seo-rankings.json and ubersuggest-*.json every day.
"""

import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from _lib.jobs.layer1 import seo_rankings  # noqa: E402


@pytest.fixture
def fake_fetch(monkeypatch):
    """Stub out the token check and the fetch script; record STRATEGY_BRAND."""
    seen = {}

    def _main():
        seen["strategy_brand"] = os.environ.get("STRATEGY_BRAND")
        seen["argv"] = list(sys.argv)
        return 0

    fake = types.SimpleNamespace(main=_main)
    monkeypatch.setattr(seo_rankings, "_token_present", lambda: True)
    monkeypatch.setattr(seo_rankings, "_load_ubersuggest_module", lambda: fake)
    monkeypatch.setattr(seo_rankings, "_count_keywords", lambda: 0)
    monkeypatch.setattr(
        seo_rankings,
        "resolve_brand_domain",
        lambda brand: (
            ("stickgolf.co.za", None) if brand == "stick" else ("swingshack.co.za", None)
        ),
    )
    monkeypatch.setattr(seo_rankings, "io_for_job", lambda *a, **k: None)
    monkeypatch.delenv("STRATEGY_BRAND", raising=False)
    return seen


def test_stick_run_sets_stick_brand(fake_fetch):
    seo_rankings.run(brand="stick")
    assert fake_fetch["strategy_brand"] == "stick"
    assert fake_fetch["argv"][1:] == ["--domain", "stickgolf.co.za"]


def test_swing_shack_run_sets_swing_shack_brand(fake_fetch):
    seo_rankings.run(brand="swing-shack")
    assert fake_fetch["strategy_brand"] == "swing-shack"


def test_env_is_restored_after_run(fake_fetch):
    os.environ["STRATEGY_BRAND"] = "something-else"
    try:
        seo_rankings.run(brand="stick")
        assert os.environ["STRATEGY_BRAND"] == "something-else"
    finally:
        os.environ.pop("STRATEGY_BRAND", None)
