"""Regression test: SEO Audit page renders a friendly skeleton on first paint,
not a dry "Loading…" string that makes the page look broken for 3+ seconds.

Background:
    The walker (sweep_walker.py) flagged the SEO Audit section with
    EMPTY=['Loading…'] in the 2026-08-12T10:46Z sweep, because the
    static HTML at campaign-os.html line 1824 was:
        <span class="sub" id="sa-summary">Loading…</span>

    The /api/intel/seo_audit_detail endpoint takes ~3s to land on the
    LIVE URL (timing captured in the 2026-08-12 investigation), so the
    user clicks SEO Audit and sees a "Loading…" wall plus 5 empty card
    bodies for the entire fetch window. The page looks broken even
    though the data is on the way.

    Pitfall 97 already established the cure for the Home page: replace
    dry "Loading…" text with a .skeleton shimmer (CSS class at line 525)
    + a short status string ("Picking today's highest-leverage action…",
    "Pulling live signals…"). The skeleton lives in static HTML so it
    paints with the first response and gets replaced wholesale when
    renderSeoAudit() calls $('#sa-summary').textContent = ...

    This test mirrors the pitfall-97 fix shape (sibling to test_v2026_08_10
    brief-skeleton tests) and pins:
      * Post-fix sa-summary string contains a .skeleton bar + "Auditing"
      * Post-fix sa-summary string is em-dash-free
      * Pre-fix "Loading…" string is gone
      * The sa-score card carries a .skeleton block on first paint (so
        the score card doesn't look blank during the 3s fetch)
      * renderSeoAudit() / refreshSeoAudit() still replaces both
        elements (regression guard: a future edit that adds a wrapper
        <span> around #sa-score and breaks innerHTML assignment will
        fail here)

Verified: see screenshots in /tmp/co-nightshift/walkthrough_seo_audit_*.png
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"


class TestSeoAuditLoadingSkeleton(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")

    def test_01_post_fix_sa_summary_has_skeleton(self):
        """The post-fix sa-summary carries a .skeleton bar + status string."""
        # Walk balanced <span>/</span> to capture the full body (the inner
        # .skeleton span closes first, so a naive (.*?) regex stops early).
        idx = self.html.find('<span class="sub" id="sa-summary">')
        self.assertGreater(idx, 0, "#sa-summary span missing")
        rest = self.html[idx:]
        depth = 0
        i = 0
        end = -1
        while i < len(rest):
            open_idx = rest.find("<span", i)
            close_idx = rest.find("</span>", i)
            if close_idx == -1:
                break
            if open_idx != -1 and open_idx < close_idx:
                depth += 1
                i = open_idx + 5
            else:
                depth -= 1
                i = close_idx + 7
                if depth == 0:
                    end = close_idx + 7
                    break
        self.assertGreater(end, 0, "Could not find balanced </span> for #sa-summary")
        body = rest[:end]
        self.assertIn(
            'class="skeleton"',
            body,
            "Post-fix sa-summary should carry a .skeleton bar (pitfall 97 pattern)",
        )
        self.assertIn(
            "Auditing site",
            body,
            "Post-fix sa-summary should carry a real status string ('Auditing site...')",
        )

    def test_02_post_fix_sa_summary_emdash_free(self):
        """The new string contains no em-dashes (standing rule)."""
        idx = self.html.find('<span class="sub" id="sa-summary">')
        self.assertGreater(idx, 0, "#sa-summary span missing")
        rest = self.html[idx:]
        depth = 0
        i = 0
        end = -1
        while i < len(rest):
            open_idx = rest.find("<span", i)
            close_idx = rest.find("</span>", i)
            if close_idx == -1:
                break
            if open_idx != -1 and open_idx < close_idx:
                depth += 1
                i = open_idx + 5
            else:
                depth -= 1
                i = close_idx + 7
                if depth == 0:
                    end = close_idx + 7
                    break
        self.assertGreater(end, 0, "Could not find balanced </span> for #sa-summary")
        body = rest[:end]
        self.assertNotIn(
            "\u2014",
            body,
            "Post-fix sa-summary contains an em-dash (standing rule violation)",
        )

    def test_03_pre_fix_loading_string_gone(self):
        """The bare 'Loading…' (and 'Loading...') placeholder is gone."""
        # Match the exact static markup: <span class="sub" id="sa-summary">Loading…</span>
        self.assertNotIn(
            '<span class="sub" id="sa-summary">Loading…</span>',
            self.html,
            "Pre-fix sa-summary 'Loading…' placeholder still present (visual stall)",
        )
        self.assertNotIn(
            '<span class="sub" id="sa-summary">Loading...</span>',
            self.html,
            "Pre-fix sa-summary 'Loading...' placeholder still present",
        )

    def test_04_sa_score_has_skeleton_on_first_paint(self):
        """The sa-score card has skeleton bars in static HTML so it doesn't
        render as a blank card during the 3s fetch. Greedy regex across
        newlines + balanced </div> closing so we capture the full block,
        not just the first skeleton."""
        # Find <div id="sa-score"> and walk forward until we see the matching </div>.
        idx = self.html.find('<div id="sa-score">')
        self.assertGreater(idx, 0, "#sa-score div missing from static HTML")
        # Slice from idx onward and count balanced <div>/</div>.
        rest = self.html[idx:]
        depth = 0
        i = 0
        end = -1
        while i < len(rest):
            open_idx = rest.find("<div", i)
            close_idx = rest.find("</div>", i)
            if close_idx == -1:
                break
            if open_idx != -1 and open_idx < close_idx:
                depth += 1
                i = open_idx + 4
            else:
                depth -= 1
                i = close_idx + 6
                if depth == 0:
                    end = close_idx + 6
                    break
        self.assertGreater(end, 0, "Could not find balanced closing </div> for #sa-score")
        body = rest[:end]
        self.assertIn(
            'class="skeleton"',
            body,
            "sa-score card has no skeleton — will render blank during fetch",
        )
        # At least 3 skeleton bars (matches the kvs structure that replaces it)
        self.assertGreaterEqual(
            body.count('class="skeleton"'),
            3,
            "sa-score card should have at least 3 skeleton bars to mirror the kvs layout",
        )

    def test_05_js_still_replaces_sa_summary_and_sa_score(self):
        """Regression guard: refreshSeoAudit() still calls innerHTML /
        textContent on #sa-summary and #sa-score, so the static skeleton
        gets cleared when the data lands. A future refactor that wraps
        the elements in extra containers will fail here."""
        # Must have at least one innerHTML / textContent assignment on
        # each of the two selectors.
        sa_summary_writes = re.findall(
            r"\$\(\s*['\"]#sa-summary['\"]\s*\)\.(?:text|innerText|innerHTML)",
            self.html,
        )
        self.assertGreaterEqual(
            len(sa_summary_writes), 1,
            "#sa-summary no longer has any JS write — skeleton would never be cleared",
        )
        sa_score_writes = re.findall(
            r"\$\(\s*['\"]#sa-score['\"]\s*\)\.(?:html|innerHTML)",
            self.html,
        )
        self.assertGreaterEqual(
            len(sa_score_writes), 1,
            "#sa-score no longer has any JS write — skeleton would never be cleared",
        )

    def test_06_no_new_emdashes_in_new_strings(self):
        """The new copy ('Auditing site…') uses the horizontal ellipsis …, NOT an em-dash."""
        self.assertIn(
            "Auditing site\u2026",
            self.html,
            "New status string 'Auditing site…' missing — it's the user-visible copy",
        )
        # The ellipsis … (U+2026) is allowed; em-dash — (U+2014) is banned.
        # Locate the new string and assert no em-dash co-occurs within 50 chars.
        idx = self.html.find("Auditing site\u2026")
        self.assertGreater(idx, 0)
        window = self.html[max(0, idx - 50): idx + 50]
        self.assertNotIn(
            "\u2014",
            window,
            "em-dash appears within 50 chars of the new status string",
        )


if __name__ == "__main__":
    unittest.main()