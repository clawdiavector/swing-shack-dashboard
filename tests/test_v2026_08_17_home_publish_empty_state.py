"""Regression test: Home "Ready to publish" empty state is actionable.

Before this fix the card rendered a bare `<li class="empty">Nothing queued
yet</li>` — a dead end on the highest-traffic screen in Campaign OS. It now
renders an icon + title + context-aware subtitle + two working CTAs.

Static test (no browser needed): asserts the markup + handler + CSS are all
present in campaign-os.html. The browser-level assertions (CTA actually
navigates, no page errors) are covered by the nightshift Playwright walkthrough.
"""
import os
import re
import unittest

HTML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'campaign-os', 'campaign-os.html')


class TestHomePublishEmptyState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(HTML_PATH, encoding='utf-8') as f:
            cls.src = f.read()

    def test_dead_end_empty_state_is_gone(self):
        """The bare 'Nothing queued yet' dead-end must not come back."""
        self.assertNotIn(
            '<li class="empty">Nothing queued yet</li>', self.src,
            'the non-actionable Home publish empty state has regressed')

    def test_empty_state_markup_present(self):
        self.assertIn('data-home-empty="publish"', self.src)
        self.assertIn('Nothing approved and waiting', self.src)
        self.assertIn('class="empty home-empty-state"', self.src)

    def test_all_three_ctas_wired(self):
        """Each data-home-empty-action value must have a matching go() branch."""
        actions = set(re.findall(r'data-home-empty-action="([a-z]+)"', self.src))
        # 'review' and 'create' are mutually exclusive primaries (review shows
        # when drafts are waiting, create when the queue is fully empty);
        # 'calendar' is the always-present secondary.
        self.assertEqual(actions, {'review', 'create', 'calendar'},
                         f'unexpected CTA action set: {actions}')
        handler = re.search(
            r"const action = btn\.getAttribute\('data-home-empty-action'\);"
            r"(.*?)\}\);", self.src, re.S)
        self.assertIsNotNone(handler, 'delegated click handler not found')
        body = handler.group(1)
        for action, section in (('review', 'review'),
                                ('create', 'create'),
                                ('calendar', 'calendar')):
            self.assertIn(f"go('{section}')", body,
                          f'no go() branch for action {action!r}')

    def test_handler_is_delegated_not_direct(self):
        """renderBrief() rebuilds the card's innerHTML, so binding must be
        delegated on document, otherwise the CTAs die on the next refresh."""
        self.assertIn(
            "document.addEventListener('click', (e) => {\n"
            "  const btn = e.target.closest('[data-home-empty-action]');",
            self.src,
            'CTA handler is not delegated on document')

    def test_subtitle_is_context_aware(self):
        """Copy must branch on review.length rather than hardcode a number."""
        self.assertIn('${review.length > 0', self.src)
        self.assertIn('still need your sign-off', self.src)
        self.assertIn('No drafts in review either', self.src)

    def test_css_beats_the_has_selector_specificity(self):
        """`.card:has(> ul > li.empty:only-child) li.empty` forces italic and
        strips padding. The override must be present or the card renders
        as squashed italic text."""
        self.assertIn(
            '.card:has(> ul > li.home-empty-state:only-child) li.home-empty-state',
            self.src, 'specificity override for the :has() rule is missing')
        self.assertIn('.home-empty-state{font-style:normal', self.src)

    def test_no_em_dash_in_user_facing_copy(self):
        """Standing rule: em dash banned in published copy."""
        block = re.search(r'data-home-empty="publish".*?</li>`', self.src, re.S)
        self.assertIsNotNone(block)
        self.assertNotIn('\u2014', block.group(0),
                         'em dash found in Home empty-state copy')


if __name__ == '__main__':
    unittest.main()
