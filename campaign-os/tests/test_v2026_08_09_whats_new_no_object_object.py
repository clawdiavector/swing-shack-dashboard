"""
Regression test: Brief "What's new" titles must never render literal
"[object Object]" text on the live page.

History: WHATS_NEW was authored to *describe* the GBP-location bug by name
("GBP profile 'Location [object Object]' becomes city, region..."). The body
of the entry correctly explained the fix, but the title itself contained the
bug token verbatim. The Brief page rendered it as-is in the morning, so
Christelle opened Campaign OS and read "[object Object]" in production —
looking like a live regression instead of a fixed one.

This test parses WHATS_NEW out of campaign-os/app.py and asserts no entry
(title or body) contains the literal string "[object Object]".

Pure-static grep test (no live server), per the convention used by
test_v2026_08_09_ideas_empty_collapse.py.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP_PY = REPO / "campaign-os" / "app.py"
LEAK_PATTERN = re.compile(r"\[object\s+object\]", re.IGNORECASE)


def extract_whats_new_block(src: str) -> str:
    """Return the substring of src that holds the WHATS_NEW list literal."""
    start = src.find("WHATS_NEW = [")
    if start == -1:
        return ""
    # Find the matching close bracket by scanning from the start.
    depth = 0
    for i in range(start, len(src)):
        ch = src[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    return ""


class WhatsNewNoObjectObjectTests(unittest.TestCase):
    """The Brief What's-new card must never leak [object Object] text."""

    @classmethod
    def setUpClass(cls):
        cls.src = APP_PY.read_text(encoding="utf-8")

    def test_no_object_object_in_whats_new(self):
        block = extract_whats_new_block(self.src)
        self.assertTrue(block, "WHATS_NEW list not found in campaign-os/app.py")
        leaks = LEAK_PATTERN.findall(block)
        self.assertEqual(
            leaks,
            [],
            f"WHATS_NEW still contains {len(leaks)} [object Object] literal(s). "
            "A user opening the Morning Brief will see '[object Object]' in a "
            "title — looks like a live regression. Rewrite the title to describe "
            "the fix without quoting the buggy token.",
        )


if __name__ == "__main__":
    unittest.main()