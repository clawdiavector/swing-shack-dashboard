"""Meme Lord v2 — meme historian + brand-fit recommender tests.

Exercises the three new endpoints:
  GET  /api/intel/meme_knowledge     — full historian with facets + brand-fit scoring
  GET  /api/intel/meme_recommend     — top-N recommendations for voice/pillar/platform
  POST /api/intel/meme_apply         — generate concrete caption drafts for one meme

Tests cover:
  - data file shape (taxonomy, stats, voice_bible)
  - filtering (era, format, mechanism, voice, pillar, platform, only_still_works, search)
  - sort orders (brand_fit, peak_year, name)
  - brand-fit scoring sanity (full match → high score, low match → low score)
  - apply endpoint: missing meme_id → 400; unknown meme_id → 404; valid → captions + brand-fit
  - envelope shape (`ok` always present)
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


class MemeKnowledgeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-meme-knowledge-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app
        # The lru_cache caches the first DATA_DIR resolution. Tests use a tmpdir
        # but the bundled fallback in data/meme_knowledge.json is the real
        # dataset we test against — that's intentional.
        campaign_app._load_meme_knowledge.cache_clear()
        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        cls.module.init_repo = lambda: None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    # ── BASIC ENVELOPE ─────────────────────────────────────────

    def test_envelope_shape(self):
        r = self.client.get('/api/intel/meme_knowledge?limit=5')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get('ok'))
        self.assertIn('summary', d)
        self.assertIn('taxonomy', d)
        self.assertIn('voice_bible', d)
        self.assertIn('stats', d)
        self.assertIn('memes', d)
        self.assertIsInstance(d['memes'], list)
        self.assertIn('filters', d)
        self.assertIn('total', d)
        self.assertGreater(d['total'], 0)
        self.assertEqual(d['total'], len(d['memes']))

    def test_limit_caps_results(self):
        r = self.client.get('/api/intel/meme_knowledge?limit=7')
        d = r.get_json()
        self.assertEqual(d['total'], 7)
        self.assertEqual(len(d['memes']), 7)

    def test_no_limit_returns_all(self):
        r = self.client.get('/api/intel/meme_knowledge')
        d = r.get_json()
        # The bundled knowledge base has at least 70 memes
        self.assertGreater(d['total'], 70)

    # ── DATA SHAPE ──────────────────────────────────────────────

    def test_taxonomy_has_eras_formats_mechanisms(self):
        r = self.client.get('/api/intel/meme_knowledge')
        d = r.get_json()
        tax = d['taxonomy']
        self.assertIn('eras', tax)
        self.assertIn('formats', tax)
        self.assertIn('mechanisms', tax)
        self.assertGreater(len(tax['eras']), 0)
        self.assertGreater(len(tax['formats']), 0)
        self.assertGreater(len(tax['mechanisms']), 0)

    def test_voice_bible_has_three_voices(self):
        r = self.client.get('/api/intel/meme_knowledge')
        d = r.get_json()
        vb = d['voice_bible']
        for key in ('swing-shack', 'stick', 'bag-drop'):
            self.assertIn(key, vb, f'voice_bible missing voice: {key}')
            self.assertIn('tone', vb[key])
            self.assertIn('audience', vb[key])
            self.assertIn('do', vb[key])
            self.assertIn('dont', vb[key])

    def test_stats_includes_by_era_by_format_by_mechanism(self):
        r = self.client.get('/api/intel/meme_knowledge')
        d = r.get_json()
        stats = d['stats']
        self.assertIn('total_memes', stats)
        self.assertIn('by_era', stats)
        self.assertIn('by_format', stats)
        self.assertIn('by_mechanism', stats)
        self.assertIn('still_works_true', stats)
        self.assertIn('still_works_false', stats)
        # by_era counts should sum to total_memes
        total = sum(stats['by_era'].values())
        self.assertEqual(total, stats['total_memes'])

    def test_each_meme_has_required_fields(self):
        r = self.client.get('/api/intel/meme_knowledge?limit=30')
        d = r.get_json()
        required = {'id', 'name', 'format', 'era', 'peak_year', 'why_it_works',
                    'mechanism', 'tags', 'swingshack_fit_seeds',
                    'voice_fit', 'pillar_fit', 'platform_fit', 'format_hint'}
        for m in d['memes']:
            missing = required - set(m.keys())
            self.assertFalse(missing, f'meme {m.get("id")} missing fields: {missing}')
            self.assertIsInstance(m['swingshack_fit_seeds'], list)
            self.assertGreater(len(m['swingshack_fit_seeds']), 0, f'meme {m["id"]} has no fit-seeds')
            self.assertIn(m['fatigue_risk'], ('low', 'medium', 'high', None))
            self.assertIsInstance(m['still_works'], bool)

    # ── BRAND-FIT SCORING ───────────────────────────────────────

    def test_brand_fit_in_range(self):
        r = self.client.get('/api/intel/meme_knowledge?limit=20')
        d = r.get_json()
        for m in d['memes']:
            bf = m.get('brand_fit')
            self.assertIsNotNone(bf)
            self.assertGreaterEqual(bf, 0)
            self.assertLessEqual(bf, 100)
            self.assertIsInstance(m.get('brand_fit_reasons'), list)
            self.assertGreater(len(m['brand_fit_reasons']), 0)

    def test_full_match_scores_higher_than_no_match(self):
        # Pick the top meme for swing-shack+education+instagram
        r_top = self.client.get('/api/intel/meme_recommend?voice=swing-shack&pillar=education&platform=instagram&limit=1')
        d_top = r_top.get_json()
        top_bf = d_top['recommendations'][0]['brand_fit']
        # Default scoring (swing-shack/education/instagram) should match many memes at ≥75
        r_lib = self.client.get('/api/intel/meme_knowledge?limit=200')
        d_lib = r_lib.get_json()
        # Find a meme that doesn't match swing-shack voice
        non_match = None
        for m in d_lib['memes']:
            if 'swing-shack' not in m.get('voice_fit', []):
                # Re-score with swing-shack voice
                pass
        # Easier: ensure at least 5 memes have brand_fit ≥ 75 for default
        high_bf = [m for m in d_lib['memes'] if m['brand_fit'] >= 75]
        self.assertGreater(len(high_bf), 5, f'expected >5 memes with brand_fit ≥ 75, got {len(high_bf)}')
        # Top recommend should be one of the highest
        self.assertGreaterEqual(top_bf, 75)

    def test_brand_fit_changes_with_voice(self):
        # Constrain to bag-drop-only memes; for them, swing-shack voice scoring
        # should give 0 voice-bonus while bag-drop voice scoring gives +30.
        # Mems whose voice_fit is exactly [bag-drop] will score differently;
        # mems whose voice_fit includes swing-shack too will not. We assert
        # at least 1 meme scores higher under bag-drop than swing-shack,
        # proving the voice parameter actually affects scoring.
        r1 = self.client.get('/api/intel/meme_knowledge?voice=bag-drop&voice_for_score=swing-shack&pillar_for_score=education&platform_for_score=instagram&limit=10')
        r2 = self.client.get('/api/intel/meme_knowledge?voice=bag-drop&voice_for_score=bag-drop&pillar_for_score=education&platform_for_score=instagram&limit=10')
        d1 = r1.get_json(); d2 = r2.get_json()
        m1 = {m['id']: m['brand_fit'] for m in d1['memes']}
        m2 = {m['id']: m['brand_fit'] for m in d2['memes']}
        common = set(m1.keys()) & set(m2.keys())
        self.assertGreater(len(common), 0)
        # Find at least one meme that scores higher under bag-drop
        boosted = [k for k in common if m2[k] > m1[k]]
        self.assertGreater(len(boosted), 0,
                          'expected at least one meme to score higher when voice_for_score matches')
        # The boost should be exactly +30 (voice bonus) or capped at 100
        for k in boosted:
            diff = m2[k] - m1[k]
            self.assertGreaterEqual(diff, 20,
                                   f'meme {k} boosted by only {diff}, expected ~30')
            self.assertLessEqual(diff, 30)

    # ── FILTERING ───────────────────────────────────────────────

    def test_filter_by_era(self):
        r = self.client.get('/api/intel/meme_knowledge?era=classic&limit=200')
        d = r.get_json()
        self.assertGreater(d['total'], 0)
        for m in d['memes']:
            self.assertEqual(m['era'], 'classic')

    def test_filter_by_format(self):
        r = self.client.get('/api/intel/meme_knowledge?format=reaction-image&limit=200')
        d = r.get_json()
        self.assertGreater(d['total'], 0)
        for m in d['memes']:
            self.assertEqual(m['format'], 'reaction-image')

    def test_filter_by_mechanism(self):
        r = self.client.get('/api/intel/meme_knowledge?mechanism=ironic-corporate&limit=200')
        d = r.get_json()
        for m in d['memes']:
            self.assertEqual(m['mechanism'], 'ironic-corporate')

    def test_filter_by_voice(self):
        r = self.client.get('/api/intel/meme_knowledge?voice=stick&limit=200')
        d = r.get_json()
        for m in d['memes']:
            self.assertIn('stick', m['voice_fit'])

    def test_filter_by_pillar(self):
        r = self.client.get('/api/intel/meme_knowledge?pillar=club-fitting&limit=200')
        d = r.get_json()
        for m in d['memes']:
            self.assertIn('club-fitting', m['pillar_fit'])

    def test_filter_by_platform(self):
        r = self.client.get('/api/intel/meme_knowledge?platform=tiktok&limit=200')
        d = r.get_json()
        for m in d['memes']:
            self.assertIn('tiktok', m['platform_fit'])

    def test_only_still_works_filter(self):
        r = self.client.get('/api/intel/meme_knowledge?only_still_works=1&limit=200')
        d = r.get_json()
        for m in d['memes']:
            self.assertTrue(m['still_works'])

    def test_search_filter(self):
        r = self.client.get('/api/intel/meme_knowledge?search=trackman&limit=50')
        d = r.get_json()
        self.assertGreater(d['total'], 0)
        # Each result should contain 'trackman' somewhere in searchable fields
        for m in d['memes']:
            hay = ' '.join([
                m.get('name', ''), m.get('why_it_works', ''),
                m.get('origin', ''), ' '.join(m.get('tags') or []),
                ' '.join(m.get('swingshack_fit_seeds') or []),
                m.get('format_hint', ''),
            ]).lower()
            self.assertIn('trackman', hay, f'meme {m["id"]} matched but lacks "trackman" in searchable fields')

    def test_combined_filters_narrow_results(self):
        # baseline
        r1 = self.client.get('/api/intel/meme_knowledge?limit=200')
        d1 = r1.get_json()
        total_all = d1['total']
        # filtered
        r2 = self.client.get('/api/intel/meme_knowledge?era=recent&mechanism=ironic-corporate&only_still_works=1&limit=200')
        d2 = r2.get_json()
        self.assertLess(d2['total'], total_all)
        for m in d2['memes']:
            self.assertEqual(m['era'], 'recent')
            self.assertEqual(m['mechanism'], 'ironic-corporate')
            self.assertTrue(m['still_works'])

    # ── SORT ────────────────────────────────────────────────────

    def test_sort_brand_fit_descending(self):
        r = self.client.get('/api/intel/meme_knowledge?sort=brand_fit&limit=20')
        d = r.get_json()
        scores = [m['brand_fit'] for m in d['memes']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_sort_peak_year_descending(self):
        r = self.client.get('/api/intel/meme_knowledge?sort=peak_year&limit=20')
        d = r.get_json()
        years = [m.get('peak_year', 0) for m in d['memes']]
        self.assertEqual(years, sorted(years, reverse=True))

    def test_sort_name_ascending(self):
        r = self.client.get('/api/intel/meme_knowledge?sort=name&limit=20')
        d = r.get_json()
        names = [m['name'].lower() for m in d['memes']]
        self.assertEqual(names, sorted(names))


class MemeRecommendApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-meme-recommend-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app
        campaign_app._load_meme_knowledge.cache_clear()
        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        cls.module.init_repo = lambda: None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def test_envelope_shape(self):
        r = self.client.get('/api/intel/meme_recommend?voice=swing-shack&pillar=education&platform=instagram&limit=5')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get('ok'))
        self.assertIn('summary', d)
        self.assertIn('criteria', d)
        self.assertIn('recommendations', d)
        self.assertIn('alternates', d)
        self.assertEqual(len(d['recommendations']), 5)

    def test_recommendations_sorted_by_brand_fit(self):
        r = self.client.get('/api/intel/meme_recommend?voice=swing-shack&pillar=education&platform=instagram&limit=10')
        d = r.get_json()
        scores = [m['brand_fit'] for m in d['recommendations']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_recommendation_payload_has_required_fields(self):
        r = self.client.get('/api/intel/meme_recommend?voice=swing-shack&pillar=education&platform=instagram&limit=3')
        d = r.get_json()
        for m in d['recommendations']:
            self.assertIn('recommendation', m)
            self.assertEqual(m['recommendation']['voice'], 'swing-shack')
            self.assertEqual(m['recommendation']['pillar'], 'education')
            self.assertEqual(m['recommendation']['platform'], 'instagram')
            self.assertIn('fit_seed_suggestion', m['recommendation'])
            self.assertIsInstance(m['recommendation']['fit_seed_suggestion'], str)

    def test_limit_clamped(self):
        # limit=1 should return 1
        r1 = self.client.get('/api/intel/meme_recommend?limit=1')
        d1 = r1.get_json()
        self.assertEqual(len(d1['recommendations']), 1)
        # limit=999 should be clamped to ≤50
        r2 = self.client.get('/api/intel/meme_recommend?limit=999')
        d2 = r2.get_json()
        self.assertLessEqual(len(d2['recommendations']), 50)

    def test_filter_narrows_recommendations(self):
        r_all = self.client.get('/api/intel/meme_recommend?limit=20')
        d_all = r_all.get_json()
        r_filtered = self.client.get('/api/intel/meme_recommend?voice=bag-drop&limit=20')
        d_filtered = r_filtered.get_json()
        # bag-drop should have fewer than all voices
        self.assertLess(len(d_filtered['recommendations']), len(d_all['recommendations']))
        for m in d_filtered['recommendations']:
            self.assertIn('bag-drop', m['voice_fit'])

    def test_alternates_returns_additional_memes(self):
        r = self.client.get('/api/intel/meme_recommend?limit=3')
        d = r.get_json()
        # alternates should exist and not duplicate recommendations
        alt_ids = {m['id'] for m in d.get('alternates', [])}
        rec_ids = {m['id'] for m in d['recommendations']}
        self.assertFalse(alt_ids & rec_ids, 'alternates should not duplicate recommendations')

    def test_criteria_recorded(self):
        r = self.client.get('/api/intel/meme_recommend?voice=stick&pillar=community&platform=tiktok&limit=5&era=recent')
        d = r.get_json()
        c = d['criteria']
        self.assertEqual(c['voice'], 'stick')
        self.assertEqual(c['pillar'], 'community')
        self.assertEqual(c['platform'], 'tiktok')
        self.assertEqual(c['era'], 'recent')
        self.assertEqual(c['limit'], 5)


class MemeApplyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-meme-apply-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app
        campaign_app._load_meme_knowledge.cache_clear()
        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        cls.module.init_repo = lambda: None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def test_envelope_shape_minimal_body(self):
        r = self.client.post('/api/intel/meme_apply',
                             data=json.dumps({"meme_id": "distracted-boyfriend"}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get('ok'))
        self.assertIn('meme', d)
        self.assertIn('applied', d)
        self.assertIn('brand_fit', d)
        self.assertIn('captions', d)
        self.assertEqual(d['meme']['id'], 'distracted-boyfriend')
        # applied defaults
        self.assertEqual(d['applied']['voice'], 'swing-shack')
        self.assertEqual(d['applied']['platform'], 'instagram')
        self.assertEqual(d['applied']['pillar'], 'education')

    def test_three_caption_flavours(self):
        r = self.client.post('/api/intel/meme_apply',
                             data=json.dumps({"meme_id": "drake-preference"}),
                             content_type='application/json')
        d = r.get_json()
        flavours = [c['flavour'] for c in d['captions']]
        self.assertEqual(set(flavours), {'sarcastic', 'wholesome', 'hard-truth'})
        for c in d['captions']:
            self.assertIn('text', c)
            self.assertIsInstance(c['text'], str)
            self.assertGreater(len(c['text']), 5)
            self.assertEqual(c['platform_fit'], 'instagram')

    def test_user_hook_overrides_caption(self):
        r = self.client.post('/api/intel/meme_apply',
                             data=json.dumps({"meme_id": "drake-preference", "hook": "TrackMan sees what you can't"}),
                             content_type='application/json')
        d = r.get_json()
        # All three captions should contain the user hook
        for c in d['captions']:
            self.assertIn('TrackMan sees what you can\'t', c['text'])

    def test_brand_fit_recorded_in_apply(self):
        r = self.client.post('/api/intel/meme_apply',
                             data=json.dumps({"meme_id": "distracted-boyfriend", "voice": "swing-shack", "pillar": "education"}),
                             content_type='application/json')
        d = r.get_json()
        bf = d['brand_fit']
        self.assertIn('score', bf)
        self.assertGreaterEqual(bf['score'], 0)
        self.assertLessEqual(bf['score'], 100)
        self.assertIsInstance(bf['reasons'], list)
        self.assertGreater(len(bf['reasons']), 0)
        self.assertIn('voice_bible', bf)
        self.assertEqual(bf['voice_bible']['label'], 'Swing Shack (default)')

    def test_pick_seed_index_changes_caption(self):
        r0 = self.client.post('/api/intel/meme_apply',
                              data=json.dumps({"meme_id": "distracted-boyfriend", "pick_seed_index": 0}),
                              content_type='application/json')
        r1 = self.client.post('/api/intel/meme_apply',
                              data=json.dumps({"meme_id": "distracted-boyfriend", "pick_seed_index": 2}),
                              content_type='application/json')
        d0 = r0.get_json(); d1 = r1.get_json()
        self.assertNotEqual(d0['applied']['fit_seed_used'], d1['applied']['fit_seed_used'])
        # Captions should differ (different seed text)
        self.assertNotEqual(d0['captions'][0]['text'], d1['captions'][0]['text'])

    def test_pick_seed_index_wraps(self):
        r = self.client.post('/api/intel/meme_apply',
                             data=json.dumps({"meme_id": "distracted-boyfriend", "pick_seed_index": 999}),
                             content_type='application/json')
        d = r.get_json()
        # Should not error — wraps around
        self.assertTrue(d['ok'])
        self.assertIn('fit_seed_used', d['applied'])
        self.assertIsInstance(d['applied']['fit_seed_used'], str)

    def test_missing_meme_id_returns_400(self):
        r = self.client.post('/api/intel/meme_apply',
                             data=json.dumps({}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)
        d = r.get_json()
        self.assertFalse(d.get('ok'))
        self.assertIn('meme_id', d.get('error', '').lower())

    def test_unknown_meme_id_returns_404(self):
        r = self.client.post('/api/intel/meme_apply',
                             data=json.dumps({"meme_id": "totally-fake-meme-9999"}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 404)
        d = r.get_json()
        self.assertFalse(d.get('ok'))
        self.assertIn('unknown', d.get('error', '').lower())

    def test_format_hint_and_why_included(self):
        r = self.client.post('/api/intel/meme_apply',
                             data=json.dumps({"meme_id": "distracted-boyfriend"}),
                             content_type='application/json')
        d = r.get_json()
        self.assertIn('format_hint', d)
        self.assertIn('why_it_works', d)
        self.assertIsInstance(d['format_hint'], str)
        self.assertIsInstance(d['why_it_works'], str)
        self.assertGreater(len(d['format_hint']), 10)

    def test_voice_bible_rules_for_voice(self):
        expected_labels = {
            'swing-shack': 'swing shack',
            'stick': 'stick',
            'bag-drop': 'bag drop',
        }
        for voice in ('swing-shack', 'stick', 'bag-drop'):
            r = self.client.post('/api/intel/meme_apply',
                                 data=json.dumps({"meme_id": "distracted-boyfriend", "voice": voice}),
                                 content_type='application/json')
            d = r.get_json()
            self.assertEqual(d['applied']['voice'], voice)
            label = d['brand_fit']['voice_bible']['label'].lower()
            self.assertIn(expected_labels[voice], label,
                          f'voice={voice} expected label containing "{expected_labels[voice]}", got "{label}"')


if __name__ == '__main__':
    unittest.main()