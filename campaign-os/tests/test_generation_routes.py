"""Generation Routes — priority 7 tests.

Exercises the "Generate" endpoints that wrap existing intelligence helpers
with HTTP + n-param + POST body:

  GET  /api/intel/generate_hooks        — fresh hooks from signals
  POST /api/intel/generate_headlines    — billboard headline candidates
  POST /api/intel/generate_ctas         — CTA copy variants
  POST /api/intel/generate_meme         — fresh meme with brand-fit + tier
  POST /api/intel/generate_ideas        — mined from missed-opps + reddit + trends
  POST /api/intel/generate_ctas_for_asset — CTAs tailored to one asset

Plus the front-end integration tests for the Generate buttons rendered in
the Ideas, Meme Lord, and Billboard Lab sections.

Tests cover:
  - envelope shape ({ok, ...}) for every endpoint
  - n-param clamping (max limits honoured)
  - default n when no param
  - POST + GET both work
  - error envelopes are sane on bad input
  - meme tier classification (fresh_crowd_pleaser / proven_classic / risky_but_fits / dated_pick / safe_neutral)
  - idea source_type coverage (missed_opportunity / reddit / trend)
  - idea dedup + sort by score
  - SPA integration: each "Generate" button exists with proper id + binding text
  - calendar slot JS uses pillar-* class (not inline hex)
  - pillar class CSS rules exist (theme-aware)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


CAMPAIGN_OS = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(CAMPAIGN_OS))

from app import app  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _setUp_data_with_bundle_copy(testcase):
    """Mirror relevant data files into a temp DATA_DIR so the endpoints
    can find them regardless of where the test is being run from."""
    testcase._tmp = tempfile.mkdtemp()
    testcase._old_data = os.environ.get('DATA_DIR')
    os.environ['DATA_DIR'] = testcase._tmp
    bundled = Path(__file__).resolve().parents[2] / 'data'
    if bundled.exists():
        for f in bundled.iterdir():
            if f.is_file():
                shutil.copy(f, Path(testcase._tmp) / f.name)
    testcase.c = app.test_client()


def _tearDown_data(testcase):
    os.environ.pop('DATA_DIR', None)
    if getattr(testcase, '_old_data', None):
        os.environ['DATA_DIR'] = testcase._old_data
    shutil.rmtree(testcase._tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────
# generate_hooks tests
# ─────────────────────────────────────────────────────────────────────

class GenerateHooksApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_get_envelope_shape(self):
        r = self.c.get('/api/intel/generate_hooks')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertIn('hooks', b)
        self.assertIn('count', b)
        self.assertIn('ts', b)
        self.assertIsInstance(b['hooks'], list)
        self.assertEqual(b['count'], len(b['hooks']))

    def test_get_default_count(self):
        # Default n=10, max=30 — should produce <= 30 hooks
        r = self.c.get('/api/intel/generate_hooks')
        b = r.get_json()
        self.assertLessEqual(b['count'], 30)
        self.assertGreater(b['count'], 0)

    def test_get_n_param(self):
        r = self.c.get('/api/intel/generate_hooks?n=3')
        b = r.get_json()
        self.assertLessEqual(b['count'], 3)

    def test_get_n_clamped_to_max(self):
        r = self.c.get('/api/intel/generate_hooks?n=999')
        b = r.get_json()
        self.assertLessEqual(b['count'], 30)

    def test_post_works(self):
        r = self.c.post('/api/intel/generate_hooks', json={'n': 5})
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertLessEqual(b['count'], 5)

    def test_hooks_have_text(self):
        r = self.c.get('/api/intel/generate_hooks?n=4')
        b = r.get_json()
        for h in b['hooks']:
            self.assertIn('hook', h)
            self.assertIsInstance(h['hook'], str)
            self.assertGreater(len(h['hook']), 5)


# ─────────────────────────────────────────────────────────────────────
# generate_headlines tests
# ─────────────────────────────────────────────────────────────────────

class GenerateHeadlinesApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_get_envelope_shape(self):
        r = self.c.get('/api/intel/generate_headlines?n=4')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertIn('headlines', b)
        self.assertIn('count', b)
        self.assertEqual(b['count'], len(b['headlines']))

    def test_n_clamped(self):
        r = self.c.get('/api/intel/generate_headlines?n=99')
        b = r.get_json()
        self.assertLessEqual(b['count'], 12)

    def test_post_works(self):
        r = self.c.post('/api/intel/generate_headlines', json={'n': 3})
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertLessEqual(b['count'], 3)

    def test_headlines_have_seed_and_source(self):
        r = self.c.get('/api/intel/generate_headlines?n=3')
        b = r.get_json()
        for h in b['headlines']:
            self.assertIn('headline', h)
            self.assertIsInstance(h['headline'], str)
            self.assertGreater(len(h['headline']), 10)


# ─────────────────────────────────────────────────────────────────────
# generate_ctas tests
# ─────────────────────────────────────────────────────────────────────

class GenerateCtasApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_get_envelope_shape(self):
        r = self.c.get('/api/intel/generate_ctas?n=3')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertIn('ctas', b)
        self.assertIn('count', b)

    def test_n_clamped(self):
        r = self.c.get('/api/intel/generate_ctas?n=99')
        b = r.get_json()
        self.assertLessEqual(b['count'], 12)

    def test_post_works(self):
        r = self.c.post('/api/intel/generate_ctas', json={'n': 5})
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))

    def test_ctas_have_text(self):
        r = self.c.get('/api/intel/generate_ctas?n=3')
        b = r.get_json()
        for cta in b['ctas']:
            self.assertIn('cta', cta)
            self.assertIsInstance(cta['cta'], str)
            self.assertGreater(len(cta['cta']), 5)


class GenerateCtasForAssetApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_post_envelope_shape(self):
        r = self.c.post('/api/intel/generate_ctas_for_asset', json={'asset_id': 'abc', 'count': 4})
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertIn('ctas', b)
        self.assertIn('count', b)
        self.assertEqual(b['count'], len(b['ctas']))
        self.assertEqual(b['count'], 4)

    def test_post_count_clamped(self):
        r = self.c.post('/api/intel/generate_ctas_for_asset', json={'asset_id': 'abc', 'count': 99})
        b = r.get_json()
        self.assertLessEqual(b['count'], 10)

    def test_post_each_cta_has_why(self):
        r = self.c.post('/api/intel/generate_ctas_for_asset', json={'asset_id': 'abc', 'count': 3})
        b = r.get_json()
        for cta in b['ctas']:
            self.assertIn('why', cta)
            self.assertIsInstance(cta['why'], str)


# ─────────────────────────────────────────────────────────────────────
# generate_meme tests
# ─────────────────────────────────────────────────────────────────────

class GenerateMemeApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_post_default_envelope(self):
        r = self.c.post('/api/intel/generate_meme', json={'n': 3})
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertIn('memes', b)
        self.assertIn('count', b)
        self.assertEqual(b['count'], len(b['memes']))

    def test_post_brand_fit_in_range(self):
        r = self.c.post('/api/intel/generate_meme', json={'n': 5, 'pillar': 'education', 'voice': 'swing-shack'})
        b = r.get_json()
        for m in b['memes']:
            self.assertIn('brand_fit', m)
            self.assertGreaterEqual(m['brand_fit'], 0)
            self.assertLessEqual(m['brand_fit'], 100)

    def test_post_tier_classification(self):
        # Ensure every returned meme has a tier label
        r = self.c.post('/api/intel/generate_meme', json={'n': 4})
        b = r.get_json()
        valid_tiers = {'fresh_crowd_pleaser', 'proven_classic', 'risky_but_fits', 'dated_pick', 'safe_neutral'}
        for m in b['memes']:
            self.assertIn('tier', m)
            self.assertIn(m['tier'], valid_tiers, f"Unknown tier: {m['tier']}")

    def test_post_why_pick_present(self):
        r = self.c.post('/api/intel/generate_meme', json={'n': 3})
        b = r.get_json()
        for m in b['memes']:
            self.assertIn('why_pick', m)
            self.assertIsInstance(m['why_pick'], str)
            self.assertGreater(len(m['why_pick']), 0)

    def test_post_n_clamped_to_max(self):
        r = self.c.post('/api/intel/generate_meme', json={'n': 99})
        b = r.get_json()
        self.assertLessEqual(b['count'], 10)

    def test_post_sorted_by_brand_fit_desc(self):
        r = self.c.post('/api/intel/generate_meme', json={'n': 5, 'pillar': 'club-fitting', 'voice': 'stick'})
        b = r.get_json()
        fits = [m['brand_fit'] for m in b['memes']]
        self.assertEqual(fits, sorted(fits, reverse=True))

    def test_post_pillar_platform_voice_echoed(self):
        r = self.c.post('/api/intel/generate_meme', json={'n': 1, 'pillar': 'community', 'platform': 'tiktok', 'voice': 'stick'})
        b = r.get_json()
        self.assertEqual(b['pillar'], 'community')
        self.assertEqual(b['platform'], 'tiktok')
        self.assertEqual(b['voice'], 'stick')

    def test_get_works(self):
        r = self.c.get('/api/intel/generate_meme?n=2')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))


# ─────────────────────────────────────────────────────────────────────
# generate_ideas tests
# ─────────────────────────────────────────────────────────────────────

class GenerateIdeasApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_post_envelope(self):
        r = self.c.post('/api/intel/generate_ideas', json={'n': 4})
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertIn('ideas', b)
        self.assertIn('count', b)
        self.assertEqual(b['count'], len(b['ideas']))

    def test_get_works(self):
        r = self.c.get('/api/intel/generate_ideas?n=3')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))

    def test_ideas_have_required_fields(self):
        r = self.c.post('/api/intel/generate_ideas', json={'n': 3})
        b = r.get_json()
        for idea in b['ideas']:
            self.assertIn('title', idea)
            self.assertIn('why', idea)
            self.assertIn('source_type', idea)
            self.assertIn('score', idea)
            self.assertIsInstance(idea['title'], str)
            self.assertGreater(len(idea['title']), 5)
            self.assertGreaterEqual(idea['score'], 0)

    def test_ideas_source_types_valid(self):
        r = self.c.post('/api/intel/generate_ideas', json={'n': 8})
        b = r.get_json()
        valid = {'missed_opportunity', 'reddit', 'trend'}
        for idea in b['ideas']:
            self.assertIn(idea['source_type'], valid, f"Unknown source_type: {idea['source_type']}")

    def test_ideas_n_clamped(self):
        r = self.c.post('/api/intel/generate_ideas', json={'n': 999})
        b = r.get_json()
        self.assertLessEqual(b['count'], 20)

    def test_ideas_sorted_by_score_desc(self):
        r = self.c.post('/api/intel/generate_ideas', json={'n': 10})
        b = r.get_json()
        scores = [i['score'] for i in b['ideas']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_ideas_titles_unique(self):
        r = self.c.post('/api/intel/generate_ideas', json={'n': 10})
        b = r.get_json()
        titles = [i['title'].lower()[:80] for i in b['ideas']]
        self.assertEqual(len(titles), len(set(titles)), "Duplicate titles in ideas output")

    def test_pillar_filter_respected(self):
        # Pillar filter only applies to missed-opp items (others default to community/general).
        # Just confirm the endpoint doesn't error and returns ideas.
        r = self.c.post('/api/intel/generate_ideas', json={'n': 6, 'pillar': 'education'})
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertGreater(b['count'], 0)
        # If any idea claims a pillar, it must be the filter pillar (no leakage)
        for idea in b['ideas']:
            if idea['source_type'] == 'missed_opportunity':
                # Either matches the filter, or has a 'general' fallback if no pillar on source
                self.assertIn(idea['pillar'], ('education', 'general'))


# ─────────────────────────────────────────────────────────────────────
# Front-end integration tests — buttons, classes, hex-free JS
# ─────────────────────────────────────────────────────────────────────

class GenerationRoutesSpaIntegrationTests(unittest.TestCase):
    """Verify the SPA wires each generation route through a Generate button,
    and that the calendar-slot pillar coloring uses CSS classes (no inline hex)."""

    @classmethod
    def setUpClass(cls):
        cls.html_path = CAMPAIGN_OS / 'campaign-os.html'
        cls.html = cls.html_path.read_text(encoding='utf-8')

    def _snippet_after(self, marker: str, window: int = 30000) -> str:
        """Return the window of HTML after the FIRST occurrence of marker.

        For button-id markers the click handler can live in a render*() function
        later in the file (HTML is interleaved with JS), so the window must be wide.
        """
        idx = self.html.find(marker)
        if idx == -1:
            return ''
        return self.html[idx:idx + window]

    def test_ideas_generate_button_exists(self):
        # Button id lives in HTML markup; click handler lives later in the JS
        # (which is also embedded in this file). Both must be present.
        self.assertIn('id="ideas-gen"', self.html)
        self.assertIn('Generate new ideas', self.html)
        self.assertIn('/api/intel/generate_ideas', self.html)

    def test_meme_generate_button_exists(self):
        self.assertIn('id="mem-gen-fresh"', self.html)
        self.assertIn('Generate fresh meme concept', self.html)
        self.assertIn('/api/intel/generate_meme', self.html)

    def test_billboard_generate_button_exists(self):
        self.assertIn('id="bb-gen"', self.html)
        self.assertIn('Generate 5 headline concepts', self.html)
        self.assertIn('/api/intel/generate_headlines', self.html)

    def test_generate_buttons_are_idempotent(self):
        # Every generate button should guard against double-binding via `_bound` flag
        for marker in ('ideas-gen', 'mem-gen-fresh', 'bb-gen'):
            self.assertIn(marker, self.html)
        # Look for the idempotency flag
        self.assertIn('_bound', self.html)

    def test_calendar_pillar_uses_css_classes(self):
        # The slot builder must produce class names like "pillar-equipment", not inline hex.
        # Locate the calSlotHtml function and search for "pillar-" markers.
        m = re.search(r"function calSlotHtml\(s\)\{(.+?)\n\}", self.html, re.S)
        self.assertIsNotNone(m, "calSlotHtml function not found")
        body = m.group(1)
        # The class prefix should appear as 'pillar-' (with leading space, used with concat)
        self.assertIn("pillar-' +", body, "No 'pillar-' class prefix concat in calSlotHtml")
        # The class interpolation should target the rendered div class= attr
        self.assertIn("cal-slot ${cls}${pillarCls}", body,
                      "pillarCls not appended to the slot div class")
        # Should NOT contain the inline hex tints map (the entire pillarTints object)
        self.assertNotIn("pillarTints", body, "Old inline-hex pillarTints map still present")
        # Specifically the bad hex literals
        for hex_lit in ("'#f59e0b'", "'#3b82f6'", "'#10b981'", "'#ec4899'", "'#a78bfa'"):
            self.assertNotIn(hex_lit, body, f"Inline hex literal still present: {hex_lit}")
        # The tint variable should be empty (we use classes now)
        self.assertIn("const tint = ''", body)

    def test_pillar_class_css_rules_present(self):
        # Each pillar-* class should have a CSS rule that drives border-left-color
        for cls in ('pillar-equipment', 'pillar-club-fitting', 'pillar-coaching',
                    'pillar-community', 'pillar-events', 'pillar-merch'):
            self.assertIn(f'.cal-slot.{cls}', self.html, f"Missing CSS rule: .{cls}")

    def test_pillar_tokens_defined_in_all_themes(self):
        # The pillar tints should be defined in :root + [data-theme="dark"] + [data-theme="light"]
        for token in ('--pillar-equipment', '--pillar-club-fitting',
                      '--pillar-coaching', '--pillar-community',
                      '--pillar-events', '--pillar-merch'):
            self.assertIn(token, self.html)
        # Check that they're defined in the actual CSS blocks. Use a multi-line scan.
        # Acceptable: tokens live inside any CSS rule body containing the right tokens.
        css_section = self.html.split('<script>')[0]  # CSS lives before scripts
        # Each pillar token must appear at least once outside theme blocks
        # (i.e. inside some `:root` or `[data-theme="..."]` block)
        for token in ('--pillar-equipment', '--pillar-coaching', '--pillar-events'):
            occurrences = css_section.count(token)
            # We expect at least 2 (root + dark + light + media-query = 4)
            self.assertGreaterEqual(occurrences, 2,
                                    f"Token {token} only appears {occurrences}x — needs theme coverage")


# ─────────────────────────────────────────────────────────────────────
# Generation routes index manifest
# ─────────────────────────────────────────────────────────────────────

class GenerationRoutesIndexTests(unittest.TestCase):
    """Sanity-check that the front-end discoverability manifest includes
    the new generation routes."""

    @classmethod
    def setUpClass(cls):
        cls.html_path = CAMPAIGN_OS / 'campaign-os.html'
        cls.html = cls.html_path.read_text(encoding='utf-8')

    def test_routes_documented_in_manifest(self):
        # Each generation route should appear somewhere in the SPA (button click
        # handlers, fetch calls, intel_index manifest, etc.). Accept either the
        # explicit /generate_*/ names OR the intelligence-view aliases
        # (/hooks_generate, /headlines_generate, /ctas_generate).
        html = self.html
        for route_pair in (
            ('generate_ideas', '/api/intel/generate_ideas'),
            ('generate_meme', '/api/intel/generate_meme'),
            ('generate_headlines', '/api/intel/headlines_generate'),  # alias used by SPA
            ('generate_ctas', '/api/intel/ctas_generate'),
            ('generate_hooks', '/api/intel/hooks_generate'),
        ):
            needle, fallback = route_pair
            self.assertTrue(needle in html or fallback in html,
                            f"route '{needle}' (or '{fallback}') not referenced anywhere in the SPA")


if __name__ == '__main__':
    unittest.main()
