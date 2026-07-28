"""Tests for the SEO Audit Detail engine.

Covers:
  - health-score band logic
  - audit detail endpoint envelope + filters (page / type / severity / only_fixable)
  - by_page / by_severity / by_type aggregation
  - recommendations and top_priority_actions shaping
  - fix-draft endpoint with all 4 templates (meta_description, h1, title_too_short, faq)
  - character-count validation in fix snippets
  - custom_keyword override
  - index endpoint (manifest for SPA picker)
  - bundled fallback when DATA_DIR is empty (404 + graceful index)
  - error envelopes (400 for invalid filters, missing fields, unknown page/type)
"""
import json
import os
import shutil
import sys
import tempfile
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
    Bundled fallback is exercised when DATA_DIR is empty — that's the
    BundledFallbackTests target.
    """
    tmp = tempfile.mkdtemp(prefix='campaign-os-seo-audit-test-')
    os.environ['DATA_DIR'] = tmp
    import app as app_module
    return app_module.app.test_client(), tmp


def _isolated_app_empty():
    """Like _isolated_app but with no bundled fallback (forces 404)."""
    tmp = tempfile.mkdtemp(prefix='campaign-os-seo-audit-empty-')
    os.environ['DATA_DIR'] = tmp
    import app as app_module
    # Stash the bundled data dir to a non-existent location to force 404
    original = getattr(app_module, 'BUNDLED_DATA_DIR', None)
    app_module.BUNDLED_DATA_DIR = tmp + '/_no_bundled'
    try:
        yield app_module.app.test_client(), tmp
    finally:
        app_module.BUNDLED_DATA_DIR = original


class SeoScoreTests(unittest.TestCase):
    """Unit tests for `_seo_audit_score`."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls._score = app_module._seo_audit_score

    def test_empty_audit_returns_zero(self):
        self.assertEqual(SeoScoreTests._score({}), 0)

    def test_healthy_audit_no_findings_returns_full(self):
        audit = {'recommendations': [], 'pages': [{'status': 'OK'}, {'status': 'OK'}]}
        # No findings means no deduction + 10 status bonus = clamp 100
        self.assertEqual(SeoScoreTests._score(audit), 100)

    def test_high_finding_deducts_15(self):
        audit = {'recommendations': [{'severity': 'high'}]}
        self.assertEqual(SeoScoreTests._score(audit), 85)

    def test_medium_finding_deducts_8(self):
        audit = {'recommendations': [{'severity': 'medium'}]}
        self.assertEqual(SeoScoreTests._score(audit), 92)

    def test_low_finding_deducts_3(self):
        audit = {'recommendations': [{'severity': 'low'}]}
        self.assertEqual(SeoScoreTests._score(audit), 97)

    def test_mixed_findings(self):
        audit = {'recommendations': [
            {'severity': 'high'}, {'severity': 'medium'},
            {'severity': 'medium'}, {'severity': 'low'},
        ]}
        # 100 - 15 - 8 - 8 - 3 = 66
        self.assertEqual(SeoScoreTests._score(audit), 66)

    def test_clamped_at_zero(self):
        audit = {'recommendations': [{'severity': 'high'}] * 20}
        self.assertEqual(SeoScoreTests._score(audit), 0)

    def test_clamped_at_100(self):
        audit = {'recommendations': [], 'pages': [{'status': 'OK'}] * 5}
        self.assertEqual(SeoScoreTests._score(audit), 100)

    def test_severity_case_insensitive(self):
        audit = {'recommendations': [{'severity': 'HIGH'}]}
        self.assertEqual(SeoScoreTests._score(audit), 85)

    def test_status_bonus_only_when_all_ok(self):
        audit = {'recommendations': [], 'pages': [{'status': 'OK'}, {'status': 'FAIL'}]}
        # No bonus because not all OK; no deductions; result = 100
        self.assertEqual(SeoScoreTests._score(audit), 100)


