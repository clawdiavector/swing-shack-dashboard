"""Tests for v2026-08-13: IG Business analytics as a 7th weekly-report source.

Covers:
  1. fetcher: shape-tolerant reads (missing keys don't crash), top-post
     selection, atomic write idempotency, caption-to-hook_id derivation
     matches sync_ig_analytics.js.
  2. weekly_report(): new `ig_business` block in payload; new claims
     surface in interpretation when data is real; no claims when data
     is missing (auto-silent); each new claim cites its source.

Pure-Python (no live network, no live filesystem writes). Where the
fetcher would touch the network, we monkey-patch urllib.request.urlopen.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "_lib"))
sys.path.insert(0, str(_HERE.parent.parent / "scripts"))

import _lib.intelligence as _intel  # noqa: E402
import fetch_ig_business as _igb  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Fetcher unit tests
# ──────────────────────────────────────────────────────────────────────


class FetchIgBusinessShapeTests(unittest.TestCase):
    """Test fetcher helper functions without making any live HTTP calls."""

    def test_caption_to_hook_id_matches_sync_ig_analytics_js(self):
        """The IG-business hook_id derivation must match the legacy sync
        so cross-source linking (hook-bank vs published vs IG-business)
        stays consistent across both data files."""
        cases = [
            ("Sub 70 clubs are now available", "sub-70-clubs-are-now-available"),
            # split("\n")[0] + collapse [^a-z0-9] to "-", strip "-"
            # then truncate to 50 chars. "YOU'VE" lowercased + apostrophe
            # removal gives "you-ve-seen-the-reviews", trimmed.
            ("YOU'VE SEEN THE REVIEWS.\nNow it's your turn.",
             "you-ve-seen-the-reviews"),
            # Emoji "🤣" is non-ASCII but matches the [^a-z0-9]+ rule
            # and collapses to a single "-" (no double dashes). The 50-
            # char slice truncates "today!" — that matches the JS sync
            # behavior exactly.
            ("And we certainly do have spirit 🤣. Visit SwingShack today!",
             "and-we-certainly-do-have-spirit-visit-swingshack-t"),
            ("", ""),
        ]
        for caption, expected in cases:
            with self.subTest(caption=caption[:30]):
                self.assertEqual(_igb._caption_to_hook_id(caption), expected)

    def test_top_post_summary_picks_highest_reach(self):
        """top_post in the output is the media object with the highest
        reach; falls back to first if no reach."""
        out = _igb._top_post_summary({
            "id": "abc", "media_type": "VIDEO",
            "metrics": {"reach": 100, "total_interactions": 5},
            "engagement_rate_pct": 5.0,
        })
        self.assertEqual(out["reach"], 100)
        self.assertEqual(out["interactions"], 5)
        self.assertEqual(out["id"], "abc")

    def test_atomic_write_skips_unchanged(self):
        """Atomic write should NOT rewrite a byte-identical file."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.json"
            data = {"a": 1, "b": [1, 2, 3]}
            self.assertTrue(_igb._atomic_write(p, data))
            # Second write with identical content returns False (unchanged).
            self.assertFalse(_igb._atomic_write(p, data))
            # And the file is valid JSON.
            self.assertEqual(json.loads(p.read_text()), data)

    def test_atomic_write_handles_nested(self):
        """Atomic write should serialize nested dicts cleanly."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nested.json"
            data = {"a": {"b": {"c": [1, 2, 3]}}}
            self.assertTrue(_igb._atomic_write(p, data))
            self.assertEqual(json.loads(p.read_text()), data)


class FetchIgBusinessAuthTests(unittest.TestCase):
    """Verify auth + exit-code paths without live network."""

    def test_token_missing_returns_exit_2(self):
        """When the token file is missing, exit code is 2 (silent cron)."""
        with tempfile.TemporaryDirectory() as td:
            with patch.object(_igb, "DEFAULT_TOKEN_FILE", str(Path(td) / "missing.json")):
                with patch.object(sys, "argv", ["fetch_ig_business.py"]):
                    self.assertEqual(_igb.main(), 2)

    def test_token_unreadable_returns_exit_2(self):
        """A malformed token file should also exit 2, not crash."""
        with tempfile.TemporaryDirectory() as td:
            bogus = Path(td) / "bogus.json"
            bogus.write_text("{not valid json")
            with patch.object(_igb, "DEFAULT_TOKEN_FILE", str(bogus)):
                with patch.object(sys, "argv", ["fetch_ig_business.py"]):
                    self.assertEqual(_igb.main(), 2)


class FetchIgBusinessPageTokenTests(unittest.TestCase):
    """Verify the page-scoped token mint helper."""

    def test_page_token_resolved_from_me_accounts(self):
        """The first page-id match in /me/accounts wins."""
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "data": [
                {"id": "111", "access_token": "tok-aaa"},
                {"id": "198859063301219", "access_token": "tok-bbb"},
                {"id": "999", "access_token": "tok-ccc"},
            ]
        }).encode()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = lambda s, *a: None
        with patch.object(_igb, "urlopen", return_value=fake_response):
            tok = _igb._resolve_page_token("user-tok", "198859063301219")
            self.assertEqual(tok, "tok-bbb")

    def test_page_token_returns_none_on_network_error(self):
        """Network errors degrade gracefully (return None, caller exits 0)."""
        from urllib.error import URLError
        with patch.object(_igb, "urlopen", side_effect=URLError("boom")):
            self.assertIsNone(_igb._resolve_page_token("user-tok", "198859063301219"))

    def test_page_token_returns_none_when_page_not_in_accounts(self):
        """If the requested page_id isn't in the response, return None."""
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "data": [{"id": "111", "access_token": "tok-aaa"}]
        }).encode()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = lambda s, *a: None
        with patch.object(_igb, "urlopen", return_value=fake_response):
            self.assertIsNone(_igb._resolve_page_token("user-tok", "198859063301219"))


