"""Tests for theme preferences + CSS token manifest.

Covers:
  GET  /api/intel/theme         — read current theme + supported values
  POST /api/intel/theme         — persist user's theme (dark / light / system)
  GET  /api/intel/tokens        — token manifest (design-system audit endpoint)
  campaign-os.html              — CSS structure (data-theme blocks, switcher UI,
                                  localStorage key, no raw hex outside the
                                  theme block)
"""
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class ThemeApiTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.old = os.environ.get('DATA_DIR')
        os.environ['DATA_DIR'] = self.t.name
        self.c = app.test_client()

    def tearDown(self):
        if self.old is None:
            os.environ.pop('DATA_DIR', None)
        else:
            os.environ['DATA_DIR'] = self.old
        self.t.cleanup()

    # ---- GET /api/intel/theme -----------------------------------------

    def test_get_default_envelope(self):
        r = self.c.get('/api/intel/theme')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b['ok'])
        self.assertIn('theme', b)
        self.assertIn('supported', b)
        self.assertIn('default', b)
        self.assertIn('history', b)

    def test_get_default_theme_is_dark(self):
        b = self.c.get('/api/intel/theme').get_json()
        self.assertEqual(b['theme'], 'dark')
        self.assertEqual(b['default'], 'dark')
        self.assertEqual(set(b['supported']), {'dark', 'light', 'system'})
        self.assertEqual(b['history'], [])

    def test_get_history_bounded(self):
        # Cycle through themes many times; history must stay bounded
        for cycle in range(25):
            for v in ('light', 'dark', 'system', 'light'):
                self.c.post('/api/intel/theme', json={'theme': v})
        b = self.c.get('/api/intel/theme').get_json()
        self.assertIsInstance(b['history'], list)
        self.assertLessEqual(len(b['history']), 20)
        for entry in b['history']:
            self.assertIn('theme', entry)
            self.assertIn('ts', entry)
            self.assertIn(entry['theme'], {'dark', 'light', 'system'})

    # ---- POST /api/intel/theme ----------------------------------------

    def test_set_persists(self):
        r = self.c.post('/api/intel/theme', json={'theme': 'light'})
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b['ok'])
        self.assertEqual(b['theme'], 'light')
        self.assertIn('ts', b)
        self.assertIn('history', b)
        # Reload via GET
        b2 = self.c.get('/api/intel/theme').get_json()
        self.assertEqual(b2['theme'], 'light')

    def test_set_system(self):
        r = self.c.post('/api/intel/theme', json={'theme': 'system'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['theme'], 'system')

    def test_set_invalid_returns_400(self):
        # Truly invalid (not just wrong-case — endpoint normalises to lower)
        for bad in ('neon', '', '   ', 'drak', 'midnight', 'solarized', None, 42, [], {'theme': 'light'}):
            r = self.c.post('/api/intel/theme', json={'theme': bad})
            self.assertEqual(r.status_code, 400, msg=f"theme={bad!r}")
            b = r.get_json()
            self.assertFalse(b['ok'])
            self.assertIn('error', b)
            self.assertIn('supported', b)
            self.assertEqual(set(b['supported']), {'dark', 'light', 'system'})

    def test_set_no_body_returns_400(self):
        r = self.c.post('/api/intel/theme')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()['ok'])

    def test_no_op_does_not_grow_history(self):
        self.c.post('/api/intel/theme', json={'theme': 'light'})
        # Setting same value twice should not append
        self.c.post('/api/intel/theme', json={'theme': 'light'})
        h = self.c.get('/api/intel/theme').get_json()['history']
        self.assertEqual(len(h), 1, f"history should record only the first transition, got {h}")

    def test_transitions_recorded(self):
        self.c.post('/api/intel/theme', json={'theme': 'light'})   # dark→light
        self.c.post('/api/intel/theme', json={'theme': 'system'})  # light→system
        h = self.c.get('/api/intel/theme').get_json()['history']
        # History records the FROM value of each transition
        self.assertEqual(len(h), 2)
        self.assertEqual(h[0]['theme'], 'dark')
        self.assertEqual(h[1]['theme'], 'light')

    def test_state_file_written(self):
        self.c.post('/api/intel/theme', json={'theme': 'light'})
        # The file should exist on disk
        path = os.path.join(self.t.name, 'theme-preferences.json')
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            state = json.load(f)
        self.assertEqual(state['theme'], 'light')
        self.assertIn('history', state)
        self.assertIn('ts', state)

    def test_corrupted_file_recovers(self):
        # Write garbage; loader should fall back to default safely
        path = os.path.join(self.t.name, 'theme-preferences.json')
        with open(path, 'w') as f:
            f.write('{"theme": "neon", "history": "not-a-list"}')
        b = self.c.get('/api/intel/theme').get_json()
        self.assertTrue(b['ok'])
        self.assertEqual(b['theme'], 'dark')
        self.assertEqual(b['history'], [])


class TokensApiTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.old = os.environ.get('DATA_DIR')
        os.environ['DATA_DIR'] = self.t.name
        self.c = app.test_client()

    def tearDown(self):
        if self.old is None:
            os.environ.pop('DATA_DIR', None)
        else:
            os.environ['DATA_DIR'] = self.old
        self.t.cleanup()

    def test_tokens_envelope(self):
        r = self.c.get('/api/intel/tokens')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b['ok'])
        self.assertIn('tokens', b)
        self.assertIn('token_count', b)
        self.assertIn('default_theme', b)
        self.assertIn('supported_themes', b)
        self.assertEqual(b['default_theme'], 'dark')
        self.assertEqual(set(b['supported_themes']), {'dark', 'light', 'system'})

    def test_tokens_shape(self):
        b = self.c.get('/api/intel/tokens').get_json()
        for tok in b['tokens']:
            for k in ('name', 'kind', 'dark', 'light', 'purpose'):
                self.assertIn(k, tok, msg=f"token missing {k}: {tok}")
            self.assertTrue(tok['name'].startswith('--'))
        self.assertEqual(b['token_count'], len(b['tokens']))

    def test_tokens_include_core_palette(self):
        b = self.c.get('/api/intel/tokens').get_json()
        names = {t['name'] for t in b['tokens']}
        # Must expose surface scale + accent + text + geometry
        for required in ('--bg', '--bg-2', '--bd', '--tx', '--ac', '--blu',
                         '--red', '--r', '--r-p', '--t'):
            self.assertIn(required, names, msg=f"missing core token {required}")

    def test_tokens_dark_and_light_differ(self):
        b = self.c.get('/api/intel/tokens').get_json()
        for tok in b['tokens']:
            if tok['kind'] in ('geometry', 'motion'):
                continue
            self.assertNotEqual(
                tok['dark'], tok['light'],
                msg=f"token {tok['name']} has same dark/light value"
            )

    def test_tokens_hex_format(self):
        b = self.c.get('/api/intel/tokens').get_json()
        hex_re = re.compile(r'^#[0-9a-fA-F]{3,8}$')
        for tok in b['tokens']:
            if tok['kind'] in ('geometry', 'motion'):
                continue
            self.assertRegex(tok['dark'], hex_re, msg=f"dark not hex: {tok}")
            self.assertRegex(tok['light'], hex_re, msg=f"light not hex: {tok}")


