"""SEO insights must refuse data that belongs to another brand.

Regression: the Swing Shack SEO page showed stickgolf.co.za keywords
("takomo irons south africa") because Stick's Ubersuggest files landed in
the unsuffixed files the page reads.
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from _lib import seo_insights  # noqa: E402


def _write(dir_, name, doc):
    with open(os.path.join(dir_, name), "w", encoding="utf-8") as f:
        json.dump(doc, f)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(seo_insights, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_swing_shack_data_builds(data_dir):
    _write(data_dir, "seo-rankings.json", {"domain": "swingshack.co.za", "keywords": []})
    _write(data_dir, "ubersuggest-domain.json", {"domain": "swingshack.co.za", "domainAuthority": 5})
    out = seo_insights.build_full_insights()
    assert out["domain"] == "swingshack.co.za"


def test_stick_domain_file_is_refused(data_dir):
    _write(data_dir, "seo-rankings.json", {"keywords": []})
    _write(data_dir, "ubersuggest-domain.json", {"domain": "stickgolf.co.za:organic:en:2840", "domainAuthority": 2})
    with pytest.raises(ValueError, match="stickgolf.co.za"):
        seo_insights.build_full_insights()


def test_stick_metadata_in_rankings_is_refused(data_dir):
    _write(data_dir, "seo-rankings.json", {"metadata": {"domain": "stickgolf.co.za"}, "keywords": []})
    _write(data_dir, "ubersuggest-domain.json", {"domain": "swingshack.co.za"})
    with pytest.raises(ValueError, match="stickgolf.co.za"):
        seo_insights.build_full_insights()


def test_www_prefix_is_still_swing_shack(data_dir):
    _write(data_dir, "seo-rankings.json", {"domain": "www.swingshack.co.za", "keywords": []})
    _write(data_dir, "ubersuggest-domain.json", {"domain": "www.swingshack.co.za"})
    assert seo_insights.build_full_insights()["domain"] == "www.swingshack.co.za"
