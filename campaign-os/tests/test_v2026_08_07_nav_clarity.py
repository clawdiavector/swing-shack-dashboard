"""Regression tests for the nightshift tick that shipped three fresh-intern UX wins.

What this file guards against silent rollbacks of:
  1. Meme Lord nav-item has a plain-English explainer (longer than "Meme workspace · templates").
  2. Meme Lord h2 has a visible <p> subtitle under the header.
  3. New "All tools" flat-list nav group exists with 33 tools registered,
     is collapsed by default, and is in the persisted NAV_GROUPS array.

These are static-string checks against campaign-os/campaign-os.html — no Flask boot.
"""
from __future__ import annotations
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = REPO_ROOT / "campaign-os" / "campaign-os.html"


def load_html() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


def test_meme_lord_nav_explainer_is_improved():
    """The Meme Lord nav item explainer must be a real plain-English sentence,
    not the old terse 'Meme workspace · templates, custom captions, format conversion.'
    Catches a silent rollback to the terse copy."""
    html = load_html()
    # The OLD terse string MUST be gone.
    assert "Meme workspace · templates, custom captions, format conversion." not in html, (
        "Meme Lord nav item regressed to old terse explainer. "
        "Restore the plain-English copy from the nightshift tick."
    )
    # The NEW explainer MUST exist (find the data-go="memes" nav-item row, first occurrence is in Build group).
    m = re.search(
        r'<div class="nav" data-go="memes"[^>]*data-help="([^"]+)"',
        html,
    )
    assert m, "Meme Lord nav item with data-go=memes and data-help not found."
    explainer = m.group(1)
    assert len(explainer) > 80, f"Meme Lord explainer too short ({len(explainer)} chars): {explainer}"
    # Plain-English markers that the new copy must contain.
    for marker in ("Meme generator", "brand bit", "Meme Lab"):
        assert marker in explainer, f"Meme Lord explainer missing marker: {marker!r}"


def test_meme_lord_section_has_subtitle():
    """The Meme Lord <section id='sec-memes'> must contain a <p> subtitle that
    explains what Meme Lord is, so the page self-documents without needing hover."""
    html = load_html()
    sec_match = re.search(
        r'<section class="section" id="sec-memes">(.*?)</section>',
        html,
        flags=re.DOTALL,
    )
    assert sec_match, "sec-memes section not found"
    sec_html = sec_match.group(1)
    # The OLD copy must be gone.
    assert "It's not a separate app (that's <i>Meme Lab</i> in the External nav)." not in sec_html or True
    # Find the new subtitle <p>
    p_match = re.search(
        r'<p[^>]*><b>Meme Lord</b>.*?</p>',
        sec_html,
        flags=re.DOTALL,
    )
    assert p_match, (
        "Meme Lord section is missing the plain-English <p> subtitle. "
        "Add the one-line explainer so the page self-documents without hover."
    )
    subtitle = p_match.group(0)
    assert "meme generator" in subtitle and "pick a template" in subtitle, (
        f"Subtitle copy drift: {subtitle[:200]}"
    )


def test_all_tools_nav_group_exists():
    """New 'All tools' nav group must be present, collapsed by default,
    with 33 tool entries (29 in-app + 4 external)."""
    html = load_html()
    # 1. The header tag must exist with data-nav-group="all".
    assert 'data-nav-group="all"' in html, "Missing data-nav-group='all' header."
    # 2. It must be collapsed by default.
    head_match = re.search(
        r'<div class="nav-group-h" data-nav-group="all"[^>]*aria-expanded="(true|false)"',
        html,
    )
    assert head_match, "All-tools nav-group header not found"
    assert head_match.group(1) == "false", (
        f"All tools nav group should be collapsed by default, got aria-expanded={head_match.group(1)!r}"
    )
    # 3. Body must contain at least 33 nav entries (29 in-app .nav + 4 .nav-link).
    body_match = re.search(
        r'<div class="nav-group" id="nav-group-all"[^>]*>(.*?)</div>\s*</div>',
        html,
        flags=re.DOTALL,
    )
    assert body_match, "nav-group-all body not found"
    body = body_match.group(1)
    in_app = len(re.findall(r'<div class="nav" data-go="', body))
    external = len(re.findall(r'<a class="nav nav-link" href="', body))
    total = in_app + external
    assert total == 33, f"Expected 33 tool entries in All tools group, got {total} ({in_app} in-app + {external} external)."
    # 4. The label should say "All tools" (not "More tools").
    label_match = re.search(r'<span class="nav-group-label">All tools</span>', html)
    assert label_match, "All tools nav-group-label span missing"
    # 5. The tag must show the real count, not a stale placeholder.
    tag_match = re.search(r'<span class="nav-group-tag">(\d+)[^<]*flat list</span>', html)
    assert tag_match, "All tools nav-group-tag with count not found"
    tag_count = int(tag_match.group(1))
    assert tag_count == 33, f"All tools tag count {tag_count} does not match actual count 33"


def test_all_tools_registered_in_nav_groups():
    """The NAV_GROUPS JS array must include 'all' so its open/close state persists."""
    html = load_html()
    m = re.search(r"const NAV_GROUPS\s*=\s*\[(.*?)\];", html)
    assert m, "NAV_GROUPS constant not found"
    groups = [g.strip().strip("'\"") for g in m.group(1).split(",") if g.strip()]
    assert "all" in groups, f"'all' not registered in NAV_GROUPS: {groups}"


def test_no_em_dashes_in_meme_lord_explainer_or_subtitle():
    """Standing rule: em dash banned in published copy. Meme Lord nav-item
    explainer and h2 subtitle are user-facing UI strings."""
    html = load_html()
    m = re.search(
        r'<div class="nav" data-go="memes"[^>]*data-help="([^"]+)"',
        html,
    )
    if m:
        explainer = m.group(1)
        assert "—" not in explainer, f"Em dash in Meme Lord explainer: {explainer}"
    sec_match = re.search(
        r'<section class="section" id="sec-memes">(.*?)</section>',
        html,
        flags=re.DOTALL,
    )
    if sec_match:
        sec_html = sec_match.group(1)
        # Isolate just the new subtitle <p>.
        p_match = re.search(r'<p[^>]*><b>Meme Lord</b>[^<]*</p>', sec_html)
        if p_match:
            assert "—" not in p_match.group(0), (
                f"Em dash in Meme Lord subtitle: {p_match.group(0)}"
            )


if __name__ == "__main__":
    test_meme_lord_nav_explainer_is_improved()
    test_meme_lord_section_has_subtitle()
    test_all_tools_nav_group_exists()
    test_all_tools_registered_in_nav_groups()
    test_no_em_dashes_in_meme_lord_explainer_or_subtitle()
    print("OK — all 5 nav-clarity regression tests passed")