class SeoGroupByPageTests(unittest.TestCase):
    """Unit tests for `_seo_audit_group_by_page`."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls._group = app_module._seo_audit_group_by_page

    def test_returns_list(self):
        audit = {'pages': []}
        out = SeoGroupByPageTests._group(audit)
        self.assertIsInstance(out, list)

    def test_each_page_has_required_keys(self):
        audit = {'pages': [{
            'name': 'Homepage', 'url': 'https://example.com', 'status': 'OK',
            'findings': [{'type': 'missing_h1', 'severity': 'high', 'message': 'No H1'}],
        }]}
        out = SeoGroupByPageTests._group(audit)
        self.assertEqual(len(out), 1)
        p = out[0]
        for key in ('page', 'url', 'status', 'findings', 'counts', 'score'):
            self.assertIn(key, p)
        self.assertEqual(p['page'], 'Homepage')
        self.assertEqual(p['counts']['high'], 1)
        self.assertEqual(p['counts']['medium'], 0)

    def test_sort_high_first(self):
        audit = {'pages': [
            {'name': 'A', 'findings': [{'type': 'missing_h1', 'severity': 'low', 'message': 'x'}]},
            {'name': 'B', 'findings': [{'type': 'missing_h1', 'severity': 'high', 'message': 'x'}]},
            {'name': 'C', 'findings': [{'type': 'missing_h1', 'severity': 'medium', 'message': 'x'}]},
        ]}
        out = SeoGroupByPageTests._group(audit)
        self.assertEqual([p['page'] for p in out], ['B', 'C', 'A'])

    def test_skips_non_dict_pages(self):
        audit = {'pages': [
            {'name': 'A', 'findings': []},
            'not-a-dict',
            None,
        ]}
        out = SeoGroupByPageTests._group(audit)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['page'], 'A')


class SeoFixTemplateTests(unittest.TestCase):
    """Unit tests for `_seo_fix_template`."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls._fix = app_module._seo_fix_template

    def test_meta_description_in_range(self):
        f = SeoFixTemplateTests._fix({'page': 'Homepage'}, 'missing_meta_description')
        self.assertEqual(f['kind'], 'meta_description')
        self.assertTrue(110 <= f['character_count'] <= 160, f"chars={f['character_count']}")
        self.assertTrue(f['valid'])

    def test_h1_in_range(self):
        f = SeoFixTemplateTests._fix({'page': 'Membership'}, 'missing_h1')
        self.assertEqual(f['kind'], 'h1')
        self.assertTrue(20 <= f['character_count'] <= 70, f"chars={f['character_count']}")
        self.assertTrue(f['valid'])
        self.assertIn('Swing Shack', f['snippet'])

    def test_title_in_range(self):
        f = SeoFixTemplateTests._fix({'page': 'Coaching'}, 'title_too_short')
        self.assertEqual(f['kind'], 'title')
        self.assertTrue(50 <= f['character_count'] <= 60, f"chars={f['character_count']}")
        self.assertTrue(f['valid'])
        self.assertIn('Swing Shack', f['snippet'])

    def test_faq_block(self):
        f = SeoFixTemplateTests._fix({'page': 'Homepage'}, 'missing_faq')
        self.assertEqual(f['kind'], 'faq_block')
        self.assertTrue(f['character_count'] >= 200)
        self.assertIn('How much', f['snippet'])
        self.assertIn('Swing Shack', f['snippet'])

    def test_custom_keyword(self):
        f = SeoFixTemplateTests._fix(
            {'page': 'Membership'}, 'missing_h1', custom_keyword='TrackMan simulator'
        )
        self.assertIn('Trackman Simulator', f['snippet'])

    def test_unknown_type(self):
        f = SeoFixTemplateTests._fix({'page': 'Homepage'}, 'totally_bogus')
        self.assertEqual(f['kind'], 'unknown')
        self.assertEqual(f['character_count'], 0)
        self.assertFalse(f['valid'])

    def test_long_keyword_trims_meta(self):
        f = SeoFixTemplateTests._fix(
            {'page': 'Homepage'}, 'missing_meta_description',
            custom_keyword='very long phrase ' * 20,
        )
        self.assertTrue(f['character_count'] <= 160, f"chars={f['character_count']}")

    def test_long_keyword_trims_title(self):
        f = SeoFixTemplateTests._fix(
            {'page': 'Coaching'}, 'title_too_short',
            custom_keyword='super long phrase ' * 20,
        )
        self.assertTrue(f['character_count'] <= 60, f"chars={f['character_count']}")