class ThemeCssStructureTests(unittest.TestCase):
    """Static checks against campaign-os.html — guards the design system."""

    @classmethod
    def setUpClass(cls):
        cls.html_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'campaign-os.html'
        )
        cls.html = _read(cls.html_path)
        # Just the <style> block
        m = re.search(r'<style>(.*?)</style>', cls.html, re.S)
        if not m:
            raise RuntimeError("no <style> block found in campaign-os.html")
        cls.css = m.group(1)

    def test_has_dark_theme_block(self):
        self.assertIn('[data-theme="dark"]', self.css)

    def test_has_light_theme_block(self):
        self.assertIn('[data-theme="light"]', self.css)

    def test_has_prefers_color_schemes(self):
        self.assertIn('prefers-color-scheme: light', self.css)

    def test_has_theme_switcher_dom(self):
        self.assertIn('id="theme-switch"', self.html)
        for v in ('dark', 'light', 'system'):
            self.assertIn(f'data-theme-val="{v}"', self.html)

    def test_has_init_theme_call(self):
        self.assertIn('initTheme()', self.html)
        self.assertIn('THEME_KEY', self.html)
        self.assertIn('localStorage', self.html)

    def test_has_localstorage_key(self):
        # Must store user choice under a stable key
        self.assertIn("'swing-shack:theme'", self.html)

    def test_meta_theme_color_has_id(self):
        self.assertIn('id="meta-theme-color"', self.html)

    def test_no_raw_hex_outside_theme_blocks(self):
        """No hardcoded colors outside [data-theme=...] blocks in CSS."""
        # Strip theme blocks + :root {} blocks + the meta tag line
        css = self.css
        # Remove :root { ... } blocks
        css = re.sub(r':root\s*\{[^}]*\}', '', css, flags=re.S)
        # Remove [data-theme="..."] { ... } blocks
        css = re.sub(r'\[data-theme="[^"]+"\]\s*\{[^}]*\}', '', css, flags=re.S)
        # Remove @media (prefers-color-scheme: light) { :root { ... } } blocks
        css = re.sub(
            r'@media\s*\(prefers-color-scheme:\s*light\)\s*\{\s*:root[^{]*\{[^}]*\}\s*\}',
            '', css, flags=re.S
        )
        # After stripping, the only hex tokens that should remain are inside
        # `color-mix(in srgb, var(--...) NN%, transparent)` — purely token-driven.
        # No standalone #xxxxxx outside a CSS var declaration is allowed.
        standalone = re.findall(r'(?<![\w-])#[0-9a-fA-F]{3,8}\b', css)
        self.assertEqual(
            standalone, [],
            msg=f"Found raw hex outside theme blocks: {standalone[:10]}"
        )

    def test_no_raw_hex_in_js_inline_styles(self):
        """The JS used to inject inline `style="...#xxxxxx..."`; verify it doesn't anymore.

        Acceptable: hex inside string template literals that wraps a CSS var,
        e.g. `${color}` where color is data-driven. Forbidden: literal hex
        like '#34d399' or '#7c5cff' that bypasses the token system.
        """
        # Limit to inside the <script> block
        m = re.search(r'<script>(.*?)</script>', self.html, re.S)
        if not m:
            self.skipTest("no <script> block")
        js = m.group(1)
        # Whitelist: anything inside `style="background:${...}1a..."` (data color alpha)
        # That data flow is for per-asset calendar colors, which are intentionally
        # data-driven. We only need to ensure the *fallback* defaults are tokenized.
        bad = re.findall(r"['\"](#[0-9a-fA-F]{3,8})['\"]", js)
        # Allow only the documentMeta fallback that runs when no theme is applied
        filtered = [c for c in bad if c.lower() not in {'#0a0f1a'}]
        self.assertEqual(
            filtered, [],
            msg=f"Raw hex literal in JS inline styles: {filtered}"
        )

    def test_color_mix_used_for_semantic_palette(self):
        # The era-* and bf-* helpers should use color-mix (theme-aware) not alpha hex
        for cls in ('era-classic', 'era-mid', 'era-recent', 'era-current',
                    'fatigue-low', 'fatigue-medium', 'fatigue-high',
                    'bf-hi', 'bf-md', 'bf-lo', 'bf-zero'):
            self.assertIn(f'.{cls}', self.css, msg=f"missing {cls}")
        # Each should use color-mix (theme-aware) rather than rgba alpha
        for cls in ('era-classic', 'bf-hi'):
            idx = self.css.find(f'.{cls}')
            block = self.css[idx:idx+400]
            self.assertIn('color-mix', block, msg=f"{cls} not using color-mix")
            self.assertNotIn('rgba(', block.split('\n')[0], msg=f"{cls} still using rgba")

    def test_localstorage_isolated_per_app(self):
        # The key is namespaced so it won't collide with other apps on same origin
        self.assertIn("'swing-shack:theme'", self.html)

    def test_theme_switcher_is_in_topbar(self):
        # Should appear in the topbar, alongside search
        topbar_start = self.html.find('class="topbar"')
        switcher = self.html.find('id="theme-switch"')
        self.assertGreater(topbar_start, 0)
        self.assertGreater(switcher, topbar_start,
                           msg="theme switcher should be in topbar, after topbar opens")
        # And before the first section
        first_section = self.html.find('class="section on"')
        self.assertLess(switcher, first_section,
                        msg="theme switcher should be in topbar, before sections")


if __name__ == '__main__':
    unittest.main()
