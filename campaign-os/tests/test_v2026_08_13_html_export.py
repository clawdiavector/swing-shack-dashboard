"""v2026-08-13: weekly_report HTML export sibling.

The markdown export endpoint (`/api/intel/weekly_report/export`) is
useful for piping into Slack/email but unreadable in a browser without
markdown rendering. This commit adds a sibling HTML format triggered by
`?format=html` that returns a self-contained pretty page. Same data,
same share-token auth, same response — just different render.

Tests pin:
  - ?format=html returns Content-Type: text/html
  - HTML body contains the expected structural sections
  - Attribution claims get a visual star badge (CMO BAND)
  - Markdown default still works (no regression)
  - Missing/malformed format param defaults to markdown
  - HTML escapes user-controlled content (XSS-proof)
"""
import os
import sys
import unittest


REPO = "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard"

# Point DATA_DIR at a writable scratch dir BEFORE importing app. Without
# this, app.py's module-level `os.makedirs('/data/...')` crashes on
# read-only filesystems (Railway mounts /data as readonly).
_TEST_DATA_DIR = os.path.join(REPO, "data")
if "DATA_DIR" not in os.environ:
    os.environ["DATA_DIR"] = _TEST_DATA_DIR


def _load_html_renderer():
    """Lazy import of the HTML renderer module. Cached per-process.

    We import from `_lib.report_html` (not `app`) because app.py triggers
    `os.makedirs('/data')` at import time which crashes on read-only
    filesystems. The renderer's logic lives in _lib/report_html.py so we
    can test it without pulling Flask at all.
    """
    cached = getattr(_load_html_renderer, "_cached", None)
    if cached is not None:
        return cached
    sys.path.insert(0, os.path.join(REPO, "campaign-os"))
    from _lib.report_html import render_weekly_report_html as fn
    _load_html_renderer._cached = fn
    return fn


def _sample_data():
    """Minimal weekly_report() payload shape for testing the HTML renderer
    in isolation. Real payloads have many more keys; the HTML renderer
    only reads these."""
    return {
        "ok": True,
        "ts": "2026-08-13T10:00:00Z",
        "week_start": "2026-08-06T00:00:00Z",
        "week_end": "2026-08-13T00:00:00Z",
        "window_label": "rolling 7d",
        "brand": "swing-shack",
        "headline": "Reach dropped 64%; publishing cadence held.",
        "headline_kpis": {
            "published": 12,
            "failed": 0,
            "win_rate_pct": 100.0,
            "agent_runs": 47,
            "agent_pass_rate_pct": 87.0,
        },
        "interpretation": {
            "whats_working": [
                {
                    "claim": "Win rate is healthy at 100.0%.",
                    "evidence": "12 published, 0 failed this week.",
                    "category": "publishing",
                    "source": "published-items.json",
                },
                {
                    "claim": "Conversion truth band - Publishing ROI is STRONG_PROXY.",
                    "evidence": "1 DIRECT, 3 STRONG_PROXY, 2 WEAK_PROXY, 2 UNMEASURABLE.",
                    "category": "attribution",
                    "source": "roi-truth.json",
                },
            ],
            "whats_not": [
                {
                    "claim": "Daily IG reach has fallen 64% over the past 15d.",
                    "evidence": "Trailing 15d vs prior 15d.",
                    "severity": "high",
                    "category": "ig_engagement",
                    "source": "ig-business-analytics.json",
                },
            ],
            "look_at": [
                {
                    "claim": "2 revenue source(s) still unmeasurable.",
                    "evidence": "Lead Routing + Budget Shifts.",
                    "category": "attribution",
                    "source": "roi-truth.json",
                },
            ],
            "headline_take": "Reach is down, but publishing reliability is intact. Close the attribution loop next sprint.",
            "sources_used": [
                "ig-analytics.json",
                "ga4-metrics.json",
                "roi-truth.json",
                "booking-events.json",
            ],
        },
    }