class SeoAuditDetailApiTests(unittest.TestCase):
    """Integration tests for /api/intel/seo_audit_detail."""

    def setUp(self):
        self.client, self.tmp = _isolated_app()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_envelope_shape(self):
        r = self.client.get('/api/intel/seo_audit_detail')
        d = r.get_json()
        for key in ('ok', 'ts', 'site', 'updated', 'score', 'band',
                    'total_findings', 'by_severity', 'by_type', 'by_page',
                    'recommendations', 'top_priority_actions',
                    'filters_applied', 'valid_types', 'valid_severities', 'valid_pages'):
            self.assertIn(key, d, f'missing key: {key}')
        self.assertTrue(d['ok'])
        self.assertIn(d['band'], ('healthy', 'needs_attention', 'poor', 'critical'))

    def test_score_in_range(self):
        r = self.client.get('/api/intel/seo_audit_detail')
        d = r.get_json()
        self.assertGreaterEqual(d['score'], 0)
        self.assertLessEqual(d['score'], 100)

    def test_by_severity_shape(self):
        d = self.client.get('/api/intel/seo_audit_detail').get_json()
        self.assertIn('high', d['by_severity'])
        self.assertIn('medium', d['by_severity'])
        self.assertIn('low', d['by_severity'])
        self.assertEqual(sum(d['by_severity'].values()), d['total_findings'])

    def test_by_type_all_known_types(self):
        d = self.client.get('/api/intel/seo_audit_detail').get_json()
        for t in ('missing_meta_description', 'missing_h1', 'title_too_short', 'missing_faq'):
            self.assertIn(t, d['by_type'])

    def test_by_page_includes_all_pages(self):
        d = self.client.get('/api/intel/seo_audit_detail').get_json()
        names = {p['page'] for p in d['by_page']}
        self.assertIn('Homepage', names)
        self.assertIn('Membership', names)
        self.assertIn('Coaching', names)
        self.assertIn('Club Fitting', names)

    def test_page_filter(self):
        d = self.client.get('/api/intel/seo_audit_detail?page=Homepage').get_json()
        self.assertEqual([p['page'] for p in d['by_page']], ['Homepage'])
        for rec in d['recommendations']:
            self.assertEqual(rec['page'], 'Homepage')

    def test_type_filter(self):
        d = self.client.get('/api/intel/seo_audit_detail?type=missing_h1').get_json()
        for rec in d['recommendations']:
            self.assertEqual(rec['type'], 'missing_h1')
        # by_type should reflect filtered set
        self.assertEqual(d['by_type']['missing_h1'], len(d['recommendations']))

    def test_severity_filter(self):
        d = self.client.get('/api/intel/seo_audit_detail?severity=high').get_json()
        for rec in d['recommendations']:
            self.assertEqual(rec['severity'], 'high')
        self.assertEqual(d['by_severity'], {'high': len(d['recommendations']), 'medium': 0, 'low': 0})

    def test_only_fixable_excludes_low(self):
        d = self.client.get('/api/intel/seo_audit_detail?only_fixable=true').get_json()
        sevs = {rec['severity'] for rec in d['recommendations']}
        self.assertNotIn('low', sevs)

    def test_top_priority_actions_only_high(self):
        d = self.client.get('/api/intel/seo_audit_detail').get_json()
        for rec in d['top_priority_actions']:
            self.assertEqual(rec['severity'], 'high')

    def test_recommendation_keys(self):
        d = self.client.get('/api/intel/seo_audit_detail').get_json()
        for rec in d['recommendations']:
            for key in ('type', 'severity', 'message', 'page', 'action', 'priority'):
                self.assertIn(key, rec, f'missing rec key: {key}')

    def test_recommendations_sorted_by_priority_then_page(self):
        d = self.client.get('/api/intel/seo_audit_detail').get_json()
        recs = d['recommendations']
        priorities = [r['priority'] for r in recs]
        self.assertEqual(priorities, sorted(priorities))

    def test_filters_applied_returned(self):
        d = self.client.get('/api/intel/seo_audit_detail?page=Homepage&severity=high').get_json()
        self.assertEqual(d['filters_applied']['page'], 'Homepage')
        self.assertEqual(d['filters_applied']['severity'], 'high')
        self.assertFalse(d['filters_applied']['only_fixable'])

    def test_invalid_page_400(self):
        r = self.client.get('/api/intel/seo_audit_detail?page=NotAPage')
        self.assertEqual(r.status_code, 400)
        d = r.get_json()
        self.assertFalse(d['ok'])
        self.assertIn('valid_pages', d)
        self.assertIn('Homepage', d['valid_pages'])

    def test_invalid_type_400(self):
        r = self.client.get('/api/intel/seo_audit_detail?type=bogus')
        self.assertEqual(r.status_code, 400)
        d = r.get_json()
        self.assertIn('valid_types', d)

    def test_invalid_severity_400(self):
        r = self.client.get('/api/intel/seo_audit_detail?severity=extreme')
        self.assertEqual(r.status_code, 400)

    def test_combine_filters(self):
        d = self.client.get(
            '/api/intel/seo_audit_detail?page=Coaching&type=title_too_short&severity=medium'
        ).get_json()
        for rec in d['recommendations']:
            self.assertEqual(rec['page'], 'Coaching')
            self.assertEqual(rec['type'], 'title_too_short')
            self.assertEqual(rec['severity'], 'medium')


