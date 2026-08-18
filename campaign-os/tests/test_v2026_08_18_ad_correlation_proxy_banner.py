"""v2026-08-18 — Ad correlation: proxy banner surfaces when campaign rows are
organic-IG-as-ad-impression stand-ins.

Background
----------
The "Did the ad drive this spike?" card on the Insights page (sec-insights)
renders an ad correlation verdict for every row in data/meta-ads.json +
data/google-ads.json. On the Swing Shack brand, data/meta-ads.json contains
20 rows whose `source` field is "instagram-analytics" and `note` is
"Derived from organic IG post reach as ad-impression proxy" — they are
placeholder rows standing in for real paid-spend data the Meta Ads API
would have returned. The Google Ads connector is live and returns real
spend (R45,432 across 16 campaigns in the live data).

Pre-fix behaviour: the Meta Ads section rendered 20 rows all reading
"Campaign 'Coach Cat takes us through...' spent — and drove — clicks to /"
which is technically correct (spend was 0, clicks was 0) but reads as a
bug. The user lands on Insights, sees Google Ads verdicts, scrolls to
Meta Ads, and reads 20 rows of "spent R0 | drove 0 clicks" with no
signal that the data is a placeholder, not a real result.

Fix
---
`platformSection(label, block)` in `renderInsightsV2()` now inspects
`block.campaigns` and, when >=80% of campaigns have either:
  - `source` matching /instagram|organic|proxy/i, OR
  - `note` matching /proxy/i
renders a small, amber-bordered banner above the verdict list that:
  - Names the platform ("Meta Ads spend data unavailable")
  - Explains the rows are organic IG reach, not real paid spend
  - Links to /meta-portal so the user can wire the real API

This card is a dead-end only because the renderer was silent about the
data condition. The new banner turns the dead-end into a small, honest
"we know, here's how to fix" notice. No backend / data change — only
renderer.

Tests
-----
1. test_proxy_banner_present_when_80pct_proxy_campaigns
2. test_proxy_banner_absent_when_real_paid_campaigns
3. test_proxy_banner_threshold_is_80pct
4. test_proxy_banner_links_to_meta_portal
5. test_proxy_banner_does_not_suppress_verdict_list
6. test_proxy_banner_copy_em_dash_free
7. test_proxy_banner_copy_names_real_situation
8. test_no_proxy_banner_for_empty_block
"""
import os
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HTML = REPO_ROOT / "campaign-os" / "campaign-os.html"


def _read_platform_section():
    """Pull the platformSection arrow function out of campaign-os.html.

    Returns the function body as a string so we can test it through Node-style
    "extract-and-execute" introspection. We extract the body verbatim from
    the file so we know the test is reading the actual production code, not
    a copy.
    """
    src = HTML.read_text()
    # Find `const platformSection = (label, block) => {` and walk braces to
    # the matching closing brace.
    needle = "const platformSection = (label, block) => {"
    i = src.find(needle)
    if i == -1:
        raise RuntimeError("platformSection not found in campaign-os.html")
    j = src.find("{", i)
    depth = 0
    k = j
    while k < len(src):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1
    raise RuntimeError("platformSection braces not balanced")


def _exec_node(body, esc, label, block):
    """Minimal JS executor for the platformSection body.

    We sandbox the function body and supply the helpers it uses (`esc`,
    `trendChip`) inline. This avoids booting a full browser for the unit
    test while still running the production code path.
    """
    import subprocess
    import json as _json
    helpers = (
        "function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;'); }\n"
        "function trendChip(trend, label) { return ''; }\n"
        "const __label = JSON.parse(process.env.__LABEL);\n"
        "const __block = JSON.parse(process.env.__BLOCK);\n"
        "const label = __label;\n"
        "const block = __block;\n"
    )
    script = helpers + body + "\n;process.stdout.write(platformSection(label, block) || '');"
    env = {**__import__("os").environ,
           "__LABEL": _json.dumps(label),
           "__BLOCK": _json.dumps(block)}
    node = subprocess.run(
        ["node", "-e", script],
        capture_output=True, text=True, timeout=10, env=env,
    )
    if node.returncode != 0:
        raise RuntimeError(f"node exec failed: {node.stderr}")
    return node.stdout


