"""
Regression test for the Image Lab Brand Recipe subtitle append bug.

On 2026-08-13 we observed the recipe subtitle read:
  "swing-shack: primary deep teal; 5 archetype(s); 0 top ref(s); bible=placeholder - bible PLACEHOLDER"

The trailing " - bible PLACEHOLDER" was appended via `$('recipe-subtitle').textContent +=`
inside renderRecipePanel(), and could double up across re-renders
(e.g. brand switch or after image generation when the server returns a brand_recipe).

Fix: set the subtitle in ONE assignment that includes the badge string, not as
a follow-up append. This test asserts the source no longer contains `+=` for
the bible badge, and that the badge string is part of the initial assignment.
"""

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMAGE_LAB = REPO / "campaign-os" / "image-lab.html"

# Old buggy pattern: textContent += '... bible PLACEHOLDER ...'
BUGGY_APPEND = re.compile(
    r"recipe-subtitle[^)]*\)\.textContent\s*\+=\s*['\"][^'\"]*bible[^'\"]*PLACEHOLDER[^'\"]*['\"]",
    re.DOTALL,
)


class RecipeSubtitleBadgeTests(unittest.TestCase):
    """The recipe-subtitle must not append 'bible PLACEHOLDER' on every render."""

    @classmethod
    def setUpClass(cls):
        cls.html = IMAGE_LAB.read_text(encoding="utf-8")

    def test_no_append_for_bible_badge(self):
        match = BUGGY_APPEND.search(self.html)
        self.assertIsNone(
            match,
            "recipe-subtitle still uses `+=` to append bible status — this "
            "doubles the badge on every renderRecipePanel() call. "
            f"Found: {match.group(0) if match else None!r}",
        )

    def test_bible_badge_set_in_one_assignment(self):
        # The fix rolls the badge into the initial textContent assignment.
        # Use re.DOTALL so .* can span newlines if the assignment wraps.
        self.assertRegex(
            self.html,
            r"recipe-subtitle['\"]\)\.textContent\s*=.*bibleBadge",
            "expected the bible badge to be merged into the single "
            "textContent assignment via a `bibleBadge` const.",
        )

    def test_no_standalone_bible_placeholder_append_remaining(self):
        # Belt and suspenders: even an `+= ' - bible active'` line must be gone.
        any_append = re.search(
            r"recipe-subtitle[^)]*\)\.textContent\s*\+=",
            self.html,
        )
        self.assertIsNone(
            any_append,
            "recipe-subtitle still has any `+=` append — bug not fully fixed.",
        )


if __name__ == "__main__":
    unittest.main()
