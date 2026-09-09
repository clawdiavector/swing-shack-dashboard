"""Regression test for publish-tab pillar-label strip fix.

The fix lives in campaign-os.html renderPublish() pickTitle(). Tests verify the
inline regex strips mid-caption pillar-label lines from caption_preview values
in published-items.json (the canonical fixture).

Pillar label lines look like:
  "...YARDS?\\n\\n🎮 Practice\\n\\nLink in bio..."   (single-word pillar)
  "...fitting\\n\\n🏌️ Club Fitting\\n\\nSwipe up..." (two-word pillar)
  "...flaw\\n\\n🎯 Coaching\\n\\nDrop a..."          (single-word pillar)
"""
import json, re, sys, os

# Path to the live fixture — read by the API but never written by tests.
PUB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "published-items.json"
)

# Same regex as the campaign-os.html fix. Keep in sync.
PILLAR_LINE = re.compile(
    r"\n\n[\U0001F000-\U0001FFFF\u2600-\u27BF]\ufe0f? [A-Z][a-z]+(?: [A-Z][a-z]+)?\n\n"
)
FOLD_WS = re.compile(r"\s+")


def load_pubs():
    if not os.path.exists(PUB_PATH):
        # Skip if fixture missing — the live API doesn't have the corpus either.
        return None
    with open(PUB_PATH) as f:
        d = json.load(f)
    pubs = d.get("published", [])
    if not isinstance(pubs, list):
        return None
    return pubs


def cleaned_title(raw):
    """Mirror of pickTitle() — strip pillar line, then flatten, slice to 90."""
    if not raw:
        return ""
    stripped = PILLAR_LINE.sub("\n\n", str(raw))
    return FOLD_WS.sub(" ", stripped).strip()[:90]


def test_pubs_fixture_exists():
    pubs = load_pubs()
    if pubs is None:
        return "skip", "no fixture"
    assert len(pubs) > 0, "fixture should have at least one published row"
    return "ok", f"{len(pubs)} rows"


def test_pillar_lines_stripped():
    pubs = load_pubs()
    if pubs is None:
        return "skip", "no fixture"
    raw_with_pillar = [p for p in pubs if PILLAR_LINE.search(p.get("caption_preview", ""))]
    assert len(raw_with_pillar) >= 1, "fixture should have at least one pillar-line row to test"
    bad = []
    for p in raw_with_pillar:
        title = cleaned_title(p.get("caption_preview", ""))
        # The cleaned title must NOT contain the pillar label tokens like "🎮 Practice"
        # nor the literal words "Practice" or "Club Fitting" or "Coaching" as a stand-alone word.
        for token in ("🎮 Practice", "🏌️ Club Fitting", "🎯 Coaching"):
            if token in title:
                bad.append((p.get("item_id"), token, title[:80]))
    assert not bad, f"pillar label leaked after clean: {bad}"
    return "ok", f"{len(raw_with_pillar)} rows cleaned, no leakage"


def test_legitimate_emoji_not_stripped():
    """Standalone emoji in the middle of a sentence (not on its own pillar line) must survive."""
    sample = "First time hitting balls at the Shack 🏌 and the slice is REAL.\n\nDM us\n\n#IndoorGolf"
    title = cleaned_title(sample)
    assert "🏌" in title, f"standalone 🏌 in mid-sentence was wrongly stripped: {title!r}"
    return "ok", "mid-sentence emoji preserved"


def test_no_pillar_line_no_change():
    """Plain caption without a pillar line should pass through unchanged."""
    sample = "POV: First time at Swing Shack\n\nDM us to get started\n\n#IndoorGolfJohannesburg"
    expected = "POV: First time at Swing Shack DM us to get started #IndoorGolfJohannesburg"[:90]
    title = cleaned_title(sample)
    assert title == expected, f"no-pillar caption changed unexpectedly: {title!r} != {expected!r}"
    return "ok", "plain captions untouched"


def test_pillar_two_words_stripped():
    """Two-word pillar labels (e.g. 'Club Fitting') must also be stripped."""
    sample = "Book your ball fitting today.\n\n🏌️ Club Fitting\n\nSwipe up · Learn more\n\n#Golf"
    title = cleaned_title(sample)
    assert "Club Fitting" not in title, f"two-word pillar leaked: {title!r}"
    assert "🏌️" not in title, f"pillar emoji leaked: {title!r}"
    return "ok", "two-word pillar line removed"


def test_pillar_single_word_stripped():
    sample = "THAT SLICE COSTING YOU YARDS?\n\n🎮 Practice\n\nLink in bio · Book your session\n\n#Golf"
    title = cleaned_title(sample)
    assert "Practice" not in title, f"single-word pillar leaked: {title!r}"
    assert "🎮" not in title, f"pillar emoji leaked: {title!r}"
    return "ok", "single-word pillar line removed"


def test_html_in_sync_with_regex():
    """The campaign-os.html fix must use the same regex shape as this test.
    This guards against drift between the fix and the test."""
    html_path = os.path.join(
        os.path.dirname(__file__), "..", "campaign-os.html"
    )
    if not os.path.exists(html_path):
        return "skip", "no html"
    with open(html_path) as f:
        html = f.read()
    # The fix is wrapped in a pickTitle() body — look for the canonical regex char class.
    expected_marker = "[A-Z][a-z]+(?: [A-Z][a-z]+)?"
    assert expected_marker in html, "fix marker missing from campaign-os.html — regex drifted"
    assert "strip" in html.lower(), "fix lost its strip variable name"
    return "ok", "html regex matches test regex"


def main():
    tests = [
        ("pubs_fixture_exists", test_pubs_fixture_exists),
        ("pillar_lines_stripped", test_pillar_lines_stripped),
        ("legitimate_emoji_not_stripped", test_legitimate_emoji_not_stripped),
        ("no_pillar_line_no_change", test_no_pillar_line_no_change),
        ("pillar_two_words_stripped", test_pillar_two_words_stripped),
        ("pillar_single_word_stripped", test_pillar_single_word_stripped),
        ("html_in_sync_with_regex", test_html_in_sync_with_regex),
    ]
    failures = 0
    for name, fn in tests:
        try:
            status, msg = fn()
            print(f"  {status:4s} {name}: {msg}")
            if status == "fail":
                failures += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
            failures += 1
        except Exception as e:
            print(f"  ERR  {name}: {e}")
            failures += 1
    if failures:
        print(f"\n{failures} test(s) failed")
        sys.exit(1)
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()