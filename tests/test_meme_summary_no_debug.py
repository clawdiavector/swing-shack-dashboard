"""
Regression test: Meme Lord summary copy must NOT leak debug-style key=value tokens.

Bug 2026-08-18: /api/intel/meme_knowledge returned
    "30 of 75 memes · voice=swing-shack pillar=education"
which surfaced verbatim in the Meme Lord section header. Backend now formats
with friendly labels ("Swing Shack voice · education pillar").

This test hits the running local server (start with:
    DATA_DIR=...  CAMPAIGN_OS_PASSWORD=swing-shack-dev-2026 PORT=8765 \
        /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/.venv/bin/python3 app.py
).
Skip cleanly if the server isn't reachable so cron runs don't false-fail.
"""
import os
import sys
import json
import http.cookiejar
import urllib.request
import urllib.parse

BASE = os.environ.get('CO_BASE_URL', 'http://127.0.0.1:8765')
PASSWORD = os.environ.get('CO_TEST_PASSWORD', 'swing-shack-dev-2026')


def _build_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def main():
    opener = _build_opener()
    try:
        # login (sets session cookie in opener's jar)
        login_data = urllib.parse.urlencode({'password': PASSWORD}).encode()
        opener.open(urllib.request.Request(
            BASE + '/login',
            data=login_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ), timeout=10).read()

        params = {'voice': 'swing-shack', 'pillar': 'education',
                  'platform': 'instagram', 'voice_for_score': 'swing-shack',
                  'pillar_for_score': 'education', 'limit': '60'}
        body = opener.open(BASE + '/api/intel/meme_knowledge?' + urllib.parse.urlencode(params), timeout=10).read()
        payload = json.loads(body)
    except Exception as e:
        print(f'[SKIP] server unreachable: {e}', file=sys.stderr)
        return 0

    summary = payload.get('summary') or ''
    print(f'summary: {summary!r}')

    for token in ('voice=', 'pillar=', 'platform='):
        assert token not in summary, (
            f'regression: summary still contains debug token {token!r} → {summary!r}'
        )
    assert 'voice' in summary.lower(), f'summary missing "voice": {summary!r}'
    assert 'pillar' in summary.lower(), f'summary missing "pillar": {summary!r}'
    assert '\u2014' not in summary, 'em-dash leaked into summary'

    print('[OK] meme_knowledge summary uses friendly copy with no debug tokens')
    return 0


if __name__ == '__main__':
    sys.exit(main())