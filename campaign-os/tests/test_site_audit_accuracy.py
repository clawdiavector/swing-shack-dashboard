"""The daily site check must not report problems that are not there.

Found 2026-10-28 on the live sites: Stick's pages have an H1 (Elementor wraps its text in
spans) but the check said "No H1 found"; Stick has 18 to 42 internal links per page but the
check said 0 because the link count only looked for "swingshack"; pages are 130 to 217 KB and
the check read only the first 80 KB; Swing Shack has no /coaching page (404).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from _lib.jobs.layer1 import site_audit as sa  # noqa: E402


def _types(findings):
    return {f["type"] for f in findings}


def test_an_h1_with_nested_tags_counts_as_an_h1():
    html = '<title>A title that is long enough to pass the check</title><h1 class="x"><span>Custom</span> <span>Fitting at Stick</span></h1>'
    assert "missing_h1" not in _types(sa._audit_seo_page(html))


def test_an_empty_h1_is_still_missing():
    html = "<title>A title that is long enough to pass the check</title><h1><span> </span></h1>"
    assert "missing_h1" in _types(sa._audit_seo_page(html))


def test_two_real_h1s_are_still_flagged():
    html = "<title>A title that is long enough to pass the check</title><h1><b>One</b></h1><h1>Two</h1>"
    assert "multiple_h1" in _types(sa._audit_seo_page(html))


def test_internal_links_count_on_the_pages_own_site_not_swing_shack_only():
    html = (
        '<a href="https://stickgolf.co.za/bookings/">b</a>'
        '<a href="https://stickgolf.co.za/takomo-at-stick/">t</a>'
        '<a href="/coaching-at-stick/">c</a>'
        '<a href="https://instagram.com/stick">i</a>'
    )
    findings = sa._audit_seo_page(html, "https://stickgolf.co.za/")
    assert "weak_internal_linking" not in _types(findings)


def test_few_internal_links_are_still_flagged():
    findings = sa._audit_seo_page('<a href="https://instagram.com/x">i</a>', "https://stickgolf.co.za/")
    assert "weak_internal_linking" in _types(findings)


def test_swing_shack_links_still_count_for_swing_shack():
    html = "".join(f'<a href="https://swingshack.co.za/p{i}/">x</a>' for i in range(3))
    findings = sa._audit_seo_page(html, "https://swingshack.co.za/membership")
    assert "weak_internal_linking" not in _types(findings)


def test_the_check_reads_whole_pages_of_the_size_the_sites_serve():
    assert sa.MAX_BYTES >= 300_000


def test_swing_shack_is_not_checked_for_a_page_it_does_not_have():
    assert "/coaching" not in [p["url_suffix"] for p in sa.pages_for("swing-shack")]
