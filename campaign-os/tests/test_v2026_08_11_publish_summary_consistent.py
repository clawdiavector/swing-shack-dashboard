"""Regression test for the Publish / Publishing-pipeline summary mismatch.

The Publish page header (`#publish-summary`) used to report raw totals from the
backend (57 in queue, 57 published) while the cards underneath only rendered the
first 30 queue + 20 published — so the header lied to the user. The fix moved
the summary construction to mirror the same slice logic and added a
"(N total)" suffix when the visible slice is shorter than the corpus.

This test pins both:
  1. The shape of `postiz_overview()` so the new fields stay wired
  2. The invariant: summary numbers MUST equal the rendered card counts

The card-side counts (campaign-os.html:7521-7523) are also wired into the
test's expected slice sizes to catch any future drift.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib import intelligence  # noqa: E402  path-injected import


CARD_SLICE_QUEUE = 30
CARD_SLICE_SCHED = 30
CARD_SLICE_PUB = 20


def _summary_numbers(s: str):
    """Parse 'Queue: 30 (57 total). Scheduled: 0. Published: 20.' → dict."""
    out = {}
    for key in ("Queue", "Scheduled", "Published", "Publishing refs"):
        m = re.search(rf"{key}:\s*([\d,]+)(?:\s*\(([\d,]+)\s*total\))?", s)
        if not m:
            out[key] = None
            continue
        out[key] = {
            "visible": int(m.group(1).replace(",", "")),
            "total": int((m.group(2) or m.group(1)).replace(",", "")),
        }
    return out


def test_01_postiz_overview_returns_expected_shape():
    out = intelligence.postiz_overview()
    assert out.get("ok") is True, "postiz_overview should return ok=True"
    assert "summary" in out and isinstance(out["summary"], str)
    for key in ("queue", "scheduled", "published", "publishing_refs",
                "queue_total", "scheduled_total", "published_total", "ts", "note"):
        assert key in out, f"postiz_overview missing required key: {key}"
    # queue/published/scheduled should all be lists (sliced)
    for key in ("queue", "scheduled", "published"):
        assert isinstance(out[key], list), f"{key} should be a list"


def test_02_summary_visible_matches_rendered_slice():
    """The summary visible count must match len(queue/published/scheduled)."""
    out = intelligence.postiz_overview()
    parsed = _summary_numbers(out["summary"])
    assert parsed["Queue"]["visible"] == len(out["queue"]), (
        f"Queue visible mismatch: summary={parsed['Queue']['visible']} "
        f"len(queue)={len(out['queue'])}"
    )
    assert parsed["Scheduled"]["visible"] == len(out["scheduled"]), (
        f"Scheduled visible mismatch: summary={parsed['Scheduled']['visible']} "
        f"len(scheduled)={len(out['scheduled'])}"
    )
    assert parsed["Published"]["visible"] == len(out["published"]), (
        f"Published visible mismatch: summary={parsed['Published']['visible']} "
        f"len(published)={len(out['published'])}"
    )


def test_03_summary_total_never_under_reports():
    """If there is more data than visible, total >= visible. Otherwise equal."""
    out = intelligence.postiz_overview()
    parsed = _summary_numbers(out["summary"])
    for key in ("Queue", "Scheduled", "Published"):
        vis, tot = parsed[key]["visible"], parsed[key]["total"]
        assert tot >= vis, f"{key}: total ({tot}) should be >= visible ({vis})"


def test_04_queue_slice_capped_at_30():
    """queue returned to client is capped at 30 (matches card-side slice)."""
    out = intelligence.postiz_overview()
    assert len(out["queue"]) <= CARD_SLICE_QUEUE, (
        f"queue length {len(out['queue'])} exceeds card slice {CARD_SLICE_QUEUE}"
    )


def test_05_published_slice_capped_at_20():
    out = intelligence.postiz_overview()
    assert len(out["published"]) <= CARD_SLICE_PUB, (
        f"published length {len(out['published'])} exceeds card slice {CARD_SLICE_PUB}"
    )


def test_06_total_fields_are_numeric():
    out = intelligence.postiz_overview()
    for key in ("queue_total", "scheduled_total", "published_total"):
        assert isinstance(out[key], int), f"{key} should be int, got {type(out[key])}"
        assert out[key] >= 0, f"{key} should be non-negative"


def test_07_summary_uses_card_slice_logic_when_oversized():
    """If the corpus is larger than the visible slice, summary uses 'N (M total)'."""
    out = intelligence.postiz_overview()
    parsed = _summary_numbers(out["summary"])
    # Only assert on Queue (most likely to be oversized given the data shape):
    # when queue_total > 30, summary MUST include "(N total)".
    if out["queue_total"] > CARD_SLICE_QUEUE:
        assert parsed["Queue"]["total"] > parsed["Queue"]["visible"], (
            "queue_total > slice but summary did not surface a larger total"
        )


if __name__ == "__main__":
    failures = 0
    for fn in list(globals().values()):
        if callable(fn) and fn.__name__.startswith("test_"):
            try:
                fn()
                print(f"  ✓ {fn.__name__}")
            except AssertionError as e:
                failures += 1
                print(f"  ✗ {fn.__name__}: {e}")
    print(f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} failure(s)")
    sys.exit(0 if failures == 0 else 1)
