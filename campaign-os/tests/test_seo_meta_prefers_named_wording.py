"""The automatic description should name the brand or page when the page's own words allow it.

Found on the first live dry run (2026-10-21): the safe sentence picked for
Membership never said "Swing Shack" or "membership". Fake WordPress only.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _lib import seo_meta_publish as p  # noqa: E402
from test_seo_meta_publish import MemIO, FakeWP, NOW, item, queue  # noqa: E402

GENERIC = "A place where you can practise after work, tweak your gear, learn from coaches, and actually see progress on the numbers."
NAMED = (
    "Swing Shack isn't just indoor golf. It's a proper indoor golf club. "
    "If you're serious about improving, this is where you plug in."
)
PAGE = f"<p>{GENERIC}</p><p>{NAMED}</p>"


def test_without_a_preference_the_first_safe_candidate_still_wins():
    assert p.propose(PAGE) == GENERIC


def test_a_candidate_naming_the_brand_wins_when_preferred():
    assert p.propose(PAGE, prefer=("swing shack", "Membership")) == NAMED


def test_the_page_name_counts_too():
    html = f"<p>{GENERIC}</p><p>Membership gives you a bay between lessons, so what you learn has somewhere to go every week, and you can see it in the numbers.</p>"
    assert p.propose(html, prefer=("swing shack", "Membership")).startswith("Membership gives you")


def test_falls_back_to_the_first_safe_candidate_when_none_name_anything():
    assert p.propose(f"<p>{GENERIC}</p>", prefer=("swing shack", "Membership")) == GENERIC


def test_preference_never_overrides_the_safety_rules():
    unsafe = "Swing Shack is the best indoor golf club in Johannesburg and we guarantee you will improve your game quickly."
    assert p.propose(f"<p>{GENERIC}</p><p>{unsafe}</p>", prefer=("swing shack",)) == GENERIC
    assert p.propose(f"<p>{unsafe}</p>", prefer=("swing shack",)) is None


def test_the_run_prefers_the_named_wording_and_records_it():
    wp = FakeWP([{"id": 2255, "slug": "membership", "html": PAGE}])
    io = MemIO()
    out = p.run_auto(io, "swing-shack", queue(item()), wp, NOW, run_mode="dry-run")
    assert out["dry_run"] == 1
    assert io.files[p.LOG_FILE]["entries"][0]["after"] == NAMED
    assert wp.writes() == []