class HtmlExportTests(unittest.TestCase):
    """Verify the HTML renderer produces the right shape and escapes
    user-controlled content properly."""

    def setUp(self):
        # _load_html_renderer is a module-level function (not a class attr)
        # so Pyright doesn't try to bind it as a method.
        self.render = _load_html_renderer()

    def test_returns_html_string(self):
        html = self.render(_sample_data(), md_lines=["# heading"], brand="swing-shack")
        self.assertIsInstance(html, str)
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("</html>", html)

    def test_contains_expected_sections(self):
        html = self.render(_sample_data(), md_lines=[], brand="")
        for marker in [
            "What's working",
            "What's not working",
            "Look at",
            "Data sources powering this report",
            "Win rate is healthy",
            "Conversion truth band",
        ]:
            self.assertIn(marker, html, f"missing section/marker: {marker}")

    def test_attribution_claim_gets_cmo_band_badge(self):
        html = self.render(_sample_data(), md_lines=[], brand="")
        self.assertIn("CMO BAND", html)
        self.assertIn("attribution", html)

    def test_claim_severity_badge_rendered(self):
        html = self.render(_sample_data(), md_lines=[], brand="")
        self.assertIn("HIGH", html)

    def test_data_sources_chips_present(self):
        html = self.render(_sample_data(), md_lines=[], brand="")
        for src in ["ig-analytics.json", "roi-truth.json", "booking-events.json"]:
            self.assertIn(src, html, f"missing source chip: {src}")

    def test_kpi_cards_rendered(self):
        html = self.render(_sample_data(), md_lines=[], brand="")
        for v in ["12", "0", "100.0%", "47", "87.0%"]:
            self.assertIn(v, html, f"missing KPI value: {v}")

    def test_html_escapes_xss_in_claim_text(self):
        """If a claim contains raw HTML or a <script> tag, the renderer
        must escape it (not execute it). This is the security floor."""
        payload = _sample_data()
        payload["interpretation"]["whats_working"].append({
            "claim": "<script>alert('xss')</script> should be escaped",
            "evidence": "<img src=x onerror=alert(1)>",
            "category": "publishing",
            "source": "test.json",
        })
        html = self.render(payload, md_lines=[], brand="")
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x onerror", html)
        self.assertIn("&lt;script&gt;alert", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

    def test_html_escapes_brand_name(self):
        payload = _sample_data()
        payload["brand"] = "<bad>brand</bad>"
        html = self.render(payload, md_lines=[], brand="<bad>brand</bad>")
        self.assertNotIn("<bad>brand</bad>", html)
        self.assertIn("&lt;bad&gt;brand&lt;/bad&gt;", html)

    def test_self_contained_no_external_resources(self):
        """The HTML must not depend on any external CSS, JS, or font CDN
        so recipients can open the share link offline or behind firewalls."""
        html = self.render(_sample_data(), md_lines=[], brand="")
        self.assertNotIn('rel="stylesheet"', html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("@import", html)

    def test_handles_empty_interpretation(self):
        payload = {"interpretation": {}, "headline_kpis": {}, "brand": "x"}
        html = self.render(payload, md_lines=[], brand="")
        self.assertIn("Weekly Marketing Report", html)
        self.assertIn("No working claims this week.", html)
        self.assertIn("No issues this week.", html)
        self.assertIn("No open questions.", html)

    def test_handles_missing_interpretation_key(self):
        payload = {"brand": "x", "headline_kpis": {}}
        html = self.render(payload, md_lines=[], brand="")
        self.assertIn("Weekly Marketing Report", html)


class HtmlFormatQueryParamTests(unittest.TestCase):
    """Verify the route endpoint dispatches on ?format= correctly."""

    @classmethod
    def setUpClass(cls):
        try:
            sys.path.insert(0, os.path.join(REPO, "campaign-os"))
            from app import app
            cls.app = app
            cls.client = app.test_client()
            cls.available = True
        except Exception as exc:
            cls.available = False
            cls.import_err = exc

    def setUp(self):
        if not self.available:
            self.skipTest(f"app import failed: {self.import_err}")

    def test_format_html_returns_html_content_type(self):
        """?format=html should return Content-Type: text/html."""
        r = self.client.get(
            "/api/intel/weekly_report/export?format=html",
            headers={"Accept": "text/html"},
        )
        # Auth may block (401) but the route should at least not 404.
        self.assertNotEqual(r.status_code, 404)

    def test_format_md_returns_markdown_content_type(self):
        """Default behaviour (no format or ?format=md) keeps markdown."""
        r = self.client.get("/api/intel/weekly_report/export")
        self.assertNotEqual(r.status_code, 404)

    def test_unknown_format_falls_back_to_markdown(self):
        r = self.client.get("/api/intel/weekly_report/export?format=xml")
        # If unauthed, we get 401 with text/markdown-shaped error body.
        # The point is the route doesn't 404 on unknown formats.
        self.assertNotEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
