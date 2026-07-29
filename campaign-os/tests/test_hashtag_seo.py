"""Tests for Hashtag & SEO Pack engine.

Covers:
  - hashtag normalisation
  - hashtag set composition across all pillars/voices/platforms
  - banned filter, trending filter, search filter, count cap
  - GMB returns empty list
  - platform max cap
  - SEO pack rendering (titles, meta, h1, slug, alt, og, schema)
  - SEO score
  - input validation (400s for invalid pillar/voice/platform/count)
  - bundled fallback when DATA_DIR is empty
"""
import json
import os
import sys
import unittest

# Ensure campaign-os root on path so we can import `app`
HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN_OS_ROOT = os.path.abspath(os.path.join(HERE, '..'))
REPO_ROOT = os.path.abspath(os.path.join(CAMPAIGN_OS_ROOT, '..'))
if CAMPAIGN_OS_ROOT not in sys.path:
    sys.path.insert(0, CAMPAIGN_OS_ROOT)


def _isolated_app():
    """Return a Flask test client with an isolated DATA_DIR.

    Per-test DATA_DIR guarantees no cross-talk with the live server.
    """
    import tempfile
    tmp = tempfile.mkdtemp(prefix='campaign-os-hashtag-seo-test-')
    os.environ['DATA_DIR'] = tmp
    # bust any lru_cache for data loaders
    import app as app_module
    if hasattr(app_module, '_load_hashtag_seo'):
        app_module._load_hashtag_seo.cache_clear()
    if hasattr(app_module, '_load_meme_knowledge'):
        app_module._load_meme_knowledge.cache_clear()
    return app_module.app.test_client(), tmp


