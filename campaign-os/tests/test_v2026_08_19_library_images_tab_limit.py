"""Regression test for the Library > Images tab fix (2026-08-19 nightshift).

Bug: the "images" tab called
  /api/visual-library/<brand>/images?limit=60
which returns ~5.5 MB of inline base64 thumbnails (60 × ~27 KB data URIs).
The pane painted "Loading…" for ~7 seconds while the JSON parsed + 60 large
data URIs were stringified into the DOM, then either rendered silently or
got timed out by the test harness. From the user's POV the tab looked broken.

Fix: cap at limit=16 (same as the "generated" tab preview that already paints
in ~2s). The "Open Visual Library →" link below the pane still ladders to the
full 60-image grid for users who want everything.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HTML = REPO / 'campaign-os' / 'campaign-os.html'


class TestLibraryImagesTabLimitFix(unittest.TestCase):
    """The Images tab must cap the visual-library fetch so the pane
    paints in ~2 seconds, not 7+. The cap lives in loadLibPane's
    `else if (kind === 'images')` branch."""

    def setUp(self):
        self.html = HTML.read_text()

    def _find_images_branch(self):
        """Return the source of the `else if (kind === 'images')` branch
        in loadLibPane."""
        # Match the branch opener + everything up to the closing `}` at the
        # same brace depth. The branch is small (~25 lines) so a lazy
        # match through the next 'pane.innerHTML' line is safe enough.
        m = re.search(
            r"\} else if\(kind === 'images'\)\{(.*?)\n\s+\}\n\s+\} catch",
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "Could not find the `else if (kind === 'images')` branch in loadLibPane",
        )
        return m.group(1) if m else ""

    def test_uses_limit_16_not_limit_60(self):
        """The pre-fix limit was 60; the post-fix cap is 16. Pin it."""
        branch = self._find_images_branch()
        self.assertIn(
            "limit=16", branch,
            "Images tab must fetch with limit=16 (was limit=60, ~5.5 MB response)",
        )
        self.assertNotIn(
            "limit=60", branch,
            "Pre-fix limit=60 still present — fetches 5.5 MB and stalls the pane",
        )

    def test_branch_carries_explanatory_comment(self):
        """The fix comment explains WHY we capped at 16. If a future
        contributor deletes it the test should still pin the cap, but the
        comment is the cheap next-edit-pointer."""
        branch = self._find_images_branch()
        # The comment must mention the size or the symptom.
        self.assertTrue(
            "5.5 MB" in branch or "5.5MB" in branch or "~7 seconds" in branch,
            "Fix comment must call out the response-size symptom so the next "
            "editor knows why the cap exists",
        )

    def test_pane_uses_thumbnails_label(self):
        """The row label must read '16 thumbnails …' so the user can tell
        they're seeing a preview, not the whole catalog."""
        branch = self._find_images_branch()
        self.assertIn(
            "thumbnails", branch,
            "Pane row label must use the plural noun 'thumbnails' to signal "
            "this is a preview, not a full catalog",
        )

    def test_visual_library_link_still_present(self):
        """The 'Open Visual Library →' link is the ladder to the full
        60-image grid. It must still be in the images branch."""
        branch = self._find_images_branch()
        self.assertIn(
            "Open Visual Library", branch,
            "Images tab must keep the 'Open Visual Library →' link so "
            "users can still reach the full grid",
        )

    def test_no_em_dash_in_new_copy(self):
        """Standing rule: published copy uses pipes, commas, colons. No em-dash."""
        branch = self._find_images_branch()
        # Strip the explanatory comment (which lives inside /* ... */) before
        # scanning for em-dashes in actual user-facing copy.
        no_comment = re.sub(r"/\*.*?\*/", "", branch, flags=re.DOTALL)
        self.assertNotIn(
            "—", no_comment,
            "Em-dash found in Images-tab user-facing copy (standing rule: "
            "use pipes/commas/colons)",
        )


if __name__ == "__main__":
    unittest.main()