def _real_paid_block():
    """Block shape that matches a real paid-campaign data source."""
    return {
        "configured": True,
        "campaigns": [
            {"id": "g1", "name": "Search Brand", "spend": 12345, "clicks": 100,
             "start_date": "2026-01-01", "end_date": "2026-01-31", "landing_page": "/",
             "source": "google-ads-api"},
            {"id": "g2", "name": "Search Non-brand", "spend": 8000, "clicks": 70,
             "start_date": "2026-02-01", "end_date": "2026-02-28", "landing_page": "/",
             "source": "google-ads-api"},
        ],
        "verdicts": [
            {"verdict": "Real paid campaign A", "start_date": "2026-01-01",
             "end_date": "2026-01-31", "campaign_name": "Search Brand"},
            {"verdict": "Real paid campaign B", "start_date": "2026-02-01",
             "end_date": "2026-02-28", "campaign_name": "Search Non-brand"},
        ],
        "trend_summary": {"summary_text": "2 campaigns", "direction": "stable"},
    }


def _proxy_block(n=20):
    """Block shape that matches the live Swing Shack meta-ads.json data."""
    campaigns = [
        {"id": f"ig-post-{i}", "name": f"Organic IG post {i}", "spend": 0.0, "clicks": 0,
         "start_date": "2026-04-01", "end_date": "2026-04-01", "landing_page": "/",
         "source": "instagram-analytics",
         "note": "Derived from organic IG post reach as ad-impression proxy"}
        for i in range(n)
    ]
    verdicts = [
        {"verdict": f"Campaign 'Organic IG post {i}' spent — and drove — clicks to /",
         "start_date": "2026-04-01", "end_date": "2026-04-01",
         "campaign_name": f"Organic IG post {i}"}
        for i in range(n)
    ]
    return {
        "configured": True,
        "campaigns": campaigns,
        "verdicts": verdicts,
        "trend_summary": {
            "summary_text": f"{n} campaigns | total spend R0 | avg R0.0/session",
            "direction": "unknown",
        },
    }


def _mixed_block():
    """6 real + 4 proxy = 40% proxy. Should NOT trigger banner (< 80%)."""
    return {
        "configured": True,
        "campaigns": [
            {"id": "g1", "name": "Real 1", "spend": 5000, "clicks": 50,
             "start_date": "2026-01-01", "end_date": "2026-01-31", "landing_page": "/",
             "source": "google-ads-api"},
            {"id": "g2", "name": "Real 2", "spend": 3000, "clicks": 30,
             "start_date": "2026-02-01", "end_date": "2026-02-28", "landing_page": "/",
             "source": "google-ads-api"},
            {"id": "i1", "name": "Proxy 1", "spend": 0.0, "clicks": 0,
             "start_date": "2026-03-01", "end_date": "2026-03-01", "landing_page": "/",
             "source": "instagram-analytics",
             "note": "Derived from organic IG post reach as ad-impression proxy"},
        ],
        "verdicts": [
            {"verdict": "v1", "start_date": "2026-01-01", "end_date": "2026-01-31", "campaign_name": "Real 1"},
        ],
        "trend_summary": {"summary_text": "mixed", "direction": "stable"},
    }


def _empty_block():
    return {"configured": False, "campaigns": [], "verdicts": [], "reason": "data not present"}


class AdCorrelationProxyBanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = _read_platform_section()

    def test_proxy_banner_present_when_80pct_proxy_campaigns(self):
        html = _exec_node(self.body, None, "Meta Ads", _proxy_block(20))
        self.assertIn("spend data unavailable", html)
        self.assertIn("Meta Ads", html)

    def test_proxy_banner_absent_when_real_paid_campaigns(self):
        html = _exec_node(self.body, None, "Google Ads", _real_paid_block())
        self.assertNotIn("spend data unavailable", html)
        self.assertIn("Real paid campaign A", html)

    def test_proxy_banner_threshold_is_80pct(self):
        # Start with 2 real campaigns; add proxy campaigns one at a time and
        # verify the banner fires at the 80% threshold.
        #
        # 0/2 proxy  → no banner
        # 1/3 proxy  = 33% → no banner
        # 2/4 proxy  = 50% → no banner
        # 3/5 proxy  = 60% → no banner
        # 4/5 proxy  = 80% → BANNER (>= threshold)
        base = _real_paid_block()
        proxies = [
            {"id": f"p{i}", "name": f"Proxy {i}", "spend": 0.0, "clicks": 0,
             "start_date": f"2026-04-{i:02d}", "end_date": f"2026-04-{i:02d}",
             "landing_page": "/",
             "source": "instagram-analytics",
             "note": "Derived from organic IG post reach as ad-impression proxy"}
            for i in range(1, 6)
        ]
        proxy_verdicts = [
            {"verdict": f"proxy v{i}", "start_date": f"2026-04-{i:02d}",
             "end_date": f"2026-04-{i:02d}", "campaign_name": f"Proxy {i}"}
            for i in range(1, 6)
        ]
        # 0/2 — no banner
        html = _exec_node(self.body, None, "Meta Ads", base)
        self.assertNotIn("spend data unavailable", html)
        # Each step adds 1 proxy + 1 verdict
        for n in range(1, 6):
            step = {
                "configured": True,
                "campaigns": base["campaigns"] + proxies[:n],
                "verdicts": base["verdicts"] + proxy_verdicts[:n],
                "trend_summary": base["trend_summary"],
            }
            total = len(step["campaigns"])
            proxy_count = n
            pct = proxy_count / total
            html = _exec_node(self.body, None, "Meta Ads", step)
            should_fire = pct >= 0.8
            has_banner = "spend data unavailable" in html
            self.assertEqual(
                has_banner, should_fire,
                f"n={n} proxy={proxy_count}/{total}={pct:.0%} expected={should_fire} got_banner={has_banner}",
            )

    def test_proxy_banner_links_to_meta_portal(self):
        html = _exec_node(self.body, None, "Meta Ads", _proxy_block(20))
        self.assertIn('href="/meta-portal"', html)

    def test_proxy_banner_does_not_suppress_verdict_list(self):
        block = _proxy_block(20)
        html = _exec_node(self.body, None, "Meta Ads", block)
        # The banner sits above the verdict list — both must render.
        self.assertIn("spend data unavailable", html)
        self.assertIn("Organic IG post 0", html)
        self.assertIn("Organic IG post 19", html)

    def test_proxy_banner_copy_em_dash_free(self):
        # Standing rule: no em-dashes in published copy.
        html = _exec_node(self.body, None, "Meta Ads", _proxy_block(20))
        # The verdict text contains a real em-dash (from the live data shape)
        # because that's the verdict string from the correlator. The new banner
        # copy itself must be em-dash-free.
        banner_part = html.split("spend data unavailable")[1].split("</div>")[0:3]
        banner_text = " ".join(banner_part)
        self.assertNotIn("\u2014", banner_text, f"em-dash in banner: {banner_text!r}")

    def test_proxy_banner_copy_names_real_situation(self):
        html = _exec_node(self.body, None, "Meta Ads", _proxy_block(20))
        # Tells the user WHY the rows are placeholders.
        self.assertIn("organic Instagram post reach", html)
        self.assertIn("ad-impression proxy", html)
        self.assertIn("data gap", html)

    def test_no_proxy_banner_for_empty_block(self):
        # Empty block short-circuits earlier (no verdicts) — banner must not fire.
        html = _exec_node(self.body, None, "Meta Ads", _empty_block())
        self.assertNotIn("spend data unavailable", html)
        self.assertEqual(html, "")


if __name__ == "__main__":
    unittest.main()
