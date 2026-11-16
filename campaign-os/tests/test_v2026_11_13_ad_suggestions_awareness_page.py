"""The page draws an awareness card (no subject) without failing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_v2026_11_13_ad_suggestions_types as ty  # noqa: E402
import test_v2026_11_13_ad_suggestions as t  # noqa: E402
from _lib import ads_suggest  # noqa: E402


def test_an_awareness_card_renders_with_its_audience_step():
    html = ads_suggest.render_html([t._build([ty.STAR_REEL] + ty.AVERAGE)])
    assert "Awareness ad" in html and "watched50" in html
