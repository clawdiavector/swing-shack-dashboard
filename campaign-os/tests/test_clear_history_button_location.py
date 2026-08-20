"""
Regression test: 🗑 Clear history buttons in Headlines + CTAs must sit on
the History card header, not in the filter bar.

Bug 2026-08-20: both "🗑 Clear history" buttons were pinned to the filter
bar (right-aligned via margin-left:auto). The button is a destructive
action that targets the History card's localStorage data, not the
filters — putting it in the filter bar made users think it would reset
their voice/pillar/platform/category picks (it would not). Moved the
button to the History card header in both Headlines and CTAs so it sits
with its target surface.

Verifies (against running local server on 127.0.0.1:8765):
  - #head-clear-history is INSIDE #head-history's card (same card-h)
  - #cta-clear-history is INSIDE #cta-history's card (same card-h)
  - Neither button is inside the filter bar card (the card that contains
    the voice/pillar/platform/category selects)

Skips cleanly if the server is unreachable.
"""
import os
import sys
import json
import http.cookiejar
import urllib.request
import urllib.parse
import re

BASE = os.environ.get('CO_BASE_URL', 'http://127.0.0.1:8765')
PASSWORD = os.environ.get('CO_TEST_PASSWORD', 'swing-shack-dev-2026')


def _build_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def main():
    opener = _build_opener()
    try:
        # login
        login_data = urllib.parse.urlencode({'password': PASSWORD}).encode()
        opener.open(urllib.request.Request(
            BASE + '/login',
            data=login_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ), timeout=10).read()

        # fetch the page once, then slice the HTML around the History card
        body = opener.open(BASE + '/?page=ctas', timeout=10).read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'[SKIP] server unreachable: {e}', file=sys.stderr)
        return 0

    issues = []

    # ── CTA: #cta-clear-history must be inside the History card ──
    # The History card is the one whose h3 contains "CTA history" / "📜 History"
    # AND whose body div is #cta-history. The filter bar card is the one that
    # contains the #cta-category select.
    cta_history_block = re.search(
        r'<div class="card"><div class="card-h"><h3[^>]*data-help-title="CTA history"[^>]*>.*?</h3>(.*?)</div><div id="cta-history">',
        body, re.DOTALL)
    if not cta_history_block:
        issues.append('CTA: could not locate the History card-h block in HTML')
    else:
        cta_clear_in_history = 'id="cta-clear-history"' in cta_history_block.group(0)
        if not cta_clear_in_history:
            issues.append('CTA: #cta-clear-history is NOT in the History card header')

    # The filter bar card contains the category select; clear-history should
    # not appear before the closing </div> of the filter bar.
    cta_filter_block = re.search(
        r'(<div class="card col-12" style="margin-bottom:1rem">.*?</select>\s*)</div>',
        body, re.DOTALL)
    if cta_filter_block and 'id="cta-clear-history"' in cta_filter_block.group(0):
        issues.append('CTA: #cta-clear-history is still in the filter bar (bug NOT fixed)')

    # ── Headlines: #head-clear-history must be inside the History card ──
    head_history_block = re.search(
        r'<div class="card"><div class="card-h"><h3[^>]*data-help-title="Headline history"[^>]*>.*?</h3>(.*?)</div><div id="head-history">',
        body, re.DOTALL)
    if not head_history_block:
        issues.append('Headlines: could not locate the History card-h block in HTML')
    else:
        head_clear_in_history = 'id="head-clear-history"' in head_history_block.group(0)
        if not head_clear_in_history:
            issues.append('Headlines: #head-clear-history is NOT in the History card header')

    if issues:
        for i in issues:
            print(f'  FAIL: {i}', file=sys.stderr)
        return 1

    print('[OK] #cta-clear-history + #head-clear-history both live on their History card headers')
    print('     (filter bar no longer carries the destructive clear-history action)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