class SeoFixDraftApiTests(unittest.TestCase):
    """Integration tests for /api/intel/seo_audit_fix_draft."""

    def setUp(self):
        self.client, self.tmp = _isolated_app()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_meta_description_template(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Homepage', 'type': 'missing_meta_description'},
        )
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d['ok'])
        self.assertEqual(d['page'], 'Homepage')
        self.assertEqual(d['type'], 'missing_meta_description')
        self.assertIn('action', d)
        self.assertEqual(d['fix']['kind'], 'meta_description')
        self.assertTrue(d['fix']['valid'])

    def test_h1_template(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Membership', 'type': 'missing_h1'},
        )
        d = r.get_json()
        self.assertEqual(d['fix']['kind'], 'h1')
        self.assertTrue(d['fix']['valid'])

    def test_title_template(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Coaching', 'type': 'title_too_short'},
        )
        d = r.get_json()
        self.assertEqual(d['fix']['kind'], 'title')
        self.assertTrue(d['fix']['valid'])

    def test_faq_template(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Homepage', 'type': 'missing_faq'},
        )
        d = r.get_json()
        self.assertEqual(d['fix']['kind'], 'faq_block')
        self.assertGreaterEqual(d['fix']['character_count'], 200)

    def test_custom_keyword_override(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Homepage', 'type': 'missing_h1', 'custom_keyword': 'TrackMan simulator'},
        )
        d = r.get_json()
        self.assertIn('Trackman Simulator', d['fix']['snippet'])

    def test_missing_page_400(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': '', 'type': 'missing_h1'},
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()['ok'])

    def test_missing_type_400(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Homepage', 'type': ''},
        )
        self.assertEqual(r.status_code, 400)

    def test_invalid_type_400(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Homepage', 'type': 'totally_bogus'},
        )
        self.assertEqual(r.status_code, 400)
        d = r.get_json()
        self.assertIn('valid_types', d)

    def test_unknown_page_404(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'NotReal', 'type': 'missing_h1'},
        )
        self.assertEqual(r.status_code, 404)
        d = r.get_json()
        self.assertIn('valid_pages', d)

    def test_non_string_keyword_400(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Homepage', 'type': 'missing_h1', 'custom_keyword': 123},
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()['ok'])

    def test_no_body_400(self):
        r = self.client.post('/api/intel/seo_audit_fix_draft', data='')
        self.assertEqual(r.status_code, 400)

    def test_meta_long_keyword_still_valid(self):
        r = self.client.post(
            '/api/intel/seo_audit_fix_draft',
            json={'page': 'Homepage', 'type': 'missing_meta_description',
                  'custom_keyword': 'super long phrase ' * 15},
        )
        d = r.get_json()
        self.assertLessEqual(d['fix']['character_count'], 160)
        self.assertTrue(d['fix']['valid'])

    def test_fix_snippet_includes_brand(self):
        """Every fix template should mention 'Swing Shack'."""
        for ftype in ('missing_meta_description', 'missing_h1', 'title_too_short', 'missing_faq'):
            r = self.client.post(
                '/api/intel/seo_audit_fix_draft',
                json={'page': 'Homepage', 'type': ftype},
            )
            d = r.get_json()
            self.assertIn('Swing Shack', d['fix']['snippet'], f"missing brand in {ftype}")