class HashtagNormalisationTests(unittest.TestCase):
    """Unit tests for `_normalise_tag`."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls._normalise_tag = app_module._normalise_tag

    def test_adds_leading_hash(self):
        self.assertEqual(HashtagNormalisationTests._normalise_tag('swingshack'), '#swingshack')

    def test_lowercases(self):
        self.assertEqual(HashtagNormalisationTests._normalise_tag('#SwingShack'), '#swingshack')

    def test_strips_duplicate_hash(self):
        self.assertEqual(HashtagNormalisationTests._normalise_tag('##swingshack'), '#swingshack')
        self.assertEqual(HashtagNormalisationTests._normalise_tag('###swingshack'), '#swingshack')

    def test_strips_whitespace(self):
        self.assertEqual(HashtagNormalisationTests._normalise_tag('  #swingshack  '), '#swingshack')

    def test_rejects_empty(self):
        self.assertIsNone(HashtagNormalisationTests._normalise_tag(''))
        self.assertIsNone(HashtagNormalisationTests._normalise_tag('   '))
        self.assertIsNone(HashtagNormalisationTests._normalise_tag('#'))

    def test_rejects_non_string(self):
        self.assertIsNone(HashtagNormalisationTests._normalise_tag(None))
        self.assertIsNone(HashtagNormalisationTests._normalise_tag(123))
        self.assertIsNone(HashtagNormalisationTests._normalise_tag([]))


class HashtagApiTests(unittest.TestCase):
    """Integration tests for /api/intel/hashtags."""

    def setUp(self):
        self.client, self.tmp = _isolated_app()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_envelope_shape(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack&platform=instagram'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['pillar'], 'education')
        self.assertEqual(data['voice'], 'swing-shack')
        self.assertEqual(data['platform'], 'instagram')
        self.assertIn('ordered', data)
        self.assertIn('by_category', data)
        self.assertIn('score', data)
        self.assertIn('reasons', data)
        self.assertIn('banned_filtered', data)
        self.assertIn('platform_info', data)
        self.assertIn('ts', data)

    def test_ordered_tags_have_leading_hash(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=club-fitting&voice=bag-drop&platform=tiktok'
        )
        data = resp.get_json()
        self.assertTrue(data['ok'])
        for tag in data['ordered']:
            self.assertTrue(tag.startswith('#'), f"Tag {tag} missing leading #")

    def test_ordered_no_duplicates(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=community&voice=stick&platform=facebook'
        )
        data = resp.get_json()
        self.assertEqual(len(data['ordered']), len(set(data['ordered'])))

    def test_banned_filter_excludes(self):
        """No banned tag should appear in the ordered output."""
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack'
        )
        data = resp.get_json()
        banned = set(data['banned_filtered'])
        for tag in data['ordered']:
            self.assertNotIn(tag, banned, f"Banned tag {tag} leaked into output")

    def test_banned_only_returns_banned(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack&banned_only=1'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertNotIn('ordered', data)
        self.assertGreater(len(data['banned_filtered']), 0)
        for tag in data['banned_filtered']:
            self.assertTrue(tag.startswith('#'))

    def test_all_pillars(self):
        for pillar in ('education', 'club-fitting', 'community', 'events'):
            with self.subTest(pillar=pillar):
                resp = self.client.get(
                    f'/api/intel/hashtags?pillar={pillar}&voice=swing-shack&platform=instagram'
                )
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertTrue(data['ok'])
                self.assertEqual(data['pillar'], pillar)
                # at least one tag for every pillar
                self.assertGreater(len(data['ordered']), 0)

    def test_all_voices(self):
        for voice in ('swing-shack', 'stick', 'bag-drop'):
            with self.subTest(voice=voice):
                resp = self.client.get(
                    f'/api/intel/hashtags?pillar=education&voice={voice}&platform=instagram'
                )
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertTrue(data['ok'])
                self.assertEqual(data['voice'], voice)

    def test_all_platforms(self):
        for platform in ('instagram', 'tiktok', 'facebook', 'twitter', 'gmb'):
            with self.subTest(platform=platform):
                resp = self.client.get(
                    f'/api/intel/hashtags?pillar=education&voice=swing-shack&platform={platform}'
                )
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertTrue(data['ok'])
                self.assertEqual(data['platform'], platform)

    def test_gmb_returns_empty(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack&platform=gmb'
        )
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['ordered'], [])

    def test_count_cap(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack&platform=instagram&count=3'
        )
        data = resp.get_json()
        self.assertLessEqual(len(data['ordered']), 3)
        self.assertEqual(data['count'], len(data['ordered']))

    def test_count_respects_platform_max(self):
        """twitter has max=3; even if we ask for 30, we should get ≤ 3."""
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack&platform=twitter&count=30'
        )
        data = resp.get_json()
        self.assertLessEqual(len(data['ordered']), 3)

    def test_search_filter(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=club-fitting&voice=stick&platform=instagram&search=jhb'
        )
        data = resp.get_json()
        self.assertTrue(data['ok'])
        for tag in data['ordered']:
            self.assertIn('jhb', tag.lower())

    def test_include_trending_zero(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=club-fitting&voice=bag-drop&platform=instagram&include_trending=0'
        )
        data = resp.get_json()
        # trending should be empty in by_category
        self.assertEqual(data['by_category']['trending'], [])

    def test_invalid_pillar(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=NOPE&voice=swing-shack'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['ok'])
        self.assertIn('pillar', data['error'])

    def test_invalid_voice(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=NOPE'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['ok'])
        self.assertIn('voice', data['error'])

    def test_invalid_platform(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack&platform=myspace'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['ok'])
        self.assertIn('platform', data['error'])

    def test_invalid_count(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack&count=foo'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['ok'])

    def test_missing_pillar(self):
        resp = self.client.get('/api/intel/hashtags?voice=swing-shack')
        self.assertEqual(resp.status_code, 400)

    def test_missing_voice(self):
        resp = self.client.get('/api/intel/hashtags?pillar=education')
        self.assertEqual(resp.status_code, 400)

    def test_score_in_range(self):
        for pillar in ('education', 'club-fitting', 'community', 'events'):
            for voice in ('swing-shack', 'stick', 'bag-drop'):
                for platform in ('instagram', 'tiktok', 'twitter', 'gmb'):
                    with self.subTest(pillar=pillar, voice=voice, platform=platform):
                        resp = self.client.get(
                            f'/api/intel/hashtags?pillar={pillar}&voice={voice}&platform={platform}'
                        )
                        data = resp.get_json()
                        self.assertTrue(data['ok'])
                        self.assertGreaterEqual(data['score'], 0)
                        self.assertLessEqual(data['score'], 100)

    def test_by_category_keys_present(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack'
        )
        data = resp.get_json()
        for key in ('brand', 'pillar_core', 'pillar_long_tail',
                    'pillar_local', 'pillar_community', 'voice_vocab', 'trending'):
            self.assertIn(key, data['by_category'])

    def test_brand_tag_present(self):
        resp = self.client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack'
        )
        data = resp.get_json()
        self.assertIn('#swingshack', data['by_category']['brand'])


class SeoPackApiTests(unittest.TestCase):
    """Integration tests for /api/intel/seo_pack (GET + POST)."""

    def setUp(self):
        self.client, self.tmp = _isolated_app()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_envelope_shape_get(self):
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=education&voice=swing-shack'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['pillar'], 'education')
        self.assertEqual(data['voice'], 'swing-shack')
        self.assertIn('pack', data)
        self.assertIn('ts', data)

    def test_pack_keys(self):
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=community&voice=bag-drop'
        )
        data = resp.get_json()
        pack = data['pack']
        for key in ('page_title', 'meta_description', 'h1', 'slug',
                    'alt_text', 'og_description', 'schema_type',
                    'primary_keyword', 'secondary_keywords', 'score',
                    'reasons', 'slug_rules', 'alt_text_rules'):
            self.assertIn(key, pack)

    def test_post_works(self):
        resp = self.client.post(
            '/api/intel/seo_pack',
            json={'pillar': 'events', 'voice': 'stick'},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['pack']['pillar'], 'events')

    def test_post_custom_keyword(self):
        resp = self.client.post(
            '/api/intel/seo_pack',
            json={
                'pillar': 'education', 'voice': 'swing-shack',
                'custom_keyword': 'golf lessons randburg',
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['pack']['primary_keyword'], 'golf lessons randburg')

    def test_page_title_under_70_chars(self):
        for pillar in ('education', 'club-fitting', 'community', 'events'):
            with self.subTest(pillar=pillar):
                resp = self.client.get(
                    f'/api/intel/seo_pack?pillar={pillar}&voice=swing-shack'
                )
                data = resp.get_json()
                self.assertLessEqual(data['pack']['page_title_length'], 70)

    def test_meta_description_in_range(self):
        for pillar in ('education', 'club-fitting', 'community', 'events'):
            with self.subTest(pillar=pillar):
                resp = self.client.get(
                    f'/api/intel/seo_pack?pillar={pillar}&voice=swing-shack'
                )
                data = resp.get_json()
                # should aim for 110..160
                self.assertGreaterEqual(data['pack']['meta_description_length'], 110)
                self.assertLessEqual(data['pack']['meta_description_length'], 160)

    def test_slug_well_formed(self):
        for pillar in ('education', 'club-fitting', 'community', 'events'):
            with self.subTest(pillar=pillar):
                resp = self.client.get(
                    f'/api/intel/seo_pack?pillar={pillar}&voice=swing-shack'
                )
                data = resp.get_json()
                slug = data['pack']['slug']
                self.assertNotIn(' ', slug)
                self.assertTrue(slug.replace('-', '').replace('_', '').isalnum())
                self.assertLessEqual(len(slug), 60)

    def test_alt_text_sized(self):
        for pillar in ('education', 'club-fitting', 'community', 'events'):
            with self.subTest(pillar=pillar):
                resp = self.client.get(
                    f'/api/intel/seo_pack?pillar={pillar}&voice=swing-shack'
                )
                data = resp.get_json()
                alt = data['pack']['alt_text']
                self.assertGreaterEqual(len(alt), 20)
                self.assertLessEqual(len(alt), 125)

    def test_schema_type_per_pillar(self):
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=education&voice=swing-shack'
        )
        self.assertIn('LocalBusiness', resp.get_json()['pack']['schema_type'])

    def test_score_in_range(self):
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=club-fitting&voice=stick'
        )
        score = resp.get_json()['pack']['score']
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_score_above_threshold_for_known_pillar(self):
        """For a known pillar the score should be high (most criteria met)."""
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=education&voice=swing-shack'
        )
        score = resp.get_json()['pack']['score']
        self.assertGreaterEqual(score, 80)

    def test_invalid_pillar(self):
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=NOPE&voice=swing-shack'
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_voice(self):
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=education&voice=NOPE'
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_invalid_pillar(self):
        resp = self.client.post(
            '/api/intel/seo_pack',
            json={'pillar': 'invalid', 'voice': 'swing-shack'},
        )
        self.assertEqual(resp.status_code, 400)

    def test_secondary_keywords_present(self):
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=club-fitting&voice=swing-shack'
        )
        data = resp.get_json()
        self.assertGreater(len(data['pack']['secondary_keywords']), 0)

    def test_primary_keyword_in_meta_description(self):
        """At least one of the primary keyword tokens should appear in meta description."""
        resp = self.client.get(
            '/api/intel/seo_pack?pillar=education&voice=swing-shack'
        )
        data = resp.get_json()
        meta = data['pack']['meta_description'].lower()
        primary_tokens = data['pack']['primary_keyword'].lower().split()
        matches = [t for t in primary_tokens if t in meta]
        self.assertGreater(len(matches), 0,
                           f"No primary keyword token found in meta: {meta}")


class SeoIndexApiTests(unittest.TestCase):
    """Integration tests for /api/intel/seo_index."""

    def setUp(self):
        self.client, self.tmp = _isolated_app()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_envelope_shape(self):
        resp = self.client.get('/api/intel/seo_index')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        for key in ('brand', 'voices', 'pillars', 'platforms',
                    'trending_signals', 'banned', 'stats'):
            self.assertIn(key, data)

    def test_pillars_listed(self):
        resp = self.client.get('/api/intel/seo_index')
        data = resp.get_json()
        self.assertEqual(set(data['pillars'].keys()),
                         {'education', 'club-fitting', 'community', 'events'})

    def test_voices_listed(self):
        resp = self.client.get('/api/intel/seo_index')
        data = resp.get_json()
        self.assertEqual(set(data['voices'].keys()),
                         {'swing-shack', 'stick', 'bag-drop'})

    def test_platforms_listed(self):
        resp = self.client.get('/api/intel/seo_index')
        data = resp.get_json()
        self.assertEqual(set(data['platforms'].keys()),
                         {'instagram', 'tiktok', 'facebook', 'twitter', 'gmb'})

    def test_stats_have_expected_keys(self):
        resp = self.client.get('/api/intel/seo_index')
        data = resp.get_json()
        for key in ('tags_total', 'pillars', 'voices', 'platforms',
                    'trending_signals', 'banned_tags'):
            self.assertIn(key, data['stats'])


class BundledFallbackTests(unittest.TestCase):
    """Verify the engine loads bundled data when DATA_DIR has no file."""

    def test_loads_from_bundled_when_data_dir_empty(self):
        import tempfile
        empty = tempfile.mkdtemp(prefix='campaign-os-empty-')
        os.environ['DATA_DIR'] = empty
        import app as app_module
        if hasattr(app_module, '_load_hashtag_seo'):
            app_module._load_hashtag_seo.cache_clear()
        pack = app_module._load_hashtag_seo()
        # bundled data should always be present
        self.assertGreater(len(pack.get('pillars') or {}), 0)
        self.assertGreater(len(pack.get('voices') or {}), 0)
        self.assertGreater(len(pack.get('platforms') or {}), 0)
        # engine still serves requests
        client = app_module.app.test_client()
        resp = client.get(
            '/api/intel/hashtags?pillar=education&voice=swing-shack&platform=instagram'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        import shutil
        shutil.rmtree(empty, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()