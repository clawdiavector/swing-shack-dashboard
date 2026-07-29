"""Headlines & CTAs Studio v2 — tests for the curated CTA knowledge base.

Exercises:
  GET /api/intel/cta_knowledge       — filterable CTA library + headline seeds
  GET /api/intel/cta_recommend       — top-N CTAs scored on voice+pillar+platform
  GET /api/intel/cta_index           — manifest for the SPA picker
  data/cta_knowledge.json            — schema + content shape

Tests cover:
  - data file shape (categories, ctas, headline_seeds)
  - envelope shape ({ok, ...}) for every endpoint
  - filter dimensions: category, voice, pillar, platform, search, min_score, sort
  - _score / _match annotations on recommend endpoint
  - by_category breakdown
  - valid_voices / valid_pillars / valid_platforms / valid_categories manifest
  - bundling fallback (empty DATA_DIR → empty kb)
  - headline seeds structure (template + voice_fit + pillar_fit + seed_pool)
  - CTA required fields (text, category, voices, pillars, platforms, score, evidence)
"""
from __future__ import annotations

import json
import os
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
    """Mirror relevant data files into a temp DATA_DIR so endpoints can find them."""
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
# Data file shape tests
# ─────────────────────────────────────────────────────────────────────

class CtaKnowledgeFileTests(unittest.TestCase):
    """Verify the cta_knowledge.json shape and content."""

    @classmethod
    def setUpClass(cls):
        cls.path = Path(__file__).resolve().parents[2] / 'data' / 'cta_knowledge.json'
        cls.data = json.loads(cls.path.read_text(encoding='utf-8'))

    def test_file_exists(self):
        self.assertTrue(self.path.exists(), 'cta_knowledge.json must exist in data/')

    def test_meta_block(self):
        self.assertIn('schema', self.data)
        self.assertIn('version', self.data)
        self.assertIn('updated', self.data)
        self.assertIn('description', self.data)

    def test_categories_present(self):
        cats = self.data.get('categories')
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0)
        for c in cats:
            for k in ('id', 'label', 'intent', 'description'):
                self.assertIn(k, c, f"category missing {k}: {c}")

    def test_ctas_present_and_well_formed(self):
        ctas = self.data.get('ctas')
        self.assertIsInstance(ctas, list)
        self.assertGreaterEqual(len(ctas), 8, "Should have a decent curated library")
        for cta in ctas:
            for k in ('id', 'text', 'category', 'voices', 'pillars', 'platforms', 'score', 'evidence'):
                self.assertIn(k, cta, f"CTA {cta.get('id')} missing {k}")

    def test_cta_score_in_range(self):
        for cta in self.data['ctas']:
            self.assertGreaterEqual(cta['score'], 0)
            self.assertLessEqual(cta['score'], 100)

    def test_cta_category_matches_known(self):
        valid_cats = {c['id'] for c in self.data['categories']}
        for cta in self.data['ctas']:
            self.assertIn(cta['category'], valid_cats,
                          f"Unknown CTA category: {cta['category']}")

    def test_cta_voices_pillars_platforms_are_lists(self):
        for cta in self.data['ctas']:
            self.assertIsInstance(cta['voices'], list)
            self.assertIsInstance(cta['pillars'], list)
            self.assertIsInstance(cta['platforms'], list)

    def test_headline_seeds_present(self):
        seeds = self.data.get('headline_seeds')
        self.assertIsInstance(seeds, list)
        self.assertGreater(len(seeds), 0)
        for s in seeds:
            for k in ('id', 'template', 'voice_fit', 'pillar_fit', 'platform_fit'):
                self.assertIn(k, s, f"headline seed missing {k}: {s}")

    def test_all_three_voices_represented(self):
        all_voices = set()
        for cta in self.data['ctas']:
            all_voices.update(cta['voices'])
        self.assertEqual(all_voices, {'swing-shack', 'stick', 'bag-drop'})


# ─────────────────────────────────────────────────────────────────────
# cta_knowledge endpoint tests
# ─────────────────────────────────────────────────────────────────────

class CtaKnowledgeApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_envelope_shape(self):
        r = self.c.get('/api/intel/cta_knowledge')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        for k in ('categories', 'ctas', 'headline_seeds', 'count', 'total',
                  'by_category', 'filters_applied', 'valid_categories', 'ts'):
            self.assertIn(k, b, f"missing top-level key: {k}")

    def test_no_filters_returns_all(self):
        r = self.c.get('/api/intel/cta_knowledge')
        b = r.get_json()
        self.assertGreater(b['count'], 0)
        self.assertEqual(b['count'], len(b['ctas']))

    def test_category_filter(self):
        r = self.c.get('/api/intel/cta_knowledge?category=book')
        b = r.get_json()
        for c in b['ctas']:
            self.assertEqual(c['category'], 'book')

    def test_voice_filter(self):
        r = self.c.get('/api/intel/cta_knowledge?voice=stick')
        b = r.get_json()
        for c in b['ctas']:
            self.assertIn('stick', c['voices'])

    def test_pillar_filter(self):
        r = self.c.get('/api/intel/cta_knowledge?pillar=club-fitting')
        b = r.get_json()
        for c in b['ctas']:
            self.assertIn('club-fitting', c['pillars'])

    def test_platform_filter(self):
        r = self.c.get('/api/intel/cta_knowledge?platform=tiktok')
        b = r.get_json()
        for c in b['ctas']:
            self.assertIn('tiktok', c['platforms'])

    def test_search_filter(self):
        r = self.c.get('/api/intel/cta_knowledge?search=trackman')
        b = r.get_json()
        for c in b['ctas']:
            text = (c.get('text') or '') + ' ' + (c.get('evidence') or '') + ' ' + (c.get('id') or '')
            self.assertIn('trackman', text.lower(),
                          f"Search 'trackman' should match: {c.get('id')}")

    def test_min_score_filter(self):
        r = self.c.get('/api/intel/cta_knowledge?min_score=85')
        b = r.get_json()
        for c in b['ctas']:
            self.assertGreaterEqual(c['score'], 85)

    def test_sort_score_default(self):
        r = self.c.get('/api/intel/cta_knowledge')
        b = r.get_json()
        scores = [c['score'] for c in b['ctas']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_sort_category(self):
        r = self.c.get('/api/intel/cta_knowledge?sort=category')
        b = r.get_json()
        cats = [c['category'] for c in b['ctas']]
        self.assertEqual(cats, sorted(cats))

    def test_by_category_breakdown(self):
        r = self.c.get('/api/intel/cta_knowledge?pillar=club-fitting')
        b = r.get_json()
        self.assertIsInstance(b['by_category'], dict)
        # All keys should be known categories
        valid_cats = set(b['valid_categories'])
        for k in b['by_category'].keys():
            self.assertIn(k, valid_cats)

    def test_filters_applied_echoed(self):
        r = self.c.get('/api/intel/cta_knowledge?category=book&voice=stick&pillar=club-fitting')
        b = r.get_json()
        f = b['filters_applied']
        self.assertEqual(f['category'], 'book')
        self.assertEqual(f['voice'], 'stick')
        self.assertEqual(f['pillar'], 'club-fitting')

    def test_empty_filter_returns_empty(self):
        # 'pillar=nonexistent' should return no CTAs
        r = self.c.get('/api/intel/cta_knowledge?pillar=nonexistent')
        b = r.get_json()
        self.assertEqual(b['count'], 0)
        self.assertEqual(b['ctas'], [])

    def test_invalid_min_score_falls_back_to_zero(self):
        r = self.c.get('/api/intel/cta_knowledge?min_score=not-a-number')
        b = r.get_json()
        self.assertEqual(b['filters_applied']['min_score'], None)


# ─────────────────────────────────────────────────────────────────────
# cta_recommend endpoint tests
# ─────────────────────────────────────────────────────────────────────

class CtaRecommendApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_envelope_shape(self):
        r = self.c.get('/api/intel/cta_recommend?voice=swing-shack&pillar=club-fitting&platform=instagram')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        self.assertIn('ctas', b)
        self.assertIn('count', b)
        self.assertIn('voice', b)
        self.assertIn('pillar', b)
        self.assertIn('platform', b)

    def test_default_n_is_5(self):
        r = self.c.get('/api/intel/cta_recommend')
        b = r.get_json()
        self.assertLessEqual(b['count'], 5)

    def test_n_clamped(self):
        r = self.c.get('/api/intel/cta_recommend?n=99')
        b = r.get_json()
        self.assertLessEqual(b['count'], 12)

    def test_n_zero_becomes_one(self):
        r = self.c.get('/api/intel/cta_recommend?n=0')
        b = r.get_json()
        self.assertGreaterEqual(b['count'], 1)

    def test_match_indicators_when_filters_supplied(self):
        # The diversity round may include CTAs that don't match all filters
        # (so the result is category-diverse). Verify that at least one match has
        # all three flags True and that no match has False flags when filters were
        # supplied — _match can be True or None (no filter), but never False.
        r = self.c.get('/api/intel/cta_recommend?voice=swing-shack&pillar=club-fitting&platform=instagram&n=8')
        b = r.get_json()
        for cta in b['ctas']:
            self.assertIn('_match', cta)
            m = cta['_match']
            for flag in ('voice', 'pillar', 'platform'):
                self.assertIsNotNone(m[flag], f"{flag} match should not be None when filter supplied")
                self.assertTrue(m[flag], f"{flag} match should be True when filter supplied: {cta['id']}")
        # And at least one CTA must match all three filters
        full_match = [c for c in b['ctas']
                      if c['_match']['voice'] and c['_match']['pillar'] and c['_match']['platform']]
        self.assertGreater(len(full_match), 0, "At least one CTA should fully match all three filters")

    def test_match_indicators_none_when_no_filters(self):
        r = self.c.get('/api/intel/cta_recommend?n=3')
        b = r.get_json()
        for cta in b['ctas']:
            m = cta.get('_match', {})
            self.assertIsNone(m.get('voice'))
            self.assertIsNone(m.get('pillar'))
            self.assertIsNone(m.get('platform'))

    def test_score_field_present(self):
        r = self.c.get('/api/intel/cta_recommend?voice=swing-shack&pillar=club-fitting')
        b = r.get_json()
        for cta in b['ctas']:
            self.assertIn('_score', cta)
            self.assertGreaterEqual(cta['_score'], 0)

    def test_sorted_by_score_desc(self):
        r = self.c.get('/api/intel/cta_recommend?voice=swing-shack&pillar=club-fitting&platform=instagram&n=8')
        b = r.get_json()
        scores = [c['_score'] for c in b['ctas']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_invalid_n_falls_back_to_5(self):
        r = self.c.get('/api/intel/cta_recommend?n=not-a-number')
        b = r.get_json()
        # Should still return results with default count
        self.assertGreater(b['count'], 0)
        self.assertLessEqual(b['count'], 5)


# ─────────────────────────────────────────────────────────────────────
# cta_index endpoint tests
# ─────────────────────────────────────────────────────────────────────

class CtaIndexApiTests(unittest.TestCase):
    def setUp(self):
        _setUp_data_with_bundle_copy(self)

    def tearDown(self):
        _tearDown_data(self)

    def test_envelope_shape(self):
        r = self.c.get('/api/intel/cta_index')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b.get('ok'))
        for k in ('categories', 'valid_voices', 'valid_pillars', 'valid_platforms',
                  'valid_categories', 'seed_count', 'cta_count', 'ts'):
            self.assertIn(k, b, f"missing top-level key: {k}")

    def test_voices_complete(self):
        r = self.c.get('/api/intel/cta_index')
        b = r.get_json()
        self.assertEqual(set(b['valid_voices']), {'swing-shack', 'stick', 'bag-drop'})

    def test_pillars_complete(self):
        r = self.c.get('/api/intel/cta_index')
        b = r.get_json()
        self.assertGreaterEqual(len(b['valid_pillars']), 2)

    def test_platforms_complete(self):
        r = self.c.get('/api/intel/cta_index')
        b = r.get_json()
        self.assertGreaterEqual(len(b['valid_platforms']), 3)

    def test_counts_nonzero(self):
        r = self.c.get('/api/intel/cta_index')
        b = r.get_json()
        self.assertGreater(b['cta_count'], 0)
        self.assertGreater(b['seed_count'], 0)


# ─────────────────────────────────────────────────────────────────────
# Bundled fallback tests
# ─────────────────────────────────────────────────────────────────────

class CtaKnowledgeBundledFallbackTests(unittest.TestCase):
    """Engine must serve requests even when DATA_DIR is empty (falls back to bundled data)."""

    def test_kb_loads_with_empty_DATA_DIR(self):
        old = os.environ.get('DATA_DIR')
        tmp = tempfile.mkdtemp()
        try:
            os.environ['DATA_DIR'] = tmp
            c = app.test_client()
            r = c.get('/api/intel/cta_index')
            self.assertEqual(r.status_code, 200)
            b = r.get_json()
            # Even with empty DATA_DIR, the bundled fallback should work
            self.assertGreater(b['cta_count'], 0,
                               "Bundled fallback should provide CTAs when DATA_DIR is empty")
        finally:
            os.environ.pop('DATA_DIR', None)
            if old:
                os.environ['DATA_DIR'] = old
            shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────
# Front-end integration tests
# ─────────────────────────────────────────────────────────────────────

class CtaStudioSpaIntegrationTests(unittest.TestCase):
    """Verify the SPA has the new Headlines & CTAs v2 controls wired correctly."""

    @classmethod
    def setUpClass(cls):
        cls.html_path = CAMPAIGN_OS / 'campaign-os.html'
        cls.html = cls.html_path.read_text(encoding='utf-8')

    def test_headlines_section_has_filter_controls(self):
        # Voice + Pillar + Count selects + Clear history button
        for marker in ('id="head-voice"', 'id="head-pillar"', 'id="head-count"',
                       'id="head-gen"', 'id="head-recommend"', 'id="head-clear-history"',
                       'id="head-history"', 'id="head-gen-count"'):
            self.assertIn(marker, self.html, f"Headlines section missing: {marker}")

    def test_ctas_section_has_filter_controls(self):
        for marker in ('id="cta-voice"', 'id="cta-pillar"', 'id="cta-platform"',
                       'id="cta-category"', 'id="cta-gen"', 'id="cta-recommend"',
                       'id="cta-clear-history"', 'id="cta-history"', 'id="cta-gen-count"'):
            self.assertIn(marker, self.html, f"CTAs section missing: {marker}")

    def test_headlines_history_state_present(self):
        self.assertIn('HEAD_STATE', self.html)
        self.assertIn('ss:headlines:history', self.html)
        self.assertIn('_loadHeadHistory', self.html)
        self.assertIn('_saveHeadHistory', self.html)

    def test_ctas_history_state_present(self):
        self.assertIn('CTA_STATE', self.html)
        self.assertIn('ss:ctas:history', self.html)
        self.assertIn('_loadCtaHistory', self.html)
        self.assertIn('_saveCtaHistory', self.html)

    def test_cta_endpoint_wiring(self):
        # Verify the SPA calls the new endpoints
        self.assertIn('/api/intel/cta_knowledge', self.html)
        self.assertIn('/api/intel/cta_recommend', self.html)

    def test_cta_category_color_map_present(self):
        # The category colour map should be defined
        self.assertIn('_CTA_CAT_COLORS', self.html)
        self.assertIn('_CTA_CAT_LABELS', self.html)
        # All six categories should appear in the HTML somewhere (filter dropdown, map, etc.)
        for cat in ('book', 'learn', 'discover', 'social', 'soft', 'ugc'):
            # Use a word-boundary-ish check: the cat should appear as a quoted key
            self.assertTrue(
                f'"{cat}":' in self.html or f'>{cat}<' in self.html or f'value="{cat}"' in self.html,
                f"CTA category '{cat}' not present anywhere in the SPA"
            )

    def test_use_to_caption_action(self):
        # 'Use → Caption' buttons should be in the SPA
        self.assertIn('data-use-head', self.html)
        self.assertIn('data-use-cta', self.html)
        self.assertIn('Use → Caption', self.html)

    def test_re_run_history_buttons(self):
        self.assertIn('data-rerun-hist', self.html)
        self.assertIn('data-rerun-cta-hist', self.html)
        self.assertIn('Re-run', self.html)


if __name__ == '__main__':
    unittest.main()
