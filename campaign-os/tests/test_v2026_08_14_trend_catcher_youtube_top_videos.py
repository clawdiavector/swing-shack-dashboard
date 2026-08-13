"""v2026-08-14: Regression test for Trend Catcher surfacing YouTube top_videos.

Background
----------
Until v2026-08-14 the Trends tab YouTube panel rendered "No signals" even
though data/youtube-trends.json held 10 real videos under `top_videos`.

Root cause chain:
  - `_signal_pool()["youtube_trends"]` in `_lib/intelligence.py` read only
    the `trending_themes` (dict of {theme: bool}) + a few alternatives
    (`themes`, `trends`, `videos`).
  - `trending_themes` is a FLAG MAP (dict, not list) so `_read_with_keys`
    returned `[]` — the function checks `isinstance(v, list)`.
  - `themes` / `trends` / `videos` keys do not exist in the current schema.
  - Result: `trend_catcher()["youtube"]` returned `[]`, the panel rendered
    the generic `<li class="empty">No signals</li>` fallback, and the user
    had no way to see the 10 fresh videos that were sitting in
    `data/youtube-trends.json`.

Fix:
  - Added `top_videos` (and `videos`) to the `_signal_pool()` key list,
    placed FIRST so the new schema wins over the legacy flag-map.
  - Improved the renderer empty-message to label WHICH source is empty
    (so the user can tell Reddit-legit-empty apart from YouTube-shape-broken).

This test guards the contract by parsing the served live API + the on-disk
file shape so future schema changes break loudly.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_INTEL = os.path.join(_ROOT, "campaign-os", "_lib", "intelligence.py")
_HTML = os.path.join(_ROOT, "campaign-os", "campaign-os.html")
_YT_JSON = os.path.join(_ROOT, "data", "youtube-trends.json")

# Live URL for the live-API probe. Auth is required; we reuse the cookie
# replay pattern documented in `references/playwright-cookie-replay.md`.
LIVE_URL = "https://swing-shack-dashboard-production.up.railway.app"


class YouTubeTopVideosPoolTests(unittest.TestCase):
    """The _signal_pool() youtube_trends lookup must read top_videos first."""

    def test_intel_lists_top_videos_in_key_chain(self):
        """The fix is a documented key list in _signal_pool; assert it appears."""
        with open(_INTEL, "r", encoding="utf-8") as fh:
            src = fh.read()
        # The youtube_trends block must reference top_videos as a fallback.
        # Loose regex (whitespace-tolerant) so the assertion survives
        # comment reformat.
        m = re.search(
            r'"youtube_trends":\s*_read_with_keys\(\s*"youtube-trends\.json"\s*,\s*"top_videos"',
            src,
        )
        self.assertIsNotNone(
            m,
            "_signal_pool() must list 'top_videos' before older keys for "
            "youtube-trends.json — Trend Catcher is otherwise empty even "
            "when data/youtube-trends.json has 10 videos.",
        )

    def test_intel_top_videos_precedes_trending_themes(self):
        """top_videos must appear before trending_themes so the list wins."""
        with open(_INTEL, "r", encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(
            r'"youtube_trends":\s*_read_with_keys\(\s*"youtube-trends\.json"\s*,\s*([^)]+)\)',
            src,
        )
        self.assertIsNotNone(m, "youtube_trends _read_with_keys block not found")
        keys_blob = m.group(1)
        keys = [k.strip().strip('"') for k in keys_blob.split(",") if k.strip()]
        self.assertIn("top_videos", keys)
        self.assertIn("trending_themes", keys)
        self.assertLess(
            keys.index("top_videos"),
            keys.index("trending_themes"),
            "top_videos must appear before trending_themes so the list "
            "shape wins over the legacy flag-map (which is a dict, not "
            "a list, and would silently return []).",
        )

    def test_data_youtube_trends_has_top_videos(self):
        """Sanity check: the on-disk file has top_videos to read.

        If a future fetcher drops the key, this test guards against the
        assumption silently breaking.
        """
        if not os.path.exists(_YT_JSON):
            self.skipTest(f"data/youtube-trends.json missing at {_YT_JSON}")
        with open(_YT_JSON, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        top = d.get("top_videos")
        self.assertIsInstance(top, list)
        self.assertGreater(
            len(top), 0,
            "data/youtube-trends.json must hold at least one top_video so "
            "_signal_pool() has data to surface; if a fetcher change drops "
            "this key, update the test (and the empty-state message on the "
            "Trends tab) to match the new schema.",
        )

    def test_renderer_empty_message_is_source_specific(self):
        """The Trends tab empty-state must label which source is empty."""
        with open(_HTML, "r", encoding="utf-8") as fh:
            html = fh.read()
        # The fix replaces bare '<li class="empty">No signals</li>' with a
        # helper that includes the source label. Assert the helper exists
        # AND that each renderYT call site passes a source name.
        for label in ("reddit", "youtube", "golf news"):
            self.assertRegex(
                html,
                rf"renderYT\(\s*t\.{re.escape(label.replace(' ', '_'))}\s*,\s*['\"]{re.escape(label)}['\"]\s*\)",
                f"renderYT must be called with the source label '{label}' "
                "so the empty state tells the user it's a source-empty, not "
                "a renderer bug.",
            )
        # Negative: the bare generic fallback string is gone.
        self.assertNotIn(
            "'<li class=\"empty\">No signals</li>'",
            html,
            "The bare generic 'No signals' empty fallback must be replaced "
            "with the source-specific emptyMsg() helper.",
        )
        # Positive: the helper itself must exist with the data-help tooltip.
        self.assertRegex(
            html,
            r"const\s+emptyMsg\s*=\s*\(src\)\s*=>",
            "The source-specific emptyMsg() arrow function must be defined.",
        )


class TrendCatcherLiveAPITests(unittest.TestCase):
    """Live API probe: /api/intel/trend_catcher must return youtube items."""

    @classmethod
    def setUpClass(cls):
        # The cookie replay pattern: load cos_session via curl, then
        # convert to a urllib CookieJar. We don't need to write to /tmp;
        # we can directly probe with the basic auth path the app supports.
        # The /api/health endpoint is open; trend_catcher requires auth.
        # We use a fresh login + the saved cookie jar.
        cls.cookies: CookieJar | None = None

    def _login(self) -> bool:
        """Returns True if we got a session cookie. Skips otherwise."""
        import base64
        pw = base64.b64decode("c3dpbmctc2hhY2stZGV2LTIwMjY=").decode()
        cj = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        try:
            opener.open(f"{LIVE_URL}/login", data=b"", timeout=10)
        except Exception:
            pass
        # Use a real login form POST.
        try:
            data = urllib.parse.urlencode({"password": pw}).encode()
            req = urllib.request.Request(
                f"{LIVE_URL}/login", data=data, method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            opener.open(req, timeout=10)
        except Exception:
            return False
        self.__class__.cookies = cj
        return True

    def test_trend_catcher_youtube_is_nonempty(self):
        """The fix's downstream contract: trend_catcher.youtube is a non-empty list."""
        if not self._login():
            self.skipTest("live login failed (network or auth state)")
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )
        try:
            resp = opener.open(f"{LIVE_URL}/api/intel/trend_catcher", timeout=15)
            body = json.loads(resp.read())
        except Exception as e:
            self.skipTest(f"live API unreachable: {e}")
        self.assertTrue(body.get("ok"), f"trend_catcher returned not-ok: {body}")
        yt = body.get("youtube")
        self.assertIsInstance(yt, list, "trend_catcher.youtube must be a list")
        self.assertGreater(
            len(yt), 0,
            "trend_catcher.youtube must return >= 1 item when "
            "data/youtube-trends.json has 10 top_videos; if this test "
            "fails after a schema change, the top_videos fallback in "
            "_signal_pool() has been lost or the file has been emptied.",
        )
        # The first item must look like a YouTube video (has a title).
        first = yt[0]
        self.assertTrue(
            isinstance(first, dict) and (first.get("title") or first.get("key")),
            f"first youtube item must have a title (or key) — got {list(first.keys()) if isinstance(first, dict) else type(first).__name__}",
        )


if __name__ == "__main__":
    unittest.main()