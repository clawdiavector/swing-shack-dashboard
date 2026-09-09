"""
Regression test for the favicon.ico 404 on Campaign OS.

Background: /favicon.ico was in PUBLIC_ROUTES (suggesting it should work)
but had no Flask route, so every page navigation logged a console error.
The home page HTML also had no <link rel="icon">, so browsers would
fall back to requesting /favicon.ico and hit the 404.

This test asserts:
- /favicon.ico returns 200 with image/svg+xml (any future return to 404
  fails CI loudly).
- The route returns SVG bytes (not HTML, not a 404).
- The campaign-os.html <head> declares an inline-SVG <link rel="icon">.
- The login.html <head> declares the same (login is hit pre-auth).
- No em-dashes are introduced by the new <link rel="icon"> lines.

These are all cache-bustable assertions; once this test is green on
LIVE the favicon.ico console error stops appearing in every navigation.
"""
import os
import re
import sys
import urllib.parse

# Make sure we can import app from sibling package
HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _read(rel_path):
    with open(os.path.join(APP_DIR, rel_path), 'r', encoding='utf-8') as f:
        return f.read()


def test_favicon_route_returns_svg():
    """The /favicon.ico Flask route must return 200 with SVG, not 404."""
    from app import app  # noqa: E402
    client = app.test_client()
    resp = client.get('/favicon.ico')
    assert resp.status_code == 200, (
        f'/favicon.ico returned {resp.status_code}, expected 200'
    )
    ct = resp.headers.get('Content-Type', '')
    assert 'image/svg' in ct or 'image/svg+xml' in ct, (
        f'/favicon.ico Content-Type was {ct!r}, expected image/svg+xml'
    )
    body = resp.get_data(as_text=True)
    assert '<svg' in body, 'favicon body did not contain <svg>'
    assert '#fbbf24' in body, 'favicon body missing Swing Shack amber stroke'


def test_favicon_in_public_routes():
    """PUBLIC_ROUTES should still contain /favicon.ico so auth never blocks it."""
    from app import PUBLIC_ROUTES  # noqa: E402
    assert '/favicon.ico' in PUBLIC_ROUTES


def test_home_html_declares_favicon_link():
    """The home page (campaign-os.html) must include a <link rel="icon">."""
    html = _read('campaign-os.html')
    # match <link rel="icon" type="image/svg+xml" href="..."> with any data URI
    pat = re.compile(
        r'<link\s+rel="icon"\s+type="image/svg\+xml"\s+href="(data:[^"]+)"',
        re.IGNORECASE,
    )
    m = pat.search(html)
    assert m, (
        'campaign-os.html missing <link rel="icon" type="image/svg+xml" href="data:...">'
    )
    uri = m.group(1)
    # Decode and check the SVG actually contains our flag icon
    payload = urllib.parse.unquote(uri.split(',', 1)[1])
    assert '<svg' in payload
    assert '#fbbf24' in payload
    # Cache-control hint not needed here; just make sure no em-dash leaked
    assert '—' not in uri and '–' not in uri, (
        'em-dash leaked into favicon data URI'
    )


def test_login_html_declares_favicon_link():
    """Login page is hit pre-auth; must also have the favicon link."""
    html = _read('login.html')
    pat = re.compile(
        r'<link\s+rel="icon"\s+type="image/svg\+xml"\s+href="(data:[^"]+)"',
        re.IGNORECASE,
    )
    m = pat.search(html)
    assert m, 'login.html missing <link rel="icon" type="image/svg+xml" href="data:...">'
    uri = m.group(1)
    payload = urllib.parse.unquote(uri.split(',', 1)[1])
    assert '<svg' in payload


def test_no_404_in_home_html():
    """Sanity: the favicon link is the only <link rel="icon"> in the file.

    Guards against a future regression that adds a SECOND <link rel="icon">
    with href="/favicon.ico" (which would re-introduce the 404).
    """
    html = _read('campaign-os.html')
    matches = re.findall(r'<link\s+rel="icon"', html, re.IGNORECASE)
    assert len(matches) == 1, (
        f'campaign-os.html has {len(matches)} <link rel="icon"> tags, expected 1'
    )


def test_favicon_does_not_break_other_routes():
    """Make sure the new route didn't shadow /logout."""
    from app import app  # noqa: E402
    client = app.test_client()
    # /logout without auth still returns a redirect (302) to login
    resp = client.get('/logout')
    assert resp.status_code in (302, 303), (
        f'/logout returned {resp.status_code}, expected redirect'
    )


def test_favicon_does_not_introduce_emdash():
    """The em-dash rule must hold across the favicon SVG too."""
    from app import app  # noqa: E402
    client = app.test_client()
    body = client.get('/favicon.ico').get_data(as_text=True)
    assert '—' not in body and '–' not in body, (
        'em-dash leaked into favicon SVG body'
    )