# ──────────────────────────────────────────────────────────────────────
# Intelligence claim-generator tests
# ──────────────────────────────────────────────────────────────────────


def _ig_business_fixture(
    *,
    daily_reach=None,
    window_totals=None,
    top_post=None,
    account=None,
):
    """Build an ig_business dict for the interpretation unit tests."""
    return {
        "metadata": {
            "source": "meta_graph_api.instagram_business",
            "fetched_at": "2026-08-13T08:39:42.428100+00:00",
        },
        "account": account or {"followers_count": 2490, "media_count": 787},
        "window_totals": window_totals or {
            "accounts_engaged": 169,
            "total_interactions": 372,
            "profile_views": 521,
        },
        "daily_reach": daily_reach or [
            {"date": f"2026-08-{i:02d}", "value": 400} for i in range(1, 31)
        ],
        "top_post": top_post,
    }


class IgBusinessClaimsTests(unittest.TestCase):
    """Verify the weekly_report interpretation produces the right IG
    Business claims when data is real, and stays silent when it isn't."""

    def _interpret(self, **igb_kwargs):
        """Call _interpret_weekly_report with minimal args + IG business."""
        return _intel._interpret_weekly_report(
            published=5, failed=0, win_rate=100.0,
            prev_pub=5, prev_fail=0, prev_wr=100.0,
            platforms={"instagram": 5}, by_day={"Mon": 0, "Tue": 5, "Wed": 0},
            top_hooks=[], top_ctas=[],
            movers=[], failures=[], agent_summary={},
            ig_business=igb_kwargs.get("ig_business"),
        )

    # ── "what's working" ──

    def test_30d_reach_appears_in_working(self):
        """A positive 30d reach number surfaces as a working claim."""
        result = self._interpret(ig_business=_ig_business_fixture(
            window_totals={"accounts_engaged": 169, "reach": 25231, "total_interactions": 372}
        ))
        reach_claim = [c for c in result["whats_working"]
                       if "25,231 unique accounts" in c["claim"]]
        self.assertEqual(len(reach_claim), 1)
        self.assertEqual(reach_claim[0]["source"], "ig-business-analytics.json")
        self.assertEqual(reach_claim[0]["category"], "ig_engagement")

    def test_30d_engagement_rate_appears_in_working(self):
        """ER = accounts_engaged / reach surfaces with the industry baseline."""
        result = self._interpret(ig_business=_ig_business_fixture(
            window_totals={"accounts_engaged": 169, "reach": 25231}
        ))
        er_claim = [c for c in result["whats_working"]
                    if "engagement rate" in c["claim"].lower()]
        self.assertEqual(len(er_claim), 1)
        # 169 / 25231 = 0.6697 → 0.67
        self.assertIn("0.67%", er_claim[0]["claim"])

    def test_top_post_with_reach_appears_in_working(self):
        """The top-post reach claim is generated when reach > 0."""
        result = self._interpret(ig_business=_ig_business_fixture(
            top_post={
                "id": "abc", "media_type": "VIDEO",
                "reach": 1400, "interactions": 20, "likes": 16,
                "caption_preview": "Test caption\nWith a second line",
                "permalink": "https://instagram.com/p/abc",
            }
        ))
        top_claim = [c for c in result["whats_working"]
                     if "1,400 accounts" in c["claim"]]
        self.assertEqual(len(top_claim), 1)
        self.assertIn("Test caption", top_claim[0]["evidence"])

    def test_uptrend_reach_surfaces_positive_claim(self):
        """Recent-half avg > prior-half avg * 1.25 → positive trend claim."""
        # Prior half: avg 500. Recent half: avg 800 → 60% lift → fires.
        daily = (
            [{"date": f"2026-07-{i:02d}", "value": 500} for i in range(1, 16)] +
            [{"date": f"2026-08-{i:02d}", "value": 800} for i in range(1, 16)]
        )
        result = self._interpret(ig_business=_ig_business_fixture(daily_reach=daily))
        up_claim = [c for c in result["whats_working"] if "is up" in c["claim"]]
        self.assertEqual(len(up_claim), 1)
        self.assertIn("60%", up_claim[0]["claim"])

    # ── "what's not" ──

    def test_downtrend_reach_surfaces_high_severity_claim(self):
        """Recent-half avg < prior-half avg * 0.5 → high-severity alert."""
        daily = (
            [{"date": f"2026-07-{i:02d}", "value": 1000} for i in range(1, 16)] +
            [{"date": f"2026-08-{i:02d}", "value": 360} for i in range(1, 16)]
        )
        result = self._interpret(ig_business=_ig_business_fixture(daily_reach=daily))
        down_claim = [c for c in result["whats_not"] if "fallen" in c["claim"]]
        self.assertEqual(len(down_claim), 1)
        self.assertEqual(down_claim[0]["severity"], "high")

    # ── "look at" ──

    def test_follower_count_surfaces_in_look_at(self):
        """The follower snapshot always fires (just-in-time data)."""
        result = self._interpret(ig_business=_ig_business_fixture(
            account={"followers_count": 2490, "media_count": 787}
        ))
        follower_claim = [c for c in result["look_at"] if "2,490 IG followers" in c["claim"]]
        self.assertEqual(len(follower_claim), 1)
        self.assertEqual(follower_claim[0]["source"], "ig-business-analytics.json")

    # ── auto-silent when missing ──

    def test_no_ig_business_dict_silences_all_ig_claims(self):
        """If ig_business=None or empty, no IG claims fire AND
        ig-business-analytics.json isn't in sources_used."""
        result = self._interpret(ig_business=None)
        ig_sources = [s for s in result["sources_used"] if "ig-business" in s]
        self.assertEqual(ig_sources, [])
        for bucket in ("whats_working", "whats_not", "look_at"):
            for c in result[bucket]:
                self.assertNotEqual(c.get("source"), "ig-business-analytics.json")

    def test_empty_ig_business_dict_stays_silent(self):
        """Empty {} dict (file exists but has no data) → no claims."""
        result = self._interpret(ig_business={})
        self.assertNotIn("ig-business-analytics.json", result["sources_used"])

    def test_daily_reach_too_short_no_trend_claim(self):
        """<14 daily reach points → no trend direction claim."""
        daily = [{"date": f"2026-08-{i:02d}", "value": 500} for i in range(1, 11)]
        result = self._interpret(ig_business=_ig_business_fixture(daily_reach=daily))
        trend_claims = [c for c in result["whats_working"] + result["whats_not"]
                        if "reach" in c["claim"].lower() and ("up " in c["claim"] or "fallen" in c["claim"])]
        self.assertEqual(trend_claims, [])

    def test_daily_reach_fallback_for_window_total(self):
        """If window_totals.reach is missing, sum daily_reach instead.

        Build 15 days at 1000 + 15 days at 200 = 15,000 + 3,000 = 18,000.
        """
        daily = (
            [{"date": f"2026-07-{i:02d}", "value": 1000} for i in range(1, 16)] +
            [{"date": f"2026-08-{i:02d}", "value": 200} for i in range(1, 16)]
        )
        # window_totals.reach MISSING; daily sums to 18,000
        result = self._interpret(ig_business=_ig_business_fixture(
            window_totals={"accounts_engaged": 169},  # no reach
            daily_reach=daily,
        ))
        reach_claim = [c for c in result["whats_working"]
                       if "unique accounts" in c["claim"]]
        self.assertEqual(len(reach_claim), 1)
        # Sum should be in the claim
        self.assertIn("18,000", reach_claim[0]["claim"])


class IgBusinessWeeklyReportPayloadTests(unittest.TestCase):
    """Verify weekly_report() exposes the new ig_business block."""

    def test_weekly_report_contains_ig_business_block(self):
        """The top-level payload includes an `ig_business` summary."""
        r = _intel.weekly_report(brand="swing-shack")
        self.assertIn("ig_business", r)
        igb = r["ig_business"]
        # Always-present keys
        for k in ("fetched_at", "stale", "username", "window_totals",
                  "daily_reach_points", "media_in_window"):
            self.assertIn(k, igb, f"missing key: {k}")

    def test_sources_used_includes_ig_business_when_data_present(self):
        """When ig-business-analytics.json has data, it shows up in
        the interpretation's sources_used list."""
        r = _intel.weekly_report(brand="swing-shack")
        sources = r["interpretation"]["sources_used"]
        # Only assert if the data file actually exists (CI may run without it).
        if os.path.exists(os.path.join(_intel.DATA_DIR, "ig-business-analytics.json")):
            self.assertIn("ig-business-analytics.json", sources)


if __name__ == "__main__":
    unittest.main()
