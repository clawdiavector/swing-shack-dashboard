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
    """Classic ?page=socials stays served; native route is /app/publish/socials (P5)."""
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


def test_classic_results_surfaces_still_served():
    from app import app

    client = app.test_client()
    for page in ('insights', 'performance', 'learning', 'trends', 'seo'):
        resp = client.get(f'/?page={page}', follow_redirects=False)
        assert resp.status_code in (200, 302)


def test_weekly_report_page_still_public():
    from app import app

    client = app.test_client()
    resp = client.get('/weekly-report', follow_redirects=False)
    assert resp.status_code == 200


def test_socials_status_endpoint_shape():
    from app import app

    client = app.test_client()
    resp = client.get('/api/socials/status')
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ('ok', 'graph_configured', 'oembed_reachable', 'ig_account_id', 'reason'):
        assert key in data


def test_socials_posts_endpoint_shape():
    from app import app

    client = app.test_client()
    resp = client.get('/api/socials/posts?days=30&limit=5')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'data' in data
    assert 'paging' in data
    assert '_meta' in data
    assert data['_meta'].get('days_covered') == 30


def test_socials_oembed_rejects_non_instagram_url():
    from app import app

    client = app.test_client()
    resp = client.get('/api/socials/oembed?url=https://example.com')
    assert resp.status_code == 400


def test_app_publish_socials_serves_spa():
    from app import app

    client = app.test_client()
    resp = client.get('/app/publish/socials', follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert resp.status_code in (200, 503)
    assert 'Campaign OS' in body or 'not built' in body.lower()


def test_results_alias_redirects_to_app():
    from app import app

    client = app.test_client()
    resp = client.get('/results', follow_redirects=False)
    loc = resp.headers.get('Location') or ''
    assert resp.status_code in (301, 302)
    assert '/app/results' in loc or '/login' in loc


def test_cutover_default_classic_page_query_not_redirected():
    from app import app

    client = app.test_client()
    resp = client.get('/?page=socials', follow_redirects=False)
    assert resp.status_code == 200
    assert b'Campaign OS' in resp.data


def test_cutover_enabled_maps_socials_to_native(monkeypatch):
    monkeypatch.setenv('HEROES_CUTOVER', 'true')
    from app import app

    client = app.test_client()
    resp = client.get('/?page=socials', follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert '/app/publish/socials' in (resp.headers.get('Location') or '')


def test_cutover_enabled_unmapped_performance_stays_classic(monkeypatch):
    monkeypatch.setenv('HEROES_CUTOVER', 'true')
    from app import app

    client = app.test_client()
    resp = client.get('/?page=performance', follow_redirects=False)
    assert resp.status_code == 200
    assert b'Campaign OS' in resp.data


def test_cutover_enabled_home_html_embed_stays_classic(monkeypatch):
    monkeypatch.setenv('HEROES_CUTOVER', 'true')
    from app import app

    client = app.test_client()
    resp = client.get('/home.html?page=socials&embed=1', follow_redirects=False)
    assert resp.status_code == 200
    assert b'Campaign OS' in resp.data


def test_cutover_enabled_carries_inbound_query(monkeypatch):
    monkeypatch.setenv('HEROES_CUTOVER', 'true')
    from app import app

    client = app.test_client()
    resp = client.get('/?page=gbp&brand=stick', follow_redirects=False)
    loc = resp.headers.get('Location') or ''
    assert resp.status_code in (301, 302)
    assert 'brand=stick' in loc


def test_ops_stays_classic_with_cutover_on(monkeypatch):
    monkeypatch.setenv('HEROES_CUTOVER', 'true')
    from app import app

    client = app.test_client()
    resp = client.get('/ops', follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'ops' in body.lower() or 'Campaign OS' in body


def test_public_route_prefixes_unchanged():
    from app import PUBLIC_ROUTE_PREFIXES

    assert '/weekly-report' in PUBLIC_ROUTE_PREFIXES
    assert len(PUBLIC_ROUTE_PREFIXES) == 18
