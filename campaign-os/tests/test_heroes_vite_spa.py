"""Campaign OS Vite mount — aliases, no deletes, tools stay in the desk."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def test_leftover_html_still_on_disk():
    for rel in (
        'campaign-os.html',
        'marketer-workspace.html',
        'cockpit-operational.html',
        'ops-jobs.html',
    ):
        path = os.path.join(APP_DIR, rel)
        assert os.path.isfile(path), path


def test_daily_alias_redirects_to_app():
    from app import app

    client = app.test_client()
    resp = client.get('/daily', follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert '/app/daily' in (resp.headers.get('Location') or '')


def test_app_daily_serves_spa_or_build_hint():
    from app import app

    client = app.test_client()
    resp = client.get('/app/daily', follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert resp.status_code in (200, 503)
    assert 'Campaign OS' in body or 'not built' in body.lower()


def test_root_enters_campaign_os_app():
    from app import app

    client = app.test_client()
    resp = client.get('/', follow_redirects=False)
    loc = resp.headers.get('Location') or ''
    assert resp.status_code in (301, 302)
    assert '/app/daily' in loc or '/login' in loc


def test_classic_page_query_still_served():
    from app import app

    client = app.test_client()
    resp = client.get('/?page=socials', follow_redirects=False)
    assert resp.status_code in (200, 302)
    if resp.status_code == 200:
        assert b'Campaign OS' in resp.data


def test_classic_calendar_ideas_planning_still_served():
    from app import app

    client = app.test_client()
    for page in ('calendar', 'ideas', 'planning'):
        resp = client.get(f'/?page={page}', follow_redirects=False)
        assert resp.status_code in (200, 302)


def test_classic_publish_surfaces_still_served():
    from app import app

    client = app.test_client()
    for page in ('publish', 'postiz', 'gbp', 'gmb'):
        resp = client.get(f'/?page={page}', follow_redirects=False)
        assert resp.status_code in (200, 302)