class SeoAuditIndexApiTests(unittest.TestCase):
    """Integration tests for /api/intel/seo_audit_index."""

    def setUp(self):
        self.client, self.tmp = _isolated_app()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_envelope_shape(self):
        r = self.client.get('/api/intel/seo_audit_index')
        d = r.get_json()
        for key in ('ok', 'ts', 'site', 'updated', 'score',
                    'total_findings', 'pages', 'types', 'severities',
                    'action_map', 'landing_fixes_summary', 'landing_fixes'):
            self.assertIn(key, d)
        self.assertTrue(d['ok'])

    def test_pages_list(self):
        d = self.client.get('/api/intel/seo_audit_index').get_json()
        self.assertIn('Homepage', d['pages'])
        self.assertIn('Membership', d['pages'])
        self.assertIn('Coaching', d['pages'])
        self.assertIn('Club Fitting', d['pages'])

    def test_types_list(self):
        d = self.client.get('/api/intel/seo_audit_index').get_json()
        self.assertEqual(set(d['types']),
                         {'missing_meta_description', 'missing_h1', 'title_too_short', 'missing_faq'})

    def test_action_map_has_all_types(self):
        d = self.client.get('/api/intel/seo_audit_index').get_json()
        for t in d['types']:
            self.assertIn(t, d['action_map'])

    def test_landing_fixes_summary(self):
        d = self.client.get('/api/intel/seo_audit_index').get_json()
        summary = d['landing_fixes_summary']
        self.assertIn('total', summary)
        self.assertIn('high_severity', summary)

    def test_landing_fixes_includes_records(self):
        d = self.client.get('/api/intel/seo_audit_index').get_json()
        self.assertGreater(len(d['landing_fixes']), 0)
        fix = d['landing_fixes'][0]
        for key in ('page', 'issue', 'fix', 'severity'):
            self.assertIn(key, fix)


class BundledFallbackTests(unittest.TestCase):
    """Verify endpoints gracefully fall back to bundled data (or return 404)."""

    def setUp(self):
        # Use empty DATA_DIR but rely on bundled fallback
        self.client, self.tmp = _isolated_app()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detail_uses_bundled(self):
        """When DATA_DIR has no audit, fall back to bundled seo-audit.json."""
        d = self.client.get('/api/intel/seo_audit_detail').get_json()
        # Bundled data should give us a usable audit
        self.assertTrue(d['ok'])
        self.assertGreater(d['total_findings'], 0)
        self.assertIn('Homepage', d['valid_pages'])

    def test_index_uses_bundled(self):
        d = self.client.get('/api/intel/seo_audit_index').get_json()
        self.assertTrue(d['ok'])
        self.assertGreater(len(d['pages']), 0)


if __name__ == '__main__':
    unittest.main()