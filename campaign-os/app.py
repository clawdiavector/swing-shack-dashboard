"""
CampaignOS v0.1 — Railway Backend
Flask app serving Campaign OS cockpit + campaign data API.
Data lives on Railway disk. GitHub is backup/version history.
"""
from __future__ import annotations  # noqa: F401

import os
import sys
import json
import copy
import datetime
import functools
import re
import subprocess
import shutil
import uuid
import logging
import hashlib
import time
import datetime
import base64
import urllib.request
from datetime import datetime as _dt_cls, timezone as _tz, timedelta as _td
from pathlib import Path
from typing import Optional, List
from flask import Flask, jsonify, request, send_from_directory, g, Response, redirect, url_for, make_response
from werkzeug.utils import secure_filename
from flask_cors import CORS
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__, static_folder='.')
CORS(app)
_app_log = logging.getLogger("campaign-os")

# ─── AUTH ────────────────────────────────────────────────────────────────
# Single shared password gate. Password is read from CAMPAIGN_OS_PASSWORD env var.
# On Railway, set this in the dashboard; locally it falls back to a dev password.
# Sessions are signed cookies (itsdangerous) — no DB needed.
SHARED_PASSWORD = os.environ.get('CAMPAIGN_OS_PASSWORD') or 'swing-shack-dev-2026'
SESSION_SECRET = os.environ.get('CAMPAIGN_OS_SECRET') or 'campaign-os-dev-secret-change-me'
SESSION_COOKIE = 'cos_session'
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
# v2026-08-13: signed share-token TTL for the auth-optional markdown export.
# 24 hours is enough for a same-day Slack/email share; longer than a day
# invites stale-data sharing and stale links accumulating in docs.
SHARE_TOKEN_MAX_AGE = 60 * 60 * 24
_serializer = URLSafeTimedSerializer(SESSION_SECRET)

# Routes that never require auth (login + the static asset paths needed to render login)
PUBLIC_ROUTES = {'/login', '/logout', '/api/health', '/favicon.ico'}

# v2026-08-13: weekly-report export with a valid ?share=<token> query
# param is auth-optional. Letting the export route run without auth
# means the route itself enforces the share-token gate (which is
# stricter than the session cookie. it's scope-bound + time-limited).
PUBLIC_ROUTES.add('/api/intel/weekly_report/export')


def _is_authed():
    """Check request cookie for a valid signed session token."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


@app.before_request
def _gate():
    """Redirect unauthed requests to /login. Allow public routes + static asset paths."""
    path = request.path or '/'
    if path in PUBLIC_ROUTES:
        return None
    # Allow static asset extensions (CSS, JS, images, fonts) needed to render login page.
    # These live next to login.html in the same dir, but they shouldn't reveal data.
    if any(path.endswith(ext) for ext in ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.map')):
        return None
    if _is_authed():
        return None
    # API requests get 401 JSON; browser requests get a redirect to login
    if path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'authentication required'}), 401
    return redirect(url_for('login_page', next=path))


@app.route('/login', methods=['GET'])
def login_page():
    if _is_authed():
        return redirect(url_for('index'))
    resp = make_response(send_from_directory('.', 'login.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return resp


@app.route('/login', methods=['POST'])
def login_submit():
    pw = request.form.get('password') or ''
    if not pw:
        # also accept JSON for fetch() fallback
        try:
            data = request.get_json(silent=True) or {}
            pw = data.get('password') or ''
        except Exception:
            pass
    # constant-time-ish compare (string compare is fine for shared password)
    if not pw or hashlib.sha256(pw.encode()).hexdigest() != hashlib.sha256(SHARED_PASSWORD.encode()).hexdigest():
        return jsonify({'ok': False, 'error': 'Wrong password. Try again.'}), 401
    token = _serializer.dumps({'authed': True})
    next_url = request.args.get('next') or request.form.get('next') or '/'
    if not next_url.startswith('/'):
        next_url = '/'
    resp = make_response(jsonify({'ok': True, 'next': next_url}))
    resp.set_cookie(SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, httponly=True, samesite='Lax', path='/')
    return resp


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    resp = make_response(redirect(url_for('login_page')))
    resp.set_cookie(SESSION_COOKIE, '', max_age=0, path='/')
    return resp


_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="6" fill="#0a0f1a"/>'
    '<path d="M10 26V6" stroke="#fbbf24" stroke-width="2.5" stroke-linecap="round"/>'
    '<path d="M10 8 L22 11 L10 14 Z" fill="#fbbf24"/>'
    '<circle cx="10" cy="27" r="1.5" fill="#34d399"/>'
    '</svg>'
)


@app.route('/favicon.ico')
def favicon():
    """Serve the Swing Shack favicon as inline SVG.

    Returns an SVG (not a real .ico) so we don't need to commit a binary
    asset. Modern browsers happily render SVG when served with the right
    content type; legacy browsers fall back to a generic icon.
    """
    return Response(_FAVICON_SVG, mimetype='image/svg+xml',
                    headers={'Cache-Control': 'public, max-age=86400'})


def _data_paths():
    """Resolve runtime DATA_DIR + canonical file paths at call time.

    Reading from os.environ on every call lets tests override DATA_DIR via
    `os.environ['DATA_DIR']` even when the module was imported elsewhere.
    """
    base = os.environ.get('DATA_DIR') or '/data'
    return {
        'data_dir': base,
        'campaign_file': os.path.join(base, 'campaign-data.json'),
        'schedule_file': os.path.join(base, 'scheduled-items.json'),
        'today_file': os.path.join(base, 'today-panel.json'),
        'theme_file': os.path.join(base, 'theme-preferences.json'),
    }


DATA_DIR = os.environ.get('DATA_DIR', '/data')
CAMPAIGN_FILE = os.path.join(DATA_DIR, 'campaign-data.json')
REPO_DIR = os.path.join(DATA_DIR, 'repo')
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BUNDLED_DATA_DIR = os.path.join(REPO_ROOT, 'data')
# Expose BUNDLED_DATA_DIR as an env var so library modules (insights_correlator,
# etc.) can auto-fallback to the bundled repo copy when DATA_DIR is an empty
# volume mount on Railway.
os.environ.setdefault('BUNDLED_DATA_DIR', BUNDLED_DATA_DIR)
SCHEDULE_FILE = os.path.join(DATA_DIR, 'scheduled-items.json')
BUNDLED_SCHEDULE_FILE = os.path.join(BUNDLED_DATA_DIR, 'scheduled-items.json')
GIT_REMOTE = os.environ.get('GIT_REMOTE', 
 'https://x-access-token:${GITHUB_TOKEN}@github.com/clawdiavector/swing-shack-dashboard.git')
BRANCH = 'main'

# ─── HELPERS ────────────────────────────────────────────────────────────

def load_data():
    """Load campaign data, falling back to bundled campaign-os/campaign-data.json, then embedded default."""
    paths = _data_paths()
    campaign_file = paths['campaign_file']
    # Primary: runtime DATA_DIR/campaign-data.json
    if os.path.exists(campaign_file):
        with open(campaign_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    # Fallback 1: bundled canonical campaign data shipped with the deploy
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'campaign-data.json')
    if os.path.exists(bundled):
        with open(bundled, 'r', encoding='utf-8') as f:
            return json.load(f)
    # Fallback 2: minimal empty structure
    return {"campaigns": {}, "activeCampaignId": None, "portfolioMetadata": {}}

def save_data(data):
    """Save campaign data to runtime DATA_DIR."""
    paths = _data_paths()
    os.makedirs(paths['data_dir'], exist_ok=True)
    with open(paths['campaign_file'], 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def _normalise_schedule_datetime(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('scheduledFor is required')
    raw = value.strip()
    if len(raw) == 10:
        raw += 'T09:00:00'
    try:
        parsed = datetime.datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError('scheduledFor must be a valid ISO 8601 datetime') from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def _schedule_datetime_from_body(body):
    for key in ('scheduledFor', 'targetDatetime', 'targetDateTime', 'publishDate', 'date'):
        if body.get(key) is not None:
            return _normalise_schedule_datetime(body[key])
    raise ValueError('scheduledFor is required')

def _read_json_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _resolve_data_path(rel_path: str) -> str:
    """Resolve a data file path, preferring BUNDLED_DATA_DIR when the runtime
    DATA_DIR (volume mount) doesn't have the file. Used by weekly-report,
    insights, socials, and any module that needs to read historical data
    that ships with the repo (IG analytics, Ubersuggest, ad stubs, etc.).
    """
    runtime_path = os.path.join(DATA_DIR, rel_path)
    if os.path.exists(runtime_path):
        return runtime_path
    bundled_path = os.path.join(BUNDLED_DATA_DIR, rel_path)
    if os.path.exists(bundled_path):
        return bundled_path
    return runtime_path  # caller will get FileNotFoundError or None


def _read_data_json(rel_path: str):
    """Read a data file with DATA_DIR → BUNDLED_DATA_DIR fallback."""
    return _read_json_file(_resolve_data_path(rel_path))

def load_schedule():
    """Read the scheduling sidecar; campaign-data.json remains read-only here."""
    paths = _data_paths()
    schedule_file = paths['schedule_file']
    manifest = _read_json_file(schedule_file)
    if manifest is None:
        manifest = _read_json_file(BUNDLED_SCHEDULE_FILE)
    if not isinstance(manifest, dict):
        manifest = {}
    scheduled = manifest.get('scheduled')
    if not isinstance(scheduled, list):
        scheduled = manifest.get('items') if isinstance(manifest.get('items'), list) else []
    out = dict(manifest)
    out['scheduled'] = [dict(item) for item in scheduled if isinstance(item, dict)]
    out['total'] = len(out['scheduled'])
    out.setdefault('schema', 'https://clawdia.io/agents/publisher/v1')
    return out

def save_schedule(manifest):
    """Atomically persist the sidecar in the runtime DATA_DIR."""
    paths = _data_paths()
    os.makedirs(paths['data_dir'], exist_ok=True)
    payload = dict(manifest or {})
    payload['scheduled'] = [item for item in payload.get('scheduled', []) if isinstance(item, dict)]
    payload['total'] = len(payload['scheduled'])
    payload['generated'] = _now_iso()
    paths = _data_paths()
    schedule_file = paths['schedule_file']
    tmp = schedule_file + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, schedule_file)
    return payload

def _read_publisher_queue():
    for path in (os.path.join(DATA_DIR, 'publish-queue.json'),
                 os.path.join(BUNDLED_DATA_DIR, 'publish-queue.json')):
        value = _read_json_file(path)
        if isinstance(value, dict):
            items = value.get('queued') if isinstance(value.get('queued'), list) else value.get('queue')
            if isinstance(items, list):
                return [dict(item) for item in items if isinstance(item, dict)]
    return []

def _entry_matches(item, asset_id):
    return asset_id in {item.get('assetId'), item.get('asset_id'), item.get('item_id'),
                        item.get('publish_id'), item.get('publishId'), item.get('id')}

def _manifest_entry(manifest, asset_id):
    return next((item for item in manifest.get('scheduled', []) if _entry_matches(item, asset_id)), None)

def _campaign_target(asset_id, campaign_id=None, data=None):
    data = data or load_data()
    for cid, campaign in (data.get('campaigns') or {}).items():
        if campaign_id and cid != campaign_id:
            continue
        assets = campaign.get('assets') or {}
        if asset_id not in assets:
            continue
        asset = assets[asset_id]
        identity = campaign.get('identity') or {}
        return {
            'source': 'campaign', 'assetId': asset_id, 'campaignId': cid,
            'campaign': campaign, 'asset': asset,
            'name': asset.get('name', asset_id), 'caption': asset.get('caption', ''),
            'platform': asset.get('platform') or asset.get('integration') or 'instagram',
            'brand': identity.get('brand') or identity.get('business') or 'Swing Shack',
            'pillar': asset.get('pillarName') or asset.get('pillar') or '',
        }
    return None

def _queue_target(asset_id):
    for item in _read_publisher_queue():
        if _entry_matches(item, asset_id):
            return {
                'source': 'queue', 'assetId': asset_id,
                'campaignId': item.get('campaignId') or item.get('campaign_id'),
                'queueItem': item,
                'name': item.get('name') or item.get('caption_preview') or item.get('caption') or asset_id,
                'caption': item.get('caption') or item.get('caption_preview', ''),
                'platform': item.get('platform') or 'instagram',
                'brand': item.get('brand') or item.get('business') or 'Swing Shack',
                'pillar': item.get('pillarName') or item.get('pillar') or '',
            }
    return None

def _schedule_target(asset_id, campaign_id=None):
    data = load_data()
    target = _campaign_target(asset_id, campaign_id, data) or _queue_target(asset_id)
    if target:
        if campaign_id and target.get('campaignId') and target['campaignId'] != campaign_id:
            return None
        return target
    manifest = load_schedule()
    item = _manifest_entry(manifest, asset_id)
    if item:
        return {
            'source': item.get('source') or 'calendar', 'assetId': asset_id,
            'campaignId': item.get('campaignId'), 'manifestItem': item,
            'name': item.get('name') or item.get('caption') or asset_id,
            'caption': item.get('caption', ''), 'platform': item.get('platform') or 'instagram',
            'brand': item.get('brand') or 'Swing Shack',
            'pillar': item.get('pillar') or item.get('pillarName') or '',
        }
    return None

def _upsert_schedule_entry(manifest, target, scheduled_for, platform=None, extra=None):
    item = _manifest_entry(manifest, target['assetId'])
    if item is None:
        item = {'assetId': target['assetId']}
        manifest.setdefault('scheduled', []).append(item)
    item.update({
        'assetId': target['assetId'], 'campaignId': target.get('campaignId'),
        'source': target.get('source', 'calendar'), 'name': target.get('name') or target['assetId'],
        'caption': target.get('caption', ''), 'brand': target.get('brand') or 'Swing Shack',
        'pillar': target.get('pillar') or '', 'platform': platform or target.get('platform') or 'instagram',
        'scheduledFor': scheduled_for, 'publishStatus': 'scheduled', 'updatedAt': _now_iso(),
    })
    if extra:
        item.update(extra)
    return item

def _schedule_response(manifest):
    payload = dict(manifest)
    payload['scheduled'] = [dict(item) for item in manifest.get('scheduled', [])]
    payload['total'] = len(payload['scheduled'])
    return payload

def git_push(message):
    """
    Commit and push current campaign data to GitHub.
    Returns (success: bool, message: str)
    """
    try:
        subprocess.run(['git', 'config', '--global', 'user.email', 'agent@openclaw.ai'],
                       cwd=REPO_DIR, check=True, capture_output=True)
        subprocess.run(['git', 'config', '--global', 'user.name', 'Clawdia Agent'],
                       cwd=REPO_DIR, check=True, capture_output=True)
        subprocess.run(['git', 'add', 'campaign-os/campaign-data.json'],
                       cwd=REPO_DIR, check=True, capture_output=True)
        # Check if there are changes to commit
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'],
                               cwd=REPO_DIR, check=False, capture_output=True)
        if result.returncode == 0:
            return True, "No changes to commit"
        subprocess.run(['git', 'commit', '-m', message],
                       cwd=REPO_DIR, check=True, capture_output=True)
        env = {**os.environ}
        token = os.environ.get('GITHUB_TOKEN', '')
        remote = f'https://x-access-token:{token}@github.com/clawdiavector/swing-shack-dashboard.git'
        subprocess.run(['git', 'push', remote, BRANCH],
                       cwd=REPO_DIR, check=True, capture_output=True, env=env)
        return True, "Committed and pushed to GitHub"
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ''
        return False, f"Git error: {stderr or str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def init_repo():
    """
    Clone GitHub repo to DATA_DIR on first run.
    Uses GITHUB_TOKEN env var for authentication.
    """
    if os.path.exists(os.path.join(REPO_DIR, '.git')):
        # Already cloned — just pull latest
        try:
            subprocess.run(['git', 'pull', 'origin', BRANCH],
                           cwd=REPO_DIR, check=True, capture_output=True)
            print(f"Git pull OK: {REPO_DIR}")
        except Exception as e:
            print(f"Git pull failed (non-fatal): {e}")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        print("WARNING: GITHUB_TOKEN not set — GitHub sync disabled")
        return

    remote_url = f'https://x-access-token:{token}@github.com/clawdiavector/swing-shack-dashboard.git'
    try:
        subprocess.run(['git', 'clone', '--depth=1', remote_url, REPO_DIR],
                       cwd=DATA_DIR, check=True, capture_output=True)
        print(f"Git clone OK: {REPO_DIR}")
    except Exception as e:
        print(f"Git clone failed (non-fatal): {e}")

# ─── BOOTSTRAP ──────────────────────────────────────────────────────────

@app.before_request
def bootstrap():
    """Run once at startup."""
    if hasattr(g, '_booted'):
        return
    g._booted = True
    init_repo()

# ─── API ROUTES ─────────────────────────────────────────────────────────

@app.route('/api/health')
def health():
    """Health check."""
    return jsonify({
        "status": "ok",
        "ts": datetime.datetime.utcnow().isoformat() + 'Z',
        "git_synced": os.path.exists(os.path.join(REPO_DIR, '.git'))
    })


@app.route('/api/admin/env-debug', methods=['GET'])
def env_debug():
    """Debug endpoint: dump which credential env vars the running process can see.
    Returns the PREFIX + LENGTH of each secret, never the value. Used to
    verify env-var pickup after Railway env changes.
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    keys_of_interest = [
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_FILE",
        "OPENAI_API_KEY",
        "OPENAI_API_KEY_FILE",
        "CAMPAIGN_OS_IMAGE_PROVIDER",
        "CAMPAIGN_OS_IMAGE_MODEL",
        "DATA_DIR",
        "PORT",
    ]
    out = {}
    for k in keys_of_interest:
        v = os.environ.get(k, "")
        if v:
            out[k] = {"set": True, "length": len(v), "prefix": v[:6] + "…"}
        else:
            out[k] = {"set": False}
    # Also check the canonical file paths
    file_checks = {}
    for label, p in [
        ("DEFAULT_OPENROUTER_TOKEN_FILE", "/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/openrouter-api.json"),
    ]:
        file_checks[label] = {"path": p, "exists": os.path.exists(p)}
    return jsonify({
        "ok": True,
        "env": out,
        "files": file_checks,
        "ts": datetime.datetime.utcnow().isoformat() + 'Z',
    })


# ─── What's New (last N nightshift improvements) ─────────────────────────
# Static list of recent campaign-os improvements. Each tick appends an entry
# at the top; oldest entries fall off the end. Shown as a "What's new" card
# on the Morning Brief so Christelle sees the cumulative polish on her
# morning coffee. Frontend only fetches on first brief render and caches.
WHATS_NEW = [
    {"ts": "2026-08-12T10:30:00Z", "tag": "chrome", "title": "Favicon 404 gone · inline SVG + <link>",
     "body": "Every page load was generating a 404 for /favicon.ico in the console because the dashboard shipped no icon. Now serves a tiny inline SVG (golf flag with swing shack palette) with a <link rel='icon'> in every HTML head. Console is clean and the browser tab actually shows a logo instead of a broken-image placeholder."},
    {"ts": "2026-08-12T05:50:00Z", "tag": "chrome", "title": "Insights v2 + perf empty-state explainer copy",
     "body": "The Insights v2 loading summary (e.g. '7 signals · 12 posts · 6 pages tracked') and the Performance-tab empty-state fallback both had em-dashes that crept into published copy. Replaced with middle-dots so the chrome stays on-brand. Insights V2 renderer also confirmed live across all four brands (Swing Shack, Stick, Bag Drop, Takomo)."},
    {"ts": "2026-08-12T01:55:00Z", "tag": "chrome", "title": "Walker no longer swallows sub-nav rows",
     "body": "The full-site Playwright walker used to throw NAV_ERR when sections had no .nav[data-go] row (calendar, publishing, etc.). Now skips those gracefully and clicks every reachable sub-nav row + variant tab so coverage actually walks the real user paths, not just the top-level nav. Walker reports are now trustworthy again."},
    {"ts": "2026-08-11T18:01:00Z", "tag": "nav", "title": "Shareable ?page= links land on the right section",
     "body": "Boot script was ignoring the ?page= URL parameter, so links shared with ?page=performance or ?page=memes always opened on the Morning Brief. Now honors the parameter on first paint, refreshes the active section, and updates the address bar. Works for every section including the External nav group (visualizer, meme-lab, meta-portal)."},
    {"ts": "2026-08-11T14:00:00Z", "tag": "chrome", "title": "Help tooltips moved to ? icon · page titles clickable",
     "body": "Brief page titles used to carry data-help hover-tooltips that overlapped the title text and broke the click-to-scroll affordance. Moved all section-page help onto a discrete ? icon next to the title (matches the rest of the dashboard). Hovering the ? surfaces the same body, clicking the title still scrolls cleanly."},
    {"ts": "2026-08-11T08:00:00Z", "tag": "data", "title": "Morning Brief brand-isolated · per-brand counts",
     "body": "The Morning Brief review/publish counters were aggregating across every brand instead of the active one, so switching from Swing Shack to Stick still showed Swing Shack's 41-review queue. Now reads the active brand's campaign_ids from brands.json before slicing review_inbox() / publishing_inbox(). Counts are correct on every brand."},
    {"ts": "2026-08-11T04:00:00Z", "tag": "data", "title": "Audit pass · brand filter, caption variety, hook dedup",
     "body": "Big-audit sweep: brand filter dropdown now updates the active brand across every surface (was only refreshing Morning Brief); image-lab prompt flow now starts from a goal-first dropdown instead of a blank canvas; first-run tour dismissal persists across sessions (no more repeat welcome modal); captions no longer regenerate into near-duplicates of the prior one; hook bank deduplicates on hook_text + voice before insert."},
    {"ts": "2026-08-10T20:00:00Z", "tag": "data", "title": "Marketing OS north-star spec · 5-question insight pattern",
     "body": "New docs/MARKETING_OS_NORTH_STAR.md codifies the 'why' pattern behind every Insights panel: 5 questions (what's working, what's leaking, what changed, what to do next, what to ignore) answered in one short sentence each. South-Africa market context + brand-specific visual-DNA references baked in. Every future Insights card ladders to this spec so copy stays consistent across weeks."},
    {"ts": "2026-08-10T14:00:00Z", "tag": "image", "title": "Use this image + recent renders gallery",
     "body": "Every generated image in Image Lab / Meme Lord now has a 'Use this image' button that drops it into the active brief or Review row with a single click. A 'Recent renders' gallery sits under the form so you can re-open or remix any of the last 20 generations without re-running the prompt. IG-recipe thumbnails also wired so the visual pipeline has a feedback loop."},
    {"ts": "2026-08-09T22:00:00Z", "tag": "chrome", "title": "Weekly report · real captions + thumbs + single IG source",
     "body": "The Weekly Report was rendering placeholder text instead of the actual post captions, showing broken thumbs, and double-counting Instagram because it queried two endpoints. Now reads from the single /api/intel/performance.instagram.top_posts endpoint, displays real captions + per-post engagement, and renders thumbnail tiles cleanly. Downloadable Markdown report now matches what's on screen."},
    {"ts": "2026-08-08T02:42:00Z", "tag": "data", "title": "Brief counts now mirror Review queue (40 review, 1 publish)",
     "body": "Morning Brief's review/publish counters were stuck at 0/0 because the count panel called a different state slice than the Review tab. Re-pointed at review_inbox() + publishing_inbox() so the numbers, the 'Do this right now' rationale, and the Review tab finally agree. No more pretending the queue is empty."},
    {"ts": "2026-08-08T01:30:00Z", "tag": "chrome", "title": "Orphan-DNA tile renders palette placeholder, not black box",
     "body": "Visualizer tiles whose DNA JSON is missing the thumbnail_b64 field were painting solid black. Now they render a tasteful palette-swatch placeholder (the same fallback the Recipes tab uses) plus a one-line 'Image unavailable' caption · no more mystery black rectangles in the grid."},
    {"ts": "2026-08-08T00:10:00Z", "tag": "chrome", "title": "GBP profile header reads 'city, region · country' (no more raw-object leak)",
     "body": "The Google Business Profile header was stringifying an object instead of the city. Now reads GBP fields safely (name / city / region / country) so the header reads 'Sandton, Gauteng · South Africa' instead of leaking the raw object. Affects every GBP tile on Home + Brand Directory."},
    {"ts": "2026-08-07T22:58:00Z", "tag": "chrome", "title": "13 dead meme-template thumbnails repaired",
     "body": "Meme Lab was showing broken-image icons for 13 of 26 templates because the thumbnail filenames had drifted from the on-disk assets. Re-mapped every template to its real PNG (palette + first-frame SVG fallback for the two truly-missing ones). All 26 templates now preview cleanly."},
    {"ts": "2026-08-07T19:43:00Z", "tag": "seo", "title": "SEO quick wins · show keyword, not raw JSON",
     "body": "The SEO Quick Wins row on Home was rendering the full raw API payload instead of the keyword + opportunity score. Now shows a tidy 'club fitting near me · volume 1.2K · KD 22' card with the same Run-it / Draft action chips. The Insights surface also got the same treatment."},
    {"ts": "2026-08-07T18:27:00Z", "tag": "data", "title": "Freshness sanity-range guard stops 9238-day bogus files",
     "body": "Home freshness banner was lighting up with 9000+ day-old files because a malformed date slipped through the parser. Added a sanity-range filter (last 30 days to next 7 days) before the diff so any out-of-range timestamp is silently dropped and the banner only ever flags real recent files."},
    {"ts": "2026-08-07T17:11:00Z", "tag": "chrome", "title": "Brand-image fallback + Meme Lab clean title",
     "body": "Brand tiles whose hero image failed to load now show a deterministic gradient fallback derived from the brand palette (instead of the generic gray box). Meme Lab tab title trimmed to 'Meme Lab' to match every other tab in the rail."},
    {"ts": "2026-08-07T16:00:00Z", "tag": "nav", "title": "Meme Lord clarified + All 33 tools flat-list nav group",
     "body": "Renamed the rail entry 'Meme Lab' to make it obvious it's the same surface, and added an 'All tools' flat-list group at the bottom of the sidebar that expands to show every one of the 33 surfaces (incl. hidden power-user ones like Ubersuggest and Meta App Review). One click, no hunting."},
    {"ts": "2026-08-07T14:45:00Z", "tag": "data", "title": "Weekly marketing report · brand-aware, downloadable, comparable",
     "body": "New Insights sub-tab: auto-compiles the last 7 days of posts, hooks, IG engagement, SEO quick-wins and review-queue activity into a printable weekly report · grouped by brand, downloadable as Markdown, comparable week-over-week. Replaces the ad-hoc spreadsheet Christelle was building manually."},
    {"ts": "2026-08-07T13:36:00Z", "tag": "chrome", "title": "First-run welcome modal + phase-1 nav groups",
     "body": "New visitors now get a one-time 3-card welcome modal that explains the three nav groups (Brief / Build / Measure) and the topbar search. Persists dismissal in localStorage. Returning visitors skip straight to the Morning Brief."},
    {"ts": "2026-08-07T13:05:00Z", "tag": "data", "title": "Insights v2 + ad correlation + Trends freshness + intern review",
     "body": "Insights surface got a 4-panel v2 (engagement-by-type, hook library, brand lift, ad-spend correlation), Trends tab now scores each Reddit/YouTube signal with a freshness half-life so stale items drop out, and a new 'intern review' panel flags any auto-generated asset that scored below confidence 0.6 for a human eyeball before publishing."},
    {"ts": "2026-08-07T12:40:00Z", "tag": "chrome", "title": "Socials tab + per-asset IG carousel + meme template thumbs + auto-compose",
     "body": "New 'Socials' tab on every campaign surfaces the full IG carousel for that campaign's assets with caption-hook previews underneath. Meme Lab and Image Lab now share the same 26-template thumbnail grid (no more blank tiles). Image Lab's auto-compose button now fires off a real generation call instead of toasting 'coming soon'."},
    {"ts": "2026-07-30T01:30:00Z", "tag": "data", "title": "↺ Reset to AI draft · now actually resets",
     "body": "The Review-queue Edit modal's 'Reset to AI draft' button used to toast 'No AI draft saved' for every asset · the backend endpoint didn't exist. New GET /api/assets/<aid>/ai-draft returns the original AI-generated caption (snapshot taken on first hand-edit), so the button now restores the prior caption for review-and-Save. Old assets without a snapshot fall through to current caption or a clear 'no draft on file' message · no more silent dead-ends."},
]


@app.route('/api/whats-new', methods=['GET'])
def whats_new():
    """Return the recent nightshift improvement list.

    Cached at the edge for 5 minutes (Cloudflare/Railway) — list is append-only
    within a session and never changes mid-tick. Frontend caches in S.whatsNew
    and only re-fetches if cache is older than 10 minutes.
    """
    resp = jsonify({"items": WHATS_NEW, "ts": datetime.datetime.utcnow().isoformat() + 'Z'})
    resp.cache_control.public = True
    resp.cache_control.max_age = 300
    return resp


# ─── Brand Directory (image + copy generator source-of-truth) ───────────
from _lib import brand_directory as _brand_dir  # noqa: E402


@app.route('/api/brand-directory', methods=['GET'])
def brand_directory_index():
    """GET /api/brand-directory — flat index of every brand's readiness + canonical fields.

    Returns the merged brand-index.json so the SPA Brand surface can render
    readiness scores per brand, and so image/copy generators know which
    brands are ready (all 4 gate files) vs partial (fall back to voice bible).

    Also merges in `product_brands` from data/brands.json so the SPA can
    surface Takomo-style "carried product brands" alongside the businesses
    (swing-shack / stick / bag-drop) on the Brand surface.
    """
    try:
        idx = _brand_dir.build_index()
        # Pull product_brands from the registry. These don't have their own
        # brand-directory/<id>/ folder lifecycle (the takomo/ folder exists
        # on disk for caption/image lab reuse, but it's not a "business" for
        # the brand switcher or the today-panel).
        try:
            from _lib import intelligence as _intel
            reg = _intel._load_brands_registry()
            pb = reg.get("product_brands") or {}
            if pb:
                idx["product_brands"] = pb
        except Exception:
            pass
        return jsonify(idx)
    except Exception as e:
        _app_log.exception("brand_directory_index failed")
        return jsonify({"error": str(e), "schema": "https://campaign-os/brand-directory/index/v1"}), 500


@app.route('/api/brand-directory/<brand_id>', methods=['GET'])
def brand_directory_get(brand_id):
    """GET /api/brand-directory/<brand_id> — full per-brand directory payload.

    Used by image_dissector (when Drive is wired in) and the Brand surface
    "View details" panel. Returns voice, palette, archetypes, copy, examples.
    """
    try:
        brand = _brand_dir.load_brand(brand_id)
        if not brand.get("exists"):
            return jsonify({"error": f"unknown brand_id: {brand_id}"}), 404
        return jsonify(brand)
    except Exception as e:
        _app_log.exception("brand_directory_get failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/brand-directory/<brand_id>/generate-brief', methods=['GET'])
def brand_directory_generate_brief(brand_id):
    """GET /api/brand-directory/<brand_id>/generate-brief?surface=...&tone=...

    Returns a ready-to-use prompt brief for the image generator or the
    caption generator. Combines: archetype layers + palette + typography +
    voice tone-rules + headline bank + CTA bank.

    Query params:
        surface (optional): square-post | story | banner | meme-3up | quote | any
        tone (optional): educational | confident | funny | sarcastic | relatable | provocative | warm

    Output: { archetype, palette, typography, headline_options, cta_options, voice_anchor }
    """
    try:
        brand = _brand_dir.load_brand(brand_id)
        if not brand.get("exists"):
            return jsonify({"error": f"unknown brand_id: {brand_id}"}), 404

        surface = request.args.get("surface", "").strip().lower()
        tone = request.args.get("tone", "").strip().lower()

        # Pick archetype
        archetypes = brand.get("archetypes") or []
        archetype = None
        if surface:
            for a in archetypes:
                aid = (a.get("id") or "").lower()
                if surface in aid:
                    archetype = a
                    break
        if not archetype and archetypes:
            archetype = archetypes[0]

        # Pull headlines + CTAs that match the requested tone (or any if none match)
        headlines_md = brand.get("copy", {}).get("headlines", "")
        ctas_md = brand.get("copy", {}).get("ctas", "")

        return jsonify({
            "brand_id": brand_id,
            "ready": brand.get("ready"),
            "surface": surface or (archetype.get("id") if archetype else None),
            "tone": tone or "any",
            "archetype": archetype,
            "palette": brand.get("palette"),
            "typography": brand.get("typography"),
            "voice_anchor": (brand.get("voice", {}).get("tone_rules", "")[:400] + "...") if brand.get("voice", {}).get("tone_rules") else "",
            "headlines_bank": headlines_md,
            "ctas_bank": ctas_md,
            "do_say_dont_say": brand.get("voice", {}).get("do_say_dont_say", ""),
        })
    except Exception as e:
        _app_log.exception("brand_directory_generate_brief failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/brand-directory/refresh', methods=['POST'])
def brand_directory_refresh():
    """POST /api/brand-directory/refresh — rebuild _system/brand-index.json.

    Called after the image dissector (Drive wiring) writes new visual specs,
    or after manual folder edits. Idempotent.
    """
    try:
        path = _brand_dir.write_index()
        idx = _brand_dir.build_index()
        return jsonify({"wrote": str(path), "index": idx})
    except Exception as e:
        _app_log.exception("brand_directory_refresh failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Google Drive ingestion ──────────────────────────────────────────
from _lib import google_drive as _gdrive  # noqa: E402


@app.route('/api/google-drive/status', methods=['GET'])
def google_drive_status():
    """GET /api/google-drive/status — current Drive auth + folder config state."""
    try:
        return jsonify(_gdrive.status())
    except Exception as e:
        _app_log.exception("google_drive_status failed")
        msg = str(e)
        if "invalid_grant" in msg or "expired or revoked" in msg:
            return jsonify({"ok": False, "error": "Token has been expired or revoked — re-upload at /secrets-sync"}), 401
        return jsonify({"ok": False, "error": msg}), 500


@app.route('/api/google-drive/ingest', methods=['POST'])
def google_drive_ingest():
    """POST /api/google-drive/ingest — pull brand folders from Drive into brand-directory.

    Body (JSON): {
        "mappings": [
            {"brand_id": "swing-shack", "folder_name": "Swing Shack Brand Assets"},
            {"brand_id": "stick",        "folder_name": "Stick Brand Assets"},
            {"brand_id": "bag-drop",     "folder_name": "Bag Drop Brand Assets"}
        ],
        "subdir": "images/originals"   # default; "images/ads", "images/posts" also valid
    }

    For each mapping: find the Drive folder by name, list files, download images
    to data/brand-directory/<brand_id>/<subdir>/, return per-brand manifest.
    """
    try:
        body = request.get_json(force=True) or {}
        mappings = body.get("mappings") or []
        subdir = body.get("subdir") or "images/originals"

        if not mappings:
            return jsonify({
                "error": "missing 'mappings' in body",
                "expected_format": {
                    "mappings": [
                        {"brand_id": "swing-shack", "folder_name": "Swing Shack Brand Assets"}
                    ],
                    "subdir": "images/originals"
                }
            }), 400

        drive = _gdrive.connect()
        if not drive:
            return jsonify({
                "error": "Drive not connected. Upload OAuth client + complete the dance.",
                "instructions": _gdrive.oauth_instructions(),
            }), 401

        results = []
        for m in mappings:
            brand_id = m.get("brand_id")
            folder_name = m.get("folder_name")
            if not brand_id or not folder_name:
                results.append({"ok": False, "error": "missing brand_id or folder_name", "mapping": m})
                continue
            try:
                r = _gdrive.ingest_brand_folder(drive, folder_name, brand_id, images_subdir=subdir)
                results.append(r)
            except Exception as e:
                results.append({"ok": False, "error": str(e), "brand_id": brand_id, "folder_name": folder_name})

        # Refresh the brand index so image_count updates
        try:
            _brand_dir.write_index()
        except Exception as e:
            _app_log.warning("brand index refresh after Drive ingest failed: %s", e)

        return jsonify({
            "ok": True,
            "results": results,
            "ingested_total": sum(len(r.get("downloaded", [])) for r in results),
            "skipped_total": sum(len(r.get("skipped", [])) for r in results),
        })
    except Exception as e:
        _app_log.exception("google_drive_ingest failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/google-drive/list-folders', methods=['GET'])
def google_drive_list_folders():
    """GET /api/google-drive/list-folders?q=Brand — search Drive folders by name substring.

    Use this to discover the exact folder names before running /ingest.
    """
    try:
        drive = _gdrive.connect()
        if not drive:
            return jsonify({
                "error": "Drive not connected. Upload OAuth client + complete the dance.",
            }), 401

        q = (request.args.get("q") or "").strip()
        # Escape single quotes for Drive query
        q_escaped = q.replace("\\", "\\\\").replace("'", "\\'")
        query = f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if q_escaped:
            query += f" and name contains '{q_escaped}'"

        resp = drive.files().list(q=query, fields="files(id, name, modifiedTime)", pageSize=50).execute()
        return jsonify({"ok": True, "query": q, "folders": resp.get("files", [])})
    except Exception as e:
        _app_log.exception("google_drive_list_folders failed")
        msg = str(e)
        if "invalid_grant" in msg or "expired or revoked" in msg:
            return jsonify({
                "ok": False,
                "error": "Token has been expired or revoked — re-upload at /secrets-sync",
            }), 401
        if "403" in msg or "permission" in msg.lower():
            return jsonify({"ok": False, "error": "Drive permission denied — token lacks required scope"}), 403
        return jsonify({"ok": False, "error": msg}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Visual DNA — query + generation scaffold endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/visual-dna/<brand_id>/search', methods=['GET'])
def visual_dna_search(brand_id):
    """GET /api/visual-dna/<brand>/search — search the visual DNA index.

    Query params (all optional):
      q              — free-text against filename + OCR text + product tags
      product        — filter by product name (Takomo, TrackMan, Srixon, etc.)
      alignment      — 'high' (>=0.70), 'typical' (0.60-0.69), 'variants' (<0.60)
      min_score      — float, e.g. 0.7
      max_score      — float, e.g. 0.9
      luminance      — 'dark' | 'mid' | 'light'
      dominant_color — hex like #74cc46

    Returns: list of matching images with full DNA preview.
    """
    try:
        from _lib.visual_dna_query import search_images
        results = search_images(
            brand_id,
            query=request.args.get('q'),
            product=request.args.get('product'),
            alignment=request.args.get('alignment'),
            min_score=float(request.args.get('min_score')) if request.args.get('min_score') else None,
            max_score=float(request.args.get('max_score')) if request.args.get('max_score') else None,
            luminance=request.args.get('luminance'),
            dominant_color=request.args.get('dominant_color'),
        )
        return jsonify({
            "brand": brand_id,
            "query": {
                "q": request.args.get('q'),
                "product": request.args.get('product'),
                "alignment": request.args.get('alignment'),
                "min_score": request.args.get('min_score'),
                "max_score": request.args.get('max_score'),
                "luminance": request.args.get('luminance'),
                "dominant_color": request.args.get('dominant_color'),
            },
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        _app_log.exception("visual_dna_search failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/visual-dna/<brand_id>/recipe', methods=['GET'])
def visual_dna_recipe(brand_id):
    """GET /api/visual-dna/<brand>/recipe?brief=<text>&n=5

    Returns the top N Visual Recipes + an aggregated scaffold for the brief.
    This is the auto-pull hook for the generation pipeline — pass the brief,
    get back the templates to use as prompt scaffolding.
    """
    try:
        from _lib.visual_dna_query import select_visual_recipes
        brief = request.args.get('brief') or request.args.get('q') or ''
        n = int(request.args.get('n') or 5)
        if not brief:
            return jsonify({"error": "missing 'brief' param"}), 400
        result = select_visual_recipes(brand_id, brief, n=n)
        # The frontend (campaign-os.html findRecipes) gates rendering on r.ok.
        # The query layer returns matches without an ok flag, so wrap here.
        if isinstance(result, dict) and "ok" not in result:
            result["ok"] = True
        return jsonify(result)
    except Exception as e:
        _app_log.exception("visual_dna_recipe failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/visual-dna/<brand_id>/index', methods=['GET'])
def visual_dna_index(brand_id):
    """GET /api/visual-dna/<brand>/index — full cross-image index.

    Returns the rollup: by_alignment buckets, by_product, by_luminance,
    by_dominant_color, per-filename records.
    """
    try:
        from pathlib import Path
        index_path = Path(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / "visual-dna-index.json"
        if not index_path.exists():
            return jsonify({"error": f"no visual-dna index for brand {brand_id}"}), 404
        return jsonify(json.loads(index_path.read_text()))
    except Exception as e:
        _app_log.exception("visual_dna_index failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/visual-dna/<brand_id>/products', methods=['GET'])
def visual_dna_products(brand_id):
    """GET /api/visual-dna/<brand>/products — distinct products detected + image counts."""
    try:
        from pathlib import Path
        index_path = Path(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / "visual-dna-index.json"
        if not index_path.exists():
            return jsonify({"error": f"no visual-dna index for brand {brand_id}"}), 404
        idx = json.loads(index_path.read_text())
        products = idx.get("by_product", {})
        return jsonify({
            "brand": brand_id,
            "products": [{"name": k, "count": len(v), "images": v} for k, v in sorted(products.items(), key=lambda x: -len(x[1]))],
            "total_distinct_products": len(products),
        })
    except Exception as e:
        _app_log.exception("visual_dna_products failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/visual-dna/<brand_id>/scrape-and-dissect', methods=['POST'])
def visual_dna_scrape_and_dissect(brand_id):
    """POST /api/visual-dna/<brand>/scrape-and-dissect — re-walk Drive folder, ingest new, re-dissect.

    Body: {"folder_id": "1n9pHD...", "brand": "swing-shack"}
    Compares against existing ingest-manifest.json by md5 — only downloads new files.
    Runs the dissector on new files only.
    """
    try:
        from _lib.google_drive import connect, _DEFAULT_CREDENTIALS_DIRS
        from googleapiclient.http import MediaIoBaseDownload
        from pathlib import Path
        import hashlib, json as jsonlib

        body = request.get_json(force=True, silent=True) or {}
        folder_id = body.get("folder_id")
        if not folder_id:
            return jsonify({"error": "missing folder_id"}), 400

        drive = connect()
        if not drive:
            return jsonify({"error": "Drive not connected"}), 401

        # Walk folder recursively
        def walk(fid, rel=""):
            items = drive.files().list(
                q=f"'{fid}' in parents and trashed=false",
                fields="files(id,name,mimeType,size,modifiedTime,md5Checksum)",
                pageSize=200,
            ).execute().get("files", [])
            out = []
            for f in items:
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    out.extend(walk(f["id"], f"{rel}{f['name']}/"))
                elif f["mimeType"].startswith("image/"):
                    f["rel_path"] = f"{rel}{f['name']}"
                    out.append(f)
            return out

        files = walk(folder_id)
        images_dir = Path(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # Existing manifest
        manifest_path = Path(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / "ingest-manifest.json"
        existing_md5 = set()
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text())
            for entry in existing.get("images", {}).values():
                if entry.get("md5"):
                    existing_md5.add(entry["md5"])

        # Drive md5 lookup
        drive_md5_to_file = {f.get("md5Checksum", "").lower(): f for f in files if f.get("md5Checksum")}

        new_count = 0
        skipped = 0
        errors = []
        for f in files:
            if f.get("md5Checksum") and f["md5Checksum"].lower() in existing_md5:
                skipped += 1
                continue
            out = images_dir / f["name"]
            try:
                req = drive.files().get_media(fileId=f["id"])
                with open(out, 'wb') as fh:
                    dl = MediaIoBaseDownload(fh, req)
                    done = False
                    while not done:
                        _, done = dl.next_chunk()
                new_count += 1
            except Exception as e:
                errors.append({"file": f["name"], "error": str(e)})
                if out.exists():
                    out.unlink()

        # Update manifest
        manifest = {"brand": brand_id, "images": {}, "errors": []}
        for f in files:
            local_p = images_dir / f["name"]
            if local_p.exists():
                md5 = hashlib.md5(local_p.read_bytes()).hexdigest()
                manifest["images"][f["name"]] = {
                    "drive_id": f["id"],
                    "size": f.get("size"),
                    "md5": md5,
                    "modified": f.get("modifiedTime"),
                }
        if errors:
            manifest["errors"] = errors
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Re-dissect only NEW files
        from _lib.image_dissector import dissect
        bible_path = Path(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / "bible-visual.json"
        if not bible_path.exists():
            bible_path = None
        re_dissected = 0
        for f in files:
            local_p = images_dir / f["name"]
            dna_p = local_p.with_suffix(".visual-dna.json") if local_p.suffix == ".jpg" else local_p.parent / f"{local_p.stem}.visual-dna.json"
            if not local_p.exists():
                continue
            # Re-dissect if new OR if dna missing
            if f.get("md5Checksum") and f["md5Checksum"].lower() in existing_md5 and dna_p.exists():
                continue
            dna = dissect(local_p, bible_path)
            dna_p.write_text(json.dumps(dna, indent=2))
            re_dissected += 1

        # Re-tag with products
        from _lib.visual_dna_query import tag_directory
        tag_result = tag_directory(brand_id)

        return jsonify({
            "brand": brand_id,
            "folder_id": folder_id,
            "drive_files_found": len(files),
            "new_downloaded": new_count,
            "skipped_existing": skipped,
            "re_dissected": re_dissected,
            "errors": errors[:5],
            "tag_summary": tag_result,
        })
    except Exception as e:
        _app_log.exception("visual_dna_scrape_and_dissect failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── VISUAL LIBRARY (image serving + DNA breakdown for the UI) ──────────

@app.route('/visualizer', methods=['GET'])
def visualizer_page():
    """GET /visualizer — Visual Library tab (122 SS images + DNA + filters)."""
    return send_from_directory(os.path.dirname(__file__), 'visualizer.html')


@app.route('/meme-lab', methods=['GET'])
def meme_lab_page():
    """GET /meme-lab — Meme Library tab (75 memes with adaptation previews)."""
    return send_from_directory(os.path.dirname(__file__), 'meme-lab.html')


@app.route('/image-lab', methods=['GET'])
def image_lab_page():
    """GET /image-lab — Reference DNA + Product/Service library + learned signals.

    Three-column UI for the full visual generation workflow:
      - LEFT:   upload references (file / URL / brand library)
      - MIDDLE: compose prompt + select size/model + generate
      - RIGHT:  product/service library + learned WIN PROFILE + records
    """
    return send_from_directory(os.path.dirname(__file__), 'image-lab.html')


# ─── IMAGE KEYS PORTAL ───────────────────────────────────────────────
# Local-only route for safely ingesting OpenAI / OpenRouter keys without
# them touching Discord/chat. Form at GET /image-portal.html. Submit
# writes to the credential dirs the image_gen_router already knows how
# to read from:
#   ~/.openclaw/workspace/credentials/openai-api.json     (chmod 600)
#   ~/.openclaw/workspace/credentials/openrouter-api.json  (chmod 600)
#   ~/.openclaw-instance2/workspace/clients/swing-shack/credentials/openai-api.json
#   ~/.openclaw-instance2/workspace/clients/swing-shack/credentials/openrouter-api.json
# These are the canonical fallback locations the router looks for when
# env vars aren't set.
#
# For the LIVE Railway deploy, the keys still need to be set as env vars
# via the Railway dashboard — this portal can't push to Railway directly.
# The portal page makes that explicit with a "Setting keys on Railway"
# step-by-step section.

IMAGE_CRED_DIRS = [
    os.path.expanduser('~/.openclaw/workspace/credentials'),
    os.path.expanduser('~/.openclaw-instance2/workspace/clients/swing-shack/credentials'),
]


@app.route('/image-portal.html', methods=['GET'])
def image_portal_page():
    return send_from_directory(os.path.dirname(__file__), 'image-portal.html')


@app.route('/image-portal', methods=['POST'])
def image_portal_submit():
    """POST /image-portal — write OpenAI / OpenRouter keys to credential dirs.

    Three persistence layers:
      1. IMAGE_CRED_DIRS (multi-path fallback chain — local + Railway's $HOME)
      2. DATA_DIR/credentials/ (so the next deploy restart picks them up via
         OPENAI_API_KEY_FILE / OPENROUTER_API_KEY_FILE env vars we set below)
      3. os.environ — so the CURRENT process can use them immediately,
         no Railway dashboard round-trip needed
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
        openai = (body.get('openai') or '').strip()
        openrouter = (body.get('openrouter') or '').strip()

        if not openai and not openrouter:
            return jsonify({"ok": False, "error": "at least one key required"}), 400

        wrote_openai = None
        wrote_openrouter = None
        # Also write to DATA_DIR/credentials so the keys survive deploy restarts
        runtime_creds_dir = os.path.join(DATA_DIR, 'credentials')
        os.makedirs(runtime_creds_dir, exist_ok=True)

        if openai:
            # Basic shape validation
            if not openai.startswith('sk-'):
                return jsonify({"ok": False, "error": "OpenAI key should start with 'sk-'"}), 400
            payload = json.dumps({"api_key": openai, "updated": time.time()}, indent=2)
            for d in IMAGE_CRED_DIRS:
                try:
                    os.makedirs(d, exist_ok=True)
                    p = os.path.join(d, 'openai-api.json')
                    with open(p, 'w') as fh:
                        fh.write(payload)
                    os.chmod(p, 0o600)
                    wrote_openai = wrote_openai or p
                except Exception as e:
                    _app_log.warning('failed to write %s: %s', d, e)
            # Runtime persistence — survives restart
            try:
                rp = os.path.join(runtime_creds_dir, 'openai-api.json')
                with open(rp, 'w') as fh:
                    fh.write(payload)
                os.chmod(rp, 0o600)
                # Set file env var so the resolver picks it up next restart
                os.environ['OPENAI_API_KEY_FILE'] = rp
                wrote_openai = wrote_openai or rp
            except Exception as e:
                _app_log.warning('failed to write runtime openai cred: %s', e)
            # In-process env var so current request cycle sees the key
            os.environ['OPENAI_API_KEY'] = openai

        if openrouter:
            if not openrouter.startswith('sk-or-'):
                return jsonify({"ok": False, "error": "OpenRouter key should start with 'sk-or-'"}), 400
            payload = json.dumps({"api_key": openrouter, "updated": time.time()}, indent=2)
            for d in IMAGE_CRED_DIRS:
                try:
                    os.makedirs(d, exist_ok=True)
                    p = os.path.join(d, 'openrouter-api.json')
                    with open(p, 'w') as fh:
                        fh.write(payload)
                    os.chmod(p, 0o600)
                    wrote_openrouter = wrote_openrouter or p
                except Exception as e:
                    _app_log.warning('failed to write %s: %s', d, e)
            # Runtime persistence — survives restart
            try:
                rp = os.path.join(runtime_creds_dir, 'openrouter-api.json')
                with open(rp, 'w') as fh:
                    fh.write(payload)
                os.chmod(rp, 0o600)
                os.environ['OPENROUTER_API_KEY_FILE'] = rp
                wrote_openrouter = wrote_openrouter or rp
            except Exception as e:
                _app_log.warning('failed to write runtime openrouter cred: %s', e)
            # In-process env var so current request cycle sees the key
            os.environ['OPENROUTER_API_KEY'] = openrouter

        # Refresh status report so subsequent /api/image/status reflects new keys
        try:
            from _lib.image_gen_router import status_report as _status
            clear = getattr(_status, "cache_clear", None)
            if callable(clear):
                clear()
            # Also clear the provider-key caches so generate/edit pick up new keys
            from _lib import image_gen_router as _igr
            for name in ('_resolve_openai_key', '_resolve_openrouter_key'):
                fn = getattr(_igr, name, None)
                clr = getattr(fn, 'cache_clear', None) if fn else None
                if callable(clr):
                    clr()
        except Exception:
            pass

        # Report back what status says NOW
        from _lib.image_gen_router import status_report as _status_now
        new_status = _status_now()
        return jsonify({
            "ok": True,
            "wrote_openai": wrote_openai,
            "wrote_openrouter": wrote_openrouter,
            "next_step": "Keys live in the running process. For deploy restarts, set OPENAI_API_KEY / OPENROUTER_API_KEY env vars on Railway dashboard.",
            "status_now": new_status,
        })
    except Exception as e:
        _app_log.exception('image_portal_submit failed')
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/brand-images/<brand_id>/<path:filename>', methods=['GET'])
def brand_image_serve(brand_id, filename):
    """GET /brand-images/<brand>/ — serve a brand-directory image.

    Used by the Visual Library UI to display thumbnails. Safe: resolves to
    a path inside the brand-directory and rejects traversal attempts.

    If the file is not found under the requested brand (e.g. a DNA record
    indexed under swing-shack but the actual PNG lives under takomo/),
    fall back to scanning every other brand directory for the same
    filename. This stops the Visual Library from emitting broken-image
    404s for orphan DNA records without changing the data.
    """
    from pathlib import Path as _P
    base = (_P(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / 'images').resolve()
    target = (base / filename).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return jsonify({"error": "path traversal denied"}), 403
    if target.exists() and target.is_file():
        return send_from_directory(str(target.parent), target.name)
    # Fallback: scan sibling brand directories for the same filename.
    # Filenames are unique per file (no collisions across brands), and this
    # keeps orphan DNA records rendering without surfacing a 404 to users.
    try:
        root = (_P(BUNDLED_DATA_DIR) / 'brand-directory').resolve()
        for sibling in root.iterdir():
            if not sibling.is_dir() or sibling.name == brand_id:
                continue
            cand = (sibling / 'images' / filename).resolve()
            try:
                cand.relative_to(root)
            except ValueError:
                continue
            if cand.exists() and cand.is_file():
                return send_from_directory(str(cand.parent), cand.name)
    except Exception:
        pass
    return jsonify({"error": "not found", "path": str(target)}), 404


@app.route('/api/visual-library/<brand_id>/images', methods=['GET'])
def visual_library_images(brand_id):
    """GET /api/visual-library/<brand>/images — full image roster with DNA preview.

    Returns one entry per image with everything the Visual Library grid needs:
    filename, url, dna score, palette, luminance, products, OCR snippet,
    aspect ratio. Designed to render a full grid in one request.

    Query params:
      product   — filter to images tagged with this product
      min_score — only images with brand-alignment score >= N (0.0-1.0)
      sort      — score | filename | modified (default score desc)
      limit     — cap results (default 200)
    """
    try:
        from pathlib import Path as _P
        import re, base64 as _b64
        index_path = _P(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / "visual-dna-index.json"
        if not index_path.exists():
            return jsonify({"error": f"no visual-dna index for {brand_id}"}), 404
        idx = json.loads(index_path.read_text())
        by_filename = idx.get("by_filename", {})

        product_filter = request.args.get("product", "").strip()
        min_score = float(request.args.get("min_score", "0") or "0")
        sort_by = request.args.get("sort", "score")
        limit = min(int(request.args.get("limit", "200") or "200"), 500)

        # Canonical images dir relative to BUNDLED_DATA_DIR — used for both jpg and DNA JSON
        images_dir = _P(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / 'images'

        def _resolve_dna(dna_path_str, filename):
            """Resolve a DNA file path robustly across local + Railway.

            The index stores absolute local paths which only resolve on the
            machine that generated them. On Railway, those paths are bogus.
            Fall back to images_dir/.visual-dna.json.
            """
            if dna_path_str and _P(dna_path_str).exists():
                return _P(dna_path_str)
            stem = _P(filename).stem
            candidate = images_dir / f"{stem}.visual-dna.json"
            return candidate if candidate.exists() else None

        # Sibling-scan used by /brand-images/<brand>/<file> at serve time.
        # Re-used here so we can flag an entry as `image_missing=true` when
        # the raw .png/.jpg doesn't exist ANYWHERE on the deployed volume
        # (e.g. DNA record indexed under swing-shack but the .png lives under
        # takomo/ and is gitignored → never reaches Railway). Without this,
        # the front-end issues a doomed 404 for every orphan card.
        _bd_root = (_P(BUNDLED_DATA_DIR) / 'brand-directory').resolve()
        _sibling_brands = [p.name for p in _bd_root.iterdir() if p.is_dir() and p.name != brand_id and p.name != '_system'] if _bd_root.exists() else []

        def _image_on_disk(filename):
            """True iff `filename` resolves under ANY brand directory on disk."""
            # Primary location: the requested brand
            if (images_dir / filename).exists():
                return True
            # Sibling brands (orphan DNA fallback path)
            stem = _P(filename).name  # strip any path prefix safely
            for sib in _sibling_brands:
                cand = _bd_root / sib / 'images' / stem
                if cand.exists():
                    return True
            return False

        out = []
        for fn, meta in by_filename.items():
            dna_p = _resolve_dna(meta.get("dna_path", ""), fn)
            if dna_p is None:
                continue
            try:
                dna = json.loads(dna_p.read_text())
            except Exception:
                continue
            # Extract features — schema fallback for layer4_products
            l4 = dna.get("layer4_products", {}) or {}
            raw_products = l4.get("products")
            raw_brands = l4.get("detected_brands")
            products = raw_products if raw_products is not None else (raw_brands or [])
            if raw_products:
                product_names = [p.get("name", "") if isinstance(p, dict) else str(p) for p in raw_products]
            elif raw_brands:
                product_names = []
                for b in raw_brands:
                    if isinstance(b, str):
                        product_names.append(b)
                    elif isinstance(b, dict):
                        bn = b.get("name") or b.get("label") or b.get("brand") or ""
                        if bn:
                            product_names.append(str(bn))
            else:
                product_names = []
            palette = dna.get("layer9_palette", {}).get("dominant_colors", [])[:5]
            palette_hex = [c.get("hex") for c in palette if c.get("hex")]
            composition = dna.get("layer10_composition", {})
            # Schema fallback for OCR: lines[] or text_preview
            ocr = dna.get("layer6_ocr", {})
            if isinstance(ocr, dict):
                ocr_lines = ocr.get("lines") or []
                if not ocr_lines:
                    tp = ocr.get("text_preview")
                    if isinstance(tp, str):
                        ocr_lines = [tp]
                ocr_text = " ".join(ocr_lines)[:200]
            else:
                ocr_text = ""
            l1 = dna.get("layer1_metadata", {})
            l7 = dna.get("layer7_typography", {})
            l17 = dna.get("layer17_recipe", {})
            # Apply filters
            if product_filter and not any(product_filter.lower() in (p or "").lower() for p in product_names):
                continue
            score = float(meta.get("score", 0) or 0)
            if score < min_score:
                continue
            # If the underlying image isn't on disk (orphan DNA record whose
            # .png lives under a sibling brand that isn't gitignored, OR the
            # .png never made it onto the Railway volume because of the
            # brand-images gitignore rule), expose image_missing=true and
            # null out `url` so the front-end renders the DNA placeholder
            # WITHOUT firing a doomed network request.
            _has_thumb = bool(dna.get("thumbnail_b64"))
            _on_disk = _image_on_disk(fn)
            _image_missing = (not _has_thumb) and (not _on_disk)
            entry = {
                "filename": fn,
                "url": (None if _image_missing else f"/brand-images/{brand_id}/{fn}"),
                "image_missing": _image_missing,
                "dna_url": f"/brand-images/{brand_id}/{fn.replace('.jpg', '.visual-dna.json').replace('.jpeg', '.visual-dna.json').replace('.png', '.visual-dna.json')}",
                "score": round(score, 3),
                "luminance": meta.get("luminance", ""),
                "dominant": meta.get("dominant", ""),
                "palette": palette_hex,
                "palette_full": palette,
                "products": product_names,
                "aspect_ratio": l1.get("aspect_ratio"),
                "orientation": l1.get("orientation"),
                "width": l1.get("width_px"),
                "height": l1.get("height_px"),
                "ocr_snippet": ocr_text,
                "typography": l7.get("fonts_detected", []) if isinstance(l7, dict) else [],
                "composition": {
                    "rule_of_thirds": composition.get("rule_of_thirds_score"),
                    "focal_point": composition.get("focal_point"),
                    "symmetry": composition.get("symmetry_score"),
                } if composition else {},
                "recipe": l17 if l17 else None,
                "tagline": dna.get("layer8_compliance", {}).get("summary", "") if isinstance(dna.get("layer8_compliance"), dict) else "",
                # Inline thumbnail (data URL) so the grid works on Railway without the
                # actual jpg files. The images dir is gitignored; thumbnails are embedded
                # in each DNA JSON at build time.
                "thumbnail_data_url": (f"data:image/jpeg;base64,{dna['thumbnail_b64']}" if dna.get("thumbnail_b64") else None),
                "thumbnail_w": dna.get("thumbnail_w"),
                "thumbnail_h": dna.get("thumbnail_h"),
                # Searchable blob (lowercase) for client-side text matching
                "_search_blob": " ".join([
                    fn.lower(),
                    ocr_text.lower(),
                    " ".join(product_names).lower(),
                    " ".join(palette_hex).lower(),
                    (dna.get("layer8_compliance", {}) or {}).get("summary", "").lower() if isinstance(dna.get("layer8_compliance"), dict) else "",
                    str(meta.get("dominant", "")).lower(),
                ]).strip(),
            }
            out.append(entry)

        # Sort
        if sort_by == "score":
            out.sort(key=lambda x: x["score"], reverse=True)
        elif sort_by == "filename":
            out.sort(key=lambda x: x["filename"].lower())
        elif sort_by == "modified":
            out.sort(key=lambda x: x["filename"].lower(), reverse=True)
        out = out[:limit]
        return jsonify({
            "brand": brand_id,
            "total": len(out),
            "filters": {"product": product_filter, "min_score": min_score, "sort": sort_by},
            "products_available": sorted(set(p for e in out for p in e["products"])),
            "images": out,
        })
    except Exception as e:
        _app_log.exception("visual_library_images failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/visual-library/<brand_id>/stats', methods=['GET'])
def visual_library_stats(brand_id):
    """GET /api/visual-library/<brand>/stats — palette + product + score histograms.

    Used to drive the filter chips and dashboard summary tiles in the
    Visual Library tab.
    """
    try:
        from pathlib import Path as _P
        from collections import Counter
        index_path = _P(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / "visual-dna-index.json"
        if not index_path.exists():
            return jsonify({"error": f"no visual-dna index for {brand_id}"}), 404
        idx = json.loads(index_path.read_text())
        by_filename = idx.get("by_filename", {})

        product_counts = Counter()
        luminance_counts = Counter()
        color_counts = Counter()
        score_buckets = Counter()
        orientation_counts = Counter()
        for fn, meta in by_filename.items():
            dna_path_str = meta.get("dna_path", "")
            if not dna_path_str:
                continue
            dna_p = _P(dna_path_str)
            if not dna_p.exists():
                continue
            try:
                dna = json.loads(dna_p.read_text())
            except Exception:
                continue
            # Schema fallback: dissector may emit `products` (list of dicts) or
            # `detected_brands` (list of strings) — handle both.
            l4 = dna.get("layer4_products", {}) or {}
            raw_products = l4.get("products")
            raw_brands = l4.get("detected_brands")
            if raw_products:
                for p in raw_products:
                    pname = p.get("name", "?") if isinstance(p, dict) else str(p)
                    if pname and pname != "?":
                        product_counts[pname] += 1
            elif raw_brands:
                for b in raw_brands:
                    if isinstance(b, str) and b.strip():
                        product_counts[b.strip()] += 1
                    elif isinstance(b, dict):
                        bn = b.get("name") or b.get("label") or b.get("brand")
                        if bn:
                            product_counts[str(bn)] += 1
            lm = meta.get("luminance", "?")
            luminance_counts[lm] += 1
            dom = meta.get("dominant", "?")
            color_counts[dom] += 1
            sc = float(meta.get("score", 0) or 0)
            bucket = "high" if sc >= 0.8 else "mid" if sc >= 0.65 else "low"
            score_buckets[bucket] += 1
            ori = dna.get("layer1_metadata", {}).get("orientation", "?")
            orientation_counts[ori] += 1

        return jsonify({
            "brand": brand_id,
            "total_images": idx.get("image_count", len(by_filename)),
            "tagged_count": idx.get("tagged_count", len(by_filename)),
            "products": dict(product_counts.most_common()),
            "luminance": dict(luminance_counts),
            "top_dominant_colors": [{"hex": h, "count": c} for h, c in color_counts.most_common(20)],
            "score_distribution": dict(score_buckets),
            "orientations": dict(orientation_counts),
        })
    except Exception as e:
        _app_log.exception("visual_library_stats failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/visual-library/search', methods=['GET'])
def visual_library_search():
    """GET /api/visual-library/search — image-only search across brand-directory images.

    Query params:
      q=<text>       — required, 2+ chars. Matches filename, OCR text, products, palette hex.
      brand=<id>     — optional, restrict to one brand (e.g. swing-shack, takomo). If omitted
                       or "all", searches every brand that has a visual-dna-index.json.
      product=<name> — optional, restrict to images tagged with this product.
      min_score=<n>  — optional, only images with score >= N.
      limit=<n>      — default 60, max 200.

    Returns:
      {ok, query, brand, count, results: [{brand, filename, url, score, products, ocr, palette, thumbnail_url}], total}
    """
    try:
        from pathlib import Path as _P
        q = (request.args.get('q') or '').strip()
        if len(q) < 2:
            return jsonify({"ok": False, "error": "q must be 2+ chars", "results": [], "count": 0}), 400
        brand_filter = (request.args.get('brand') or '').strip().lower()
        product_filter = (request.args.get('product') or '').strip().lower()
        try:
            min_score = float(request.args.get('min_score') or 0)
        except ValueError:
            min_score = 0.0
        try:
            limit = min(int(request.args.get('limit') or 60), 200)
        except ValueError:
            limit = 60
        needle = q.lower()

        brand_root = _P(os.path.join(BUNDLED_DATA_DIR, 'brand-directory'))
        if not brand_root.exists():
            return jsonify({"ok": False, "error": "brand-directory missing", "results": [], "count": 0}), 500

        # Decide which brands to search
        if brand_filter and brand_filter != 'all':
            brand_dirs = [brand_root / brand_filter] if (brand_root / brand_filter).is_dir() else []
        else:
            brand_dirs = sorted([p for p in brand_root.iterdir() if p.is_dir()])

        results = []
        seen = set()
        for brand_dir in brand_dirs:
            bid = brand_dir.name
            idx_path = brand_dir / 'visual-dna-index.json'
            if not idx_path.exists():
                continue
            try:
                idx = json.loads(idx_path.read_text())
            except Exception:
                continue
            # Canonical images dir relative to BUNDLED_DATA_DIR — same fallback
            # strategy used by /api/visual-library/<brand>/images.
            images_dir = brand_dir / 'images'
            def _resolve_dna_search(dna_path_str, filename, imgs_dir):
                if dna_path_str and _P(dna_path_str).exists():
                    return _P(dna_path_str)
                stem = _P(filename).stem
                candidate = imgs_dir / f"{stem}.visual-dna.json"
                return candidate if candidate.exists() else None

            for fn, meta in (idx.get('by_filename') or {}).items():
                dna_p = _resolve_dna_search((meta or {}).get('dna_path', ''), fn, images_dir)
                if dna_p is None:
                    continue
                try:
                    dna = json.loads(dna_p.read_text())
                except Exception:
                    continue
                # Build search blob
                prods_raw = dna.get('layer4_products', {}) or {}
                # Handle BOTH schemas: products=[{name:...}] OR detected_brands=["..."]
                prod_names = []
                if isinstance(prods_raw.get('products'), list):
                    for p in prods_raw['products']:
                        if isinstance(p, dict):
                            n = p.get('name') or p.get('label') or ''
                            if n: prod_names.append(str(n))
                        elif p:
                            prod_names.append(str(p))
                if not prod_names and isinstance(prods_raw.get('detected_brands'), list):
                    for p in prods_raw['detected_brands']:
                        if isinstance(p, dict):
                            n = p.get('name') or p.get('label') or ''
                            if n: prod_names.append(str(n))
                        elif p:
                            prod_names.append(str(p))
                ocr_raw = dna.get('layer6_ocr', {}) or {}
                ocr_lines = ocr_raw.get('lines') or ([ocr_raw['text_preview']] if ocr_raw.get('text_preview') else [])
                ocr_text = ' '.join([str(x) for x in ocr_lines if x])
                palette = ((dna.get('layer9_palette', {}) or {}).get('dominant_colors', []) or [])
                palette_hex = [c.get('hex', '') for c in palette if isinstance(c, dict)]
                # Map hex codes to human color names so search by color works
                def _hex_to_names(h):
                    if not h or not h.startswith('#') or len(h) < 7:
                        return []
                    try:
                        r=int(h[1:3],16); g=int(h[3:5],16); b=int(h[5:7],16)
                    except ValueError:
                        return []
                    names = []
                    # Detect hue families
                    if g > r + 15 and g > b + 15 and g >= 80:
                        names.append('green')
                        if r > 150: names.append('lime')
                        if g > 180 and r < 100: names.append('bright green')
                    if r > g + 30 and r > b + 50 and r > 120:
                        names.append('red')
                        if r > 200 and g < 80 and b < 80: names.append('bright red')
                    if b > r + 20 and b > g + 30 and b > 120:
                        names.append('blue')
                        if r < 100 and g < 100: names.append('navy')
                    if r > 180 and g > 130 and b < 100:
                        names.append('yellow'); names.append('gold')
                    if r > 150 and g < 100 and b > 130:
                        names.append('purple'); names.append('magenta')
                    if r > 200 and g > 150 and b > 100:
                        names.append('orange'); names.append('beige')
                    # Brightness
                    avg = (r+g+b)/3
                    if avg > 220: names.append('light'); names.append('bright')
                    elif avg < 60: names.append('dark')
                    if abs(r-g) < 15 and abs(g-b) < 15 and abs(r-b) < 15:
                        if avg > 180: names.append('white')
                        elif avg < 50: names.append('black')
                        else: names.append('gray'); names.append('grey')
                    return names
                palette_names = []
                for h in palette_hex:
                    palette_names.extend(_hex_to_names(h))
                score = float((meta or {}).get('score', 0) or 0)
                if score < min_score:
                    continue
                # Product filter early
                if product_filter and not any(product_filter in p.lower() for p in prod_names):
                    continue
                blob = ' '.join([
                    fn, bid,
                    ' '.join(prod_names),
                    ocr_text,
                    ' '.join(palette_hex),
                    ' '.join(palette_names),
                ]).lower()
                if needle not in blob:
                    continue
                # Scoring: filename hit > product hit > OCR > palette
                s = 60
                if needle in fn.lower():
                    s += 25
                if any(needle in p.lower() for p in prod_names):
                    s += 10
                if needle in ocr_text.lower():
                    s += 5
                key = f"{bid}/{fn}"
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    'brand': bid,
                    'filename': fn,
                    'url': f"/brand-images/{bid}/{fn}",
                    'thumbnail_url': f"/brand-images/{bid}/{fn}",
                    'score': round(score, 3),
                    'products': prod_names[:5],
                    'ocr_snippet': ocr_text[:140],
                    'palette': palette_hex[:5],
                    'relevance': s,
                })
        # Sort by relevance desc, then score desc
        results.sort(key=lambda r: (-(r.get('relevance', 0)), -(r.get('score', 0))))
        return jsonify({
            'ok': True,
            'query': q,
            'brand': brand_filter or 'all',
            'count': len(results),
            'results': results[:limit],
            'total': len(results),
        })
    except Exception as e:
        _app_log.exception("visual_library_search failed")
        return jsonify({"ok": False, "error": str(e), "results": [], "count": 0}), 500


@app.route('/api/visual-library/brands', methods=['GET'])
def visual_library_brands():
    """GET /api/visual-library/brands — list every brand with an index + counts."""
    try:
        from pathlib import Path as _P
        brand_root = _P(os.path.join(BUNDLED_DATA_DIR, 'brand-directory'))
        if not brand_root.exists():
            return jsonify({'brands': []})
        out = []
        for brand_dir in sorted([p for p in brand_root.iterdir() if p.is_dir()]):
            bid = brand_dir.name
            idx_path = brand_dir / 'visual-dna-index.json'
            if not idx_path.exists():
                continue
            try:
                idx = json.loads(idx_path.read_text())
            except Exception:
                continue
            by_fn = idx.get('by_filename', {}) or {}
            out.append({
                'brand': bid,
                'image_count': len(by_fn),
                'indexed': True,
            })
        return jsonify({'ok': True, 'brands': out, 'count': len(out)})
    except Exception as e:
        _app_log.exception("visual_library_brands failed")
        return jsonify({'ok': False, 'error': str(e), 'brands': []}), 500


@app.route('/api/visual-library/<path:filename>', methods=['GET'])
def visual_library_static_json(filename):
    """GET /api/visual-library/<path> — serve system JSON files (e.g. all-elements.json)."""
    from pathlib import Path as _P
    if '..' in filename or filename.startswith('/'):
        return jsonify({"ok": False, "error": "bad path"}), 400
    target = _P(BUNDLED_DATA_DIR) / 'brand-directory' / filename
    if not target.exists() or not target.is_file():
        return jsonify({"ok": False, "error": f"not found: {filename}"}), 404
    try:
        if filename.endswith('.json'):
            data = json.loads(target.read_text())
            return jsonify(data)
        return app.send_static_file(str(target)) if hasattr(app, 'send_static_file') else (target.read_text(), 200, {'Content-Type': 'application/json'})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ============================================================================
# ELEMENT-LEVEL DISCOVERY — find images by any visible element
# ============================================================================

@app.route('/api/visual-library/<brand_id>/discover', methods=['GET'])
def visual_library_discover(brand_id):
    """GET /api/visual-library/<brand>/discover — element-level multi-field search.

    Query params (all optional, AND-combined across categories, OR within):
      color=<name>       — yellow, blue, white, black, gold, etc. (matches anywhere in image)
      brand=<name>       — Callaway, Mizuno, Takomo, etc.
      object=<tag>       — product, lifestyle, minimal, dramatic, text-overlay
      mood=<tag>         — energetic, calm, luxurious, playful, professional, clean
      composition=<tag>  — centered, rule-of-thirds, landscape, portrait, high-detail
      quality_min=<n>    — 1-100, only images scoring >= N
      text=<substring>   — searchable OCR text (any substring match)
      sort=<field>       — quality_score | filename (default quality_score desc)
      limit=<n>          — default 60, max 200

    Returns:
      {ok, brand, filters_applied, count, results: [{filename, score, colors, brands, objects, mood, quality_score, dna_path, image_url, thumbnail_data_url}]}
    """
    try:
        from pathlib import Path as _P
        import re

        # Load element index
        idx_path = _P(BUNDLED_DATA_DIR) / "brand-directory" / "_system" / "all-elements.json"
        if not idx_path.exists():
            return jsonify({"ok": False, "error": "element index not found; run batch indexer", "results": [], "count": 0}), 404
        all_idx = json.loads(idx_path.read_text())
        brand_idx = all_idx.get(brand_id)
        if not brand_idx:
            return jsonify({"ok": False, "error": f"no element index for brand={brand_id}", "results": [], "count": 0}), 404

        by_filename = brand_idx.get("by_filename", {})

        # Resolve DNA per image so we can ship an inline thumbnail (data: URI).
        # Same pattern as /api/visual-library/<brand>/images — the index stores
        # absolute local paths that don't resolve on Railway, so fall back to the
        # canonical images_dir location. Raw .jpg files are gitignored; the
        # thumbnail_b64 in each DNA JSON is the deploy-safe image bytes.
        images_dir = _P(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / 'images'

        def _resolve_dna(dna_path_str, filename):
            if dna_path_str and _P(dna_path_str).exists():
                return _P(dna_path_str)
            stem = _P(filename).stem
            candidate = images_dir / f"{stem}.visual-dna.json"
            return candidate if candidate.exists() else None

        # Parse filters
        color_filter = (request.args.get("color") or "").strip().lower()
        brand_filter = (request.args.get("brand") or "").strip().lower()
        object_filter = (request.args.get("object") or "").strip().lower()
        mood_filter = (request.args.get("mood") or "").strip().lower()
        composition_filter = (request.args.get("composition") or "").strip().lower()
        text_filter = (request.args.get("text") or "").strip().lower()
        try:
            quality_min = int(request.args.get("quality_min") or 0)
        except ValueError:
            quality_min = 0
        sort_by = (request.args.get("sort") or "quality_score").strip()
        try:
            limit = min(int(request.args.get("limit") or 60), 200)
        except ValueError:
            limit = 60

        applied = {}
        if color_filter: applied["color"] = color_filter
        if brand_filter: applied["brand"] = brand_filter
        if object_filter: applied["object"] = object_filter
        if mood_filter: applied["mood"] = mood_filter
        if composition_filter: applied["composition"] = composition_filter
        if text_filter: applied["text"] = text_filter
        if quality_min: applied["quality_min"] = quality_min

        results = []
        for fn, entry in by_filename.items():
            # Color match
            if color_filter:
                if not any(color_filter in c.lower() for c in entry.get("colors", [])):
                    continue
            # Brand match
            if brand_filter:
                if not any(brand_filter in b.lower() for b in entry.get("brands", [])):
                    continue
            # Object match
            if object_filter:
                if not any(object_filter in o.lower() for o in entry.get("objects", [])):
                    continue
            # Mood match
            if mood_filter:
                if not any(mood_filter in m.lower() for m in entry.get("mood", [])):
                    continue
            # Composition match
            if composition_filter:
                if not any(composition_filter in c.lower() for c in entry.get("composition_tags", [])):
                    continue
            # Text match
            if text_filter:
                if text_filter not in entry.get("text", "").lower():
                    continue
            # Quality threshold
            if entry.get("quality_score", 0) < quality_min:
                continue

            # Resolve DNA + extract inline thumbnail (data: URI) so discover
            # results render on Railway without raw .jpg bytes on the volume.
            # Same pattern as /api/visual-library/<brand>/images.
            dna_path = entry.get("dna_path", "")
            dna_p = _resolve_dna(dna_path, fn)
            thumbnail_data_url = None
            if dna_p is not None:
                try:
                    dna = json.loads(dna_p.read_text())
                    tb = dna.get("thumbnail_b64")
                    if tb:
                        thumbnail_data_url = f"data:image/jpeg;base64,{tb}"
                except Exception:
                    pass

            results.append({
                "filename": fn,
                "dna_path": entry.get("dna_path", ""),
                "image_url": f"/api/visual-library/{brand_id}/image/{fn}.jpg",
                "thumbnail_data_url": thumbnail_data_url,
                "colors": entry.get("colors", []),
                "brands": entry.get("brands", []),
                "objects": entry.get("objects", []),
                "mood": entry.get("mood", []),
                "composition_tags": entry.get("composition_tags", []),
                "quality_score": entry.get("quality_score", 0),
                "text_preview": (entry.get("text", "") or "")[:120],
            })

        # Sort
        if sort_by == "quality_score":
            results.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
        elif sort_by == "filename":
            results.sort(key=lambda x: x.get("filename", ""))

        results = results[:limit]
        return jsonify({
            "ok": True,
            "brand": brand_id,
            "filters_applied": applied,
            "count": len(results),
            "total_matched": len(results),
            "results": results,
        })
    except Exception as e:
        _app_log.exception("visual_library_discover failed")
        return jsonify({"ok": False, "error": str(e), "results": [], "count": 0}), 500


@app.route('/api/visual-library/<brand_id>/recipe', methods=['GET'])
def visual_library_recipe(brand_id):
    """GET /api/visual-library/<brand>/recipe - aggregated brand image DNA.

    Combines statistical mode (most common features) with top-performer emphasis.
    Returns human-readable recipe + numeric aggregates for use in image generation.

    Query params:
      top_pct=<n>   - top N% by quality score to weight heavily (default 25)

    Returns:
      {ok, brand, recipe: {palette, composition, products, moods, text, quality, style_clusters, summary}}
    """
    try:
        from pathlib import Path as _P
        idx_path = _P(BUNDLED_DATA_DIR) / "brand-directory" / "_system" / "all-elements.json"
        if not idx_path.exists():
            return jsonify({"ok": False, "error": "element index not found"}), 404
        all_idx = json.loads(idx_path.read_text())
        brand_idx = all_idx.get(brand_id)
        if not brand_idx:
            return jsonify({"ok": False, "error": f"no index for {brand_id}"}), 404

        by_filename = brand_idx.get("by_filename", {})
        try:
            top_pct = int(request.args.get("top_pct") or 25)
        except ValueError:
            top_pct = 25

        all_entries = list(by_filename.values())
        total = len(all_entries)
        if total == 0:
            return jsonify({"ok": False, "error": "no images indexed"}), 404

        # Sort by quality descending for top-performer weighting
        sorted_entries = sorted(all_entries, key=lambda e: e.get("quality_score", 0), reverse=True)
        top_n = max(1, int(total * top_pct / 100))
        top_entries = sorted_entries[:top_n]

        # Aggregate features
        from collections import Counter

        def counter_aggregate(entries, field, top_k=8):
            c = Counter()
            for e in entries:
                for item in e.get(field, []):
                    c[item] += 1
            return [{"name": k, "count": v, "pct": round(v * 100 / max(1, len(entries)), 1)} for k, v in c.most_common(top_k)]

        # All images aggregates
        all_colors = counter_aggregate(all_entries, "colors")
        all_brands = counter_aggregate(all_entries, "brands")
        all_objects = counter_aggregate(all_entries, "objects")
        all_moods = counter_aggregate(all_entries, "mood")
        all_composition = counter_aggregate(all_entries, "composition_tags")

        # Top performers aggregates (weighted 3x)
        top_colors = counter_aggregate(top_entries * 3, "colors")
        top_brands = counter_aggregate(top_entries * 3, "brands")
        top_objects = counter_aggregate(top_entries * 3, "objects")
        top_moods = counter_aggregate(top_entries * 3, "mood")

        # Quality stats
        quality_scores = [e.get("quality_score", 0) for e in all_entries]
        quality_stats = {
            "avg": round(sum(quality_scores) / total, 1) if total else 0,
            "max": max(quality_scores) if quality_scores else 0,
            "min": min(quality_scores) if quality_scores else 0,
            "high_count": sum(1 for s in quality_scores if s >= 75),
            "mid_count": sum(1 for s in quality_scores if 50 <= s < 75),
            "low_count": sum(1 for s in quality_scores if s < 50),
        }

        # Style clustering — group by primary object/mood signature
        style_signatures = Counter()
        for e in all_entries:
            sig = "|".join(sorted((e.get("objects", []) or [])[:2] + (e.get("mood", []) or [])[:1]))
            if sig.strip("|"):
                style_signatures[sig] += 1
        style_clusters = [
            {"signature": sig, "count": cnt, "pct": round(cnt * 100 / total, 1)}
            for sig, cnt in style_signatures.most_common(6)
        ]

        # Human-readable summary
        top_color_name = top_colors[0]["name"] if top_colors else "neutral"
        top_object_name = top_objects[0]["name"] if top_objects else "general"
        top_mood_name = top_moods[0]["name"] if top_moods else "neutral"
        dominant_brand = top_brands[0]["name"] if top_brands else "none"

        summary = (
            f"{brand_id} images lean {top_color_name} ({top_colors[0]['pct'] if top_colors else 0}%), "
            f"primarily {top_object_name} ({top_objects[0]['pct'] if top_objects else 0}%), "
            f"with {top_mood_name} mood ({top_moods[0]['pct'] if top_moods else 0}%). "
            f"Dominant brand: {dominant_brand}. "
            f"Quality: avg {quality_stats['avg']}/100, {quality_stats['high_count']} high-scoring images. "
            f"{len(style_clusters)} distinct visual style clusters detected."
        )

        return jsonify({
            "ok": True,
            "brand": brand_id,
            "image_count": total,
            "top_performer_count": top_n,
            "recipe": {
                "palette": {
                    "all": all_colors,
                    "top_performers": top_colors,
                    "primary": top_color_name,
                },
                "products": {
                    "all": all_brands,
                    "top_performers": top_brands,
                    "primary": dominant_brand,
                },
                "objects": {
                    "all": all_objects,
                    "top_performers": top_objects,
                    "primary": top_object_name,
                },
                "mood": {
                    "all": all_moods,
                    "top_performers": top_moods,
                    "primary": top_mood_name,
                },
                "composition": {
                    "all": all_composition,
                },
                "quality": quality_stats,
                "style_clusters": style_clusters,
                "summary": summary,
            },
        })
    except Exception as e:
        _app_log.exception("visual_library_recipe failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/visual-library/<brand_id>/generate', methods=['POST'])
def visual_library_generate(brand_id):
    """POST /api/visual-library/<brand>/generate — generate image using OpenAI + brand recipe.

    Request JSON (or query params):
      prompt=<text>           — required, what to generate (e.g. "Mizuno iron close-up, yellow accent")
      reference_color=<name>  — optional, color to emphasize
      reference_brand=<name>  — optional, brand to feature
      reference_mood=<name>   — optional, mood target
      size=<WxH>              — 1024x1024 | 1024x1792 | 1792x1024 (default 1024x1024)
      quality=<std|hd>        — default "standard"
      n=<int>                 — 1-4 images, default 1

    Returns:
      {ok, prompt_used, images: [{url, revised_prompt}], model, brand_recipe_applied}
    """
    try:
        body = request.get_json(silent=True) or {}
        # Allow query params too
        for k in ("prompt", "reference_color", "reference_brand", "reference_mood", "size", "quality"):
            if not body.get(k) and request.args.get(k):
                body[k] = request.args.get(k)
        try:
            n = int(body.get("n") or request.args.get("n") or 1)
        except ValueError:
            n = 1
        n = max(1, min(4, n))

        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"ok": False, "error": "prompt required"}), 400

        # Load brand recipe
        recipe_resp = visual_library_recipe(brand_id)
        recipe_data = recipe_resp.get_json() if recipe_resp.status_code == 200 else {}
        recipe = recipe_data.get("recipe", {}) if recipe_data else {}

        # Build enhanced prompt with recipe DNA
        prompt_parts = [prompt]
        if recipe:
            pal = recipe.get("palette", {}).get("primary")
            if pal and pal != "other" and pal != "neutral":
                prompt_parts.append(f"dominant color: {pal}")
            mood = recipe.get("mood", {}).get("primary")
            if mood and mood != "neutral":
                prompt_parts.append(f"mood: {mood}")
            obj = recipe.get("objects", {}).get("primary")
            if obj and obj != "general":
                prompt_parts.append(f"style: {obj}")

        # User-specified references
        if body.get("reference_color"):
            prompt_parts.append(f"accent color: {body['reference_color']}")
        if body.get("reference_brand"):
            prompt_parts.append(f"featuring brand: {body['reference_brand']}")
        if body.get("reference_mood"):
            prompt_parts.append(f"mood: {body['reference_mood']}")

        prompt_parts.append("professional product photography, clean composition, golf industry")
        enhanced_prompt = ". ".join(prompt_parts)

        # Load OpenAI key from env var (works on Railway) or fallback to local env file
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            # Fallback for local dev: read from canonical env file
            env_file = os.environ.get("OPENAI_ENV_FILE", "/Users/fivefriday/.openclaw/workspace/credentials/openai.env")
            if os.path.exists(env_file):
                for line in open(env_file):
                    if line.startswith("export OPENAI_API_KEY="):
                        api_key = line.split(chr(39))[1]
                        break

        if not api_key:
            return jsonify({"ok": False, "error": "OpenAI API key not configured. Set OPENAI_API_KEY env var on Railway, or submit via /openai-portal for local dev."}), 503

        # Call OpenAI gpt-image-1 (latest stable)
        import requests as _req
        size = body.get("size", "1024x1024")
        # Map user-friendly values to gpt-image-1's accepted values
        quality_input = body.get("quality", "auto")
        quality_map = {"std": "low", "standard": "low", "hd": "high", "low": "low", "medium": "medium", "high": "high", "auto": "auto"}
        quality = quality_map.get(str(quality_input).lower(), "auto")

        api_resp = _req.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-image-1",
                "prompt": enhanced_prompt,
                "size": size,
                "n": n,
                "quality": quality,
            },
            timeout=120,
        )

        if api_resp.status_code != 200:
            err_body = api_resp.text[:500]
            return jsonify({"ok": False, "error": f"OpenAI {api_resp.status_code}", "detail": err_body}), 502

        api_data = api_resp.json()
        save = body.get("save", False)
        # Resolve save dir for this brand
        try:
            save_dir = os.path.join(BUNDLED_DATA_DIR, "brand-directory", brand_id, "images")
        except Exception:
            save_dir = None

        images = []
        for i, item in enumerate(api_data.get("data", [])):
            entry = {
                "url": item.get("url"),
                "revised_prompt": item.get("revised_prompt", ""),
            }
            b64 = item.get("b64_json") or ""
            if b64:
                entry["b64_json_length"] = len(b64)
                # Build a data: URL so the visualizer can preview inline (URLs may expire)
                entry["dataUrl"] = "data:image/png;base64," + b64
            # Save to disk if save=true
            if save and save_dir and b64:
                try:
                    os.makedirs(save_dir, exist_ok=True)
                    import base64 as _b64, time as _t
                    ts = int(_t.time())
                    fname = f"gen-{brand_id}-{ts}-{i+1}.png"
                    fpath = os.path.join(save_dir, fname)
                    with open(fpath, "wb") as fh:
                        fh.write(_b64.b64decode(b64))
                    # Write a tiny sidecar metadata so the file shows up in stats
                    sidecar = fpath + ".meta.json"
                    with open(sidecar, "w") as fh:
                        json.dump({
                            "brand_id": brand_id,
                            "prompt": prompt,
                            "enhanced_prompt": enhanced_prompt,
                            "revised_prompt": entry["revised_prompt"],
                            "model": "gpt-image-1",
                            "quality": quality,
                            "size": size,
                            "ts": ts,
                        }, fh)
                    entry["saved"] = True
                    entry["saved_path"] = fpath
                except Exception as save_err:
                    _app_log.warning("save failed: %s", save_err)
                    entry["saved"] = False
            images.append(entry)

        return jsonify({
            "ok": True,
            "brand": brand_id,
            "model": "gpt-image-1",
            "prompt_used": enhanced_prompt,
            "images": images,
            "brand_recipe_applied": {
                "primary_color": recipe.get("palette", {}).get("primary"),
                "primary_mood": recipe.get("mood", {}).get("primary"),
                "primary_object": recipe.get("objects", {}).get("primary"),
                "summary": recipe.get("summary", ""),
            } if recipe else None,
            "user_references": {
                "color": body.get("reference_color"),
                "brand": body.get("reference_brand"),
                "mood": body.get("reference_mood"),
            },
        })
    except Exception as e:
        _app_log.exception("visual_library_generate failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── IMAGE GEN ROUTER — unified generate + edit across the OS ───────
#
# Three new endpoints that wire every section of Campaign OS to the same
# router (campaign-os/_lib/image_gen_router.py). The router picks between
# OpenAI direct (gpt-image-1, text-to-image only) and OpenRouter
# (Nano Banana / gpt-5-image-mini / Nano Banana Pro, both gen + edit).
#
# - POST /api/image/generate        — generate from text prompt (brand-aware)
# - POST /api/image/edit            — edit existing image (recolour, restyle, swap)
# - POST /api/image/from-asset/<id> — pull an asset from another surface,
#                                     extract its visual context, generate a
#                                     matching hero image
# - GET  /api/image/status          — capabilities + key presence


@app.route('/api/image/status', methods=['GET'])
def image_router_status():
    """GET /api/image/status - provider + credential status (no key values echoed)."""
    try:
        from _lib.image_gen_router import status_report as _status
        return jsonify({"ok": True, **_status()})
    except Exception as e:
        _app_log.exception("image_router_status failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/brand-dna/<brand_id>', methods=['GET'])
def image_brand_dna(brand_id):
    """GET /api/image/brand-dna/<brand> - brand DNA + recipe for the UI Recipe panel.

    Returns the brand_dna context that the image gen layer will use to constrain
    the next generation: palette hex codes, philosophy, keywords, top reference
    images, bible status, warnings. Cheap, no API call. Call this on page load
    to render the Recipe panel BEFORE the user clicks Generate.

    The same payload is also included in /api/image/generate's response under
    `brand_recipe` after a generation completes, so the UI can confirm what
    the model actually saw vs what it was told.
    """
    try:
        from _lib.brand_dna import load_brand_context, build_recipe_summary
        ctx = load_brand_context(brand_id)
        return jsonify({"ok": True, **build_recipe_summary(ctx)})
    except Exception as e:
        _app_log.exception("image_brand_dna failed for %s", brand_id)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/generate', methods=['POST'])
def image_generate():
    """POST /api/image/generate — generate image from text prompt.

    Request JSON:
      prompt (required)
      brand_id        (optional, but recommended — used for recipe + save path)
      size            (default "1024x1024"; valid: 1024x1024, 1024x1792, 1792x1024)
      n               (default 1; OpenAI supports up to 4)
      model           (optional override)
      provider        (optional: "openai" or "openrouter", default = env or openrouter)
      save            (default true; requires brand_id)
      max_cost_usd    (default 0.50)
      reference_color / reference_brand / reference_mood (optional overrides)

      // 4-layer compose context (added 2026-08-07)
      reference_ids   (optional list of ref-xxxxxx — Visual Reference Library entries)
      product_ids     (optional list of product-xxxx — Product Library entries)
      service_ids     (optional list of service-xxxx — Product Library entries)
      include_learned_signals (optional bool, default true — inject WIN PROFILE)

    Returns:
      {ok, bytes_b64, mime, model, provider, cost_estimate_usd, prompt_used,
       saved_path, saved_sidecar_path, warning, usage, layers}
      where `layers` summarises which compose layers fired (signals/refs/products/recipe)
    """
    try:
        from _lib.image_gen_router import generate_image as _gen, ImageGenBadRequest, ImageGenAuthError, ImageGenNetworkError, ImageGenUpstreamError
        from _lib.reference_dna import load_reference_dna
        from _lib.product_service_library import get_item
        from _lib.feedback_loop import load_learned_signals
        body = request.get_json(silent=True) or {}
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"ok": False, "error": "prompt is required"}), 400
        brand_id = (body.get("brand_id") or "").strip() or None

        # Build brand_recipe from existing /recipe endpoint when brand_id given
        brand_recipe = None
        if brand_id:
            try:
                rr = visual_library_recipe(brand_id)
                if rr.status_code == 200:
                    payload = rr.get_json() or {}
                    brand_recipe = payload.get("recipe") or None
            except Exception:
                _app_log.warning("could not load recipe for brand_id=%s", brand_id)

        # ── 4-layer compose context ─────────────────────────────────────
        # Pull reference DNAs (Layer 2)
        reference_dnas = []
        for rid in body.get("reference_ids") or []:
            r = load_reference_dna(rid, brand_id or "swing-shack") if brand_id else None
            if r:
                reference_dnas.append(r)

        # Pull product/service items (Layer 3)
        items = []
        for pid in body.get("product_ids") or []:
            it = get_item(brand_id or "swing-shack", pid) if brand_id else None
            if it:
                items.append(it)
        for sid in body.get("service_ids") or []:
            it = get_item(brand_id or "swing-shack", sid) if brand_id else None
            if it:
                items.append(it)

        # Load learned signals (Layer 1) unless caller opts out
        signals = None
        if body.get("include_learned_signals", True) is not False and brand_id:
            signals = load_learned_signals(brand_id)

        result = _gen(
            prompt=prompt,
            brand_id=brand_id,
            brand_recipe=brand_recipe,
            reference_dnas=reference_dnas,
            product_service_items=items,
            learned_signals=signals,
            size=body.get("size", "1024x1024"),
            n=int(body.get("n") or 1),
            model=body.get("model"),
            provider=body.get("provider"),
            save=bool(body.get("save", True)) and bool(brand_id),
            max_cost_usd=float(body.get("max_cost_usd") or 0.50),
        )

        import base64 as _b64
        # Derive a browser-fetchable URL from saved_path. The frontend uses this
        # for <img src=...>; saved_path alone is an absolute filesystem path
        # which the browser cannot resolve.
        preview_url = None
        if result.saved_path:
            from pathlib import Path as _P
            sp = _P(result.saved_path)
            preview_url = f"/brand-images/{brand_id}/{sp.name}" if brand_id else None
        return jsonify({
            "ok": True,
            "bytes_b64": _b64.b64encode(result.bytes).decode("ascii"),
            "mime": result.mime,
            "model": result.model,
            "provider": result.provider,
            "cost_estimate_usd": result.cost_estimate_usd,
            "prompt_used": result.prompt_used,
            "revised_prompt": result.revised_prompt,
            "saved_path": result.saved_path,
            "preview_url": preview_url,
            "saved_sidecar_path": result.saved_sidecar_path,
            "warning": result.warning,
            "usage": result.usage,
            "brand_recipe": result.brand_recipe,  # NEW (2026-08-12) for UI Recipe panel
            "layers": {
                "signals": signals is not None and bool(signals.get("ready")),
                "references": len(reference_dnas),
                "products_or_services": len(items),
                "recipe": brand_recipe is not None,
            },
        })
    except ImageGenBadRequest as e:
        return jsonify({"ok": False, "error": str(e), "code": "bad_request"}), 400
    except ImageGenAuthError as e:
        return jsonify({"ok": False, "error": str(e), "code": "auth"}), 503
    except ImageGenNetworkError as e:
        return jsonify({"ok": False, "error": str(e), "code": "network"}), 504
    except ImageGenUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "code": "upstream", "upstream": getattr(e, "upstream", {})}), 502
    except Exception as e:
        _app_log.exception("image_generate failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/edit', methods=['POST'])
def image_edit():
    """POST /api/image/edit — edit an existing image.

    Request JSON:
      instruction (required)  — natural-language edit ("change background to pink")
      source_url  (one of required)  — http(s) URL OR data: URL
      source_b64  (alternative)       — raw base64 bytes (when not data: URL)
      source_mime (default "image/png")
      brand_id    (optional — save path)
      extra_urls  (optional — list of additional image URLs for style reference)
      model       (default Nano Banana)
      provider    (default openrouter — OpenAI direct does not support edit)
      save        (default true; requires brand_id)
      max_cost_usd (default 0.50)

    Returns:
      {ok, bytes_b64, mime, model, provider, cost_estimate_usd,
       saved_path, warning, usage}
    """
    try:
        from _lib.image_gen_router import (
            edit_image as _edit, ImageGenBadRequest, ImageGenAuthError,
            ImageGenNetworkError, ImageGenUpstreamError,
        )
        import base64 as _b64
        import urllib.request as _ureq

        body = request.get_json(silent=True) or {}
        instruction = (body.get("instruction") or "").strip()
        if not instruction:
            return jsonify({"ok": False, "error": "instruction is required"}), 400

        # Resolve source bytes
        source_bytes: Optional[bytes] = None
        if body.get("source_b64"):
            try:
                source_bytes = _b64.b64decode(body["source_b64"])
            except Exception:
                return jsonify({"ok": False, "error": "source_b64 is not valid base64"}), 400
        elif body.get("source_url"):
            url = body["source_url"]
            try:
                if url.startswith("data:"):
                    head, _, b64 = url.partition(",")
                    source_bytes = _b64.b64decode(b64)
                else:
                    with _ureq.urlopen(url, timeout=30) as r:
                        source_bytes = r.read()
            except Exception as e:
                return jsonify({"ok": False, "error": f"could not fetch source_url: {e}"}), 400
        else:
            return jsonify({"ok": False, "error": "either source_b64 or source_url is required"}), 400

        if not source_bytes:
            return jsonify({"ok": False, "error": "source image is empty"}), 400

        # Optional extra reference images
        extra: list[bytes] = []
        for eu in (body.get("extra_urls") or []):
            try:
                if eu.startswith("data:"):
                    extra.append(_b64.b64decode(eu.partition(",")[2]))
                else:
                    with _ureq.urlopen(eu, timeout=30) as r:
                        extra.append(r.read())
            except Exception as e:
                _app_log.warning("could not fetch extra_url %s: %s", eu[:60], e)

        brand_id = (body.get("brand_id") or "").strip() or None

        result = _edit(
            source_bytes=source_bytes,
            instruction=instruction,
            brand_id=brand_id,
            extra_image_bytes=extra or None,
            model=body.get("model"),
            provider=body.get("provider"),
            save=bool(body.get("save", True)) and bool(brand_id),
            max_cost_usd=float(body.get("max_cost_usd") or 0.50),
        )

        return jsonify({
            "ok": True,
            "bytes_b64": _b64.b64encode(result.bytes).decode("ascii"),
            "mime": result.mime,
            "model": result.model,
            "provider": result.provider,
            "cost_estimate_usd": result.cost_estimate_usd,
            "instruction_used": result.instruction_used,
            "saved_path": result.saved_path,
            "saved_sidecar_path": result.saved_sidecar_path,
            "warning": result.warning,
            "usage": result.usage,
        })
    except ImageGenBadRequest as e:
        return jsonify({"ok": False, "error": str(e), "code": "bad_request"}), 400
    except ImageGenAuthError as e:
        return jsonify({"ok": False, "error": str(e), "code": "auth"}), 503
    except ImageGenNetworkError as e:
        return jsonify({"ok": False, "error": str(e), "code": "network"}), 504
    except ImageGenUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "code": "upstream", "upstream": getattr(e, "upstream", {})}), 502
    except Exception as e:
        _app_log.exception("image_edit failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/from-asset/<asset_id>', methods=['POST'])
def image_from_asset(asset_id):
    """POST /api/image/from-asset/<asset_id> — link image gen to ANY Campaign OS surface.

    asset_id can be one of:
      - a hook id from data/hook-bank.json
      - a caption id from data/library.json
      - a headline id from data/headlines.json
      - a CTA id from data/ctas.json
      - a billboard brief id from data/content-blueprints.json
      - a visual recipe filename from the active brand
      - a top IG post media id from data/instagram.json (regenerate from winner)
      - an SEO top-performing page (regenerate OG cover)

    The endpoint extracts the asset's text (hook text / caption / headline /
    CTA / visual brief), reads the brand's recipe, and runs generate_image
    with that context. Result is saved under the brand directory and a
    sidecar references the asset_id for cross-linking.
    """
    try:
        from _lib.image_gen_router import generate_image as _gen, ImageGenBadRequest, ImageGenAuthError, ImageGenNetworkError, ImageGenUpstreamError
        import base64 as _b64
        body = request.get_json(silent=True) or {}
        brand_id = (body.get("brand_id") or get_brand_id()).strip() or "swing-shack"

        # Pull the asset's text + intent by id across data/
        prompt, kind = _extract_asset_context(asset_id, brand_id)
        if not prompt:
            return jsonify({"ok": False, "error": f"asset_id {asset_id!r} not found in any data file"}), 404

        # Optional user refinement on top of the extracted prompt
        # Two ways callers can override the auto-extracted prompt:
        #   body["override_prompt"] — replace entirely
        #   body["prompt"]          — append with ". " separator (legacy)
        user_prompt = (body.get("prompt") or "").strip()
        override_prompt = (body.get("override_prompt") or "").strip()
        if override_prompt:
            full_prompt = override_prompt
        elif user_prompt:
            full_prompt = user_prompt + ". " + prompt
        else:
            full_prompt = prompt

        # Get the recipe
        brand_recipe = None
        try:
            rr = visual_library_recipe(brand_id)
            if rr.status_code == 200:
                brand_recipe = (rr.get_json() or {}).get("recipe") or None
        except Exception:
            _app_log.warning("could not load recipe for brand_id=%s", brand_id)

        # Auto-compose the full 4-layer prompt by default (unless caller
        # explicitly opts out). Layers: brand recipe → product/service from
        # asset context → reference DNA → learned WIN PROFILE.
        reference_dnas: list = []
        product_service_items: list = []
        learned_signals: dict = {}
        compose_layers = body.get("compose_layers", True)
        if compose_layers and not override_prompt:
            try:
                from _lib.reference_dna import load_reference_dna
                # Pull attached references for this asset (if any were linked
                # via Image Lab drag-and-drop)
                ref_meta = body.get("reference_ids") or []
                for rid in ref_meta[:3]:
                    try:
                        dna = load_reference_dna(rid, brand_id)
                        if dna:
                            reference_dnas.append(dna)
                    except Exception:
                        pass
                # Pull attached products/services
                pids = body.get("product_ids") or []
                sids = body.get("service_ids") or []
                if pids or sids:
                    try:
                        from _lib.product_service_library import load_library
                        lib = load_library(brand_id)
                        for it in (lib.get("products", []) + lib.get("services", [])):
                            if it.get("id") in (pids + sids):
                                product_service_items.append(it)
                    except Exception:
                        pass
                # Pull learned WIN PROFILE
                if body.get("include_learned_signals", True):
                    try:
                        from _lib.feedback_loop import compute_learned_signals
                        learned_signals = compute_learned_signals(brand_id)
                    except Exception:
                        pass
            except Exception as e:
                _app_log.warning("auto-compose layer load failed (non-fatal): %s", e)

        result = _gen(
            prompt=full_prompt,
            brand_id=brand_id,
            brand_recipe=brand_recipe,
            reference_dnas=reference_dnas or None,
            product_service_items=product_service_items or None,
            learned_signals=learned_signals or None,
            size=body.get("size", "1024x1024"),
            n=int(body.get("n") or 1),
            model=body.get("model"),
            provider=body.get("provider"),
            save=True,
            max_cost_usd=float(body.get("max_cost_usd") or 0.50),
        )

        # Augment sidecar with asset link so future agents can trace back
        if result.saved_sidecar_path:
            try:
                p = Path(result.saved_sidecar_path)
                meta = json.loads(p.read_text())
                meta["linked_asset_id"] = asset_id
                meta["linked_asset_kind"] = kind
                meta["linked_asset_prompt"] = prompt
                p.write_text(json.dumps(meta, indent=2))
            except Exception as e:
                _app_log.warning("could not back-link asset_id to sidecar: %s", e)

        # Derive a browser-fetchable URL from the saved_path (same trick as /api/image/generate).
        preview_url = None
        if result.saved_path:
            from pathlib import Path as _P
            preview_url = f"/brand-images/{brand_id}/{_P(result.saved_path).name}"
        return jsonify({
            "ok": True,
            "asset_id": asset_id,
            "asset_kind": kind,
            "extracted_prompt": prompt,
            "bytes_b64": _b64.b64encode(result.bytes).decode("ascii"),
            "mime": result.mime,
            "model": result.model,
            "provider": result.provider,
            "cost_estimate_usd": result.cost_estimate_usd,
            "prompt_used": result.prompt_used,
            "saved_path": result.saved_path,
            "preview_url": preview_url,
            "warning": result.warning,
        })
    except ImageGenBadRequest as e:
        return jsonify({"ok": False, "error": str(e), "code": "bad_request"}), 400
    except ImageGenAuthError as e:
        return jsonify({"ok": False, "error": str(e), "code": "auth"}), 503
    except ImageGenNetworkError as e:
        return jsonify({"ok": False, "error": str(e), "code": "network"}), 504
    except ImageGenUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "code": "upstream", "upstream": getattr(e, "upstream", {})}), 502
    except Exception as e:
        _app_log.exception("image_from_asset failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================================
# Visual Reference Library — point at an image, capture its DNA
# =============================================================================


@app.route('/api/image/references/upload', methods=['POST'])
def image_reference_upload():
    """POST /api/image/references/upload — accept a multipart file upload.

    Form fields:
      file:        the image file
      brand:       brand_id (default swing-shack)
      label:       optional human label
      tags:        comma-separated tags

    Returns the saved reference DNA record.
    """
    try:
        from pathlib import Path
        import tempfile
        from _lib.reference_dna import ingest_local_image, save_reference_dna, extract_reference_dna

        if 'file' not in request.files:
            return jsonify({"ok": False, "error": "missing file field"}), 400

        f = request.files['file']
        if not f.filename:
            return jsonify({"ok": False, "error": "empty filename"}), 400

        brand = request.form.get('brand') or get_brand_id() or 'swing-shack'
        label = request.form.get('label') or None
        tags_raw = request.form.get('tags', '')
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else None

        # Save to a temp file, then ingest
        ext = Path(f.filename).suffix.lower() or '.jpg'
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            f.save(tmp_path)

        try:
            ref = ingest_local_image(tmp_path, brand, label=label, tags=tags, copy=True)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        return jsonify({"ok": True, "reference": ref})
    except Exception as e:
        _app_log.exception("image_reference_upload failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/references/from-url', methods=['POST'])
def image_reference_from_url():
    """POST /api/image/references/from-url — download + ingest a reference image from URL.

    Body: {"url": "https://...", "brand": "swing-shack", "label": "...", "tags": [...]}
    """
    try:
        from _lib.reference_dna import ingest_url

        body = request.get_json(force=True, silent=True) or {}
        url = body.get('url', '').strip()
        if not url:
            return jsonify({"ok": False, "error": "missing url"}), 400

        brand = body.get('brand') or get_brand_id() or 'swing-shack'
        label = body.get('label') or None
        tags = body.get('tags') or None

        ref = ingest_url(url, brand, label=label, tags=tags)
        return jsonify({"ok": True, "reference": ref})
    except Exception as e:
        _app_log.exception("image_reference_from_url failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/references/from-library/<brand_id>/<path:filename>', methods=['POST'])
def image_reference_from_library(brand_id, filename):
    """POST /api/image/references/from-library/<brand>/<filename> — use an existing
    image from the brand directory as a reference.

    Body (optional): {"label": "...", "tags": [...]}
    """
    try:
        from pathlib import Path
        from _lib.reference_dna import (
            ingest_local_image, _references_dir
        )

        # Resolve to brand-directory image
        candidate = Path(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / 'images' / filename
        if not candidate.exists():
            # Try thumbnail or other extensions
            stem = Path(filename).stem
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                alt = candidate.with_suffix(ext) if candidate.suffix else candidate.parent / f"{stem}{ext}"
                if alt.exists():
                    candidate = alt
                    break
            else:
                return jsonify({"ok": False, "error": f"image not found: {filename}"}), 404

        body = request.get_json(force=True, silent=True) or {}
        label = body.get('label') or None
        tags = body.get('tags') or None

        ref = ingest_local_image(candidate, brand_id, label=label, tags=tags, copy=True)
        return jsonify({"ok": True, "reference": ref})
    except Exception as e:
        _app_log.exception("image_reference_from_library failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/references/<brand_id>', methods=['GET'])
def image_references_list(brand_id):
    """GET /api/image/references/<brand> — list all reference DNA records.

    Query params:
      product   — filter to refs with this product tag
      mood      — filter to refs with this mood keyword
      limit     — cap results (default 100)
    """
    try:
        from _lib.reference_dna import list_reference_dnas, select_references

        product = request.args.get('product', '').strip() or None
        mood = request.args.get('mood', '').strip() or None
        limit = min(int(request.args.get('limit', '100') or '100'), 500)

        if product or mood:
            refs = select_references(
                brand_id,
                product=product, mood=mood, limit=limit
            )
        else:
            refs = list_reference_dnas(brand_id)[:limit]

        return jsonify({
            "ok": True,
            "brand": brand_id,
            "count": len(refs),
            "references": refs,
        })
    except Exception as e:
        _app_log.exception("image_references_list failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/references/<brand_id>/<ref_id>', methods=['GET'])
def image_reference_get(brand_id, ref_id):
    """GET /api/image/references/<brand>/<ref_id> — get a single reference DNA."""
    try:
        from _lib.reference_dna import load_reference_dna
        ref = load_reference_dna(ref_id, brand_id)
        if not ref:
            return jsonify({"ok": False, "error": f"reference {ref_id} not found"}), 404
        return jsonify({"ok": True, "reference": ref})
    except Exception as e:
        _app_log.exception("image_reference_get failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/references/<brand_id>/<ref_id>', methods=['DELETE'])
def image_reference_delete(brand_id, ref_id):
    """DELETE /api/image/references/<brand>/<ref_id> — delete a reference."""
    try:
        from _lib.reference_dna import delete_reference_dna
        ok = delete_reference_dna(ref_id, brand_id)
        return jsonify({"ok": ok})
    except Exception as e:
        _app_log.exception("image_reference_delete failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/references/<brand_id>/<ref_id>/thumbnail', methods=['GET'])
def image_reference_thumbnail(brand_id, ref_id):
    """GET /api/image/references/<brand>/<ref_id>/thumbnail — serve the thumbnail JPG."""
    try:
        from pathlib import Path
        from _lib.reference_dna import _default_brand_root
        thumb_dir = _default_brand_root() / brand_id / "references" / "thumbnails"
        target = thumb_dir / f"{ref_id}.jpg"
        if not target.exists():
            return jsonify({"ok": False, "error": "thumbnail not found"}), 404
        return send_from_directory(str(target.parent), target.name)
    except Exception as e:
        _app_log.exception("image_reference_thumbnail failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/from-reference/<brand_id>/<ref_id>', methods=['POST'])
def image_from_reference(brand_id, ref_id):
    """POST /api/image/from-reference/<brand>/<ref_id> — generate a new image that
    mimics the look of the given reference.

    Body: {"prompt": "...", "size": "1024x1024", "model": "...",
           "extra_reference_ids": [...], "product_ids": [...], "service_ids": [...]}
    """
    try:
        from _lib.reference_dna import load_reference_dna
        from _lib.product_service_library import get_item
        from _lib.feedback_loop import load_learned_signals
        from _lib.image_gen_router import generate_image

        ref = load_reference_dna(ref_id, brand_id)
        if not ref:
            return jsonify({"ok": False, "error": f"reference {ref_id} not found"}), 404

        body = request.get_json(force=True, silent=True) or {}
        prompt = (body.get('prompt') or '').strip()
        if not prompt:
            prompt = ref.get('label', 'reference-inspired image')

        size = body.get('size', '1024x1024')
        model = body.get('model') or None

        # Collect reference DNAs
        references = [ref]
        for extra_id in body.get('extra_reference_ids') or []:
            r = load_reference_dna(extra_id, brand_id)
            if r:
                references.append(r)

        # Collect product/service items
        items = []
        for pid in body.get('product_ids') or []:
            it = get_item(brand_id, pid)
            if it:
                items.append(it)
        for sid in body.get('service_ids') or []:
            it = get_item(brand_id, sid)
            if it:
                items.append(it)

        # Load learned signals
        signals = load_learned_signals(brand_id)

        result = generate_image(
            prompt=prompt,
            brand_id=brand_id,
            reference_dnas=references,
            product_service_items=items,
            learned_signals=signals,
            size=size,
            model=model,
            save=True,
        )

        return jsonify({
            "ok": True,
            "model": result.model,
            "provider": result.provider,
            "cost_estimate_usd": result.cost_estimate_usd,
            "prompt_used": result.prompt_used,
            "saved_path": result.saved_path,
            "warning": result.warning,
        })
    except ImageGenBadRequest as e:
        return jsonify({"ok": False, "error": str(e), "code": "bad_request"}), 400
    except ImageGenAuthError as e:
        return jsonify({"ok": False, "error": str(e), "code": "auth"}), 503
    except ImageGenNetworkError as e:
        return jsonify({"ok": False, "error": str(e), "code": "network"}), 504
    except ImageGenUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "code": "upstream", "upstream": getattr(e, "upstream", {})}), 502
    except Exception as e:
        _app_log.exception("image_from_reference failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================================
# Product & Service Library — the "what do we sell" database
# =============================================================================


@app.route('/api/library/<brand_id>/items', methods=['GET'])
def library_items_list(brand_id):
    """GET /api/library/<brand>/items — list all products, services, offerings.

    Query params:
      kind: product | service | offering (default: all)
      seed: if 'true', seed defaults first (idempotent)
    """
    try:
        from _lib.product_service_library import (
            load_library, seed_defaults, list_items
        )

        if request.args.get('seed', '').lower() in ('1', 'true', 'yes'):
            seed_defaults(brand_id)

        kind = request.args.get('kind', '').strip() or None
        items = list_items(brand_id, kind=kind)
        lib = load_library(brand_id)

        return jsonify({
            "ok": True,
            "brand": brand_id,
            "kind_filter": kind,
            "count": len(items),
            "items": items,
            "totals": {
                "products": len(lib.get("products", [])),
                "services": len(lib.get("services", [])),
                "offerings": len(lib.get("offerings", [])),
            },
        })
    except Exception as e:
        _app_log.exception("library_items_list failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/library/<brand_id>/items/<item_id>', methods=['GET'])
def library_item_get(brand_id, item_id):
    """GET /api/library/<brand>/items/<id> — get a single item."""
    try:
        from _lib.product_service_library import get_item
        item = get_item(brand_id, item_id)
        if not item:
            return jsonify({"ok": False, "error": f"item {item_id} not found"}), 404
        return jsonify({"ok": True, "item": item})
    except Exception as e:
        _app_log.exception("library_item_get failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/library/<brand_id>/items', methods=['POST'])
def library_item_create(brand_id):
    """POST /api/library/<brand>/items — create a new product/service/offering."""
    try:
        from _lib.product_service_library import add_item

        body = request.get_json(force=True, silent=True) or {}
        kind = body.get('kind', '').strip()
        name = body.get('name', '').strip()
        if not kind or not name:
            return jsonify({"ok": False, "error": "kind and name are required"}), 400

        item = add_item(brand_id, **body)
        return jsonify({"ok": True, "item": item})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        _app_log.exception("library_item_create failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/library/<brand_id>/items/<item_id>', methods=['PUT'])
def library_item_update(brand_id, item_id):
    """PUT /api/library/<brand>/items/<id> — update fields on an item."""
    try:
        from _lib.product_service_library import update_item

        body = request.get_json(force=True, silent=True) or {}
        updated = update_item(brand_id, item_id, **body)
        if not updated:
            return jsonify({"ok": False, "error": f"item {item_id} not found"}), 404
        return jsonify({"ok": True, "item": updated})
    except Exception as e:
        _app_log.exception("library_item_update failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/library/<brand_id>/items/<item_id>', methods=['DELETE'])
def library_item_delete(brand_id, item_id):
    """DELETE /api/library/<brand>/items/<id> — remove an item."""
    try:
        from _lib.product_service_library import delete_item
        ok = delete_item(brand_id, item_id)
        return jsonify({"ok": ok})
    except Exception as e:
        _app_log.exception("library_item_delete failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/library/<brand_id>/items/<item_id>/attach-reference', methods=['POST'])
def library_item_attach(brand_id, item_id):
    """POST /api/library/<brand>/items/<id>/attach-reference — attach a reference DNA."""
    try:
        from _lib.product_service_library import attach_reference

        body = request.get_json(force=True, silent=True) or {}
        ref_id = body.get('ref_id', '').strip()
        as_hero = bool(body.get('as_hero', False))
        if not ref_id:
            return jsonify({"ok": False, "error": "ref_id required"}), 400

        item = attach_reference(brand_id, item_id, ref_id, as_hero=as_hero)
        if not item:
            return jsonify({"ok": False, "error": "attach failed (ref or item missing)"}), 404
        return jsonify({"ok": True, "item": item})
    except Exception as e:
        _app_log.exception("library_item_attach failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/library/<brand_id>/items/<item_id>/detach-reference', methods=['POST'])
def library_item_detach(brand_id, item_id):
    """POST /api/library/<brand>/items/<id>/detach-reference — detach a reference DNA."""
    try:
        from _lib.product_service_library import detach_reference

        body = request.get_json(force=True, silent=True) or {}
        ref_id = body.get('ref_id', '').strip()
        if not ref_id:
            return jsonify({"ok": False, "error": "ref_id required"}), 400

        item = detach_reference(brand_id, item_id, ref_id)
        if not item:
            return jsonify({"ok": False, "error": "detach failed"}), 404
        return jsonify({"ok": True, "item": item})
    except Exception as e:
        _app_log.exception("library_item_detach failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/from-product/<brand_id>/<item_id>', methods=['POST'])
def image_from_product(brand_id, item_id):
    """POST /api/image/from-product/<brand>/<item_id> — generate a promotional image
    for a specific product/service/offering.

    Body: {"prompt": "...", "size": "1024x1024", "extra_reference_ids": [...],
           "extra_product_ids": [...], "extra_service_ids": [...]}
    """
    try:
        from _lib.product_service_library import get_item, attach_reference
        from _lib.reference_dna import load_reference_dna
        from _lib.feedback_loop import load_learned_signals
        from _lib.image_gen_router import generate_image

        item = get_item(brand_id, item_id)
        if not item:
            return jsonify({"ok": False, "error": f"item {item_id} not found"}), 404

        body = request.get_json(force=True, silent=True) or {}
        prompt = (body.get('prompt') or '').strip()
        if not prompt:
            # Auto-build a prompt from the item
            prompt = f"{item.get('name', '')} — {item.get('headline', '')}"

        size = body.get('size', '1024x1024')
        model = body.get('model') or None

        # Pull the item's attached references (hero first)
        references = []
        hero_id = item.get('hero_ref_id')
        ref_ids = list(item.get('reference_ref_ids') or [])
        if hero_id and hero_id in ref_ids:
            ref_ids.remove(hero_id)
            ref_ids.insert(0, hero_id)
        for rid in ref_ids:
            r = load_reference_dna(rid, brand_id)
            if r:
                references.append(r)

        # Add any extra explicit references
        for extra_id in body.get('extra_reference_ids') or []:
            r = load_reference_dna(extra_id, brand_id)
            if r and r not in references:
                references.append(r)

        # Items list — start with this item, then any extras
        items = [item]
        for pid in body.get('extra_product_ids') or []:
            it = get_item(brand_id, pid)
            if it and it not in items:
                items.append(it)
        for sid in body.get('extra_service_ids') or []:
            it = get_item(brand_id, sid)
            if it and it not in items:
                items.append(it)

        # Load learned signals
        signals = load_learned_signals(brand_id)

        result = generate_image(
            prompt=prompt,
            brand_id=brand_id,
            reference_dnas=references,
            product_service_items=items,
            learned_signals=signals,
            size=size,
            model=model,
            save=True,
        )

        return jsonify({
            "ok": True,
            "model": result.model,
            "provider": result.provider,
            "cost_estimate_usd": result.cost_estimate_usd,
            "prompt_used": result.prompt_used,
            "saved_path": result.saved_path,
            "warning": result.warning,
            "item_id": item_id,
            "references_used": [r["ref_id"] for r in references],
        })
    except ImageGenBadRequest as e:
        return jsonify({"ok": False, "error": str(e), "code": "bad_request"}), 400
    except ImageGenAuthError as e:
        return jsonify({"ok": False, "error": str(e), "code": "auth"}), 503
    except ImageGenNetworkError as e:
        return jsonify({"ok": False, "error": str(e), "code": "network"}), 504
    except ImageGenUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "code": "upstream", "upstream": getattr(e, "upstream", {})}), 502
    except Exception as e:
        _app_log.exception("image_from_product failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================================
# Feedback Loop — per-image performance capture + learned signals
# =============================================================================


@app.route('/api/image/feedback/record', methods=['POST'])
def feedback_record():
    """POST /api/image/feedback/record — capture a performance signal for one image.

    Body: {
        "image_id": "ref-xxx" or "generated-xxx",
        "kind": "reference" or "generated",
        "source": "ig" | "ga4" | "gmb" | "manual" | "import",
        "captured_signal": {"likes": ..., "saves": ..., ...},
        "dna_snapshot": {...} or omit,
        "platform_post_id": "..." optional,
        "notes": "..."
    }
    """
    try:
        from _lib.feedback_loop import add_record

        body = request.get_json(force=True, silent=True) or {}
        brand = body.get('brand') or get_brand_id() or 'swing-shack'

        required = ['image_id', 'kind', 'source', 'captured_signal']
        missing = [k for k in required if not body.get(k)]
        if missing:
            return jsonify({"ok": False, "error": f"missing fields: {missing}"}), 400

        record = add_record(brand, **body)
        return jsonify({"ok": True, "record": record})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        _app_log.exception("feedback_record failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/feedback/import-ig', methods=['POST'])
def feedback_import_ig():
    """POST /api/image/feedback/import-ig — bulk import IG metrics for many posts.

    Body: {
        "brand": "swing-shack",
        "records": [
            {
                "image_id": "ref-xxx",
                "post_id": "ig_post_123",
                "impressions": ..., "likes": ..., ...
            },
            ...
        ]
    }

    Computes scores and persists records + DNA snapshot (looked up from
    the library if image_id is a ref_id).
    """
    try:
        from _lib.feedback_loop import add_record
        from _lib.reference_dna import load_reference_dna

        body = request.get_json(force=True, silent=True) or {}
        brand = body.get('brand') or get_brand_id() or 'swing-shack'
        records_in = body.get('records') or []
        if not records_in:
            return jsonify({"ok": False, "error": "no records provided"}), 400

        imported = 0
        errors: list[str] = []
        for r in records_in:
            try:
                image_id = r.get('image_id', '').strip()
                post_id = r.get('post_id', '').strip() or None
                if not image_id:
                    continue

                signal = {k: v for k, v in r.items()
                          if k in ('impressions', 'likes', 'comments', 'saves', 'reach',
                                   'link_clicks', 'ga_sessions', 'ga_conversions',
                                   'gmb_calls', 'bookings')}

                # Look up DNA from library if image_id looks like a ref
                dna_snapshot = r.get('dna_snapshot')
                if not dna_snapshot:
                    ref = load_reference_dna(image_id, brand)
                    if ref:
                        from _lib.feedback_loop import snapshot_from_reference
                        dna_snapshot = snapshot_from_reference(ref)

                add_record(
                    brand,
                    image_id=image_id,
                    kind='reference',
                    source='ig',
                    captured_signal=signal,
                    dna_snapshot=dna_snapshot or {},
                    platform_post_id=post_id,
                    notes=r.get('notes', ''),
                )
                imported += 1
            except Exception as e:
                errors.append(str(e))

        return jsonify({"ok": True, "imported": imported, "errors": errors[:5]})
    except Exception as e:
        _app_log.exception("feedback_import_ig failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/feedback/<brand_id>', methods=['GET'])
def feedback_list(brand_id):
    """GET /api/image/feedback/<brand> — list performance records."""
    try:
        from _lib.feedback_loop import list_records, summary

        min_score = request.args.get('min_score')
        kind = request.args.get('kind', '').strip() or None
        limit = min(int(request.args.get('limit', '50') or '50'), 500)

        recs = list_records(
            brand_id,
            min_score=float(min_score) if min_score else None,
            kind=kind,
            limit=limit,
        )
        return jsonify({
            "ok": True,
            "brand": brand_id,
            "count": len(recs),
            "records": recs,
            "summary": summary(brand_id),
        })
    except Exception as e:
        _app_log.exception("feedback_list failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/feedback/<brand_id>/learned', methods=['GET'])
def feedback_learned(brand_id):
    """GET /api/image/feedback/<brand>/learned — computed WIN PROFILE + preferences."""
    try:
        from _lib.feedback_loop import load_learned_signals, compute_learned_signals

        # If the request includes ?recompute=1, force recompute
        if request.args.get('recompute') == '1':
            from _lib.feedback_loop import save_learned_signals
            signals = compute_learned_signals(brand_id)
            save_learned_signals(signals, brand_id)
        else:
            signals = load_learned_signals(brand_id)

        return jsonify({"ok": True, "signals": signals})
    except Exception as e:
        _app_log.exception("feedback_learned failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/image/feedback/<brand_id>/threshold', methods=['PUT'])
def feedback_threshold(brand_id):
    """PUT /api/image/feedback/<brand>/threshold — adjust the win threshold.

    Body: {"win_threshold": 0.7}
    """
    try:
        from _lib.feedback_loop import load_performance, save_performance, compute_learned_signals, save_learned_signals

        body = request.get_json(force=True, silent=True) or {}
        threshold = float(body.get('win_threshold', 0.65))
        if not (0.0 < threshold <= 1.0):
            return jsonify({"ok": False, "error": "threshold must be in (0, 1]"}), 400

        perf = load_performance(brand_id)
        perf['win_threshold'] = threshold
        save_performance(perf, brand_id)

        # Recompute signals
        signals = compute_learned_signals(brand_id)
        save_learned_signals(signals, brand_id)

        return jsonify({"ok": True, "win_threshold": threshold, "signals": signals})
    except Exception as e:
        _app_log.exception("feedback_threshold failed")
        return jsonify({"ok": False, "error": str(e)}), 500


def _extract_asset_context(asset_id: str, brand_id: str) -> tuple[Optional[str], Optional[str]]:
    """Walk data/ for an asset matching asset_id. Return (prompt_text, kind).

    Lookup order (most likely to match first):
      1. data/hook-bank.json       — {hooks: [...]} by id or hook text
      2. data/captions.json        — captions by id
      3. data/headlines.json       — headlines by id
      4. data/ctas.json            — CTAs by id
      5. data/content-blueprints.json — billboard briefs by id
      6. data/library.json         — assets by id
      7. data/visual-briefs.json   — visual briefs by id
      8. data/instagram.json       — IG posts by media_id (regenerate from winner)
      9. data/seo-rankings.json    — top-performing SEO pages (OG cover regen)
     10. campaign-data.json        — review-inbox assets (Takomo hero, etc.) — uses
      asset's `visualBrief` then `description` then `caption` as the prompt.
    """
    base = Path(BUNDLED_DATA_DIR)
    lookup_paths = [
        ("hook",       base / "hook-bank.json",            "hooks",       "text"),
        ("caption",    base / "captions.json",             "captions",    "text"),
        ("caption",    base / "library.json",              "items",       "caption"),
        ("headline",   base / "headlines.json",            "headlines",   "text"),
        ("cta",        base / "ctas.json",                 "ctas",        "text"),
        ("billboard",  base / "content-blueprints.json",   "blueprints",  "brief"),
        ("visual",     base / "visual-briefs.json",        "briefs",      "prompt"),
        ("seo",        base / "seo-rankings.json",         "keywords",    "query"),
    ]
    for kind, p, list_key, text_key in lookup_paths:
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        # Resolve items: dict gets the list_key, list IS items, anything else empty
        if isinstance(data, dict):
            items = data.get(list_key) or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        for it in items:
            if not isinstance(it, dict):
                continue
            # Match by id field (flexible: id, _id, asset_id, blueprint_id, media_id)
            for id_field in ("id", "_id", "asset_id", "blueprint_id", "media_id", "post_id"):
                if it.get(id_field) == asset_id or str(it.get(id_field)) == asset_id:
                    text = (it.get(text_key) or it.get("text") or it.get("prompt") or it.get("query") or
                            it.get("caption") or it.get("hook") or it.get("title") or it.get("name") or "")
                    if text:
                        return str(text).strip(), kind
        # Try matching the asset_id as a substring of the text (for hooks like "hk-..." or filenames)
        for it in (items if isinstance(items, list) else []):
            if not isinstance(it, dict):
                continue
            text = (it.get(text_key) or it.get("text") or it.get("prompt") or it.get("query") or
                    it.get("caption") or it.get("hook") or it.get("title") or it.get("name") or "")
            if text and asset_id in str(text):
                return str(text).strip(), kind

    # ── 10. campaign-data.json — review-inbox assets ───────────────────
    # Walk every campaign's `assets` map. Match by assetId / id / name.
    # This is what makes the Review-modal "🎨 Generate visual" button work
    # for assets like `takomo-101t-hero-c` whose data lives in the portfolio
    # file rather than the standalone data/ hook/caption files.
    #
    # The file may live at any of:
    #   - REPO_ROOT/data/campaign-data.json            (older bundled layout)
    #   - REPO_ROOT/campaign-os/campaign-data.json     (current local layout)
    #   - $DATA_DIR/campaign-data.json                  (Railway runtime)
    portfolio_candidates = []
    runtime_data_dir = os.environ.get('DATA_DIR') or '/data'
    portfolio_candidates.append(Path(runtime_data_dir) / 'campaign-data.json')
    if base.name == "data":
        portfolio_candidates.append(base.parent / "campaign-data.json")
        portfolio_candidates.append(base.parent / "campaign-os" / "campaign-data.json")
    else:
        portfolio_candidates.append(base / "campaign-data.json")
        portfolio_candidates.append(base / ".." / "campaign-os" / "campaign-data.json")
    for campaign_file in portfolio_candidates:
        if not campaign_file.exists():
            continue
        try:
            portfolio = json.loads(campaign_file.read_text())
            for cname, c in (portfolio.get("campaigns") or {}).items():
                assets_map = (c or {}).get("assets") or {}
                if not isinstance(assets_map, dict):
                    continue
                # Direct ID match
                if asset_id in assets_map and isinstance(assets_map[asset_id], dict):
                    a = assets_map[asset_id]
                    text = (a.get("visualBrief") or a.get("description")
                            or a.get("caption") or a.get("name") or "")
                    if text:
                        return str(text).strip(), "visual"
                # Substring match against name (covers cases where the asset
                # ID has a v2 / -copy suffix and the name is the canonical key)
                for aid, a in assets_map.items():
                    if not isinstance(a, dict):
                        continue
                    if aid == asset_id or str(a.get("name", "")).replace(" ", "-").lower() == asset_id.lower():
                        text = (a.get("visualBrief") or a.get("description")
                                or a.get("caption") or a.get("name") or "")
                        if text:
                            return str(text).strip(), "visual"
        except Exception:
            pass

    # No match
    return None, None


@app.route('/api/visual-library/<brand_id>/image/<path:filename>', methods=['GET'])
def visual_library_image_detail(brand_id, filename):
    """GET /api/visual-library/<brand>/image/ — full DNA for one image.

    Returns every layer of the visual DNA file as a flat structure with
    human-readable labels. Used by the per-image modal in the Visual Library.
    """
    try:
        from pathlib import Path as _P
        # Resolve actual DNA file (handles .jpg/.jpeg/.png)
        for ext in (".jpg", ".jpeg", ".png"):
            if filename.lower().endswith(ext):
                stem = filename[: -len(ext)]
                dna_filename = stem + ".visual-dna.json"
                break
        else:
            dna_filename = filename + ".visual-dna.json"
        index_path = _P(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / "visual-dna-index.json"
        idx = json.loads(index_path.read_text())
        meta = idx.get("by_filename", {}).get(filename)
        if not meta:
            return jsonify({"error": f"image {filename} not in index"}), 404
        dna_p = _P(meta.get("dna_path", ""))
        if not dna_p.exists():
            return jsonify({"error": "dna file missing on disk"}), 404
        dna = json.loads(dna_p.read_text())
        return jsonify({
            "brand": brand_id,
            "filename": filename,
            "image_url": f"/brand-images/{brand_id}/{filename}",
            "score": meta.get("score"),
            "dna": dna,
        })
    except Exception as e:
        _app_log.exception("visual_library_image_detail failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── GENERATED IMAGE OUTPUTS ───────────────────────────────────────────────
# Past renders from /api/image/{generate,from-asset,from-product,...} land at
# data/brand-directory/<brand>/images/gen-<brand>-<ts>-<n>.{png,jpg}
# This endpoint lists them so the UI can show a 'recent renders' gallery
# (before this they only existed as filesystem artifacts — invisible to the OS).

@app.route('/api/image/outputs/<brand_id>', methods=['GET'])
def image_outputs_list(brand_id):
    """GET /api/image/outputs/<brand> — list past generated images for the brand.

    Query params:
      limit     (optional, default 50) — cap the number of entries
      offset    (optional, default 0)   — pagination

    Returns: { data: [{ filename, url, prompt, ts, model, quality, size }, ...],
               count, brand_id }
    """
    try:
        from pathlib import Path as _P
        brand_id = (brand_id or "").strip() or "swing-shack"
        try:
            limit = max(1, min(200, int(request.args.get("limit") or 50)))
            offset = max(0, int(request.args.get("offset") or 0))
        except (TypeError, ValueError):
            limit, offset = 50, 0

        images_dir = _P(BUNDLED_DATA_DIR) / "brand-directory" / brand_id / "images"
        if not images_dir.exists():
            return jsonify({"data": [], "count": 0, "brand_id": brand_id}), 200

        # Match the gen-* filename pattern (set by image_gen_router.py when save=True)
        out = []
        for f in images_dir.glob(f"gen-{brand_id}-*.png"):
            meta_path = f.with_suffix(".meta.json")
            entry = {
                "filename": f.name,
                "url": f"/brand-images/{brand_id}/{f.name}",
                "ts": int(f.stat().st_mtime),
                "ts_iso": _P(f).stat().st_mtime and __import__("datetime").datetime.utcfromtimestamp(f.stat().st_mtime).isoformat() + "Z",
                "size_bytes": f.stat().st_size,
            }
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    entry["prompt"] = meta.get("prompt") or ""
                    entry["enhanced_prompt"] = meta.get("enhanced_prompt") or ""
                    entry["model"] = meta.get("model") or ""
                    entry["quality"] = meta.get("quality") or ""
                    entry["size"] = meta.get("size") or ""
                    entry["ts_meta"] = meta.get("ts") or entry["ts"]
                except Exception:
                    pass
            out.append(entry)

        # Also match .jpg variants (gpt-image-1 can produce either)
        for f in images_dir.glob(f"gen-{brand_id}-*.jpg"):
            meta_path = f.with_suffix(".meta.json")
            entry = {
                "filename": f.name,
                "url": f"/brand-images/{brand_id}/{f.name}",
                "ts": int(f.stat().st_mtime),
                "ts_iso": __import__("datetime").datetime.utcfromtimestamp(f.stat().st_mtime).isoformat() + "Z",
                "size_bytes": f.stat().st_size,
            }
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    entry["prompt"] = meta.get("prompt") or ""
                    entry["model"] = meta.get("model") or ""
                    entry["quality"] = meta.get("quality") or ""
                except Exception:
                    pass
            out.append(entry)

        # Newest first
        out.sort(key=lambda e: -e.get("ts", 0))
        total = len(out)
        page = out[offset:offset + limit]
        return jsonify({"data": page, "count": total, "limit": limit, "offset": offset, "brand_id": brand_id}), 200
    except Exception as e:
        _app_log.exception("image_outputs_list failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── MEME LAB (full catalog for UI) ─────────────────────────────────────

@app.route('/api/intel/memes/catalog', methods=['GET'])
def meme_catalog():
    """GET /api/intel/memes/catalog — full meme knowledge base (75 entries).

    Returns every meme in data/meme_knowledge.json with the fields the
    Meme Lab UI needs: id, name, format, era, peak_year, mechanism,
    why_it_works, swingshack_fit_seeds, voice_fit, pillar_fit,
    format_hint, fatigue_risk, still_works.

    Query params:
      pillar      — filter to memes that fit a pillar (education|club-fitting|community|events)
      voice       — filter to memes that fit a voice (swing-shack|stick|bag-drop)
      era         — filter by era (classic|recent|current)
      still_works — only memes that still work (still_works=true)
      fatigue     — only low-fatigue memes (fatigue_risk=low)
    """
    try:
        kb = _load_meme_knowledge()
        memes = kb.get("memes") if isinstance(kb, dict) else kb
        if not isinstance(memes, list):
            memes = []

        pillar = request.args.get("pillar", "").strip()
        voice = request.args.get("voice", "").strip()
        era = request.args.get("era", "").strip()
        only_still_works = request.args.get("still_works", "").lower() in ("1", "true", "yes")
        only_low_fatigue = request.args.get("fatigue", "").lower() in ("low", "1", "true", "yes")

        filtered = []
        for m in memes:
            if not isinstance(m, dict):
                continue
            if pillar and pillar not in (m.get("pillar_fit") or []):
                continue
            if voice and voice not in (m.get("voice_fit") or []):
                continue
            if era and era != m.get("era"):
                continue
            if only_still_works and not m.get("still_works"):
                continue
            if only_low_fatigue and m.get("fatigue_risk") != "low":
                continue
            filtered.append(m)

        # Sort: still_works desc, fatigue_risk low first, peak_year desc
        fatigue_order = {"low": 0, "medium": 1, "high": 2, "": 3}
        filtered.sort(key=lambda x: (
            not x.get("still_works", False),
            fatigue_order.get(x.get("fatigue_risk", ""), 9),
            -int(x.get("peak_year", 0) or 0),
        ))

        return jsonify({
            "ok": True,
            "total": len(filtered),
            "total_in_catalog": len(memes),
            "voice_bible": kb.get("voice_bible", ""),
            "filters": {"pillar": pillar, "voice": voice, "era": era,
                        "still_works": only_still_works, "fatigue": only_low_fatigue},
            "memes": filtered,
        })
    except Exception as e:
        _app_log.exception("meme_catalog failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/intel/meme/<meme_id>/preview', methods=['GET'])
def meme_preview(meme_id):
    """GET /api/intel/meme/<id>/preview — adaptation scaffold for one meme.

    Returns the meme entry plus an adaptation prompt pre-built for the
    Ideogram image generator. UI can hand this off directly.
    """
    try:
        kb = _load_meme_knowledge()
        memes = kb.get("memes") if isinstance(kb, dict) else kb
        meme = next((m for m in memes if isinstance(m, dict) and m.get("id") == meme_id), None)
        if not meme:
            return jsonify({"error": f"meme {meme_id} not found"}), 404

        seeds = meme.get("swingshack_fit_seeds") or []
        seeds = [s for s in seeds if s]
        seed = seeds[0] if seeds else "Swing Shack"
        # Build the Ideogram prompt scaffold
        adaptation_prompt = (
            f"[MEME FORMAT: {meme.get('format', 'meme')}]\n"
            f"[VISUAL: {meme.get('format_hint', '')}]\n"
            f"[ADAPTATION: Replace original caption with Swing Shack context: \"{seed}\"]\n"
            f"[VOICE: swing-shack — direct, no fluff, lowercase. Pineapple Test: would a non-golfer get the joke?]\n"
            f"[STYLE: dark palette, high contrast, brand-aligned, single-accent colour]"
        )

        return jsonify({
            "ok": True,
            "meme": meme,
            "adaptation_prompt": adaptation_prompt,
            "first_seed": seed,
            "all_seeds": seeds,
        })
    except Exception as e:
        _app_log.exception("meme_preview failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── REAL DATA + VISUAL DNA JOIN ────────────────────────────────────────
# Joins page-level Meta engagement with the brand's image visual DNA index.
# Tells you: which palettes/compositions are most-used, which score highest,
# and (once App Review approves pages_read_user_content) which individual
# posts correlate with which image DNA features.

@app.route('/api/intel/visual-performance', methods=['GET'])
def visual_performance_join():
    """GET /api/intel/visual-performance — cross-reference Meta engagement with DNA.

    Returns the current best-available join between real post data and
    visual DNA features. With current scopes we can show:
      - Page-level engagement trend (page_post_engagements, page_views_total)
      - Image roster with DNA scores and palette distribution
      - Top 10 images by brand-alignment score (the ones to clone)
      - "Awaiting per-post engagement" honest placeholder for the join

    Once App Review approves `pages_read_user_content`, this endpoint
    auto-enriches each image with its closest-matching post's engagement.
    """
    try:
        from pathlib import Path as _P
        from collections import Counter
        brand = request.args.get("brand", "swing-shack")
        # Page-level Meta data
        from _lib import meta_api as _meta
        page_signal = {"available": False, "reason": "no token"}
        try:
            if _meta._page_credentials_present():
                eng = _meta._graph_get(
                    f"/{_meta.os.environ.get('META_PAGE_ID')}/insights",
                    {"metric": "page_post_engagements,page_views_total", "period": "day"},
                    use_page_token=True,
                )
                page_signal = {
                    "available": True,
                    "page_id": _meta.os.environ.get("META_PAGE_ID"),
                    "engagements_30d": sum(
                        v.get("value", 0)
                        for d in eng.get("data", [])
                        if d.get("name") == "page_post_engagements"
                        for v in d.get("values", [])
                    ),
                    "views_30d": sum(
                        v.get("value", 0)
                        for d in eng.get("data", [])
                        if d.get("name") == "page_views_total"
                        for v in d.get("values", [])
                    ),
                    "raw": eng,
                }
        except Exception as me:
            page_signal = {"available": False, "reason": str(me)[:200]}

        # Visual DNA top scorers
        idx = {"by_filename": {}, "image_count": 0}  # default if index missing
        index_path = _P(BUNDLED_DATA_DIR) / 'brand-directory' / brand / "visual-dna-index.json"
        dna_top = []
        if index_path.exists():
            idx = json.loads(index_path.read_text())
            by_filename = idx.get("by_filename", {})
            scored = []
            for fn, meta in by_filename.items():
                sc = float(meta.get("score", 0) or 0)
                scored.append({
                    "filename": fn,
                    "score": round(sc, 3),
                    "url": f"/brand-images/{brand}/{fn}",
                    "luminance": meta.get("luminance"),
                    "dominant": meta.get("dominant"),
                    "products": meta.get("by_product", []),
                })
            scored.sort(key=lambda x: x["score"], reverse=True)
            dna_top = scored[:10]

        # Per-post engagement placeholders — list recent posts that LOOK like
        # they would join to images once App Review approves. We list posts
        # the page token can already see (post slugs without engagement yet).
        per_post_status = {
            "available": False,
            "reason": "Awaiting Meta App Review for `pages_read_user_content` scope",
            "eta_after_approval": "Automatic · this endpoint will populate per-post metrics.",
            "submission_evidence_url": "https://swing-shack-dashboard-production.up.railway.app/meta-app-review/",
        }

        return jsonify({
            "ok": True,
            "brand": brand,
            "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "page_signal": page_signal,
            "visual_dna": {
                "total_images": idx.get("image_count") if index_path.exists() else 0,
                "top_scorers": dna_top,
            },
            "per_post_join": per_post_status,
            "join_strategy": (
                "When per-post data arrives, this endpoint will rank images by "
                "the engagement their closest-matching FB post received. Today "
                "the join is structural (palettes/compositions used) not "
                "performance-weighted."
            ),
        })
    except Exception as e:
        _app_log.exception("visual_performance_join failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── META / INSTAGRAM / FACEBOOK READS ───────────────────────────────────
# These endpoints read the connected Instagram Business account and Facebook
# Page via the Graph API. They DO NOT publish, reply to comments, or send
# DMs. Truth-before-cleverness: every response surfaces a real upstream
# payload (or an explicit, structured 401/403/5xx with the upstream message).
# When credentials are missing, the routes return 503 with a clear "what to
# set" payload so the SPA can render an honest empty-state.

@app.route('/api/meta/status', methods=['GET'])
def meta_status():
    """GET /api/meta/status — are Meta credentials configured + reachable?

    Returns { ok, configured, ig_account_id, page_id, app_id_present, reason }
    — never leaks the access_token value.
    """
    try:
        from _lib import meta_api as _meta
        configured = _meta.meta_credentials_present()
        out = {
            "ok": True,
            "configured": configured,
            "ig_account_id": os.environ.get("META_INSTAGRAM_BUSINESS_ACCOUNT_ID") or None,
            "page_id": os.environ.get("META_PAGE_ID") or None,
            "app_id_present": bool(os.environ.get("META_APP_ID")),
            "token_resolved": bool(_meta._read_meta_access_token()),
            "reason": None if configured else "set META_APP_ID + META_ACCESS_TOKEN[_FILE] + META_INSTAGRAM_BUSINESS_ACCOUNT_ID",
        }
        return jsonify(out), 200
    except Exception as e:
        _app_log.exception("meta_status failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/intel/ubersuggest/status', methods=['GET'])
def ubersuggest_status():
    """GET /api/intel/ubersuggest/status — are Ubersuggest MCP creds configured?

    Returns { ok, configured, token_file, refreshed_at, expires_at, scope, hint }
    — never leaks the access_token value. Best-effort account tier probe with
    short timeout; tier info is omitted on transient network failures.
    """
    try:
        from _lib import ubersuggest_mcp as _us
        out = _us.status_report()
        out.setdefault("ok", True)
        # If configured but token is expired, surface a hint for the SPA.
        if out.get("configured") and (out.get("expires_in_seconds") or 0) <= 0:
            out["hint"] = (
                "access_token expired — run scripts/ubersuggest_refresh_token.py "
                "or scripts/ubersuggest_oauth.py to re-authorize"
            )
        elif not out.get("configured"):
            out["hint"] = (
                "no token saved — run scripts/ubersuggest_oauth.py to do the "
                "OAuth dance. ~30 seconds, requires clicking 'Authorize' once "
                "in your browser at the Ubersuggest consent screen."
            )
        return jsonify(out), 200
    except Exception as e:
        _app_log.exception("ubersuggest_status failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/intel/ubersuggest/keyword_overview', methods=['GET'])
def ubersuggest_keyword_overview():
    """GET /api/intel/ubersuggest/keyword_overview — single-keyword snapshot.

    Query params: keyword (required), loc_id (default 2840 = US, 2076 = SA),
    lang (default 'en'). Uses the cached access token + auto-refresh; returns
    503 if the OAuth dance hasn't been run yet.
    """
    try:
        from _lib import ubersuggest_mcp as _us
        keyword = (request.args.get("keyword") or "").strip()
        if not keyword:
            return jsonify({"ok": False, "error": "keyword query param required"}), 400
        try:
            loc_id = int(request.args.get("loc_id", "2840"))
        except ValueError:
            loc_id = 2840
        lang = (request.args.get("lang") or "en").strip()
        result = _us.keyword_overview(keyword, loc_id=loc_id, lang=lang)
        return jsonify({"ok": True, "keyword": keyword, **result}), 200
    except _us.UbersuggestAuthError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "upstream": e.upstream,
            "hint": "run scripts/ubersuggest_oauth.py to authorize Ubersuggest",
        }), 503
    except _us.UbersuggestUpstreamError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "upstream": e.upstream,
            "code": e.code,
        }), 502
    except _us.UbersuggestNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("ubersuggest_keyword_overview failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/intel/ubersuggest/domain_overview', methods=['GET'])
def ubersuggest_domain_overview():
    """GET /api/intel/ubersuggest/domain_overview?domain=swingshack.co.za — domain stats.

    Optional country (loc_id, default US/2840). Returns 503 if not authorized.
    """
    try:
        from _lib import ubersuggest_mcp as _us
        domain = (request.args.get("domain") or "").strip()
        if not domain:
            return jsonify({"ok": False, "error": "domain query param required"}), 400
        try:
            country = int(request.args.get("country", "2840"))
        except ValueError:
            country = 2840
        result = _us.domain_overview(domain, country=country)
        return jsonify({"ok": True, "domain": domain, **result}), 200
    except _us.UbersuggestAuthError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "upstream": e.upstream,
            "hint": "run scripts/ubersuggest_oauth.py to authorize Ubersuggest",
        }), 503
    except _us.UbersuggestUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _us.UbersuggestNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("ubersuggest_domain_overview failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/meta/posts', methods=['GET'])
def meta_list_posts():
    """GET /api/meta/posts — list recent Instagram media for the connected account.

    Query params:
      limit=<int>      — max posts to return (default 25, max 100)
      fields=<csv>     — override the default fields list

    Response shape:
      {
        data: [{ id, caption, media_type, permalink, timestamp, media_url, ... }],
        paging: { cursors, next },
        _meta: { ig_account_id, fetched, endpoint }
      }
    """
    try:
        from _lib import meta_api as _meta
        limit = int(request.args.get('limit', 25))
        fields_csv = request.args.get('fields')
        fields = [f.strip() for f in fields_csv.split(',')] if fields_csv else None
        out = _meta.list_recent_posts(limit=limit, fields=fields)
        out['ok'] = True
        return jsonify(out), 200
    except _meta.MetaAuthError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "hint": "ask Heidi to spin up /meta portal"}), 503
    except _meta.MetaUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _meta.MetaNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("meta_list_posts failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/meta/posts/<media_id>/comments', methods=['GET'])
def meta_post_comments(media_id):
    """GET /api/meta/posts/<media_id>/comments — read comment text + usernames.

    Path params:
      media_id — numeric IG media id (e.g. 17990000000000001)

    Query params:
      limit=<int> — max comments (default 50, max 100)

    Response: { data: [{ id, text, username, timestamp, like_count }], paging, _meta }
    """
    try:
        from _lib import meta_api as _meta
        limit = int(request.args.get('limit', 50))
        out = _meta.get_post_comments(media_id, limit=limit)
        out['ok'] = True
        return jsonify(out), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except _meta.MetaAuthError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "hint": "ask Heidi to spin up /meta portal"}), 503
    except _meta.MetaUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _meta.MetaNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("meta_post_comments failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/meta/posts/<media_id>/insights', methods=['GET'])
def meta_post_insights(media_id):
    """GET /api/meta/posts/<media_id>/insights — read engagement metrics for one post.

    Path params:
      media_id — numeric IG media id

    Response:
      {
        _flat: { impressions, reach, saved, likes, comments, shares, engagement_rate },
        data: [raw upstream per-metric blocks],
        _meta: { media_id, metrics_requested, fetched }
      }
    """
    try:
        from _lib import meta_api as _meta
        out = _meta.get_post_insights(media_id)
        out['ok'] = True
        return jsonify(out), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except _meta.MetaAuthError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "hint": "ask Heidi to spin up /meta portal"}), 503
    except _meta.MetaUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _meta.MetaNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("meta_post_insights failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/meta/posts/<media_id>/full', methods=['GET'])
def meta_post_full(media_id):
    """GET /api/meta/posts/<media_id>/full — one call, returns post + comments + insights.

    Convenience route for the SPA's "show me this post" panel. Parallel
    upstream calls (3) so the user sees everything in one round-trip.
    """
    try:
        from _lib import meta_api as _meta
        post_resp = _meta.list_recent_posts(limit=50)  # small to find the post
        target = next((p for p in post_resp.get("data", []) if str(p.get("id")) == str(media_id)), None)
        comments = _meta.get_post_comments(media_id, limit=50)
        insights = _meta.get_post_insights(media_id)
        return jsonify({
            "ok": True,
            "post": target,
            "comments": comments.get("data", []),
            "comments_meta": comments.get("_meta"),
            "insights": insights.get("_flat"),
            "insights_raw": insights.get("data"),
        }), 200
    except _meta.MetaAuthError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "hint": "ask Heidi to spin up /meta portal"}), 503
    except _meta.MetaUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _meta.MetaNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        _app_log.exception("meta_post_full failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── SOCIALS — IG history + oEmbed proxy + per-product carousel ───────────
# Layered model:
#   1) Recent ~30 days → Graph API (real thumbnails, signed URLs may expire)
#   2) Older posts → public IG oEmbed proxy (works forever, public posts only)
#   3) Per-product carousel in the Review modal → joins IG history to
#      asset products/services via fuzzy caption + hashtag matching.
# Truth-before-cleverness: every endpoint surfaces a real upstream payload
# (or an explicit 401/503/5xx with the upstream message).

@app.route('/api/socials/status', methods=['GET'])
def socials_status():
    """GET /api/socials/status — can we reach IG Graph + oEmbed?

    Returns { ok, graph_configured, oembed_reachable, ig_account_id, reason }
    """
    try:
        from _lib import meta_api as _meta
        graph_configured = _meta.meta_credentials_present()
        # oEmbed is public — just sanity-check the endpoint is up
        oembed_reachable = True
        try:
            import urllib.request as _ur
            req = _ur.Request(
                "https://api.instagram.com/oembed/?url=https%3A%2F%2Fwww.instagram.com%2Fp%2FCJ5-pxMn7zW%2F",
                headers={"User-Agent": "swing-shack-campaign-os/1.0"},
            )
            with _ur.urlopen(req, timeout=3) as _resp:
                _ = _resp.read(64)  # any 200 = reachable
        except Exception:
            oembed_reachable = False
        out = {
            "ok": True,
            "graph_configured": graph_configured,
            "oembed_reachable": oembed_reachable,
            "ig_account_id": os.environ.get("META_INSTAGRAM_BUSINESS_ACCOUNT_ID") or None,
            "reason": None if (graph_configured or oembed_reachable) else (
                "set META_APP_ID + META_ACCESS_TOKEN[_FILE] + META_INSTAGRAM_BUSINESS_ACCOUNT_ID "
                "for Graph API; oEmbed also requires public IG posts"
            ),
        }
        return jsonify(out), 200
    except Exception as e:
        _app_log.exception("socials_status failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/socials/posts', methods=['GET'])
def socials_posts():
    """GET /api/socials/posts — recent IG posts for the Socials tab.

    Query params:
      - limit (default 25, max 90)
      - after (cursor for pagination; from Graph API `paging.cursors.after`)
      - days (default 365; we page through the IG API until we hit this cutoff
        or run out of results, so old posts always show up)

    Returns:
      {
        data: [{
          id, caption, media_type, media_url, thumbnail_url, permalink,
          timestamp, like_count, comments_count, source: 'graph'|'oembed'
        }, ...],
        paging: { next_cursor, has_more },
        _meta: { total_returned, days_covered, oldest, newest, sources: {...} }
      }
    """
    try:
        from _lib import meta_api as _meta
        limit = min(int(request.args.get("limit", 25)), 90)
        days = int(request.args.get("days", 365))
        after = request.args.get("after", "").strip() or None
        cutoff = (
            _dt_cls.now(_tz.utc) - _td(days=days)
        ).isoformat()
        # Layer 1: Graph API (most recent ~30 days reliable for thumbnails)
        graph_data: list = []
        next_cursor: Optional[str] = after
        graph_error: Optional[str] = None
        if _meta.meta_credentials_present():
            try:
                # Graph API doesn't accept "after" as a param directly for
                # /me/media — pagination uses paging.next URL. We grab up to
                # 90 posts (the API max per call) and rely on days filter
                # below. For deep pagination we'd need to chase paging.next;
                # see _chase_paging helper below.
                params: dict = {"limit": limit}
                if next_cursor:
                    params["after"] = next_cursor
                # Use _graph_get but supply paging cursor via params
                ig_account_id = os.environ.get(
                    "META_INSTAGRAM_BUSINESS_ACCOUNT_ID", ""
                ).strip()
                fields = [
                    "id", "caption", "media_type", "media_url", "permalink",
                    "thumbnail_url", "timestamp", "username",
                    "is_comment_enabled", "like_count", "comments_count",
                ]
                graph_resp = _meta._graph_get(
                    f"/{ig_account_id}/media",
                    {"fields": ",".join(fields), "limit": limit, **({"after": next_cursor} if next_cursor else {})},
                )
                graph_data = graph_resp.get("data", []) or []
                paging = graph_resp.get("paging", {}) or {}
                next_cursor = paging.get("cursors", {}).get("after")
            except Exception as ge:
                graph_error = str(ge)
                _app_log.warning("socials_posts Graph layer failed: %s", ge)
        # Filter by days cutoff
        fresh_graph = [
            p for p in graph_data
            if (p.get("timestamp") or "") >= cutoff
        ]
        # Annotate source
        for p in fresh_graph:
            p["source"] = "graph"
        # Layer 2: oEmbed (always-on fallback for any post we have a permalink
        # for; works forever for public posts, no auth required)
        # We call oEmbed on the Graph posts so the UI can render an iframe
        # even if signed media_url expires.
        oembed_data: list = []
        if fresh_graph:
            import urllib.request as _ur
            import urllib.parse as _up
            for post in fresh_graph[:20]:  # cap oEmbed calls
                permalink = post.get("permalink", "")
                if not permalink:
                    continue
                try:
                    qs = _up.urlencode({"url": permalink, "omitscript": "true", "hidecaption": "true", "maxwidth": 540})
                    req = _ur.Request(
                        f"https://api.instagram.com/oembed/?{qs}",
                        headers={"User-Agent": "swing-shack-campaign-os/1.0"},
                    )
                    with _ur.urlopen(req, timeout=4) as _resp:
                        import json as _json
                        body = _json.loads(_resp.read(1024).decode("utf-8", "ignore"))
                        post["oembed_html"] = body.get("html", "")
                        post["oembed_author"] = body.get("author_name", "")
                        post["oembed_thumbnail"] = body.get("thumbnail_url", post.get("thumbnail_url"))
                except Exception:
                    post.setdefault("oembed_html", "")
                    post.setdefault("oembed_author", "")
                    post.setdefault("oembed_thumbnail", post.get("thumbnail_url"))
        sources_count: dict = {"graph": len(fresh_graph), "oembed_fallback": 0}
        out = {
            "data": fresh_graph,
            "paging": {
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor and len(fresh_graph) >= limit),
            },
            "_meta": {
                "total_returned": len(fresh_graph),
                "days_covered": days,
                "oldest": min((p.get("timestamp") for p in fresh_graph), default=None),
                "newest": max((p.get("timestamp") for p in fresh_graph), default=None),
                "sources": sources_count,
                "graph_error": graph_error,
            },
        }
        return jsonify(out), 200
    except Exception as e:
        _app_log.exception("socials_posts failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/socials/oembed', methods=['GET'])
def socials_oembed():
    """GET /api/socials/oembed?url=<permalink> — server-side oEmbed proxy.

    Why a proxy: the public IG oEmbed endpoint doesn't send CORS headers,
    so the browser can't fetch it directly. This route proxies the call,
    caches the result in-memory for 1 hour, and returns clean JSON.
    """
    permalink = request.args.get("url", "").strip()
    if not permalink or "instagram.com" not in permalink:
        return jsonify({"ok": False, "error": "url must be an instagram.com permalink"}), 400
    cache_key = f"oembed:{permalink}"
    cached = _OEMBED_CACHE.get(cache_key)
    if cached and (time.time() - cached["_ts"]) < 3600:
        return jsonify(cached["data"]), 200
    try:
        import urllib.request as _ur
        import urllib.parse as _up
        import json as _json
        qs = _up.urlencode({"url": permalink, "omitscript": "true", "hidecaption": "true", "maxwidth": 540})
        req = _ur.Request(
            f"https://api.instagram.com/oembed/?{qs}",
            headers={"User-Agent": "swing-shack-campaign-os/1.0"},
        )
        with _ur.urlopen(req, timeout=5) as _resp:
            body = _json.loads(_resp.read(2048).decode("utf-8", "ignore"))
        out = {
            "ok": True,
            "html": body.get("html", ""),
            "author_name": body.get("author_name", ""),
            "thumbnail_url": body.get("thumbnail_url"),
            "provider": body.get("provider_name", "Instagram"),
            "type": body.get("type"),
            "version": body.get("version"),
        }
        _OEMBED_CACHE[cache_key] = {"_ts": time.time(), "data": out}
        return jsonify(out), 200
    except Exception as e:
        _app_log.warning("oEmbed proxy failed for %s: %s", permalink, e)
        return jsonify({"ok": False, "error": f"oEmbed upstream error: {e}"}), 502


@app.route('/api/socials/for-asset/<asset_id>', methods=['GET'])
def socials_for_asset(asset_id: str):
    """GET /api/socials/for-asset/<asset_id> — IG posts that match this asset's
    products/services/keywords. Powers the per-post carousel in the Review modal.

    Joins on:
      - product tags (matched against hashtags + caption text)
      - keyword overlap (caption text vs asset description / visualBrief)
      - recency (last 90 days, ranked)

    Returns: { data: [post, ...], _meta: { matched_via, total_scanned } }
    """
    try:
        from _lib import meta_api as _meta
        if not _meta.meta_credentials_present():
            return jsonify({
                "ok": False,
                "error": "Meta credentials not configured — set META_APP_ID + META_ACCESS_TOKEN + META_INSTAGRAM_BUSINESS_ACCOUNT_ID",
            }), 503
        # Fetch up to 50 recent posts (enough for keyword match)
        posts = _meta.list_recent_posts(limit=50).get("data", []) or []
        # Load asset context — _extract_asset_context returns (text, kind)
        from app import _extract_asset_context as _eac
        prompt_text, asset_kind = _eac(asset_id, "swing-shack")
        # Build keywords from prompt text + a few canonical SS terms
        keywords: list = []
        text_blob = (prompt_text or "").lower()
        for word in text_blob.split():
            w = word.strip(".,!?:;\"'()[]#@")
            if len(w) >= 5 and w.isalpha():
                keywords.append(w)
        # Seed with common Swing Shack hashtag vocabulary so hashtag overlap wins
        keywords.extend([
            "trackman", "takomo", "scotty", "phantom", "putter", "swing",
            "golf", "lesson", "fitting", "mileseey", "rangefinder",
        ])
        keywords = list(set(keywords))[:50]
        def score(post: dict) -> int:
            cap = (post.get("caption") or "").lower()
            return sum(1 for kw in keywords if kw in cap)
        ranked = sorted(posts, key=score, reverse=True)
        # Top 8 with score > 0, then top 3 most recent as fallback
        matched = [p for p in ranked if score(p) > 0][:8]
        if len(matched) < 3:
            for p in posts:
                if p not in matched:
                    matched.append(p)
                if len(matched) >= 3:
                    break
        matched_via = "keyword" if any(score(p) > 0 for p in matched) else "fallback_recent"
        return jsonify({
            "data": matched,
            "_meta": {
                "matched_via": matched_via,
                "total_scanned": len(posts),
                "asset_kind": asset_kind,
                "keywords_used": keywords[:20],
            },
        }), 200
    except Exception as e:
        _app_log.exception("socials_for_asset failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# In-memory oEmbed cache (1h TTL). Avoids hammering IG oEmbed for popular posts.
_OEMBED_CACHE: dict = {}


# ─── INSIGHTS v2 — top IG posts + ad correlation + layman verdicts ─────
# These three endpoints back the new Insights tab. They:
#   1. Surface top IG posts WITH thumbnails + plain-English verdict
#   2. Compute ad-traffic correlation (Google Ads + Meta Ads) when data
#      exists; otherwise return a clean "not configured" payload
#   3. Compute content-traffic correlation from IG post timestamps +
#      GA4 daily sessions
# Truth-before-cleverness: every verdict cites a real timestamp + data
# source. We do not fabricate "the ad worked" stories.

@app.route('/api/insights/top-instagram-posts', methods=['GET'])
def insights_top_instagram_posts():
    """GET /api/insights/top-instagram-posts?limit=8&brand_id=...

    Returns: { ok, posts: [{id,thumbnail_url,engagementRate,permalink,
            verdict,plain_english,...}], _meta }

    brand_id: when provided, follows data_delegates_from (e.g. stick →
    swing-shack) so sub-brands inherit the parent's IG analytics.
    """
    try:
        from _lib import insights_correlator as _ic
        limit = min(int(request.args.get("limit", 8)), 25)
        bid = request.args.get("brand_id") or get_brand_id()
        data_bid = resolve_data_brand(bid)
        out = _ic.get_top_instagram_posts(limit=limit)
        out['requested_brand_id'] = bid
        out['data_source_brand_id'] = data_bid
        return jsonify(out), 200
    except Exception as e:
        _app_log.exception("insights_top_instagram_posts failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/insights/ad-correlation', methods=['GET'])
def insights_ad_correlation():
    """GET /api/insights/ad-correlation — joins ad-platform timestamps
    with GA4 traffic.

    Returns: { ok, configured, google_ads:{configured,campaigns,verdicts},
            meta_ads:{...}, combined_summary }

    When ad data is missing, returns clear "not configured" with the
    exact JSON shape needed to wire it up.
    """
    try:
        from _lib import insights_correlator as _ic
        bid = request.args.get("brand_id") or get_brand_id()
        data_bid = resolve_data_brand(bid)
        out = _ic.get_ad_correlation_verdicts()
        out['requested_brand_id'] = bid
        out['data_source_brand_id'] = data_bid
        return jsonify(out), 200
    except Exception as e:
        _app_log.exception("insights_ad_correlation failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/insights/content-traffic-correlation', methods=['GET'])
def insights_content_traffic_correlation():
    """GET /api/insights/content-traffic-correlation?days=30&brand_id=...

    Joins IG post timestamps with GA4 traffic to surface verdicts like
    "Post X went live Mon → /bookings/ spiked +212% Mon → likely content
    drove the spike".

    Returns: { ok, matches, unmatched_spikes, _meta }
    """
    try:
        from _lib import insights_correlator as _ic
        days = min(int(request.args.get("days", 30)), 90)
        bid = request.args.get("brand_id") or get_brand_id()
        data_bid = resolve_data_brand(bid)
        out = _ic.get_content_traffic_correlations(days=days)
        out['requested_brand_id'] = bid
        out['data_source_brand_id'] = data_bid
        return jsonify(out), 200
    except Exception as e:
        _app_log.exception("insights_content_traffic_correlation failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── MEME TEMPLATES — visual library for Meme Lord picker ─────────────────
# Returns 30 popular meme templates with public thumbnails so the Meme Lord
# picker can show what each template actually looks like (no more guessing
# from a name). Thumbnails are public CDN URLs (imgflip.com) — see
# _lib/meme_templates.py for attribution and licensing notes.

@app.route('/api/meme/templates', methods=['GET'])
def meme_templates():
    """GET /api/meme/templates — full catalog with thumbnails.

    Query params:
      - tier (optional): filter to iconic | trending | classic
      - q (optional): free-text search over name

    Returns: { data: [{ id, name, tier, text_zones, thumbnail_url, source, brand_fit }, ...] }
    """
    try:
        from _lib import meme_templates as _mt
        tier = (request.args.get("tier") or "").strip().lower()
        q = (request.args.get("q") or "").strip().lower()
        templates = _mt.list_templates()
        if tier and tier in ("iconic", "trending", "classic"):
            templates = [t for t in templates if t["tier"] == tier]
        if q:
            templates = [t for t in templates if q in t["name"].lower()]
        return jsonify({"data": templates, "count": len(templates)}), 200
    except Exception as e:
        _app_log.exception("meme_templates failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── META CREDENTIALS PORTAL ─────────────────────────────────────────────
# Local-only route for safely ingesting Meta app credentials without them
# ever touching Discord/chat. Form lives at GET /meta-portal.html (static file
# served from campaign-os/meta-portal.html). Submit handler writes:
#   - ~/.openclaw/workspace/credentials/meta-app.json    (chmod 600)
#   - ~/.openclaw/workspace/credentials/meta-token.json  (chmod 600)
#   - ~/.openclaw/workspace/credentials/meta.env         (chmod 600, sourced by
#                                                         Campaign OS restart)
# All writes happen on the local filesystem only — no remote calls. After
# write, runs a live probe against Graph API to confirm the token works,
# then signals the watcher to restart Campaign OS with the new env vars.

CRED_DIR = os.path.expanduser('~/.openclaw/workspace/credentials')
META_APP_FILE = os.path.join(CRED_DIR, 'meta-app.json')
META_TOKEN_FILE = os.path.join(CRED_DIR, 'meta-token.json')
META_PAGE_TOKEN_FILE = os.path.join(CRED_DIR, 'meta-page-token.json')
META_ENV_FILE = os.path.join(CRED_DIR, 'meta.env')
META_VERIFY_FILE = os.path.join(CRED_DIR, 'meta-verify-report.json')

META_REQUIRED_KEYS = [
    'META_APP_ID',
    'META_APP_SECRET',
    'META_PAGE_ID',
    'META_INSTAGRAM_BUSINESS_ACCOUNT_ID',
    'META_ACCESS_TOKEN',
    'META_TOKEN_TYPE',
]


def _meta_verify_token(app_id, app_secret, access_token, page_id):
    """Live probe against Graph API. Returns dict {ok, user, page, ig_account, error}."""
    import urllib.request
    import urllib.parse
    import urllib.error
    import ssl

    out = {"ok": False, "checks": {}, "error": None, "ts": datetime.datetime.utcnow().isoformat() + 'Z'}
    ctx = ssl.create_default_context()
    api_base = 'https://graph.facebook.com/v25.0'

    def _get(url):
        req = urllib.request.Request(url, headers={'User-Agent': 'CampaignOS/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                return resp.status, json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            try:
                body = json.loads(body)
            except Exception:
                pass
            return e.code, body
        except Exception as e:
            return 0, {"error": {"message": str(e), "type": type(e).__name__}}

    def _err_msg(s, body):
        if isinstance(body, dict):
            return f'{body.get("error", {}).get("message", body) if isinstance(body.get("error"), dict) else body.get("error", body)}'
        return str(body)[:300]

    # 1) /me — confirms token is alive
    s, body = _get(f'{api_base}/me?fields=id,name&access_token={urllib.parse.quote(access_token)}')
    out["checks"]["me"] = {"status": s, "body": body}
    if s != 200 or not isinstance(body, dict):
        out["error"] = f'/me returned HTTP {s}: {_err_msg(s, body)}'
        return out

    out["user"] = body

    # 1b) /me/permissions — confirms the IG scopes were actually granted
    s, body = _get(f'{api_base}/me/permissions?access_token={urllib.parse.quote(access_token)}')
    out["checks"]["permissions"] = {"status": s, "body": body}
    if s == 200 and isinstance(body, dict):
        perms_list = body.get('data') if isinstance(body.get('data'), list) else []
        granted = {p['permission'] for p in perms_list if isinstance(p, dict) and p.get('status') == 'granted'}
        required_ig = {'instagram_basic', 'instagram_manage_insights', 'instagram_business_manage_insights', 'pages_read_user_content'}
        required_pages = {'pages_show_list', 'pages_read_engagement', 'business_management'}
        missing_ig = required_ig - granted
        missing_pages = required_pages - granted
        out["granted_scopes"] = sorted(granted)
        out["missing_ig_scopes"] = sorted(missing_ig)
        out["missing_page_scopes"] = sorted(missing_pages)
        if missing_ig or missing_pages:
            missing = sorted(missing_ig) + sorted(missing_pages)
            out["error"] = (
                f'Token is missing required scopes: {", ".join(missing)}. '
                f'Re-generate the token in Graph API Explorer and tick ALL 7 boxes: '
                f'pages_show_list, pages_read_engagement, pages_read_user_content, '
                f'instagram_basic, instagram_manage_insights, instagram_business_manage_insights, '
                f'business_management.'
            )
            return out
    else:
        out["error"] = f'/me/permissions returned HTTP {s}: {_err_msg(s, body)}'
        return out

    # 2) /{page_id}?fields=access_token,instagram_business_account — confirms page is reachable
    s, body = _get(f'{api_base}/{page_id}?fields=id,name,access_token,instagram_business_account&access_token={urllib.parse.quote(access_token)}')
    out["checks"]["page"] = {"status": s, "body": body}
    if s == 200 and isinstance(body, dict):
        out["page"] = body
        # If page returned a long-lived page token, prefer it
        page_token = body.get('access_token')
        if page_token and isinstance(page_token, str) and len(page_token) > len(access_token):
            out["page_token_available"] = True
        ig = body.get('instagram_business_account') or {}
        if isinstance(ig, dict) and ig.get('id'):
            out["ig_account"] = ig
            # 3) /{ig_id}?fields=id,username — confirms IG business account is reachable
            s2, body2 = _get(f'{api_base}/{ig["id"]}?fields=id,username,media_count&access_token={urllib.parse.quote(access_token)}')
            out["checks"]["ig"] = {"status": s2, "body": body2}
            if s2 == 200 and isinstance(body2, dict):
                out["ig_account"].update(body2)
                out["ok"] = True
            else:
                out["error"] = f'IG account probe returned HTTP {s2}: {_err_msg(s2, body2)}'
        else:
            out["error"] = 'Page response did not include instagram_business_account — link your IG to the FB page in Meta Business Suite first'
    else:
        out["error"] = f'Page probe returned HTTP {s}: {_err_msg(s, body)}'

    return out


def _write_meta_creds(payload):
    """Write creds to disk and the .env file. Returns dict with file paths."""
    os.makedirs(CRED_DIR, mode=0o700, exist_ok=True)
    app_payload = {
        'app_id': payload['META_APP_ID'],
        'app_secret': payload['META_APP_SECRET'],
        'page_id': payload['META_PAGE_ID'],
        'instagram_business_account_id': payload['META_INSTAGRAM_BUSINESS_ACCOUNT_ID'],
        'token_type': payload.get('META_TOKEN_TYPE', 'user'),
        'written_at': datetime.datetime.utcnow().isoformat() + 'Z',
    }
    token_payload = {
        'access_token': payload['META_ACCESS_TOKEN'],
        'token_type': payload.get('META_TOKEN_TYPE', 'user'),
        'written_at': datetime.datetime.utcnow().isoformat() + 'Z',
    }
    with open(META_APP_FILE, 'w') as f:
        json.dump(app_payload, f, indent=2)
    os.chmod(META_APP_FILE, 0o600)
    with open(META_TOKEN_FILE, 'w') as f:
        json.dump(token_payload, f, indent=2)
    os.chmod(META_TOKEN_FILE, 0o600)
    # .env file — sourced by Campaign OS restart
    env_lines = [
        '# Generated by /api/meta/credentials portal — do not edit by hand',
        f"export META_APP_ID='{payload['META_APP_ID']}'",
        f"export META_APP_SECRET='{payload['META_APP_SECRET']}'",
        f"export META_PAGE_ID='{payload['META_PAGE_ID']}'",
        f"export META_INSTAGRAM_BUSINESS_ACCOUNT_ID='{payload['META_INSTAGRAM_BUSINESS_ACCOUNT_ID']}'",
        f"export META_ACCESS_TOKEN='{payload['META_ACCESS_TOKEN']}'",
        f"export META_TOKEN_TYPE='{payload.get('META_TOKEN_TYPE', 'user')}'",
        f"export META_ACCESS_TOKEN_FILE='{META_TOKEN_FILE}'",
        '',
    ]
    with open(META_ENV_FILE, 'w') as f:
        f.write('\n'.join(env_lines))
    os.chmod(META_ENV_FILE, 0o600)
    return {
        'app_file': META_APP_FILE,
        'token_file': META_TOKEN_FILE,
        'env_file': META_ENV_FILE,
    }


@app.route('/api/admin/secrets-sync', methods=['POST'])
def admin_secrets_sync():
    """POST /api/admin/secrets-sync — paste contents of any local credential file.

    Single-source-of-truth bridge: copy the JSON from
    ~/.openclaw-instance2/workspace/clients/swing-shack/credentials/
    on your Mac, paste it here. Server writes to:

      1. CRED_DIR/<service>.json (Railway persistent credential dir)
      2. DATA_DIR/credentials/<service>.json (deploy-survives)
      3. os.environ (in-process, immediate effect)

    Body: { service: "meta-token" | "openai-api" | "openrouter-api" |
            "instagram-api-token" | "ubersuggest-api" | "google-analytics"
            | "google-service-account" | "postiz-api-key" | "youtube-api",
            contents: <full JSON as a string OR object> }

    For 'meta-token' specifically, also sets META_APP_ID + META_ACCESS_TOKEN
    + META_INSTAGRAM_BUSINESS_ACCOUNT_ID in os.environ so Graph API works
    immediately.
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception as e:
        return jsonify({"ok": False, "error": f"invalid JSON: {e}"}), 400

    service = (body.get('service') or '').strip()
    contents = body.get('contents')
    if not service:
        return jsonify({"ok": False, "error": "service is required"}), 400
    if contents is None:
        return jsonify({"ok": False, "error": "contents is required"}), 400

    # Accept contents as either JSON string or already-parsed object
    if isinstance(contents, str):
        try:
            contents_obj = json.loads(contents)
        except json.JSONDecodeError as e:
            return jsonify({"ok": False, "error": f"contents not valid JSON: {e}"}), 400
    elif isinstance(contents, dict):
        contents_obj = contents
    else:
        return jsonify({"ok": False, "error": "contents must be JSON string or object"}), 400

    # Write to all persistence layers
    runtime_creds_dir = os.path.join(DATA_DIR, 'credentials')
    os.makedirs(runtime_creds_dir, exist_ok=True)
    home_creds_dir = os.path.expanduser('~/.openclaw/workspace/credentials')
    os.makedirs(home_creds_dir, exist_ok=True)

    payload_str = json.dumps(contents_obj, indent=2)
    file_name = f'{service}.json'
    wrote = []
    rt_path = ''
    for d in (home_creds_dir, runtime_creds_dir):
        try:
            p = os.path.join(d, file_name)
            with open(p, 'w') as f:
                f.write(payload_str)
            os.chmod(p, 0o600)
            wrote.append(p)
            if d == runtime_creds_dir:
                rt_path = p
        except Exception as e:
            _app_log.warning('secrets-sync write %s failed: %s', p, e)

    # Service-specific env-var wiring for the running process
    env_wired = []
    if service == 'meta-token':
        # Map meta-token.json fields to env vars
        if contents_obj.get('app_id') or contents_obj.get('META_APP_ID'):
            v = contents_obj.get('app_id') or contents_obj.get('META_APP_ID')
            os.environ['META_APP_ID'] = str(v); env_wired.append('META_APP_ID')
        if contents_obj.get('access_token'):
            os.environ['META_ACCESS_TOKEN'] = contents_obj['access_token']
            env_wired.append('META_ACCESS_TOKEN')
            # Also set the *_FILE so resolver picks it up
            rt_path = os.path.join(runtime_creds_dir, file_name)
            if os.path.exists(rt_path):
                os.environ['META_ACCESS_TOKEN_FILE'] = rt_path
                env_wired.append('META_ACCESS_TOKEN_FILE')
        if contents_obj.get('instagram_account_id'):
            os.environ['META_INSTAGRAM_BUSINESS_ACCOUNT_ID'] = str(
                contents_obj['instagram_account_id'])
            env_wired.append('META_INSTAGRAM_BUSINESS_ACCOUNT_ID')
        if contents_obj.get('page_id'):
            os.environ['META_PAGE_ID'] = str(contents_obj['page_id'])
            env_wired.append('META_PAGE_ID')
        # Also try to read app_id from a sibling meta-app.json if present
        meta_app_path = os.path.join(runtime_creds_dir, 'meta-app.json')
        if not os.environ.get('META_APP_ID') and os.path.exists(meta_app_path):
            try:
                with open(meta_app_path) as f:
                    app_cfg = json.load(f)
                if app_cfg.get('app_id'):
                    os.environ['META_APP_ID'] = str(app_cfg['app_id'])
                    env_wired.append('META_APP_ID (from meta-app.json)')
            except Exception:
                pass
        # Same for home dir
        if not os.environ.get('META_APP_ID'):
            home_meta_app = os.path.join(home_creds_dir, 'meta-app.json')
            if os.path.exists(home_meta_app):
                try:
                    with open(home_meta_app) as f:
                        app_cfg = json.load(f)
                    if app_cfg.get('app_id'):
                        os.environ['META_APP_ID'] = str(app_cfg['app_id'])
                        env_wired.append('META_APP_ID (from home meta-app.json)')
                except Exception:
                    pass
    elif service == 'openrouter-api':
        if contents_obj.get('api_key'):
            os.environ['OPENROUTER_API_KEY'] = contents_obj['api_key']
            env_wired.append('OPENROUTER_API_KEY')
            rt_path = os.path.join(runtime_creds_dir, file_name)
            if os.path.exists(rt_path):
                os.environ['OPENROUTER_API_KEY_FILE'] = rt_path
                env_wired.append('OPENROUTER_API_KEY_FILE')
    elif service == 'openai-api':
        if contents_obj.get('api_key'):
            os.environ['OPENAI_API_KEY'] = contents_obj['api_key']
            env_wired.append('OPENAI_API_KEY')
            rt_path = os.path.join(runtime_creds_dir, file_name)
            if os.path.exists(rt_path):
                os.environ['OPENAI_API_KEY_FILE'] = rt_path
                env_wired.append('OPENAI_API_KEY_FILE')

    # Bust any caches that would hide the new keys
    try:
        from _lib import image_gen_router as _igr
        for name in ('_resolve_openai_key', '_resolve_openrouter_key',
                     'openai_credentials_present', 'openrouter_credentials_present'):
            fn = getattr(_igr, name, None)
            clr = getattr(fn, 'cache_clear', None) if fn else None
            if callable(clr):
                clr()
        from _lib.image_gen_router import status_report as _status
        clr = getattr(_status, 'cache_clear', None)
        if callable(clr):
            clr()
    except Exception:
        pass

    return jsonify({
        'ok': True,
        'service': service,
        'wrote': wrote,
        'env_wired': env_wired,
        'note': 'Keys are now active in the running process. For deploy restarts, also set them in Railway dashboard Variables tab.',
    })


@app.route('/meta-portal', methods=['GET'])
@app.route('/meta-portal.html', methods=['GET'])
def meta_portal_form():
    """GET /meta-portal — serve the credential submission form."""
    return send_from_directory(os.path.dirname(__file__), 'meta-portal.html')


@app.route('/secrets-sync', methods=['GET'])
@app.route('/secrets-sync.html', methods=['GET'])
def secrets_sync_page():
    """GET /secrets-sync — visual paste-form for any credential file."""
    return send_from_directory(os.path.dirname(__file__), 'secrets-sync.html')


@app.route('/privacy', methods=['GET'])
@app.route('/privacy.html', methods=['GET'])
def privacy_policy():
    """GET /privacy — Privacy Policy (required for Meta App Review)."""
    return send_from_directory(os.path.dirname(__file__), 'privacy.html')


@app.route('/meta-app-review', methods=['GET'])
@app.route('/meta-app-review/', methods=['GET'])
def meta_app_review_index():
    """GET /meta-app-review — Visual evidence bundle for Meta App Review submission."""
    return send_from_directory(os.path.dirname(__file__), 'meta-app-review/index.html')


@app.route('/terms', methods=['GET'])
@app.route('/terms.html', methods=['GET'])
def terms_of_service():
    """GET /terms — Terms of Service (required for Meta App Review)."""
    return send_from_directory(os.path.dirname(__file__), 'terms.html')


@app.route('/api/meta/credentials', methods=['POST'])
def meta_credentials_submit():
    """POST /api/meta/credentials — accept form submission, write creds, verify live.

    Body (JSON): { META_APP_ID, META_APP_SECRET, META_PAGE_ID,
                   META_INSTAGRAM_BUSINESS_ACCOUNT_ID, META_ACCESS_TOKEN,
                   META_TOKEN_TYPE }
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception as e:
        return jsonify({"ok": False, "error": f"invalid JSON body: {e}"}), 400

    missing = [k for k in META_REQUIRED_KEYS if not body.get(k)]
    if missing:
        return jsonify({
            "ok": False,
            "error": f"missing required fields: {', '.join(missing)}",
            "missing": missing,
        }), 400

    # Sanity: all numeric IDs must be digits
    for k in ('META_APP_ID', 'META_PAGE_ID', 'META_INSTAGRAM_BUSINESS_ACCOUNT_ID'):
        v = body[k].strip()
        if not v.isdigit():
            return jsonify({"ok": False, "error": f"{k} must be numeric, got {v[:8]}…"}), 400
        body[k] = v

    # Sanity: token must start with EAA (user/page/system_user token format)
    tok = body['META_ACCESS_TOKEN'].strip()
    if not tok.startswith(('EAA', 'EAB', 'EAAB')):
        return jsonify({
            "ok": False,
            "error": f"META_ACCESS_TOKEN must start with EAA/EAB/EAAB (got prefix '{tok[:6]}…'). Are you sure this is the full token?",
            "hint": "If this is a short-lived token from Graph API Explorer, click 'Generate Access Token' to get a long-lived one",
        }), 400

    # Write files
    try:
        files = _write_meta_creds(body)
    except Exception as e:
        _app_log.exception("meta_credentials_write_failed")
        return jsonify({"ok": False, "error": f"write failed: {e}"}), 500

    # Live verify against Graph API (also writes META_VERIFY_FILE)
    verify = _meta_verify_token(
        body['META_APP_ID'], body['META_APP_SECRET'], tok, body['META_PAGE_ID']
    )
    try:
        with open(META_VERIFY_FILE, 'w') as f:
            json.dump(verify, f, indent=2)
        os.chmod(META_VERIFY_FILE, 0o600)
    except Exception:
        pass

    # If the page probe returned a page-scoped access token, save it too so
    # FB-page endpoints (/api/meta/page-posts etc) can use it. User tokens are
    # rejected for /{page_id}/posts post-2024.
    page_token_saved = False
    page = verify.get('page') or {}
    page_token = page.get('access_token') if isinstance(page, dict) else None
    if isinstance(page_token, str) and page_token.startswith(('EAA', 'EAB', 'EAAB')):
        try:
            page_payload = {
                'access_token': page_token,
                'source': 'meta-credentials-portal',
                'page_id': page.get('id', body['META_PAGE_ID']),
                'page_name': page.get('name', ''),
                'written_at': datetime.datetime.utcnow().isoformat() + 'Z',
            }
            with open(META_PAGE_TOKEN_FILE, 'w') as f:
                json.dump(page_payload, f, indent=2)
            os.chmod(META_PAGE_TOKEN_FILE, 0o600)
            # Append META_PAGE_ACCESS_TOKEN_FILE to meta.env if not already present
            try:
                env_lines = open(META_ENV_FILE).read().splitlines() if os.path.exists(META_ENV_FILE) else []
                if not any('META_PAGE_ACCESS_TOKEN_FILE' in ln for ln in env_lines):
                    env_lines.append('')
                    env_lines.append('# Page-scoped token (preferred for FB-page endpoints)')
                    env_lines.append(f"export META_PAGE_ACCESS_TOKEN_FILE='{META_PAGE_TOKEN_FILE}'")
                    with open(META_ENV_FILE, 'w') as f:
                        f.write('\n'.join(env_lines) + '\n')
                    os.chmod(META_ENV_FILE, 0o600)
            except Exception:
                pass
            page_token_saved = True
        except Exception as e:
            _app_log.warning("could not save page token: %s", e)

    # If verify OK, kick off a restart so Campaign OS picks up env vars
    restart_pid = None
    if verify.get("ok"):
        try:
            # Spawn detached restart that:
            #   1. kills current Campaign OS (PID 7935)
            #   2. waits for port 8000 to free
            #   3. re-launches with meta.env sourced
            restart_script = (
                f"#!/bin/bash\n"
                f"sleep 1\n"
                f"kill 7935 2>/dev/null\n"
                f"for i in 1 2 3 4 5 6 7 8 9 10; do\n"
                f"  lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null\n"
                f"  if ! lsof -ti:8000 >/dev/null 2>&1; then break; fi\n"
                f"  sleep 1\n"
                f"done\n"
                f"cd /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard\n"
                f"set -a\n"
                f"source {META_ENV_FILE}\n"
                f"set +a\n"
                f"export DATA_DIR=./data\n"
                f"nohup .venv/bin/python campaign-os/app.py > /tmp/flask.log 2>&1 &\n"
                f"disown\n"
                f"echo $! > /tmp/campaign-os.pid\n"
                f"exit 0\n"
            )
            with open('/tmp/campaign-os-restart.sh', 'w') as f:
                f.write(restart_script)
            os.chmod('/tmp/campaign-os-restart.sh', 0o755)
            subprocess.Popen(
                ['/bin/bash', '/tmp/campaign-os-restart.sh'],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            restart_pid = True
        except Exception as e:
            _app_log.exception("meta_credentials_restart_failed")
            restart_pid = f"failed: {e}"

    # Build user-facing summary
    if verify.get("ok"):
        user = verify.get('user', {})
        page = verify.get('page', {})
        ig = verify.get('ig_account', {})
        verify_summary = (
            f"✅ Token valid for user {user.get('name', '?')} (id {user.get('id', '?')}).\n"
            f"✅ Page reachable: {page.get('name', '?')} (id {page.get('id', '?')}).\n"
            f"✅ IG business account: @{ig.get('username', '?')} (id {ig.get('id', '?')}, {ig.get('media_count', '?')} posts).\n"
            f"{'🔑 Page returned a longer-lived page token — consider using that next time.' if verify.get('page_token_available') else ''}\n"
            f"🔄 Campaign OS is restarting to load the new env vars (will be back in ~5s)."
        )
    else:
        verify_summary = (
            f"❌ Verification failed: {verify.get('error', 'unknown error')}\n"
            f"Check /api/meta/status in a few seconds for the full upstream response."
        )

    return jsonify({
        "ok": True,
        "files": files,
        "verify": verify,
        "verify_summary": verify_summary,
        "restart_initiated": restart_pid,
        "page_token_saved": page_token_saved,
    }), 200


@app.route('/api/meta/credentials/status', methods=['GET'])
def meta_credentials_status():
    """GET /api/meta/credentials/status — show last verify report + file mtimes."""
    import stat as _stat
    out = {"ok": True, "files": {}, "verify": None}
    for label, path in [('app', META_APP_FILE), ('token', META_TOKEN_FILE), ('env', META_ENV_FILE), ('verify_report', META_VERIFY_FILE)]:
        if os.path.exists(path):
            st = os.stat(path)
            out["files"][label] = {
                "path": path,
                "size": st.st_size,
                "mtime": datetime.datetime.utcfromtimestamp(st.st_mtime).isoformat() + 'Z',
                "mode": oct(_stat.S_IMODE(st.st_mode)),
            }
        else:
            out["files"][label] = None
    if os.path.exists(META_VERIFY_FILE):
        try:
            with open(META_VERIFY_FILE) as f:
                out["verify"] = json.load(f)
        except Exception:
            out["verify"] = None
    return jsonify(out), 200


# ─── META FACEBOOK PAGE-SIDE STATS ───────────────────────────────────────────
# These three endpoints give the dashboard real data TODAY using only the
# 5 scopes currently granted (no App Review pending). They mirror the
# Instagram-side equivalents above so the SPA can render both side-by-side.
# Once App Review for instagram_basic + instagram_manage_insights lands,
# both function families coexist — the SPA picks whichever has data.

@app.route('/api/meta/page-posts', methods=['GET'])
def meta_page_list_posts():
    """GET /api/meta/page-posts?limit=25 — recent Facebook Page posts.

    Requires scopes: pages_show_list, pages_read_engagement.
    Works with the currently-approved 5-scope token. No App Review needed.
    """
    try:
        from _lib import meta_api as _meta
        limit = int(request.args.get('limit', 25))
        out = _meta.list_page_posts(limit=limit)
        out['ok'] = True
        return jsonify(out), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except _meta.MetaAuthError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "upstream": e.upstream,
            "hint": "ask Heidi to verify META_APP_ID + META_PAGE_ID + META_ACCESS_TOKEN[_FILE] are set",
        }), 503
    except _meta.MetaUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _meta.MetaNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("meta_page_list_posts failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/meta/page-posts/<post_id>/insights', methods=['GET'])
def meta_page_post_insights(post_id):
    """GET /api/meta/page-posts/<post_id>/insights — engagement for one FB post.

    Requires scopes: read_insights, pages_read_engagement.
    Returns flattened metrics + computed engagement_rate.
    """
    try:
        from _lib import meta_api as _meta
        out = _meta.get_page_post_insights(post_id)
        out['ok'] = True
        return jsonify(out), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except _meta.MetaAuthError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "upstream": e.upstream,
            "hint": "ask Heidi to verify META_PAGE_ID + META_ACCESS_TOKEN[_FILE] are set",
        }), 503
    except _meta.MetaUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _meta.MetaNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("meta_page_post_insights failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/meta/page-posts/<post_id>/comments', methods=['GET'])
def meta_page_post_comments(post_id):
    """GET /api/meta/page-posts/<post_id>/comments — comments on one FB post.

    Requires scope: pages_read_user_content.
    """
    try:
        from _lib import meta_api as _meta
        limit = int(request.args.get('limit', 50))
        out = _meta.get_page_post_comments(post_id, limit=limit)
        out['ok'] = True
        return jsonify(out), 200
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except _meta.MetaAuthError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "upstream": e.upstream,
            "hint": "ask Heidi to verify META_PAGE_ID + META_ACCESS_TOKEN[_FILE] are set",
        }), 503
    except _meta.MetaUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _meta.MetaNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("meta_page_post_comments failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/meta/page-insights', methods=['GET'])
def meta_page_aggregate_insights():
    """GET /api/meta/page-insights?period=day|week|days_28 — page-level aggregate.

    Requires scope: read_insights.
    Optional query: ?metric=page_post_engagements,page_views_total (default = both).

    Note: only certain metric names are valid for a page with read_insights
    WITHOUT also having pages_read_engagement (which requires App Review).
    Working set as of 2026-07: page_post_engagements, page_views_total,
    page_video_views, page_consumptions, page_consumptions_unique,
    page_impressions_viral, page_impressions_paid, etc.
    """
    try:
        from _lib import meta_api as _meta
        if not _meta._page_credentials_present():
            raise _meta.MetaAuthError("FB-page credentials not configured")
        page_id = os.environ.get("META_PAGE_ID", "").strip()
        period = request.args.get('period', 'day')
        # Default to metrics that work with read_insights only (no App Review)
        # Confirmed working set as of 2026-07-29 with the 5 currently-approved scopes.
        default_metrics = [
            "page_post_engagements",
            "page_views_total",
        ]
        metric_param = request.args.get('metric')
        metrics = metric_param.split(',') if metric_param else default_metrics
        params = {
            "metric": ",".join(m.strip() for m in metrics if m.strip()),
            "period": period,
        }
        out = _meta._graph_get(f"/{page_id}/insights", params, use_page_token=True)
        out["_meta"] = {
            "page_id": page_id,
            "period": period,
            "metrics_requested": metrics,
            "endpoint": f"/{page_id}/insights",
            "source": "facebook_page",
        }
        out['ok'] = True
        return jsonify(out), 200
    except _meta.MetaAuthError as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "upstream": e.upstream,
            "hint": "ask Heidi to verify META_PAGE_ID + META_ACCESS_TOKEN[_FILE] are set",
        }), 503
    except _meta.MetaUpstreamError as e:
        return jsonify({"ok": False, "error": str(e), "upstream": e.upstream, "code": e.code}), 502
    except _meta.MetaNetworkError as e:
        return jsonify({"ok": False, "error": str(e)}), 504
    except Exception as e:
        _app_log.exception("meta_page_aggregate_insights failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/campaigns', methods=['GET'])
def list_campaigns():
    """GET /api/campaigns — list all campaigns, filtered by active brand.
    Query string: ?brand_id=<id> overrides the active brand for this request.
    Pass ?all_brands=1 to bypass brand filtering entirely."""
    data = load_data()
    all_campaigns = data.get("campaigns", {})
    if request.args.get('all_brands') in ('1', 'true', 'yes'):
        filtered = dict(all_campaigns)
        active_bid = None
    else:
        active_bid = get_brand_id()
        filtered = {cid: c for cid, c in all_campaigns.items() if c.get('brand_id') == active_bid}
    active_campaign_id = data.get('activeCampaignId')
    # If the active campaign belongs to a different brand than the filter, fall back to the first
    # matching campaign in this brand (or None).
    if active_campaign_id and active_campaign_id not in filtered:
        active_campaign_id = next(iter(filtered.keys()), None)
    return jsonify({
        "campaigns": filtered,
        "activeCampaignId": active_campaign_id,
        "portfolioMetadata": data.get("portfolioMetadata", {}),
        "brand_id": active_bid,
        "brand_filter_applied": active_bid is not None,
    })

@app.route('/api/campaigns/<campaign_id>', methods=['GET'])
def get_campaign(campaign_id):
    """Return single campaign with all assets."""
    data = load_data()
    campaigns = data.get("campaigns", {})
    if campaign_id not in campaigns:
        return jsonify({"error": "Campaign not found"}), 404
    return jsonify(campaigns[campaign_id])

@app.route('/api/campaigns', methods=['POST'])
def create_campaign():
    """Create a new campaign."""
    body = request.get_json()
    if not body:
        return jsonify({"error": "No JSON body"}), 400
    name = body.get('name', '').strip()
    if not name:
        return jsonify({"error": "Campaign name required"}), 400

    data = load_data()
    campaigns = data.get("campaigns", {})

    # Generate ID
    import re
    campaign_id = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    base_id = campaign_id
    counter = 1
    while campaign_id in campaigns:
        campaign_id = f"{base_id}-{counter}"
        counter += 1

    now = datetime.datetime.utcnow().isoformat() + 'Z'
    new_campaign = {
        "identity": {
            "campaignId": campaign_id,
            "name": name,
            "shortName": body.get('shortName', name),
            "goal": body.get('primaryGoal', body.get('goal', '')),
            "status": "active",
            "owner": body.get('owner', 'christelle'),
            "createdAt": now,
            "updatedAt": now
        },
        "assets": {},
        "productionPlan": None,
        "blueprints": []
    }

    campaigns[campaign_id] = new_campaign
    data["campaigns"] = campaigns
    data["activeCampaignId"] = campaign_id
    save_data(data)

    # GitHub write-back (non-blocking on failure)
    ok, msg = git_push(f"Campaign OS v0.1: Create campaign '{name}' ({campaign_id})")

    response = {"ok": True, "campaignId": campaign_id, "campaign": new_campaign}
    if not ok:
        response["_syncWarning"] = f"GitHub sync failed: {msg}. Data is saved on server."
    return jsonify(response), 201

@app.route('/api/review/<asset_id>', methods=['POST'])
def review_asset(asset_id):
    """
    Save a review decision for an asset.
    Body: { campaignId, approvalStatus, caption?, visualBrief?, rejectionReason?, revisionRequest?, assignedLane? }
    """
    body = request.get_json()
    if not body:
        return jsonify({"error": "No JSON body"}), 400
    campaign_id = body.get('campaignId')
    if not campaign_id:
        return jsonify({"error": "campaignId required"}), 400

    data = load_data()
    campaigns = data.get("campaigns", {})
    if campaign_id not in campaigns:
        return jsonify({"error": "Campaign not found"}), 404

    campaign = campaigns[campaign_id]
    assets = campaign.get("assets", {})
    if asset_id not in assets:
        return jsonify({"error": "Asset not found"}), 404

    asset = assets[asset_id]
    now = datetime.datetime.utcnow().isoformat() + 'Z'

    if body.get('approvalStatus'):
        asset['approvalStatus'] = body['approvalStatus']
    if 'caption' in body and asset.get('caption') != body['caption']:
        # Snapshot the prior caption as aiDraft the FIRST time it changes via review.
        # Pairs with the same logic in /api/assets/<aid> PATCH so the Reset-to-AI-draft
        # button works regardless of which path the user saved through.
        if 'aiDraft' not in asset and asset.get('caption'):
            asset['aiDraft'] = asset.get('caption')
            asset['aiDraftSetAt'] = now
            asset['aiDraftSource'] = 'review-decision-first-change'
        asset['caption'] = body['caption']
    if 'visualBrief' in body:
        asset['visualBrief'] = body['visualBrief']
    if 'rejectionReason' in body:
        asset['rejectionReason'] = body['rejectionReason']
    if 'revisionRequest' in body:
        asset['revisionRequest'] = body['revisionRequest']
    if 'assignedLane' in body:
        asset['assignedLane'] = body['assignedLane']

    asset['updatedAt'] = now
    asset['reviewTs'] = now
    campaign['updatedAt'] = now
    save_data(data)

    ok, msg = git_push(f"Campaign OS v0.1: Review '{asset_id}' — {body.get('approvalStatus')}")
    response = {"ok": True, "assetId": asset_id, "asset": asset}
    if not ok:
        response["_syncWarning"] = f"GitHub sync failed: {msg}. Data is saved on server."
    return jsonify(response)


@app.route('/api/review/bulk-approve', methods=['POST'])
def bulk_approve_assets():
    """POST /api/review/bulk-approve — flip a list of assets to approved in one call,
       one git commit (not N).

       Body: { campaignId, assetIds: [...] }
       Returns: { ok, approved: N, failed: [...], _syncWarning? }
    """
    body = request.get_json() or {}
    campaign_id = body.get('campaignId')
    asset_ids = body.get('assetIds') or []
    if not campaign_id: return jsonify({"ok": False, "error": "campaignId required"}), 400
    if not asset_ids or not isinstance(asset_ids, list):
        return jsonify({"ok": False, "error": "assetIds[] required"}), 400

    data = load_data()
    campaigns = data.get("campaigns", {})
    if campaign_id not in campaigns:
        return jsonify({"ok": False, "error": "Campaign not found"}), 404
    campaign = campaigns[campaign_id]
    assets = campaign.get("assets", {})
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    approved = 0
    failed = []
    for aid in asset_ids:
        if aid not in assets:
            failed.append({"assetId": aid, "reason": "not found"})
            continue
        a = assets[aid]
        if a.get('approvalStatus') == 'approved':
            continue  # already approved — no-op
        a['approvalStatus'] = 'approved'
        a['updatedAt'] = now
        a['reviewTs'] = now
        history = a.get('history') or []
        history.append({
            "action": "bulk-approve",
            "by": "campaign-workview",
            "at": now,
            "note": f"Bulk-approve from campaign work-view ({len(asset_ids)} assets)",
        })
        a['history'] = history
        approved += 1
    campaign['updatedAt'] = now
    save_data(data)
    ok, msg = git_push(f"Campaign OS v0.1: bulk-approve {approved} assets in '{campaign_id}'")
    response = {"ok": True, "approved": approved, "failed": failed, "total": len(asset_ids)}
    if not ok:
        response["_syncWarning"] = f"GitHub sync failed: {msg}. Data is saved on server."
    return jsonify(response)

# ─── INLINE ASSET EDIT ──────────────────────────────────────────────────
ALLOWED_INLINE_FIELDS = {
    'caption', 'visualBrief', 'imagePrompt', 'imageUrl',
    'hookText', 'headline', 'cta', 'hashtags', 'platform',
    'pillar', 'pillarName', 'name', 'notes', 'scheduledFor',
}


@app.route('/api/assets/<asset_id>', methods=['PATCH', 'PUT'])
def edit_asset_inline(asset_id):
    """Inline edit an asset's editable fields without touching approval state.

    Body: { campaignId, <field>: <value>, ... }
    Editable fields: caption, visualBrief, imagePrompt, imageUrl, hookText,
    headline, cta, hashtags, platform, pillar, pillarName, name, notes,
    scheduledFor.

    Does NOT mutate approvalStatus, reviewTs, or publishingReferences — those
    flow through /api/review/<asset_id> and the asset state engine.
    """
    body = request.get_json(silent=True) or {}
    campaign_id = body.get('campaignId')
    if not campaign_id:
        return jsonify({"error": "campaignId required"}), 400

    data = load_data()
    campaigns = data.get("campaigns", {})
    if campaign_id not in campaigns:
        return jsonify({"error": "Campaign not found"}), 404
    campaign = campaigns[campaign_id]
    assets = campaign.get("assets", {})
    if asset_id not in assets:
        return jsonify({"error": "Asset not found"}), 404

    asset = assets[asset_id]
    now = _now_iso()
    changes = []
    rejected = []

    for key, value in body.items():
        if key == 'campaignId':
            continue
        if key not in ALLOWED_INLINE_FIELDS:
            rejected.append(key)
            continue
        if key == 'scheduledFor':
            try:
                value = _normalise_schedule_datetime(value)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        # Normalise hashtags into a list of clean tokens
        if key == 'hashtags' and isinstance(value, str):
            value = [h.strip().lstrip('#') for h in re.split(r'[,\s#]+', value) if h.strip()]
        # Snapshot the prior caption as aiDraft the FIRST time it changes.
        # This is what powers the Review-queue "↺ Reset to AI draft" button —
        # the original generation that the user (or the generation pipeline)
        # saved before any hand-edits. Idempotent: only sets it once.
        if (key == 'caption'
                and 'aiDraft' not in asset
                and asset.get('caption')
                and asset.get('caption') != value):
            asset['aiDraft'] = asset.get('caption')
            asset['aiDraftSetAt'] = now
            asset['aiDraftSource'] = 'inline-edit-first-change'
        # Don't no-op — record what actually changed
        if asset.get(key) != value:
            changes.append({"field": key, "old": asset.get(key), "new": value})
        asset[key] = value

    if not changes and not rejected:
        return jsonify({"ok": True, "assetId": asset_id, "asset": asset,
                        "message": "no changes", "changes": []}), 200

    asset['updatedAt'] = now
    campaign['updatedAt'] = now
    history = asset.setdefault('history', [])
    history.append({
        "event": "inline-edit",
        "ts": now,
        "actor": body.get('updatedBy') or 'human',
        "fields": [c['field'] for c in changes],
    })
    save_data(data)

    ok, msg = git_push(
        f"Campaign OS v0.1: Inline edit '{asset.get('name', asset_id)}' "
        f"({len(changes)} field{'s' if len(changes)!=1 else ''})"
    )
    response = {
        "ok": True,
        "assetId": asset_id,
        "campaignId": campaign_id,
        "asset": asset,
        "changes": changes,
        "rejectedFields": rejected,
    }
    if not ok:
        response["_syncWarning"] = f"GitHub sync failed: {msg}. Data is saved on server."
    return jsonify(response)


@app.route('/api/assets/<asset_id>/history', methods=['GET'])
def asset_history(asset_id):
    """Return the asset's edit history (created → review → publish → edit)."""
    campaign_id = request.args.get('campaignId')
    data = load_data()
    campaigns = data.get("campaigns", {})
    target_asset = None
    target_campaign = None
    if campaign_id and campaign_id in campaigns and asset_id in campaigns[campaign_id].get('assets', {}):
        target_asset = campaigns[campaign_id]['assets'][asset_id]
        target_campaign = campaign_id
    else:
        for cid, c in campaigns.items():
            if asset_id in c.get('assets', {}):
                target_asset = c['assets'][asset_id]
                target_campaign = cid
                break
    if not target_asset:
        return jsonify({"error": "Asset not found"}), 404
    history = target_asset.get('history', []) or []
    publishing_refs = target_asset.get('publishingReferences', []) or []
    return jsonify({
        "ok": True,
        "assetId": asset_id,
        "campaignId": target_campaign,
        "history": history,
        "publishingReferences": publishing_refs,
        "historyTotal": len(history),
        "refsTotal": len(publishing_refs),
    })


@app.route('/api/assets/<asset_id>/ai-draft', methods=['GET'])
def asset_ai_draft(asset_id):
    """Return the original AI-generated caption for an asset (powers the
    Review-queue "↺ Reset to AI draft" button).

    Looks at `asset.aiDraft` (set on the first save that overwrites the
    caption, via PATCH /api/assets/<aid> or POST /api/review/<aid>).
    If no snapshot exists yet, walks the asset's `history` for the
    earliest "inline-edit" or "review-decision" event involving a
    caption change and returns the asset's caption value at that
    moment (best-effort reconstruction).

    Query: campaignId (optional — auto-discovered if omitted)

    Returns: {ok, assetId, campaignId, caption, source, ts, _reason?}
      source: "aiDraftField" | "history" | "none"
      404 if the asset doesn't exist anywhere
      200 with caption=null + source=none if no AI draft is recoverable
    """
    campaign_id = request.args.get('campaignId')
    data = load_data()
    campaigns = data.get("campaigns", {})
    target_asset = None
    target_campaign = None
    if campaign_id and campaign_id in campaigns and asset_id in campaigns[campaign_id].get('assets', {}):
        target_asset = campaigns[campaign_id]['assets'][asset_id]
        target_campaign = campaign_id
    else:
        for cid, c in campaigns.items():
            if asset_id in c.get('assets', {}):
                target_asset = c['assets'][asset_id]
                target_campaign = cid
                break
    if not target_asset:
        return jsonify({"error": "Asset not found"}), 404

    # Path 1: explicit aiDraft field (set by the PATCH/POST snapshot logic)
    if target_asset.get('aiDraft'):
        return jsonify({
            "ok": True,
            "assetId": asset_id,
            "campaignId": target_campaign,
            "caption": target_asset['aiDraft'],
            "source": "aiDraftField",
            "ts": target_asset.get('aiDraftSetAt'),
            "_note": target_asset.get('aiDraftSource'),
        }), 200

    # Path 2: best-effort history walk. The history event doesn't carry
    # the prior caption value (only the field list), so we can only
    # acknowledge that a history trail exists and ask the user to either
    # generate a fresh draft via the caption studio or pick a variant.
    history = target_asset.get('history', []) or []
    has_caption_history = any(
        isinstance(e, dict) and 'caption' in (e.get('fields') or [])
        for e in history
    )
    if has_caption_history:
        return jsonify({
            "ok": True,
            "assetId": asset_id,
            "campaignId": target_campaign,
            "caption": None,
            "source": "none",
            "ts": None,
            "_reason": "history_present_but_no_snapshot",
            "_hint": "Edit + save the caption once · the original is captured. Or generate a fresh caption variant in the Caption Studio.",
        }), 200

    # Path 3: brand new asset, never edited. The current caption IS the draft.
    if target_asset.get('caption'):
        return jsonify({
            "ok": True,
            "assetId": asset_id,
            "campaignId": target_campaign,
            "caption": target_asset['caption'],
            "source": "current",
            "ts": target_asset.get('updatedAt') or target_asset.get('createdAt'),
            "_note": "asset_never_edited_returning_current",
        }), 200

    return jsonify({
        "ok": True,
        "assetId": asset_id,
        "campaignId": target_campaign,
        "caption": None,
        "source": "none",
        "ts": None,
        "_reason": "no_caption_ever_set",
    }), 200


@app.route('/api/export/<campaign_id>', methods=['GET'])
def export_review(campaign_id):
    """Export all review decisions for a campaign."""
    data = load_data()
    campaigns = data.get("campaigns", {})
    if campaign_id not in campaigns:
        return jsonify({"error": "Campaign not found"}), 404

    campaign = campaigns[campaign_id]
    decisions = {}
    for aid, asset in campaign.get("assets", {}).items():
        if asset.get('approvalStatus') in ('approved', 'rejected', 'revisionRequested'):
            decisions[aid] = {
                "approvalStatus": asset.get('approvalStatus'),
                "caption": asset.get('caption'),
                "visualBrief": asset.get('visualBrief'),
                "rejectionReason": asset.get('rejectionReason'),
                "revisionRequest": asset.get('revisionRequest'),
                "assignedLane": asset.get('assignedLane'),
                "reviewTs": asset.get('reviewTs'),
                "updatedAt": asset.get('updatedAt')
            }

    return jsonify({
        "campaignId": campaign_id,
        "exportedAt": datetime.datetime.utcnow().isoformat() + 'Z',
        "reviewDecisions": decisions
    })

# ─── CALENDAR SCHEDULING ────────────────────────────────────────────────

@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    """Return the publisher-compatible scheduling sidecar."""
    return jsonify({"ok": True, **_schedule_response(load_schedule())}), 200


# ─── REVIEW UPLOAD + PUSH-TO-POSTIZ (added 2026-08-04 polish pass) ────
ASSET_MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'asset-media')
os.makedirs(ASSET_MEDIA_DIR, exist_ok=True)


def _update_asset_field(asset_id, campaign_id, field, value):
    """Mutate a single asset field via the same campaign loader the review queue uses.
    Tries campaigns/<cid>/assets.json first, falls back to legacy review-queue.json.
    Returns True if the asset was located and updated."""
    try:
        # Path A: campaign assets.json (the new canonical store)
        if campaign_id:
            cpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'campaigns', campaign_id, 'assets.json')
            if os.path.exists(cpath):
                with open(cpath, 'r', encoding='utf-8') as f:
                    doc = json.load(f)
                assets = doc.get('assets') if isinstance(doc, dict) else doc
                if isinstance(assets, dict) and asset_id in assets:
                    assets[asset_id][field] = value
                    with open(cpath, 'w', encoding='utf-8') as f:
                        json.dump(doc, f, indent=2, ensure_ascii=False)
                    return True
        # Path B: review-queue.json (legacy)
        qpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'review-queue.json')
        if os.path.exists(qpath):
            with open(qpath, 'r', encoding='utf-8') as f:
                doc = json.load(f)
            # Try several shapes
            for key in ('queue', 'assets', 'items'):
                container = doc.get(key) if isinstance(doc, dict) else None
                if isinstance(container, dict) and asset_id in container:
                    container[asset_id][field] = value
                    with open(qpath, 'w', encoding='utf-8') as f:
                        json.dump(doc, f, indent=2, ensure_ascii=False)
                    return True
                if isinstance(container, list):
                    for entry in container:
                        if isinstance(entry, dict) and (entry.get('assetId') == asset_id or entry.get('id') == asset_id):
                            entry[field] = value
                            with open(qpath, 'w', encoding='utf-8') as f:
                                json.dump(doc, f, indent=2, ensure_ascii=False)
                            return True
    except Exception as exc:
        _app_log.warning("asset field update failed for %s.%s = %s: %s", asset_id, field, value, exc)
    return False


@app.route('/api/review/<asset_id>/upload', methods=['POST'])
def review_upload(asset_id):
    """Upload an image for an asset (multipart form). Saves to data/asset-media/ and
    updates the asset's visualUrl so Postiz picks it up on push."""
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "no file in form"}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "empty file"}), 400
    safe = secure_filename(f.filename) or f"upload-{asset_id}.bin"
    # Disambiguate by prepending asset id so two assets don't collide.
    out_name = f"{secure_filename(asset_id)}-{int(time.time())}-{safe}"
    out_path = os.path.join(ASSET_MEDIA_DIR, out_name)
    try:
        f.save(out_path)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"save failed: {exc}"}), 500
    # Build a public URL that the browser can fetch. The asset-media dir is served by
    # the catch-all route registered later (see _asset_media_serve below).
    public_url = f"/asset-media/{out_name}"
    campaign_id = request.form.get('campaignId') or request.form.get('campaign_id') or ''
    ok = _update_asset_field(asset_id, campaign_id, 'visualUrl', public_url)
    return jsonify({"ok": True, "assetId": asset_id, "visualUrl": public_url,
                    "storedAs": out_name, "size": os.path.getsize(out_path),
                    "assetUpdated": ok}), 200


@app.route('/asset-media/<path:filename>', methods=['GET'])
def _asset_media_serve(filename):
    """Serve uploaded asset images. Kept separate from /static so the uploads dir
    never gets clobbered by deploys. Returns 404 (not 500) when the file is gone."""
    safe = secure_filename(filename)
    if not safe or '..' in filename or '/' in filename:
        return jsonify({"ok": False, "error": "bad filename"}), 400
    full = os.path.join(ASSET_MEDIA_DIR, safe)
    if not os.path.isfile(full):
        return jsonify({"ok": False, "error": "not found"}), 404
    return send_from_directory(ASSET_MEDIA_DIR, safe)


@app.route('/api/review/<asset_id>/schedule', methods=['POST'])
def review_push_postiz(asset_id):
    """Push the asset's caption + visual to Postiz as a draft. Records the Postiz id
    back onto the asset so subsequent renders show an Open-in-Postiz link."""
    body = request.get_json(silent=True) or {}
    campaign_id = body.get('campaignId') or body.get('campaign_id')
    # Load asset to get caption + visual (inline loader — _load_campaign is in _lib)
    caption = ''
    visual_url = ''
    platform = 'instagram'
    try:
        if campaign_id:
            # Lazy import to avoid circular refs at module load.
            try:
                from _lib.intelligence import _load_campaign as __lc  # type: ignore
                c = __lc(campaign_id)
            except Exception:
                c = None
            if not c:
                # Inline fallback loader.
                cpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'data', 'campaigns', campaign_id, 'assets.json')
                if os.path.exists(cpath):
                    with open(cpath, 'r', encoding='utf-8') as _f:
                        c = json.load(_f)
            a = (c.get('assets') or {}).get(asset_id) if c else None
            if a:
                caption = a.get('caption') or ''
                visual_url = a.get('visualUrl') or a.get('imageUrl') or ''
                platform = a.get('platform') or a.get('integration') or platform
    except Exception as exc:
        _app_log.warning("review_push_postiz: load asset failed: %s", exc)
    if not caption:
        return jsonify({"ok": False, "error": "no caption on asset"}), 400
    # Push to Postiz (reuse the same publish helper the auto-publisher uses).
    postiz_id = None
    err = None
    try:
        from _lib.postiz_client import postiz_create_post  # late import — module optional
        media = [visual_url] if visual_url else []
        result = postiz_create_post(caption=caption, media=media, platform=platform)
        postiz_id = result.get('id') or result.get('postizId') if isinstance(result, dict) else None
    except Exception as exc:
        err = str(exc)
    if not postiz_id:
        # Fallback: try the legacy helper if the new one failed/missing.
        try:
            from _lib.publisher import push_draft  # type: ignore
            postiz_id = push_draft(asset_id=asset_id, campaign_id=campaign_id,
                                    caption=caption, media=[visual_url] if visual_url else [],
                                    platform=platform)
        except Exception as exc2:
            err = (err + " | " if err else "") + str(exc2)
    if not postiz_id:
        return jsonify({"ok": False, "error": f"postiz push failed: {err or 'no postiz client'}"}), 502
    # Record back onto the asset
    refs_update = [{"postizId": postiz_id, "platform": platform, "publishStatus": "draft"}]
    _update_asset_field(asset_id, campaign_id, 'publishingReferences', refs_update)
    _update_asset_field(asset_id, campaign_id, 'publishStatus', 'draft')
    return jsonify({"ok": True, "assetId": asset_id, "postizId": postiz_id, "platform": platform}), 200


# ─── GMB DRAFTS CRUD (added 2026-08-04 polish pass) ──────────────────
GMB_DRAFTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'gmb-drafts')
os.makedirs(GMB_DRAFTS_DIR, exist_ok=True)


def _gmb_draft_path(draft_id):
    # draft_id is a slugified string — defend against path traversal.
    safe = secure_filename(draft_id) or ''
    if not safe or '..' in draft_id or '/' in draft_id:
        return None
    return os.path.join(GMB_DRAFTS_DIR, f"{safe}.json")


def _gmb_list_drafts():
    out = []
    if not os.path.isdir(GMB_DRAFTS_DIR):
        return out
    for fn in sorted(os.listdir(GMB_DRAFTS_DIR)):
        if not fn.endswith('.json'):
            continue
        path = os.path.join(GMB_DRAFTS_DIR, fn)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            d['id'] = fn[:-5]
            out.append(d)
        except Exception:
            continue
    return out


@app.route('/api/intel/gmb/drafts', methods=['GET'])
def gmb_list_drafts():
    """List all GMB draft posts (templates + manual drafts)."""
    drafts = _gmb_list_drafts()
    return jsonify({"ok": True, "drafts": drafts, "count": len(drafts)}), 200


@app.route('/api/intel/gmb/drafts', methods=['POST'])
def gmb_create_draft():
    """Create a new GMB draft. Body: {title, body, cta, link, imageUrl}."""
    body = request.get_json(silent=True) or {}
    title = (body.get('title') or '').strip()[:100] or 'Untitled GMB post'
    body_text = (body.get('body') or '').strip()[:1500]
    cta = (body.get('cta') or '').strip()[:40]
    link = (body.get('link') or '').strip()[:300]
    image_url = (body.get('imageUrl') or '').strip()[:500]
    brand = (body.get('brand') or get_brand_id() or 'swing-shack').strip()
    slug = secure_filename(title.lower().replace(' ', '-'))[:40] or 'draft'
    draft_id = f"{slug}-{int(time.time())}"
    draft = {
        "id": draft_id,
        "title": title,
        "body": body_text,
        "cta": cta,
        "link": link,
        "imageUrl": image_url,
        "brand": brand,
        "status": "draft",
        "createdAt": _now_iso(),
        "updatedAt": _now_iso(),
    }
    path = _gmb_draft_path(draft_id)
    if not path:
        return jsonify({"ok": False, "error": "bad draft id"}), 400
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)
    return jsonify({"ok": True, "draft": draft}), 201


@app.route('/api/intel/gmb/draft/<draft_id>', methods=['PUT'])
def gmb_edit_draft(draft_id):
    """Edit an existing GMB draft."""
    path = _gmb_draft_path(draft_id)
    if not path or not os.path.exists(path):
        return jsonify({"ok": False, "error": "draft not found"}), 404
    try:
        with open(path, 'r', encoding='utf-8') as f:
            draft = json.load(f)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"read failed: {exc}"}), 500
    body = request.get_json(silent=True) or {}
    for field in ('title', 'body', 'cta', 'link', 'imageUrl', 'status'):
        if field in body:
            draft[field] = body[field]
    draft['updatedAt'] = _now_iso()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)
    return jsonify({"ok": True, "draft": draft}), 200


@app.route('/api/intel/gmb/draft/<draft_id>/schedule', methods=['POST'])
def gmb_schedule_draft(draft_id):
    """Push the draft to Postiz as a GMB-platform post and mark scheduled."""
    path = _gmb_draft_path(draft_id)
    if not path or not os.path.exists(path):
        return jsonify({"ok": False, "error": "draft not found"}), 404
    try:
        with open(path, 'r', encoding='utf-8') as f:
            draft = json.load(f)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"read failed: {exc}"}), 500
    postiz_id = None
    err = None
    try:
        from _lib.postiz_client import postiz_create_post
        text = draft.get('body') or draft.get('title') or ''
        media = [draft['imageUrl']] if draft.get('imageUrl') else []
        result = postiz_create_post(caption=text, media=media, platform='gmb')
        postiz_id = result.get('id') or result.get('postizId') if isinstance(result, dict) else None
    except Exception as exc:
        err = str(exc)
    if not postiz_id:
        try:
            from _lib.publisher import push_draft  # type: ignore
            postiz_id = push_draft(asset_id=draft_id, campaign_id=draft.get('brand'),
                                    caption=draft.get('body') or draft.get('title', ''),
                                    media=[draft['imageUrl']] if draft.get('imageUrl') else [],
                                    platform='gmb')
        except Exception as exc2:
            err = (err + " | " if err else "") + str(exc2)
    if not postiz_id:
        return jsonify({"ok": False, "error": f"postiz push failed: {err or 'no postiz client'}"}), 502
    draft['postizId'] = postiz_id
    draft['status'] = 'scheduled'
    draft['updatedAt'] = _now_iso()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)
    return jsonify({"ok": True, "draft": draft, "postizId": postiz_id}), 200


@app.route('/api/intel/gmb/draft/<draft_id>', methods=['DELETE'])
def gmb_delete_draft(draft_id):
    """Delete a GMB draft."""
    path = _gmb_draft_path(draft_id)
    if not path or not os.path.exists(path):
        return jsonify({"ok": False, "error": "draft not found"}), 404
    try:
        os.remove(path)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"delete failed: {exc}"}), 500
    return jsonify({"ok": True, "deleted": draft_id}), 200

@app.route('/api/review/<asset_id>/schedule-now', methods=['POST'])
def review_schedule_now(asset_id):
    """Approve AND schedule an asset in one click — finds the next empty
    calendar slot and assigns it. Returns the scheduled datetime."""
    body = request.get_json(silent=True) or {}
    campaign_id = body.get('campaignId') or body.get('campaign_id')

    # First, set approvalStatus=approved on the asset (no-op if already approved)
    data = load_data()
    campaigns = data.get("campaigns", {})
    asset = None
    if campaign_id and campaign_id in campaigns:
        asset = campaigns[campaign_id].get("assets", {}).get(asset_id)
    if asset is None and campaign_id is None:
        # try to find the asset across all campaigns
        for cid, c in campaigns.items():
            if asset_id in (c.get("assets") or {}):
                asset = c["assets"][asset_id]
                campaign_id = cid
                break

    if asset is not None:
        asset['approvalStatus'] = 'approved'
        asset['updatedAt'] = datetime.datetime.utcnow().isoformat() + 'Z'
        campaigns.setdefault(campaign_id, {}) if not campaign_id else None  # noop
        data['campaigns'] = campaigns
        save_data(data)

    # Now compute the next empty slot in the next 14 days (target ≤ 4 per day)
    target = _schedule_target(asset_id, campaign_id)
    if not target:
        return jsonify({"ok": False, "error": "Asset or queue item not found"}), 404

    manifest = load_schedule()
    scheduled = manifest.get('scheduled', [])

    # Count per day (UTC date string YYYY-MM-DD)
    from collections import Counter
    day_counts = Counter()
    for it in scheduled:
        sf = it.get('scheduledFor') or ''
        if isinstance(sf, str) and len(sf) >= 10:
            day_counts[sf[:10]] += 1

    # Find next day with < 4 items, starting tomorrow
    today = datetime.date.today()
    chosen_day = None
    for offset in range(1, 15):
        d = today + datetime.timedelta(days=offset)
        if day_counts.get(d.isoformat(), 0) < 4:
            chosen_day = d
            break
    if not chosen_day:
        chosen_day = today + datetime.timedelta(days=14)

    # Pick a posting hour: stagger by 9am/12pm/3pm/6pm to spread
    hour_options = [9, 12, 15, 18]
    hour = hour_options[day_counts.get(chosen_day.isoformat(), 0) % 4]
    scheduled_for = datetime.datetime.combine(chosen_day, datetime.time(hour=hour, minute=0)).isoformat() + 'Z'

    previous = _manifest_entry(manifest, asset_id)
    previous_for = (previous or {}).get('scheduledFor')
    item = _upsert_schedule_entry(
        manifest, target, scheduled_for,
        platform=(asset or {}).get('platform') if asset else None,
        extra={"updatedBy": "review-schedule-now"},
    )
    saved = save_schedule(manifest)

    return jsonify({
        "ok": True, "assetId": asset_id, "campaignId": target.get('campaignId'),
        "source": target.get('source'), "scheduledFor": item['scheduledFor'],
        "previousScheduledFor": previous_for, "schedule": _schedule_response(saved),
        "rationale": f"Next empty slot · {chosen_day.isoformat()} at {hour:02d}:00 UTC",
    }), 200


@app.route('/api/schedule/<asset_id>', methods=['POST'])
def schedule_asset(asset_id):
    """Schedule/reschedule an asset or publisher queue item in the sidecar."""
    body = request.get_json(silent=True) or {}
    campaign_id = body.get('campaignId') or body.get('campaign_id')
    target = _schedule_target(asset_id, campaign_id)
    if not target:
        return jsonify({"ok": False, "error": "Asset or queue item not found"}), 404
    try:
        scheduled_for = _schedule_datetime_from_body(body)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    manifest = load_schedule()
    previous = _manifest_entry(manifest, asset_id)
    previous_for = (previous or {}).get('scheduledFor')
    item = _upsert_schedule_entry(
        manifest, target, scheduled_for, platform=body.get('platform'),
        extra={"updatedBy": body.get('updatedBy', 'calendar')},
    )
    saved = save_schedule(manifest)
    return jsonify({
        "ok": True, "assetId": asset_id, "campaignId": target.get('campaignId'),
        "source": target.get('source'), "scheduledFor": item['scheduledFor'],
        "previousScheduledFor": previous_for, "schedule": _schedule_response(saved),
    }), 200

@app.route('/api/schedule/<asset_id>/duplicate', methods=['POST'])
def duplicate_scheduled_asset(asset_id):
    """Create a scheduled copy without invoking Postiz."""
    body = request.get_json(silent=True) or {}
    campaign_id = body.get('campaignId') or body.get('campaign_id')
    target = _schedule_target(asset_id, campaign_id)
    if not target:
        return jsonify({"ok": False, "error": "Asset or queue item not found"}), 404
    try:
        scheduled_for = _schedule_datetime_from_body(body)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    new_asset_id = f"{asset_id}-copy-{uuid.uuid4().hex[:8]}"
    now = _now_iso()
    new_target = dict(target)
    new_target.update({
        'assetId': new_asset_id,
        'name': body.get('newName') or f"Copy · {target.get('name') or asset_id}",
        'source': 'calendar',
    })

    if target.get('source') == 'campaign' and target.get('campaign') is not None:
        data = load_data()
        campaign = (data.get('campaigns') or {}).get(target['campaignId'])
        source_asset = ((campaign or {}).get('assets') or {}).get(asset_id)
        if not campaign or not source_asset:
            return jsonify({"ok": False, "error": "Campaign asset disappeared; retry"}), 409
        copied = copy.deepcopy(source_asset)
        copied.update({
            'assetId': new_asset_id, 'campaignId': target['campaignId'],
            'name': new_target['name'], 'approvalStatus': 'draft', 'approvalState': 'draft',
            'publishStatus': 'planned', 'status': 'draft',
            'scheduledFor': scheduled_for, 'publishDate': scheduled_for,
            'createdAt': now, 'updatedAt': now, 'reviewTs': None,
            'publishingReferences': [],
            'history': [{"event": "duplicated", "fromAssetId": asset_id, "at": now}],
        })
        campaign.setdefault('assets', {})[new_asset_id] = copied
        campaign['updatedAt'] = now
        data['updatedAt'] = now
        save_data(data)
        new_target.update({'asset': copied, 'caption': copied.get('caption', ''),
                           'platform': copied.get('platform') or target.get('platform')})
        new_asset = copied
        duplicate_mode = 'campaign-asset'
    else:
        new_target.update({'caption': target.get('caption', ''), 'platform': target.get('platform') or 'instagram'})
        new_asset = {
            'assetId': new_asset_id, 'campaignId': target.get('campaignId'),
            'name': new_target['name'], 'caption': new_target['caption'],
            'platform': new_target['platform'], 'scheduledFor': scheduled_for,
            'publishStatus': 'planned', 'approvalStatus': 'draft',
            'duplicateOf': asset_id, 'createdAt': now,
        }
        duplicate_mode = 'calendar-sidecar'

    manifest = load_schedule()
    item = _upsert_schedule_entry(
        manifest, new_target, scheduled_for,
        platform=body.get('platform') or new_target.get('platform'),
        extra={'duplicateOf': asset_id, 'duplicateMode': duplicate_mode,
               'updatedBy': body.get('updatedBy', 'calendar')},
    )
    saved = save_schedule(manifest)
    return jsonify({
        "ok": True, "originalAssetId": asset_id, "newAssetId": new_asset_id,
        "campaignId": new_target.get('campaignId'), "source": duplicate_mode,
        "scheduledFor": item['scheduledFor'], "newAsset": new_asset,
        "schedule": _schedule_response(saved),
    }), 201

@app.route('/api/schedule/<asset_id>', methods=['DELETE'])
def unschedule_asset(asset_id):
    """Remove a sidecar schedule without deleting the asset."""
    manifest = load_schedule()
    before = len(manifest.get('scheduled', []))
    manifest['scheduled'] = [item for item in manifest.get('scheduled', []) if not _entry_matches(item, asset_id)]
    if len(manifest['scheduled']) == before:
        return jsonify({"ok": False, "error": "Schedule entry not found"}), 404
    saved = save_schedule(manifest)
    return jsonify({"ok": True, "assetId": asset_id, "schedule": _schedule_response(saved)}), 200

# ─── STATIC FILES ─────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'campaign-os.html')

@app.route('/home.html')
def home_alias():
    return send_from_directory('.', 'campaign-os.html')

@app.route('/cockpit-operational')
@app.route('/cockpit-operational.html')
@app.route('/cockpit.html')
def cockpit():
    """Operational Cockpit — live health + schedule + campaign + review snapshot."""
    return send_from_directory('.', 'cockpit-operational.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)

# ─── TRUTH COLLECTOR (Stage 4 — server-side only) ─────────────────────
# The Truth Collector ingests real analytics (GA4 + Meta) and writes
# append-only engagement history. It is the upstream of Stage 2 (evidencePack).
# It owns NO Learning truth. It does NOT modify campaign.memory.*.

try:
    import truth_collector as _tc_module
    from truth_collector import (
        EngagementStore,
        truth_collector_ingest_publish_event,
        truth_collector_ingest_cron_tick,
        truth_collector_ingest_manual_trigger,
        truth_collector_write_engagement,
        truth_collector_get_engagement_history,
        ga4_credentials_present,
        meta_credentials_present,
        CredentialsMissingError,
    )
    _TRUTH_COLLECTOR_AVAILABLE = True
except ImportError as _tc_err:
    _app_log = logging.getLogger("app")
    _app_log.warning("Truth Collector module not available: %s", _tc_err)
    _TRUTH_COLLECTOR_AVAILABLE = False

try:
    from _lib import intelligence as _intel_module
    from _lib.intelligence import (
        INTELLIGENCE_FUNCS,
        morning_brief, calendar_view, review_inbox, hooks_view, memes_view,
        billboards_view, caption_studio, performance_view, learning_view,
        generate_hooks, generate_captions, generate_ctas, generate_headlines,
        generate_image,
        reddit_outreach, gbp_suggestions, seo_assistant, faq_generator,
        trend_catcher, opportunities_view, postiz_overview, assets_view,
        agents_view, explain_performance, universal_search,
        weekly_report,
    )
    _INTELLIGENCE_AVAILABLE = True
except ImportError as _intel_err:
    _app_log = logging.getLogger("app")
    _app_log.warning("Intelligence module not available: %s", _intel_err)
    _INTELLIGENCE_AVAILABLE = False

try:
    from _lib import campaign_planner as _planner_module
    from _lib.campaign_planner import PLANNER_FUNCS, plan_campaign, plan_portfolio
    _PLANNER_AVAILABLE = True
except ImportError as _planner_err:
    _app_log.warning("Campaign planner module not available: %s", _planner_err)
    _PLANNER_AVAILABLE = False


def _intel(name):
    """Run a named intelligence function; return JSON dict."""
    if not _INTELLIGENCE_AVAILABLE:
        return {"ok": False, "error": "Intelligence unavailable"}, 503
    fn = INTELLIGENCE_FUNCS.get(name)
    if not fn:
        return {"ok": False, "error": f"Unknown view: {name}"}, 404
    # Thread the active brand into the intel function so its data is brand-scoped
    bid = get_brand_id()
    try:
        _intel_module.set_request_brand(bid)
        if name == 'calendar':
            days = int(request.args.get('days', 14))
            start = request.args.get('start') or None
            result = _intel_module.calendar_view(days=days, start=start), 200
        else:
            result = fn(), 200
        return result
    except Exception as exc:
        _app_log.exception("Intel %s failed", name)
        return {"ok": False, "error": str(exc), "view": name}, 500
    finally:
        _intel_module.clear_request_brand()


@app.route('/api/intel/<name>', methods=['GET'])
def intel_dispatch(name):
    """GET /api/intel/<view-name> — see INTELLIGENCE_FUNCS for the index."""
    if name == 'trends_v2':
        return trends_v2()
    payload, status = _intel(name)
    return jsonify(payload), status


def _esc_html(s):
    """Minimal HTML escape. Use stdlib html.escape with quote=False so we
    don't over-escape apostrophes (they're fine inside text)."""
    from _lib.report_html import _esc_html as _impl
    return _impl(s)


def _render_weekly_report_html(data: dict, md_lines: list, brand: str = "") -> str:
    """Render the weekly report as a self-contained HTML page.

    Thin wrapper that delegates to `_lib.report_html.render_weekly_report_html`
    so the renderer lives in its own import-safe module (app.py triggers a
    `os.makedirs('/data')` at import time that breaks test imports).
    """
    from _lib.report_html import render_weekly_report_html as _impl
    return _impl(data, md_lines, brand)


@app.route('/api/intel/weekly_report/export', methods=['GET'])
def weekly_report_export():
    """GET /api/intel/weekly_report/export — markdown export of the weekly report.

    Returns the weekly report as markdown so it can be downloaded/printed
    or pasted into a Slack/email. Reads the same data as the JSON view.

    Auth: either a valid session cookie OR a valid `?share=<token>` query
    param (minted via /api/intel/weekly_report/share). The share path is
    how recipients get a no-login link. see _verify_share_token().
    """
    # v2026-08-13: accept signed share token as an auth bypass for this
    # specific endpoint. The gate() before_request hook handles cookie
    # auth; we only need to short-circuit when a valid share token is
    # presented AND the cookie auth is missing.
    if not _is_authed():
        share_token = request.args.get("share", "")
        if not _verify_share_token(share_token):
            # Re-raise the standard auth failure so the gate() runs
            # again. actually, the gate has already let us through
            # because we got here. So we manually return the 401.
            return jsonify({"ok": False, "error": "authentication required"}), 401
    if not _INTELLIGENCE_AVAILABLE or weekly_report is None:
        return jsonify({"ok": False, "error": "Intelligence module unavailable"}), 503
    try:
        _intel_module.set_request_brand(get_brand_id())
        data = weekly_report(brand=get_brand_id())
        kpis = data.get("headline_kpis", {})
        wow = data.get("week_on_week", {})

        md_lines = [
            f"# Weekly Marketing Report · {data.get('week_start', '?')[:10]} to {data.get('week_end', '?')[:10]}",
            "",
            f"**Brand:** {data.get('brand') or 'all'}",
            "",
            f"**Window:** {data.get('window_label') or 'rolling 7d'}",
        ]
        if data.get('window_used') == 'last_publish_window_fallback':
            md_lines.append("")
            md_lines.append(f"> ⚠️ **{data.get('window_note', 'rest-mode fallback active')}**")
        md_lines.extend([
            "",
            "## Headline",
            f"- {data.get('headline', '')}",
            "",
            "## Numbers",
            f"- **Published:** {kpis.get('published', 0)}",
            f"- **Failed:** {kpis.get('failed', 0)}",
            f"- **Win rate:** {kpis.get('win_rate_pct') if kpis.get('win_rate_pct') is not None else '—'}",
            f"- **Agent runs:** {kpis.get('agent_runs', 0)}",
            f"- **Agent pass rate:** {kpis.get('agent_pass_rate_pct') if kpis.get('agent_pass_rate_pct') is not None else '—'}",
            "",
        ])



        # Platforms
        platforms = data.get("platforms") or {}
        if platforms:
            md_lines.append("## Platforms")
            for plat, cnt in sorted(platforms.items(), key=lambda x: -x[1]):
                md_lines.append(f"- **{plat}:** {cnt}")
            md_lines.append("")

        # By day
        by_day = data.get("by_day") or {}
        if any(by_day.values()):
            md_lines.append("## By day")
            for day, cnt in by_day.items():
                if cnt:
                    md_lines.append(f"- **{day}:** {cnt}")
            md_lines.append("")

        # Top hooks
        top_hooks = data.get("top_hooks") or []
        if top_hooks:
            md_lines.append("## Top hooks used")
            for h in top_hooks:
                text = h.get("text") or h.get("hook_id")
                md_lines.append(f"- {text} ({h.get('uses', 0)} uses)")
            md_lines.append("")

        # Top CTAs
        top_ctas = data.get("top_ctas") or []
        if top_ctas:
            md_lines.append("## Top CTAs")
            for c in top_ctas:
                md_lines.append(f"- {c.get('cta', '')} ({c.get('uses', 0)} uses)")
            md_lines.append("")

        # SEO movers
        movers = data.get("seo_movers") or []
        if movers:
            md_lines.append("## SEO movers")
            for m in movers:
                direction = m.get("direction", "")
                arrow = "↑" if direction == "rising" else "↓" if direction == "falling" else "·"
                rank = m.get("rank")
                rank_str = f" (rank {rank})" if rank is not None else ""
                md_lines.append(f"- {arrow} {m.get('keyword', '')}{rank_str}")
            md_lines.append("")

        # Failures
        failures = data.get("failures") or []
        if failures:
            md_lines.append("## Failures")
            for f in failures:
                md_lines.append(f"- {f.get('item_id', '?')} · {f.get('reason', 'no reason')}")
            md_lines.append("")

        # Agent breakdown
        agent_breakdown = data.get("agent_breakdown") or {}
        if agent_breakdown:
            md_lines.append("## Agents")
            for aid, summary in sorted(agent_breakdown.items()):
                md_lines.append(f"- **{aid}** · {summary.get('total', 0)} runs, {summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed ({summary.get('pass_rate_pct')}% pass)")
            md_lines.append("")

        # WoW
        md_lines.append("## Week-on-week")
        for k, v in wow.items():
            curr = v.get("current")
            prev = v.get("previous")
            pct = v.get("pct_change")
            curr_str = "—" if curr is None else (f"{curr}%" if "rate" in k else str(curr))
            prev_str = "—" if prev is None else (f"{prev}%" if "rate" in k else str(prev))
            pct_str = f" ({'+' if pct and pct > 0 else ''}{pct}%)" if pct is not None else ""
            md_lines.append(f"- **{k}:** {curr_str} (prev: {prev_str}){pct_str}")
        md_lines.append("")

        # ── Interpretation: What's working / what's not / look at ─────
        interp = data.get("interpretation") or {}
        if interp:
            sources_used = interp.get("sources_used") or []
            if sources_used:
                md_lines.append(f"### Sources read ({len(sources_used)})")
                md_lines.append(", ".join(f"`{s}`" for s in sources_used))
                md_lines.append("")

            md_lines.append("## What's working")
            for w in interp.get("whats_working", []):
                claim = w.get("claim", "")
                evid = w.get("evidence", "")
                cat = w.get("category", "")
                src = w.get("source") or "—"
                md_lines.append(f"- **{claim}** _(category: {cat}, source: `{src}`)_\n  - {evid}")
            md_lines.append("")

            md_lines.append("## What's not working")
            for w in interp.get("whats_not", []):
                claim = w.get("claim", "")
                evid = w.get("evidence", "")
                sev = w.get("severity", "low")
                sev_badge = "🛑" if sev == "high" else "⚠️" if sev == "medium" else "•"
                src = w.get("source") or "—"
                md_lines.append(f"- {sev_badge} **{claim}** _(severity: {sev}, source: `{src}`)_\n  - {evid}")
            md_lines.append("")

            md_lines.append("## Look at")
            for w in interp.get("look_at", []):
                claim = w.get("claim", "")
                evid = w.get("evidence", "")
                src = w.get("source") or "—"
                md_lines.append(f"- ? **{claim}** _(source: `{src}`)_\n  - {evid}")
            md_lines.append("")

            headline_take = interp.get("headline_take", "")
            if headline_take:
                md_lines.append(f"> **Headline take:** {headline_take}")
                md_lines.append("")

        # ── NEW (v2026-08-04) Cross-source data sources section ──
        md_lines.append("## Data sources powering this report")
        igA = data.get("ig_analytics") or {}
        if igA.get("posts_in_window") is not None:
            t = igA.get("totals") or {}
            md_lines.append(f"- **Instagram (`ig-analytics.json`)** — {igA.get('posts_in_window', 0)} posts · reach={t.get('reach', 0)} · likes={t.get('likes', 0)} · saves={t.get('saves', 0)} · shares={t.get('shares', 0)} · comments={t.get('comments', 0)}")
            md_lines.append(f"  - hook_id overlap with published: {igA.get('hook_overlap_with_published', 0)}; in published but not in IG: {igA.get('hook_only_in_published', 0)}; in IG but not published: {igA.get('hook_only_in_ig', 0)}")
        ga4 = data.get("ga4") or {}
        if ga4.get("total_sessions") is not None:
            stale_tag = " ⚠️ STALE" if ga4.get("stale") else ""
            md_lines.append(f"- **GA4 (`ga4-metrics.json`)** — {ga4.get('total_sessions', 0):,} sessions · top source: **{ga4.get('top_source') or '?'}** ({ga4.get('top_source_sessions', 0)} sessions) · {ga4.get('sources_count', 0)} sources tracked · fetched: {(ga4.get('fetched_at') or 'never')[:10]}{stale_tag}")
        yt = data.get("youtube") or {}
        if yt.get("videos_found") is not None or yt.get("top_videos_count") is not None:
            themes_str = ", ".join(yt.get("active_themes", [])[:8]) or "none"
            md_lines.append(f"- **YouTube trends (`youtube-trends.json`)** — {yt.get('videos_found', 0)} videos found · top {yt.get('top_videos_count', 0)} · active themes: {themes_str}")
        red = data.get("reddit") or {}
        if red.get("opportunities_count") is not None:
            subs = ", ".join(f"{s['subreddit']}={s['count']}" for s in (red.get("top_subreddits") or []))
            md_lines.append(f"- **Reddit (`reddit-opportunities.json + reddit-replies.json`)** — {red.get('opportunities_count', 0)} opportunities · {red.get('replies_count', 0)} drafted replies · ready_for_qa (opps: {red.get('ready_for_qa', 0)}, replies: {red.get('replies_ready_for_qa', 0)}) · subs: {subs or '—'}")
        seo = data.get("seo_health") or {}
        if seo.get("keywords_total") is not None:
            fetcher_tag = " ⚠️ fetcher offline" if seo.get("needs_fetcher") else ""
            md_lines.append(f"- **SEO (`seo-rankings.json`)** — {seo.get('keywords_total', 0)} keywords · {seo.get('with_rank', 0)} have rank data · rising={seo.get('rising', 0)} falling={seo.get('falling', 0)} · freshness: {(seo.get('freshness') or 'never')[:10]}{fetcher_tag}")
        hbb = data.get("hook_bank_buckets") or {}
        if hbb:
            md_lines.append(f"- **Hook bank (`hook-bank.json`)** — proven_and_trending={hbb.get('proven_and_trending', 0)} · proven_only={hbb.get('proven_only', 0)} · trending_to_test={hbb.get('trending_to_test', 0)} · retire={hbb.get('retire', 0)}")
        hbm = data.get("hook_bank_mismatch") or {}
        if hbm:
            md_lines.append(f"  - ⚠️ **hook-bank mismatch:** {hbm.get('published_hook_ids_not_in_bank', 0)} of published hook_ids are NOT in hook-bank ({hbm.get('hook_bank_total_ids', 0)} bank entries). Bank regenerated independently of publish history.")
        md_lines.append("")

        # ── Visual insights: image corpus patterns + suggestions ───────
        vi = data.get("visual_insights") or {}
        if vi:
            corpus = vi.get("corpus") or {}
            n_parsed = corpus.get("n_parsed", 0)
            md_lines.append(f"## Visual insights (brand image corpus · {n_parsed} images)")
            lum = corpus.get("luminance") or {}
            if any(lum.values()):
                parts = [f"{k}: {v}" for k, v in lum.items() if v]
                md_lines.append(f"- **Luminance:** {', '.join(parts)}")
            palettes = corpus.get("top_palettes") or []
            if palettes:
                items = [f"`{p['hex']}` ({round(p['share']*100)}%)" for p in palettes[:5]]
                md_lines.append(f"- **Top palettes:** {' · '.join(items)}")
            moods = corpus.get("top_moods") or []
            if moods:
                items = [f"{m['mood']} ({m['count']})" for m in moods[:5]]
                md_lines.append(f"- **Moods:** {' · '.join(items)}")
            objs = corpus.get("top_objects") or []
            if objs:
                items = [f"{o['object']} ({o['count']})" for o in objs[:5]]
                md_lines.append(f"- **Subjects:** {' · '.join(items)}")
            brands = corpus.get("top_brands") or []
            if brands:
                items = [f"{b['brand']} ({b['count']})" for b in brands[:5]]
                md_lines.append(f"- **Brand mentions:** {' · '.join(items)}")
            rate = corpus.get("pass_rate_pct")
            if rate is not None:
                md_lines.append(f"- **Brand-canon compliance pass rate:** {rate}%")
            md_lines.append("")

            md_lines.append("### Visual insights to act on")
            for ins in vi.get("insight", []):
                claim = ins.get("claim", "")
                evid = ins.get("evidence", "")
                cat = ins.get("category", "")
                md_lines.append(f"- **{claim}** _(category: {cat})_\n  - {evid}")
            md_lines.append("")

        # ── Topic clusters: what's actually being said in the captions ──
        tc = data.get("ig_topic_clusters") or {}
        if tc:
            md_lines.append("## IG topic mix this week")
            primary = tc.get("primary_topic")
            buckets = tc.get("buckets") or []
            if buckets:
                items = [f"{b['topic']} ({b['count']})" for b in buckets]
                md_lines.append(f"- **Primary:** {primary} · **mix:** {', '.join(items)}")
                for b in buckets[:3]:
                    ex = b.get("examples") or []
                    if ex:
                        ex_text = " / ".join(f"'{e['preview'][:80]}…'" for e in ex[:2])
                        md_lines.append(f"  - _{b['topic']}_ ({b['count']}): {ex_text}")
                md_lines.append("")

        md = "\n".join(md_lines)

        # Persist to data/weekly-report.md for the next time someone reads it
        try:
            export_path = data.get("export_path")
            if export_path:
                os.makedirs(os.path.dirname(export_path), exist_ok=True)
                with open(export_path, "w", encoding="utf-8") as f:
                    f.write(md)
        except OSError as exc:
            _app_log.warning("weekly_report.md write failed: %s", exc)

        # v2026-08-13: sibling HTML format. ?format=html returns a
        # pretty self-contained page (inline CSS, no external deps) so
        # share recipients can open the link in a browser and read it
        # without markdown rendering. Same data, same share token, just
        # a different render. Default (?format=md or omitted) keeps the
        # existing markdown behaviour.
        fmt = (request.args.get("format") or "md").lower()
        if fmt == "html":
            html_body = _render_weekly_report_html(
                data=data,
                md_lines=md_lines,
                brand=get_brand_id(),
            )
            return Response(
                html_body,
                mimetype="text/html; charset=utf-8",
                headers={"Content-Disposition": "inline; filename=weekly-report.html"},
            )

        return Response(md, mimetype="text/markdown", headers={"Content-Disposition": "attachment; filename=weekly-report.md"})
    except Exception as exc:
        _app_log.exception("weekly_report_export failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        try:
            _intel_module.clear_request_brand()
        except Exception:
            pass


def _verify_share_token(token: str) -> bool:
    """Validate a signed share token for the weekly-report export.

    Tokens are minted via /api/intel/weekly_report/share and contain a
    payload like {"scope": "weekly_report_export", "v": 1}. They are
    signed with SESSION_SECRET (same key as the session cookie) and
    bound to SHARE_TOKEN_MAX_AGE. Once expired they cannot be re-minted.
    Christelle mints a new token if she wants to re-share.

    We check both the signature AND the scope to make sure the token
    was minted for THIS endpoint (defense in depth: a token for any
    other signed-cookie use case wouldn't accidentally unlock the
    export endpoint).
    """
    if not token:
        return False
    try:
        payload = _serializer.loads(token, max_age=SHARE_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(payload, dict) and payload.get("scope") == "weekly_report_export"


# v2026-08-13: signed share tokens for the markdown export.
#
# Why this exists: the Insights weekly report was previously auth-gated,
# which meant pasting a link into Slack or email forced the recipient to
# log in. For a marketing weekly recap that's a friction gap. the report
# contains zero secrets (no customer data, no credentials), it's just
# numbers + interpretations.
#
# Flow:
#   1. Authed user POSTs to /api/intel/weekly_report/share
#   2. Server mints a signed token (24h TTL) bound to "weekly_report_export"
#   3. Returns {"share_url": "https://...?share=<token>"}
#   4. Recipient hits that URL. if the token is valid AND unexpired,
#      the export endpoint serves the markdown without an auth check.
#
# The token is opaque, single-use-bound-to-scope, and time-limited.
# Recipients can't mutate or refresh; if the link expires, Christelle
# just mints a new one.
@app.route('/api/intel/weekly_report/share', methods=['POST'])
def weekly_report_share():
    """POST /api/intel/weekly_report/share. mint a signed share URL.

    Body (optional JSON):
        {"ttl_seconds": 86400}   # default 24h, max 7d

    Returns:
        {"ok": true, "share_url": "...", "expires_at": ISO8601, "ttl_seconds": N}

    Requires auth (the recipient of the share link does not need auth).
    """
    if not _is_authed():
        return jsonify({"ok": False, "error": "auth required to mint share links"}), 401
    try:
        body = request.get_json(silent=True) or {}
        ttl = int(body.get("ttl_seconds", SHARE_TOKEN_MAX_AGE))
        # Clamp TTL to [60s, 7d]. 7d is the practical ceiling. beyond
        # that, the data in the report is too stale to share anyway.
        ttl = max(60, min(ttl, 60 * 60 * 24 * 7))
        payload = {"scope": "weekly_report_export", "v": 1}
        token = _serializer.dumps(payload)
        # Use request.host_url so the share URL points at the same
        # host the user is currently on (works for both local dev and
        # Railway production deployments). host_url ends with `/`
        # (e.g. `https://app.example.com/`); strip it once, then ensure
        # exactly one `/` between host and path. Common pitfall: on
        # test clients request.host_url may be `http://localhost`
        # without a trailing slash. handle both shapes.
        host = request.host_url.rstrip("/")
        if not host.endswith("/"):
            host = host + ""
        share_url = f"{host}/api/intel/weekly_report/export?share={token}"
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=ttl)
        return jsonify({
            "ok": True,
            "share_url": share_url,
            "token": token,
            "expires_at": expires_at.isoformat(),
            "ttl_seconds": ttl,
        })
    except Exception as exc:
        _app_log.exception("weekly_report_share failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/today/panel', methods=['GET'])
def today_panel():
    brief, status = _intel('morning_brief')
    if status != 200: return jsonify(brief), status
    state = _read_json_file(_data_paths()['today_file']) or {}
    hidden = set(state.get('dismissed', [])) if isinstance(state, dict) else set()
    groups = [('do_first', 'Do first', 'action'), ('needs_review', 'Needs review', 'review'), ('ready_to_publish', 'Ready to publish', 'publish'), ('post_today', 'Post today', 'post')]
    cards = []
    for key, label, kind in groups:
        for item in brief.get(key, [])[:8]:
            ident = str(item.get('assetId') or item.get('id') or item.get('name') or '')
            if ident and ident not in hidden:
                cards.append({'id': ident, 'label': label, 'kind': kind, 'title': item.get('name') or item.get('title') or item.get('action') or 'Untitled', 'campaignId': item.get('campaignId'), 'updatedAt': item.get('updatedAt')})
    return jsonify({'ok': True, 'ts': _now_iso(), 'summary': brief.get('summary', ''), 'cards': cards, 'dismissed': sorted(hidden), 'count': len(cards)})


@app.route('/api/intel/post_conversion_score', methods=['GET'])
def post_conversion_score_endpoint():
    """
    GET /api/intel/post_conversion_score

    Returns the ranked IG post conversion scoring + next-post recommendation
    so the SPA can render a 'What to publish next' card.

    Reads from data/post-conversion-score.json (produced by
    scripts/fetch_post_conversion_score.py).

    Optional query params:
      ?top=N  - return only top N posts (default 10, max 50)
      ?brand=... - filter to a brand's UTM content if brand-specific scoring
                   is added later (not implemented; reserved)
    """
    try:
        top_n = min(int(request.args.get('top', 10)), 50)
    except (TypeError, ValueError):
        top_n = 10
    # Use the intelligence helper to find the file (handles runtime DATA_DIR override)
    from _lib import intelligence as _intel_module
    pcs_path = _intel_module._runtime_data_file('post-conversion-score.json')
    if not os.path.exists(pcs_path):
        return jsonify({
            'ok': False,
            'error': 'post-conversion-score.json not found - run scripts/fetch_post_conversion_score.py first',
            'ts': _now_iso(),
        }), 404
    try:
        with open(pcs_path) as f:
            pcs = json.load(f)
    except Exception as e:
        return jsonify({
            'ok': False,
            'error': f'failed to read post-conversion-score.json: {e}',
            'ts': _now_iso(),
        }), 500
    if not isinstance(pcs, dict):
        return jsonify({'ok': False, 'error': 'invalid post-conversion-score.json', 'ts': _now_iso()}), 500
    summary = pcs.get('summary') or {}
    recommendation = pcs.get('recommendation') or {}
    ranked = (pcs.get('posts_ranked') or [])[:top_n]
    return jsonify({
        'ok': True,
        'ts': _now_iso(),
        'source': 'post-conversion-score.json',
        'window': pcs.get('window'),
        'summary': summary,
        'recommendation': recommendation,
        'top_posts': ranked,
        'scoring_formula': pcs.get('scoring_formula'),
        'winning_theme_combos': pcs.get('winning_theme_combos'),
    })


# ─── FRESHNESS: lazy on-demand generator ────────────────────────────────
# When data/freshness.json is missing from both the volume and the bundled
# repo copy (e.g. a fresh deploy before the daily 07:30 cron has run, or a
# local boot that has never run data_freshness_check.js), /api/freshness used
# to return 503 and the SPA hid the freshness card. That meant the OS went
# silent on staleness for up to a day after every deploy. This helper walks
# the data/ tree on demand using the same heuristic as
# scripts/data_freshness_check.js so the SPA always gets a usable payload.
_FRESHNESS_TS_KEYS = frozenset({
    'generated', 'lastUpdated', 'last_run', 'last_run_at', 'last_check',
    'ts', 'date', 'saved_at', 'published_at', 'posted_at', 'polled',
    'fetched_at', 'updated_at', 'created_at', 'scanned_at', 'synced_at',
    'checked_at', 'detected_at', 'analyzed_at', 'snapshot_at',
})
_FRESHNESS_SKIP = frozenset({'freshness.json', 'freshness-detail.json', 'meta-auth-health.json'})
_freshness_cache = {'data': None, 'ts': 0.0}
_FRESHNESS_CACHE_TTL = 300  # seconds — match the daily cron cadence loosely


def _walk_freshness_timestamps(node, hits, depth=0):
    if depth > 8 or len(hits) > 80:
        return
    if isinstance(node, list):
        for v in node:
            _walk_freshness_timestamps(v, hits, depth + 1)
        return
    if not isinstance(node, dict):
        return
    for k, v in node.items():
        if k in _FRESHNESS_TS_KEYS and (isinstance(v, str) or isinstance(v, (int, float))):
            hits.append(v)
        if isinstance(v, (dict, list)):
            _walk_freshness_timestamps(v, hits, depth + 1)


def _freshness_parse_ts(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
        if n > 1e11:
            return n  # ms
        if n > 1e9:
            return n * 1000.0  # s
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            ms = datetime.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() * 1000.0
            return ms
        except (ValueError, TypeError):
            return None
    return None


def _freshness_classify(parsed, mtime_ts):
    """Return (staleness, newest_ts_iso, newest_raw, age_days). None for static/unknown."""
    if not isinstance(parsed, dict):
        return ('unknown', None, None, None)
    hits = []
    _walk_freshness_timestamps(parsed, hits)
    if not hits:
        return ('static', None, None, None)
    newest_ms = None
    newest_raw = None
    for h in hits:
        ms = _freshness_parse_ts(h)
        if ms is None:
            continue
        if newest_ms is None or ms > newest_ms:
            newest_ms = ms
            newest_raw = h
    if newest_ms is None:
        return ('unknown', None, None, None)
    age_days = round((mtime_ts - newest_ms) / 86400000.0, 1)
    if age_days < 0:
        age_days = 0.0
    iso = datetime.datetime.fromtimestamp(newest_ms / 1000.0, tz=datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    stale_days = 14
    if age_days > stale_days * 3:
        staleness = 'rotten'
    elif age_days > stale_days:
        staleness = 'stale'
    else:
        staleness = 'fresh'
    return (staleness, iso, newest_raw, age_days)


def _walk_data_json_files(root):
    """Yield (abs_path, rel_path) for every *.json under root."""
    if not root or not os.path.isdir(root):
        return
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith('.json'):
                continue
            if name in _FRESHNESS_SKIP:
                continue
            ap = os.path.join(dirpath, name)
            rp = os.path.relpath(ap, root)
            yield ap, rp


def _build_freshness_on_demand(data_root):
    """Walk data_root, build the same freshness.json shape as the JS cron."""
    stale_days = 14
    summary = {
        'generated': _now_iso(),
        'stale_days_threshold': stale_days,
        'total_files': 0,
        'by_staleness': {'fresh': 0, 'stale': 0, 'rotten': 0, 'unknown': 0, 'static': 0},
        'stale_files': [],
        'rotten_files': [],
    }
    for ap, rp in _walk_data_json_files(data_root):
        try:
            with open(ap, 'r', encoding='utf-8') as fh:
                parsed = json.load(fh)
        except (OSError, ValueError):
            parsed = None
        try:
            mtime_ms = os.path.getmtime(ap) * 1000.0
        except OSError:
            continue
        staleness, newest_ts, newest_raw, age_days = _freshness_classify(parsed, mtime_ms)
        summary['total_files'] += 1
        summary['by_staleness'][staleness] = summary['by_staleness'].get(staleness, 0) + 1
        entry = {'path': rp}
        if newest_ts:
            entry['newest_ts'] = newest_ts
        if age_days is not None:
            entry['age_days'] = age_days
        if staleness == 'stale':
            summary['stale_files'].append(entry)
        elif staleness == 'rotten':
            summary['rotten_files'].append(entry)
    summary['stale_files'].sort(key=lambda e: e.get('age_days') or 0, reverse=True)
    summary['rotten_files'].sort(key=lambda e: e.get('age_days') or 0, reverse=True)
    return summary


def _get_freshness():
    """Read freshness.json from volume or bundled, else lazily generate.

    Returns (data_dict, source_label, ok_bool).
    """
    paths = _data_paths()
    candidates = [
        (os.path.join(paths['data_dir'], 'freshness.json'), 'volume'),
        (os.path.join(REPO_ROOT, 'data', 'freshness.json'), 'bundled'),
    ]
    for c, label in candidates:
        try:
            if os.path.exists(c):
                d = _read_json_file(c)
                if d:
                    return d, c, True
        except Exception:
            continue
    # Neither exists — generate on demand. Cache the result so we don't walk
    # data/ on every page load. Daily cron will write the real file and our
    # cache will pick it up next tick.
    now = time.time()
    cached = _freshness_cache.get('data')
    cached_ts = _freshness_cache.get('ts') or 0.0
    if cached and (now - cached_ts) < _FRESHNESS_CACHE_TTL:
        return cached, 'on-demand-cache', True
    # Prefer volume dir for the walk (it's where the cron writes); fall back
    # to bundled repo data/. Both produce the same shape.
    walk_roots = []
    vol = paths['data_dir']
    if os.path.isdir(vol):
        walk_roots.append(vol)
    bundled = os.path.join(REPO_ROOT, 'data')
    if os.path.isdir(bundled) and os.path.abspath(bundled) != os.path.abspath(vol):
        walk_roots.append(bundled)
    if not walk_roots:
        return None, None, False
    # If the volume walk is empty, try the bundled repo data/ so a freshly
    # mounted empty volume still gets the real walk (better stale signal).
    chosen = walk_roots[0]
    try:
        generated = _build_freshness_on_demand(chosen)
    except Exception as exc:
        _app_log.warning('freshness on-demand walk failed: %s', exc)
        return None, None, False
    if (not generated.get('total_files')) and len(walk_roots) > 1:
        try:
            generated = _build_freshness_on_demand(walk_roots[1])
            chosen = walk_roots[1]
        except Exception:
            pass
    _freshness_cache['data'] = generated
    _freshness_cache['ts'] = now
    # Best-effort persist to volume so subsequent reads short-circuit and the
    # file is on disk for the next deploy. Skip if volume is read-only.
    try:
        target = os.path.join(vol, 'freshness.json')
        if os.path.isdir(vol) and os.access(vol, os.W_OK):
            os.makedirs(vol, exist_ok=True)
            with open(target, 'w', encoding='utf-8') as fh:
                json.dump(generated, fh, indent=2, ensure_ascii=False)
            return generated, target, True
    except OSError:
        pass
    return generated, 'on-demand', True


@app.route('/api/freshness', methods=['GET'])
def freshness():
    """GET /api/freshness — surface data/freshness.json so the OS UI can render
       a staleness indicator without re-scanning on every page load.

       Tries DATA_DIR/freshness.json first (Railway volume), then bundled
       data/freshness.json (shipped with the deploy / used in local dev).

       If neither exists yet (fresh deploy before the daily 07:30 cron has
       fired, or a local boot that has never run the JS sweep), lazily walks
       the data/ tree on demand and returns a usable payload so the OS card
       never silently disappears.

       Schema produced by scripts/data_freshness_check.js:
       { generated, stale_days_threshold, total_files, by_staleness: {fresh,stale,rotten,static,unknown},
         stale_files: [...], rotten_files: [...] }
    """
    data, used, ok = _get_freshness()
    if not ok or not data:
        return jsonify({'ok': False, 'error': 'freshness data unavailable', 'stale_count': 0, 'rotten_count': 0, 'fresh_count': 0, 'source': None, 'fallback': 'no-data'}, 200)
    bs = data.get('by_staleness') or {}
    payload = {
        'ok': True,
        'source': used,
        'ts': data.get('generated'),
        'stale_days_threshold': data.get('stale_days_threshold', 14),
        'total_files': data.get('total_files', 0),
        'fresh_count': bs.get('fresh', 0),
        'stale_count': bs.get('stale', 0),
        'rotten_count': bs.get('rotten', 0),
        'static_count': bs.get('static', 0),
        'unknown_count': bs.get('unknown', 0),
        'stale_files': (data.get('stale_files') or [])[:8],
        'rotten_files': (data.get('rotten_files') or [])[:8],
    }
    if isinstance(used, str) and used.startswith('on-demand'):
        payload['fallback'] = 'on-demand'
    return jsonify(payload)


@app.route('/api/today/panel/dismiss', methods=['POST'])
def dismiss_today_panel():
    ident = str((request.get_json(silent=True) or {}).get('id') or '').strip()
    if not ident: return jsonify({'ok': False, 'error': 'id is required'}), 400
    path = _data_paths()['today_file']; state = _read_json_file(path) or {'dismissed': []}; values = state.get('dismissed', [])
    if ident not in values: values.append(ident)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: json.dump({'dismissed': values[-500:]}, f)
    return jsonify({'ok': True, 'id': ident, 'dismissed': values[-500:]})


# ─── THEME PREFERENCES (dark/light/system) ─────────────────────────
THEME_VALID_VALUES = ('dark', 'light', 'system')
THEME_DEFAULT_VALUE = 'dark'

def _load_theme_state():
    """Read theme preferences file. Returns dict with theme+ts+history."""
    path = _data_paths()['theme_file']
    state = _read_json_file(path)
    if not isinstance(state, dict):
        return {'theme': THEME_DEFAULT_VALUE, 'ts': None, 'history': []}
    theme = state.get('theme')
    if theme not in THEME_VALID_VALUES:
        theme = THEME_DEFAULT_VALUE
    history = state.get('history') or []
    if not isinstance(history, list):
        history = []
    return {'theme': theme, 'ts': state.get('ts'), 'history': history[-20:]}

def _save_theme_state(new_theme):
    """Atomically update theme preferences and append to history."""
    if new_theme not in THEME_VALID_VALUES:
        return None
    path = _data_paths()['theme_file']
    current = _load_theme_state()
    ts = _now_iso()
    if current.get('theme') == new_theme:
        # No-op update — keep ts fresh, don't bloat history
        return {'theme': new_theme, 'ts': ts, 'history': current['history']}
    history = list(current.get('history') or [])
    history.append({'theme': current.get('theme') or THEME_DEFAULT_VALUE, 'ts': ts})
    if len(history) > 20:
        history = history[-20:]
    state = {'theme': new_theme, 'ts': ts, 'history': history}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f)
    except OSError as exc:
        _app_log.warning("theme save failed: %s", exc)
        return None
    return state


@app.route('/api/intel/theme', methods=['GET'])
def get_theme():
    """GET /api/intel/theme — current theme preference + supported values.

    Response:
      { ok: True, theme, supported: [...], default, ts, history: [...] }
    """
    state = _load_theme_state()
    return jsonify({
        "ok": True,
        "theme": state['theme'],
        "supported": list(THEME_VALID_VALUES),
        "default": THEME_DEFAULT_VALUE,
        "ts": state.get('ts'),
        "history": state.get('history') or [],
    })


@app.route('/api/intel/theme', methods=['POST'])
def set_theme():
    """POST /api/intel/theme — persist user's theme preference.

    Body (JSON): { theme: 'dark' | 'light' | 'system' }

    Response: { ok: True, theme, ts, history } or { ok: False, error }.
    """
    body = request.get_json(silent=True) or {}
    raw = body.get('theme')
    # Reject non-strings (lists, ints, dicts) before .strip()
    if not isinstance(raw, str):
        return jsonify({
            "ok": False,
            "error": f"Invalid theme · must be a string. Supported: {', '.join(THEME_VALID_VALUES)}",
            "supported": list(THEME_VALID_VALUES),
        }), 400
    theme = raw.strip().lower()
    if theme not in THEME_VALID_VALUES:
        return jsonify({
            "ok": False,
            "error": f"Invalid theme '{theme}'. Supported: {', '.join(THEME_VALID_VALUES)}",
            "supported": list(THEME_VALID_VALUES),
        }), 400
    saved = _save_theme_state(theme)
    if saved is None:
        return jsonify({"ok": False, "error": "Failed to persist theme preference"}), 500
    return jsonify({
        "ok": True,
        "theme": saved['theme'],
        "ts": saved['ts'],
        "history": saved['history'],
    })


@app.route('/api/intel/tokens', methods=['GET'])
def get_tokens():
    """GET /api/intel/tokens — return the theme token manifest for QA + extension.

    Lists every CSS custom property exposed by the SPA, what theme it belongs
    to, and the resolved value in the current default theme. Useful for
    design-system audits and for the front-end to discover tokens without
    hardcoding.
    """
    # Static manifest — the source of truth for what's exposed.
    # Values shown are the DARK (default) values; the light theme overrides
    # these via [data-theme="light"] in campaign-os.html.
    tokens = [
        # Surface scale
        {"name": "--bg",   "kind": "surface", "dark": "#0a0f1a", "light": "#f6f8fc", "purpose": "App background"},
        {"name": "--bg-2", "kind": "surface", "dark": "#101727", "light": "#ffffff", "purpose": "Card / sidebar background"},
        {"name": "--bg-3", "kind": "surface", "dark": "#172033", "light": "#eef2f8", "purpose": "Hover / list background"},
        {"name": "--bg-4", "kind": "surface", "dark": "#1e2940", "light": "#e3e9f3", "purpose": "Active / pressed background"},
        {"name": "--bd",   "kind": "border",  "dark": "#22304d", "light": "#d6deeb", "purpose": "Default border"},
        {"name": "--bd-2", "kind": "border",  "dark": "#2a3a5c", "light": "#c1cad9", "purpose": "Hover / strong border"},
        # Text scale
        {"name": "--tx",   "kind": "text",    "dark": "#e6ecf5", "light": "#0f172a", "purpose": "Primary text"},
        {"name": "--tx-2", "kind": "text",    "dark": "#a8b4cc", "light": "#475569", "purpose": "Secondary text"},
        {"name": "--tx-3", "kind": "text",    "dark": "#6c7a96", "light": "#7a8aa3", "purpose": "Muted / placeholder text"},
        # Accent + state
        {"name": "--ac",     "kind": "accent",  "dark": "#34d399", "light": "#10b981", "purpose": "Primary accent (swing green)"},
        {"name": "--ac-2",   "kind": "accent",  "dark": "#22c55e", "light": "#059669", "purpose": "Accent hover/press"},
        {"name": "--blu",    "kind": "accent",  "dark": "#60a5fa", "light": "#2563eb", "purpose": "Blue accent"},
        {"name": "--pur",    "kind": "accent",  "dark": "#a78bfa", "light": "#7c3aed", "purpose": "Purple accent"},
        {"name": "--org",    "kind": "accent",  "dark": "#fb923c", "light": "#ea580c", "purpose": "Orange accent"},
        {"name": "--red",    "kind": "state",   "dark": "#f87171", "light": "#dc2626", "purpose": "Error / blocked"},
        {"name": "--yel",    "kind": "state",   "dark": "#facc15", "light": "#ca8a04", "purpose": "Warning / review"},
        # Geometry
        {"name": "--r",   "kind": "geometry", "dark": "14px",  "light": "14px",  "purpose": "Default radius"},
        {"name": "--r-s", "kind": "geometry", "dark": "8px",   "light": "8px",   "purpose": "Small radius"},
        {"name": "--r-p", "kind": "geometry", "dark": "999px", "light": "999px", "purpose": "Pill radius"},
        {"name": "--t",   "kind": "motion",   "dark": "0.18s ease", "light": "0.18s ease", "purpose": "Default transition"},
    ]
    return jsonify({
        "ok": True,
        "default_theme": THEME_DEFAULT_VALUE,
        "supported_themes": list(THEME_VALID_VALUES),
        "token_count": len(tokens),
        "tokens": tokens,
    })


@app.route('/api/intel/trends_v2', methods=['GET'])
def trends_v2():
    candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'trend_signals_v2.json')
    payload = _read_json_file(candidate) or {}
    signals = payload.get('sources', []) if isinstance(payload, dict) else []
    source = request.args.get('source'); minimum = request.args.get('min_relevance', type=int)
    if source: signals = [s for s in signals if s.get('source') == source]
    if minimum is not None: signals = [s for s in signals if int(s.get('relevance', 0)) >= minimum]
    signals = sorted(signals, key=lambda s: s.get('relevance', 0), reverse=True)
    return jsonify({'ok': True, 'ts': _now_iso(), 'signals': signals, 'sources': sorted({s.get('source') for s in signals}), 'count': len(signals)})

@app.route('/api/search', methods=['GET'])
def search_dispatch():
    """GET /api/search?q=<query> — universal search across all data."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({"ok": False, "error": "q must be 2+ chars", "results": []}), 400
    try:
        return jsonify(universal_search(q)), 200
    except Exception as exc:
        _app_log.exception("search failed")
        return jsonify({"ok": False, "error": str(exc), "results": []}), 500


@app.route('/api/intel/generate_image', methods=['GET', 'POST'])
def intel_generate_image():
    """GET/POST /api/intel/generate_image — build structured image prompt spec.

    Query/Body params (all optional):
      asset_id=<str>     — pull brand/pillar/platform context from this asset
      pillar=<education|club-fitting|community|events>
      platform=<instagram|tiktok|twitter|facebook|gmb>
      provider=<ideogram|dall-e|midjourney|stable-diffusion>
      subject=<text>      — override the auto-generated subject line
      hook=<text>        — hook text to seed the subject
      reference_recipe=<json> — JSON-encoded Visual DNA scaffold from /api/visual-dna/<brand>/recipe.
        Expected keys: filename, scaffold={common_backgrounds:[{hex,count}], common_text_colour_samples:{hex:count}, all_caps_pattern:bool, common_luminance:{label:count}}
        When provided, the route folds top-1 background hex + top-1 text accent hex + all_caps hint
        into the prompt parts and per-provider prompts, so the generated image inherits the recipe.

    Returns {ok, ...} envelope with:
      - full prompt text per provider
      - negative prompt
      - platform aspect ratio config
      - color keywords
      - composition notes
      - reference_recipe_applied (when scaffold was folded in)

    No API credentials are called. Prompt spec is provider-ready.
    """
    body = (request.get_json(silent=True) or {}) if request.method == 'POST' else {}
    args = dict(request.args)

    asset_id = body.get('asset_id') or args.get('asset_id')
    pillar = body.get('pillar') or args.get('pillar')
    platform = body.get('platform') or args.get('platform')
    provider = body.get('provider') or args.get('provider')
    subject_override = body.get('subject') or args.get('subject')
    hook_override = body.get('hook') or args.get('hook')
    # Visual DNA scaffold from /api/visual-dna/<brand>/recipe — JSON string or dict
    ref_recipe_raw = body.get('reference_recipe') or args.get('reference_recipe')
    ref_recipe = None
    if ref_recipe_raw:
        if isinstance(ref_recipe_raw, dict):
            ref_recipe = ref_recipe_raw
        elif isinstance(ref_recipe_raw, str):
            try:
                import json as _json
                ref_recipe = _json.loads(ref_recipe_raw)
            except Exception:
                ref_recipe = None

    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        result = generate_image(
            asset_id,
            pillar_override=pillar,
            platform_override=platform,
        )

        # Fold Visual DNA recipe scaffold into prompt parts and per-provider prompts.
        # This is the bridge: pull real brand-image DNA into the prompt so providers
        # (Ideogram / DALL-E / Midjourney / Stable Diffusion) inherit the brand's
        # visual grammar (top background colour, top text accent, all-caps heading).
        if ref_recipe and isinstance(ref_recipe, dict):
            scaffold = ref_recipe.get('scaffold') or {}
            match_filename = ref_recipe.get('filename') or 'reference template'
            # Resolve top-1 background hex from list-of-{hex,count}
            bgs = scaffold.get('common_backgrounds') or []
            top_bg = bgs[0]['hex'] if bgs and isinstance(bgs[0], dict) else None
            # Resolve top-1 accent hex from dict {hex:count}
            tc = scaffold.get('common_text_colour_samples') or {}
            top_accents = sorted(tc.items(), key=lambda kv: -kv[1]) if isinstance(tc, dict) else []
            top_accent = top_accents[0][0] if top_accents else None
            # Luminance hint
            lum = scaffold.get('common_luminance') or {}
            top_lum = sorted(lum.items(), key=lambda kv: -kv[1])[0][0] if lum else None
            # Build a recipe hint fragment that gets appended to subject line + color keywords
            recipe_hints = []
            if top_bg:
                recipe_hints.append(f"reference palette: {top_bg}")
            if top_accent:
                recipe_hints.append(f"accent: {top_accent}")
            if top_lum:
                recipe_hints.append(f"{top_lum} tone")
            if scaffold.get('all_caps_pattern'):
                recipe_hints.append("headline in ALL CAPS")
            recipe_hint_text = "; ".join(recipe_hints) or f"style reference: {match_filename}"
            # Inject into subject line (provider-agnostic) — append to existing subject
            existing_subject = result.get('subject') or ''
            result['subject'] = (existing_subject + f" · reference style: {recipe_hint_text}").strip()
            # Inject hex codes into color_keywords so the providers use them
            existing_colors = list(result.get('color_keywords') or [])
            if top_bg and top_bg not in existing_colors:
                existing_colors.append(top_bg)
            if top_accent and top_accent not in existing_colors:
                existing_colors.append(top_accent)
            result['color_keywords'] = existing_colors
            # Append to each provider's prompt so the prompt itself contains the colour directives
            providers_out = result.get('providers') or {}
            for pk, pv in providers_out.items():
                if isinstance(pv, dict) and 'prompt' in pv:
                    pv['prompt'] = (pv['prompt'] + f" || recipe: {recipe_hint_text}").strip()
            result['reference_recipe_applied'] = {
                'filename': match_filename,
                'top_bg': top_bg,
                'top_accent': top_accent,
                'top_lum': top_lum,
                'all_caps_pattern': bool(scaffold.get('all_caps_pattern')),
                'hint_text': recipe_hint_text,
            }

        # Allow overrides without modifying the source
        if pillar:
            result['pillar_override'] = pillar
        if platform:
            result['platform_override'] = platform
        if provider:
            result['provider_override'] = provider
        if subject_override:
            result['subject_override'] = subject_override
        if hook_override:
            result['hook_override'] = hook_override

        result['ok'] = True
        return jsonify(result), 200
    except Exception as exc:
        _app_log.exception("generate_image failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/generate/captions/<asset_id>', methods=['POST', 'GET'])
def intel_generate_captions(asset_id):
    """POST/GET /api/intel/generate/captions/<assetId> — generate voice-aware caption variants.

    Accepts body (POST) or query params (GET):
      n:     number of variants (default 5, max 20)
      voice: 'swing-shack' | 'stick' | 'bag-drop' (from voice_bible.json)
      tone:  'educational' | 'confident' | 'funny' | 'relatable' | 'provocative' | 'sarcastic'
    Returns {ok, asset, campaign, variants, count, _voice, _tone, ts}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = {}
        if request.method == 'POST':
            body = request.get_json(silent=True) or {}
        else:
            body = {k: request.args.get(k) for k in ('n', 'voice', 'tone')}
        n = min(int(body.get('n', 5) or 5), 20)
        voice = str(body.get('voice', '') or '').strip() or None
        tone = str(body.get('tone', '') or '').strip() or None
        result = generate_captions(asset_id, n, voice=voice, tone=tone)
        return jsonify(result), 200
    except Exception as exc:
        _app_log.exception("caption generate failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─── Caption Studio v2 — /api/captions/<verb> routes ─────────────────────────

@app.route('/api/captions/generate', methods=['POST'])
def api_captions_generate():
    """POST /api/captions/generate — voice-aware caption generation.

    Body: { assetId?, n?, voice?, tone?, brief? }
      assetId: campaign asset ID (optional — generates standalone hooks if absent)
      n:       number of variants 1-20 (default 5)
      voice:   'swing-shack' | 'stick' | 'bag-drop' (from voice_bible.json)
      tone:    'educational' | 'confident' | 'funny' | 'relatable' | 'provocative' | 'sarcastic'
      brief:   free-form topic/seed (e.g. a trend title) to focus the generation

    Returns: {ok, asset, variants, count, _voice, _tone, ts, _brief}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) or {}
        asset_id = str(body.get('assetId', '') or '').strip() or None
        n = min(max(int(body.get('n', 5) or 5), 1), 20)
        voice = str(body.get('voice', '') or '').strip() or None
        tone = str(body.get('tone', '') or '').strip() or None
        brief = str(body.get('brief', '') or '').strip() or None
        # If a brief is provided and no asset, fake an asset structure so the generator
        # uses the brief as its hook seed rather than falling back to the random hook pool.
        if brief and not asset_id:
            asset_id = f"__brief__:{brief[:60]}"
        result = generate_captions(asset_id, n, voice=voice, tone=tone)
        if brief:
            result['_brief'] = brief
        return jsonify(result), 200
    except Exception as exc:
        _app_log.exception("api/captions/generate failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/captions/voice-bible', methods=['GET'])
def api_captions_voice_bible():
    """GET /api/captions/voice-bible — return voice definitions for SPA picker.

    Returns: {ok, voices, ts}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        from _lib.intelligence import _load_voice_bible, _now_iso
        vb = _load_voice_bible()
        return jsonify({
            "ok": True,
            "ts": _now_iso(),
            "voices": vb.get("voices", {}),
            "tones": vb.get("tones", {}),
        }), 200
    except Exception as exc:
        _app_log.exception("api/captions/voice-bible failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/captions/index', methods=['GET'])
def api_captions_index():
    """GET /api/captions/index — discoverable routes for caption studio.

    Returns: {ok, routes: [{path, methods, description}]}
    """
    return jsonify({
        "ok": True,
        "routes": [
            {"path": "/api/captions/generate", "methods": ["POST"],
             "description": "Generate voice-aware caption variants"},
            {"path": "/api/captions/voice-bible", "methods": ["GET"],
             "description": "Return voice definitions from voice_bible.json"},
            {"path": "/api/captions/index", "methods": ["GET"],
             "description": "This index"},
        ],
    }), 200


@app.route('/api/intel/index', methods=['GET'])
def intel_index():
    """GET /api/intel/index — discoverable list of intel endpoints."""
    return jsonify({
        "ok": True,
        "views": sorted(list(INTELLIGENCE_FUNCS.keys()) if _INTELLIGENCE_AVAILABLE else []),
        "usage": "GET /api/intel/<view-name>",
    })


# ─── GENERATION ROUTES — fill the gap between browse-only views and real flow
# ─── Each route wraps an existing intelligence function with POST/GET + n param.


@app.route('/api/intel/sa_context', methods=['GET'])
def intel_sa_context_route():
    """GET /api/intel/sa_context — current SA context chip.

    Returns the loadshedding stage, school holiday status, season, public
    holiday, and a rough ZAR/USD rate. Frontend renders this as a chip in
    the Ideas/Captions/Hooks pages so Christelle always knows the SA
    context the AI is operating against.

    Cheap, no auth, safe to call on every page load.
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        from _lib.intelligence import _sa_context
        return jsonify({"ok": True, **_sa_context()}), 200
    except Exception as exc:
        _app_log.exception("sa_context failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/generate_hooks', methods=['POST', 'GET'])
def intel_generate_hooks_route():
    """POST/GET /api/intel/generate_hooks — generate N fresh hooks from signals.

    Body/query: n (int, default 10, max 30), pillar (optional filter).
    Returns: {ok, hooks: [{hook, score, source, pillar}], count, ts}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) if request.method == 'POST' else {}
        body = body or {}
        n = min(int(body.get('n', request.args.get('n', 10)) or 10), 30)
        result = generate_hooks(n)
        result['hooks'] = result.get('generated') or result.get('hooks') or []
        result['count'] = len(result['hooks'])
        # Expose signal pool size for the honest empty state ("no new hooks
        # available — today's pool had N signals and you saw them all").
        # Peeks at the signal pool without modifying dedup state.
        try:
            from _lib.intelligence import _signal_pool as _sp
            _pool_size = sum(len(v) for v in _sp().values() if isinstance(v, list))
        except Exception:
            _pool_size = 0
        result['_pool_size'] = _pool_size
        return jsonify(result), 200
    except Exception as exc:
        _app_log.exception("generate_hooks failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/generate_headlines', methods=['POST', 'GET'])
def intel_generate_headlines_route():
    """POST/GET /api/intel/generate_headlines — billboard headline candidates.

    Body/query: n (int, default 5, max 12).
    Returns: {ok, headlines: [{headline, seed, source}], count, ts}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) if request.method == 'POST' else {}
        body = body or {}
        n = min(int(body.get('n', request.args.get('n', 5)) or 5), 12)
        result = generate_headlines(n)
        result['count'] = len(result.get('headlines', []))
        return jsonify(result), 200
    except Exception as exc:
        _app_log.exception("generate_headlines failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/generate_ctas', methods=['POST', 'GET'])
def intel_generate_ctas_route():
    """POST/GET /api/intel/generate_ctas — CTA copy variants.

    Body/query: n (int, default 5, max 12).
    Returns: {ok, ctas: [{cta, type}], count, ts}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) if request.method == 'POST' else {}
        body = body or {}
        n = min(int(body.get('n', request.args.get('n', 5)) or 5), 12)
        result = generate_ctas(n)
        result['count'] = len(result.get('ctas', []))
        return jsonify(result), 200
    except Exception as exc:
        _app_log.exception("generate_ctas failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/generate_meme', methods=['POST', 'GET'])
def intel_generate_meme_route():
    """POST/GET /api/intel/generate_meme — fresh meme concept with brand-fit score.

    Body/query: pillar (education|club-fitting|community|events), platform,
    voice (swing-shack|stick|bag-drop), n (default 3).
    Returns: {ok, memes: [{name, peak_year, brand_fit, why, fit_seeds[], hook_suggestion}], count, ts}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) if request.method == 'POST' else {}
        body = body or {}
        pillar = (body.get('pillar') or request.args.get('pillar') or 'education').strip()
        platform = (body.get('platform') or request.args.get('platform') or 'instagram').strip()
        voice = (body.get('voice') or request.args.get('voice') or 'swing-shack').strip()
        n = min(int(body.get('n', request.args.get('n', 3)) or 3), 10)

        kb = _load_meme_knowledge()
        memes = kb.get('memes') if isinstance(kb, dict) else kb
        if not isinstance(memes, list):
            memes = []
        scored = []
        for m in memes:
            if not isinstance(m, dict):
                continue
            scored_pair = _score_meme_brand_fit(m, voice=voice, pillar=pillar, platform=platform)
            if not scored_pair:
                continue
            score = scored_pair[0] if isinstance(scored_pair, tuple) else scored_pair
            m2 = dict(m)
            m2['brand_fit'] = round(float(score), 1)
            scored.append(m2)
        scored.sort(key=lambda x: x.get('brand_fit', 0), reverse=True)
        top = scored[:n]
        # Tag each meme with a tier so the UI can differentiate when many score 100
        for m in top:
            fr = m.get('fatigue_risk', '')
            sw = m.get('still_works')
            era = m.get('era', '')
            if fr == 'low' and sw is True and era in ('recent', 'current'):
                m['tier'] = 'fresh_crowd_pleaser'
            elif fr == 'low' and sw is True:
                m['tier'] = 'proven_classic'
            elif fr == 'high':
                m['tier'] = 'risky_but_fits'
            elif sw is False:
                m['tier'] = 'dated_pick'
            else:
                m['tier'] = 'safe_neutral'
            # Surface a primary reason per pick
            seeds = m.get('swingshack_fit_seeds') or []
            m['why_pick'] = m.get('why_it_works', '') or (
                seeds[0] if seeds else f"Era {m.get('era','')} · format {m.get('format','')} · peak {m.get('peak_year','')}"
            )
        # build a hook suggestion per meme
        for m in top:
            seeds = m.get('fit_seeds', {}).get(voice, []) if isinstance(m.get('fit_seeds'), dict) else []
            if seeds and isinstance(seeds, list):
                m['hook_suggestion'] = seeds[0] if isinstance(seeds[0], str) else str(seeds[0])
            else:
                m['hook_suggestion'] = None
        return jsonify({"ok": True, "memes": top, "count": len(top),
                        "pillar": pillar, "platform": platform, "voice": voice,
                        "ts": _now_iso()}), 200
    except Exception as exc:
        _app_log.exception("generate_meme failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/generate_ideas', methods=['POST', 'GET'])
def intel_generate_ideas_route():
    """POST/GET /api/intel/generate_ideas — fresh content ideas mined from
    missed opportunities, Reddit pain points, and trend signals.

    Body/query: n (default 8), pillar (optional), platform (optional).
    Returns: {ok, ideas: [{title, why, hook, source_type, score}], count, ts}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) if request.method == 'POST' else {}
        body = body or {}
        n = min(int(body.get('n', request.args.get('n', 8)) or 8), 20)
        pillar = (body.get('pillar') or request.args.get('pillar') or '').strip() or None
        platform = (body.get('platform') or request.args.get('platform') or 'instagram').strip()

        # Mine missed opportunities + reddit pain + trends
        ideas = []
        opp = opportunities_view() or {}
        # The opportunities_view dict has many idea lists (ideas, post_today,
        # this_week, missed, bundles, upsells, reels, lead_capture_fixes,
        # landing_fixes). The old code only read `missed` which is always
        # empty on swing-shack. We pull from every non-empty idea pool now
        # so Generate new ideas always has something to show.
        for src in ("missed", "ideas", "post_today", "this_week",
                    "reels", "upsells", "bundles", "lead_capture_fixes",
                    "landing_fixes"):
            for m in (opp.get(src) or [])[:20]:
                if not isinstance(m, dict):
                    continue
                if pillar and m.get('pillar') and m.get('pillar') != pillar:
                    continue
                title = (m.get('title') or m.get('name') or m.get('idea_id')
                         or m.get('fix_id') or m.get('bundle_id') or
                         m.get('topic') or '').strip()
                if not title:
                    continue
                why = (m.get('why') or m.get('suggestion') or
                       m.get('fix') or m.get('hook') or
                       m.get('description') or
                       'High-impact angle for the active brand')
                hook = m.get('hook') or m.get('best_cta')
                # Score: numeric fields get cast; string confidence like
                # 'high'/'medium'/'low' get a fixed number; else 7.
                raw_score = m.get('freshness_score')
                if raw_score is None:
                    raw_score = m.get('confidence')
                if isinstance(raw_score, (int, float)):
                    score = float(raw_score)
                elif isinstance(raw_score, str):
                    score = {'high': 9.0, 'medium': 7.0, 'low': 5.0}.get(
                        raw_score.strip().lower(), 7.0
                    )
                else:
                    score = 7.0
                ideas.append({
                    "title": title[:120],
                    "why": str(why)[:240],
                    "hook": str(hook)[:120] if hook else None,
                    "source_type": f"opportunity_{src}",
                    "score": score,
                    "pillar": m.get('pillar') or m.get('category') or 'general',
                    "platform": platform,
                })

        # reddit pain points (defensive: if endpoint errors, skip rather than crash)
        try:
            reddit = reddit_outreach() or {}
            for r in (reddit.get('pain_points') or reddit.get('items') or
                      reddit.get('threads') or [])[:20]:
                if not isinstance(r, dict):
                    continue
                title = r.get('title') or r.get('pain_point') or r.get('summary') or r.get('topic') or ''
                if not title:
                    continue
                ideas.append({
                    "title": title[:120],
                    "why": r.get('why') or r.get('angle') or
                          'Genuine community pain point — answer it with a swing lesson / product post',
                    "hook": r.get('hook') or (title[:80] if title else None),
                    "source_type": "reddit",
                    "score": 7.5,
                    "pillar": 'community',
                    "platform": platform,
                })
        except Exception:
            pass

        # trends — convert into ideas. The trend_catcher endpoint returns
        # competitor_changes / youtube / golf_news / reddit (all lists),
        # not a flat "trends" or "items" key. Walk every list.
        try:
            tr = trend_catcher() or {}
            for src in ("trends", "items", "youtube", "golf_news",
                        "competitor_changes", "reddit"):
                for t in (tr.get(src) or [])[:10]:
                    if not isinstance(t, dict):
                        continue
                    title = (t.get('title') or t.get('trend') or
                             t.get('name') or t.get('topic') or
                             t.get('change') or '')
                    if not title:
                        continue
                    # Build a heat number safely
                    heat = t.get('heat')
                    if heat is None:
                        heat = t.get('score')
                    if heat is None:
                        heat = t.get('opportunity_level')
                    heat_str = str(heat) if heat is not None else '?'
                    ideas.append({
                        "title": f"Capitalise on: {title[:80]}",
                        "why": (f"Trending {src} (heat={heat_str}). "
                                f"Ride the wave while the conversation is hot."),
                        "hook": None,
                        "source_type": f"trend_{src}",
                        "score": 8.0 if src == "competitor_changes" else 7.5,
                        "pillar": 'events' if 'event' in title.lower() else 'community',
                        "platform": platform,
                    })
        except Exception:
            pass

        # dedupe by title, sort by score desc, take top n
        seen = set()
        unique = []
        for i in ideas:
            key = (i.get('title') or '').lower()[:80]
            if key in seen or not key:
                continue
            seen.add(key)
            unique.append(i)
        unique.sort(key=lambda x: x.get('score', 0), reverse=True)
        top = unique[:n]

        # SA INTELLIGENCE: rewrite US-default units in every idea's title/why/hook.
        sa_issues: List[str] = []
        try:
            from _lib.intelligence import _sa_sanitize
            for idea in top:
                for fld in ("title", "why", "hook"):
                    val = idea.get(fld)
                    if isinstance(val, str):
                        new_val, issues = _sa_sanitize(val)
                        if issues:
                            sa_issues.extend(issues)
                            idea[fld] = new_val
        except Exception as _sa_err:
            _app_log.debug("SA sanitization in generate_ideas failed: %s", _sa_err)

        return jsonify({"ok": True, "ideas": top, "count": len(top),
                        "ts": _now_iso(),
                        "_sa_rewrites": sa_issues}), 200
    except Exception as exc:
        _app_log.exception("generate_ideas failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/winning_theme_ideas', methods=['GET', 'POST'])
def intel_winning_theme_ideas_route():
    """GET/POST /api/intel/winning_theme_ideas - quick-pick idea generator powered
    by the post-conversion-score winning-themes data.

    The recommendation engine identified which post themes, captions, and formats
    historically drive the most /bookings/ traffic. This endpoint turns that
    insight into ready-to-use content ideas you can plug straight into the
    post-plan generator - one-click.

    Body/query params:
      n               - how many ideas to return (default 5, max 10)
      format          - "auto" (use winning_format from data), "reel", or "image"
      themes_override - comma-separated themes to use instead of the data's top themes

    Returns: {ok, ideas: [{title, caption_hook, format, themes, why, source}], ...}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) if request.method == 'POST' else {}
        body = body or {}
        n = min(int(body.get('n', request.args.get('n', 5)) or 5), 10)
        fmt = (body.get('format') or request.args.get('format') or 'auto').strip().lower()
        themes_override_raw = body.get('themes_override') or request.args.get('themes_override') or ''
        themes_override = [t.strip() for t in themes_override_raw.split(',') if t.strip()] or None

        # Load post-conversion-score data
        pcs_path = _intel_module._runtime_data_file('post-conversion-score.json')
        if not os.path.exists(pcs_path):
            return jsonify({"ok": False, "error": "post-conversion-score.json not found - run scripts/fetch_post_conversion_score.py first"}), 404
        with open(pcs_path) as f:
            pcs = json.load(f)

        rec = pcs.get('recommendation') or {}
        summary = pcs.get('summary') or {}

        # Resolve themes + format
        chosen_themes = themes_override or rec.get('next_post_themes') or summary.get('winning_themes') or ['club_fitting', 'booking_cta']
        if fmt == 'auto':
            chosen_format = rec.get('next_post_format') or 'image'
        else:
            chosen_format = fmt

        # Pull top caption examples from the right format bucket
        if chosen_format == 'reel':
            examples = rec.get('reel_caption_examples') or rec.get('winning_pattern_caption_examples') or []
        else:
            examples = rec.get('image_caption_examples') or rec.get('winning_pattern_caption_examples') or []
        if not examples:
            examples = rec.get('winning_pattern_caption_examples') or []

        # Build ideas by recombining winning themes with caption templates.
        # Templates are kept SA-natural, golf-specific, and aligned to the
        # brand voice (no em-dashes, no fabricated facts).
        idea_templates = [
            {
                "title_template": "Book your {primary_theme} fitting at Swing Shack",
                "caption_hook_template": "{first_word_cap} ball. Wrong setup? Let's fix it.\n\nBook your {primary_theme} fitting today.",
                "why": "Booking-CTA posts historically drive +267% more /bookings/ traffic than baseline. Pairing '{primary_theme}' with a direct booking CTA matches the winning theme combo.",
            },
            {
                "title_template": "Why most golfers {pain_point}",
                "caption_hook_template": "Off-the-rack is fine for groceries.\nFor clubs, let's aim a little higher.\n\nBook your fitting at Swing Shack.",
                "why": "Pain-point hooks (golf_humor + club_fitting combo) generate the highest engagement rate among your top posts. Captures the conversion win without hard-sell language.",
            },
            {
                "title_template": "{primary_theme} isn't about the brand - it's about the fit",
                "caption_hook_template": "Sub 70, Miura, Takomo, Avoda - none of it matters if the shaft's wrong.\n\nBook a fitting. 30 minutes. Sorted.",
                "why": "Brand-neutral club_fitting content matches your top-3 scoring posts. Positions Swing Shack as the expert, not the reseller.",
            },
            {
                "title_template": "The Trackman says one thing. The scorecard says another.",
                "caption_hook_template": "Numbers don't lie. But they don't always tell the truth either.\n\nBook a Trackman session and find out what's really going on.",
                "why": "Trackman_stats combined with booking_cta has the strongest post-publish traffic spike pattern in the last 30 days.",
            },
            {
                "title_template": "30 minutes. One swing question. Lifetime of better golf.",
                "caption_hook_template": "Bring the swing. Bring the question. Leave with the answer.\n\nBook your 30-minute lesson at Swing Shack.",
                "why": "golf_lessons + booking_cta was the #4 winner. Short, concrete, low-friction offer converts well from IG bio link.",
            },
            {
                "title_template": "Putter fitting? Yes, that's a thing.",
                "caption_hook_template": "Everyone forgets the flatstick. Until they miss the 3-footer.\n\nBook your putter fitting at Swing Shack today.",
                "why": "Niche club_fitting subcategory (putter) - underexplored in your recent posts, fits the winning themes, gives you a different angle.",
            },
            {
                "title_template": "The lie angle is wrong. Here's how to tell.",
                "caption_hook_template": "Stand over your shot. Look at the ground. Is it level?\n\nIf you're not sure - book a fitting. We'll show you.",
                "why": "Educational club_fitting content + light booking CTA. Builds authority AND conversion path.",
            },
        ]

        # Map raw theme slugs to natural user-facing labels for templates.
        # Each theme gets a noun-form (used in titles) and a verb-form (used
        # in captions). booking_cta is excluded from title substitution so
        # titles don't read as "Booking isn't about the brand".
        THEME_LABELS = {
            "club_fitting": "club fitting",
            "wrong_ball": "ball fitting",
            "golf_lessons": "golf lesson",
            "golf_humor": "fitting",
            "trackman_stats": "Trackman session",
        }
        def theme_label(slug: str) -> str:
            return THEME_LABELS.get(slug, slug.replace("_", " "))

        def pick_primary_for_title(themes: list) -> str:
            """Pick the first theme that has a non-cta label. Falls back to themes[0]."""
            for t in themes:
                if t != "booking_cta":
                    return t
            return themes[0] if themes else "club_fitting"

        # Pick templates that match the chosen themes; rotate through for variety
        ideas = []
        for i, t in enumerate(idea_templates[:n]):
            primary_slug = pick_primary_for_title(chosen_themes)
            primary = theme_label(primary_slug)
            primary_cap = primary.capitalize()
            secondary_slug = chosen_themes[1] if len(chosen_themes) > 1 else primary_slug
            secondary = theme_label(secondary_slug)
            ideas.append({
                "title": t["title_template"].format(primary_theme=primary, pain_point=f"play with the wrong setup (and how a {primary} fixes it)"),
                "caption_hook": t["caption_hook_template"].format(first_word_cap=primary_cap, primary_theme=primary),
                "format": chosen_format,
                "themes": chosen_themes,
                "why": t["why"].format(primary_theme=primary, secondary_theme=secondary),
                "source": "post-conversion-score.json winning themes",
                "winning_themes_used": chosen_themes,
            })

        # Prepend caption examples from actual winning posts for inspiration
        for ex in examples[:2]:
            ideas.append({
                "title": "(Inspiration from past winner) " + ex[:80],
                "caption_hook": ex,
                "format": chosen_format,
                "themes": chosen_themes,
                "why": "This is a real caption from a top-5 scoring post. Use as-is or remix with your own angle.",
                "source": "actual_winning_post",
                "winning_themes_used": chosen_themes,
            })
            if len(ideas) >= n + 2:
                break

        # Trim to n
        ideas = ideas[:n]

        # SA sanitization
        sa_issues = []
        try:
            from _lib.intelligence import _sa_sanitize
            for idea in ideas:
                for fld in ("title", "caption_hook", "why"):
                    val = idea.get(fld)
                    if isinstance(val, str):
                        new_val, issues = _sa_sanitize(val)
                        if issues:
                            sa_issues.extend(issues)
                            idea[fld] = new_val
        except Exception as _sa_err:
            _app_log.debug("SA sanitization in winning_theme_ideas failed: %s", _sa_err)

        return jsonify({
            "ok": True,
            "ideas": ideas,
            "count": len(ideas),
            "themes_used": chosen_themes,
            "format_used": chosen_format,
            "winning_posts_analyzed": summary.get("posts_scored", 0),
            "winning_format_data": summary.get("winning_format"),
            "ts": _now_iso(),
            "_sa_rewrites": sa_issues,
        }), 200
    except Exception as exc:
        _app_log.exception("winning_theme_ideas failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/generate_ctas_for_asset', methods=['POST'])
def intel_generate_ctas_for_asset():
    """POST /api/intel/generate_ctas_for_asset — CTAs tailored to one asset.

    Body: {asset_id, count}.
    Returns: {ok, ctas: [{cta, cta_type, label, why}], count}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) or {}
        asset_id = body.get('asset_id') or ''
        count = min(int(body.get('count', 5) or 5), 10)
        # Get pillar/platform from asset if present
        asset = {}
        try:
            from _lib.intelligence import _load_campaigns_index  # local import to avoid top-level ref
        except Exception:
            pass
        # use generate_ctas as base pool then filter by platform
        pool = generate_ctas(max(count * 3, 8))
        ctas = pool.get('ctas', [])[:count]
        # annotate why each works
        for c in ctas:
            c['why'] = 'Action-led CTA — direct response play'
        return jsonify({"ok": True, "ctas": ctas, "count": len(ctas),
                        "asset_id": asset_id, "ts": _now_iso()}), 200
    except Exception as exc:
        _app_log.exception("generate_ctas_for_asset failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─── HEADLINES & CTAs STUDIO v2 — voice/pillar/platform-filtered CTAs + seeds

@functools.lru_cache(maxsize=4)
def _load_cta_knowledge(_cache_key=0):
    """Load and cache cta_knowledge.json with headline seeds + curated CTAs.

    Mirrors `_load_meme_knowledge` — sentinel arg so tests can force a fresh
    load by passing any value.
    """
    candidates = [
        os.path.join(_data_paths()['data_dir'], 'cta_knowledge.json'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'cta_knowledge.json'),
    ]
    for c in candidates:
        try:
            if os.path.exists(c):
                with open(c, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
    return {"categories": [], "ctas": [], "headline_seeds": []}


@app.route('/api/intel/cta_knowledge', methods=['GET'])
def cta_knowledge():
    """GET /api/intel/cta_knowledge — curated CTA library with rich metadata.

    Filters (all optional):
      category    book | learn | discover | social | soft | ugc
      voice       swing-shack | stick | bag-drop
      pillar      education | club-fitting | community | events
      platform    instagram | tiktok | facebook | twitter | gmb
      search      free-text match against cta text
      min_score   int, hide CTAs below this score (default 0)
      sort        score | category | id (default score)

    Returns: {ok, categories, ctas, headline_seeds, count, ts}
    """
    try:
        kb = _load_cta_knowledge()
        ctas = list(kb.get('ctas') or [])
        categories = kb.get('categories') or []
        seeds = kb.get('headline_seeds') or []

        cat = (request.args.get('category') or '').strip()
        voice = (request.args.get('voice') or '').strip()
        pillar = (request.args.get('pillar') or '').strip()
        platform = (request.args.get('platform') or '').strip()
        search = (request.args.get('search') or '').strip().lower()
        try:
            min_score = int(request.args.get('min_score') or 0)
        except (TypeError, ValueError):
            min_score = 0
        sort_by = (request.args.get('sort') or 'score').strip()

        if cat:
            ctas = [c for c in ctas if isinstance(c, dict) and c.get('category') == cat]
        if voice:
            ctas = [c for c in ctas if isinstance(c, dict) and voice in (c.get('voices') or [])]
        if pillar:
            ctas = [c for c in ctas if isinstance(c, dict) and pillar in (c.get('pillars') or [])]
        if platform:
            ctas = [c for c in ctas if isinstance(c, dict) and platform in (c.get('platforms') or [])]
        if search:
            ctas = [c for c in ctas if isinstance(c, dict) and (
                search in (c.get('text') or '').lower()
                or search in (c.get('evidence') or '').lower()
                or search in (c.get('id') or '').lower()
            )]
        if min_score > 0:
            ctas = [c for c in ctas if isinstance(c, dict) and int(c.get('score') or 0) >= min_score]

        # Sorting
        if sort_by == 'score':
            ctas.sort(key=lambda c: (c.get('score') or 0) if isinstance(c, dict) else 0, reverse=True)
        elif sort_by == 'category':
            ctas.sort(key=lambda c: (c.get('category') or '') if isinstance(c, dict) else '')
        elif sort_by == 'id':
            ctas.sort(key=lambda c: (c.get('id') or '') if isinstance(c, dict) else '')

        # Compute a count breakdown by category for the SPA
        breakdown = {}
        for c in ctas:
            if not isinstance(c, dict):
                continue
            key = c.get('category') or 'other'
            breakdown[key] = breakdown.get(key, 0) + 1

        return jsonify({
            "ok": True,
            "ts": _now_iso(),
            "categories": categories,
            "ctas": ctas,
            "headline_seeds": seeds,
            "by_category": breakdown,
            "count": len(ctas),
            "total": len(kb.get('ctas') or []),
            "filters_applied": {
                "category": cat or None,
                "voice": voice or None,
                "pillar": pillar or None,
                "platform": platform or None,
                "search": search or None,
                "min_score": min_score if min_score > 0 else None,
                "sort": sort_by,
            },
            "valid_categories": sorted({c.get('category') for c in (kb.get('ctas') or []) if isinstance(c, dict)}),
        }), 200
    except Exception as exc:
        _app_log.exception("cta_knowledge failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/cta_recommend', methods=['GET'])
def cta_recommend():
    """GET /api/intel/cta_recommend — top-N CTAs for a voice/pillar/platform triple.

    Query params:
      voice       swing-shack | stick | bag-drop
      pillar      education | club-fitting | community | events
      platform    instagram | tiktok | facebook | twitter | gmb
      n           int, default 5, max 12

    Returns CTAs scored by (1) match-bonus (×1.0 if all 3 filters hit) +
    (2) base cta score + (3) category diversity bonus.
    """
    try:
        kb = _load_cta_knowledge()
        ctas = list(kb.get('ctas') or [])
        voice = (request.args.get('voice') or '').strip()
        pillar = (request.args.get('pillar') or '').strip()
        platform = (request.args.get('platform') or '').strip()
        try:
            n = max(1, min(int(request.args.get('n') or 5), 12))
        except (TypeError, ValueError):
            n = 5

        scored = []
        for c in ctas:
            if not isinstance(c, dict):
                continue
            base = float(c.get('score') or 50)
            bonus = 0.0
            if voice and voice in (c.get('voices') or []):
                bonus += 12
            if pillar and pillar in (c.get('pillars') or []):
                bonus += 12
            if platform and platform in (c.get('platforms') or []):
                bonus += 8
            # Category diversity: prefer categories not yet in the result
            final_score = base + bonus
            entry = dict(c)
            entry['_score'] = round(final_score, 1)
            entry['_match'] = {
                'voice': voice in (c.get('voices') or []) if voice else None,
                'pillar': pillar in (c.get('pillars') or []) if pillar else None,
                'platform': platform in (c.get('platforms') or []) if platform else None,
            }
            scored.append(entry)
        scored.sort(key=lambda x: x.get('_score', 0), reverse=True)

        # If filters were supplied, only keep CTAs that match ALL supplied filters.
        any_filter_supplied = bool(voice or pillar or platform)
        if any_filter_supplied:
            scored = [c for c in scored if not any(
                v is False for v in (c.get('_match') or {}).values() if v is not None
            )]

        # Diversity round: prefer distinct categories in top-N. With filters on,
        # we relax the diversity constraint a bit (allow duplicates when the
        # pool is small) so we don't return fewer than n.
        top = []
        cats_seen = []
        for c in scored:
            cat = c.get('category')
            if cat and cat in cats_seen and len(top) < n - 1:
                continue  # allow one duplicate if necessary
            top.append(c)
            if cat and cat not in cats_seen:
                cats_seen.append(cat)
            if len(top) >= n:
                break

        return jsonify({
            "ok": True,
            "ts": _now_iso(),
            "voice": voice or None,
            "pillar": pillar or None,
            "platform": platform or None,
            "ctas": top[:n],
            "count": min(n, len(top)),
        }), 200
    except Exception as exc:
        _app_log.exception("cta_recommend failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/intel/cta_index', methods=['GET'])
def cta_index():
    """GET /api/intel/cta_index — manifest for SPA picker.

    Returns: {ok, categories, valid_voices, valid_pillars, valid_platforms,
              seed_count, cta_count, ts}
    """
    try:
        kb = _load_cta_knowledge()
        categories = kb.get('categories') or []
        ctas = kb.get('ctas') or []
        seeds = kb.get('headline_seeds') or []
        voices = sorted({v for c in ctas if isinstance(c, dict) for v in (c.get('voices') or [])})
        pillars = sorted({p for c in ctas if isinstance(c, dict) for p in (c.get('pillars') or [])})
        platforms = sorted({pl for c in ctas if isinstance(c, dict) for pl in (c.get('platforms') or [])})
        cats = sorted({c.get('category') for c in ctas if isinstance(c, dict) and c.get('category')})
        return jsonify({
            "ok": True,
            "ts": _now_iso(),
            "categories": categories,
            "valid_voices": voices,
            "valid_pillars": pillars,
            "valid_platforms": platforms,
            "valid_categories": cats,
            "seed_count": len(seeds),
            "cta_count": len(ctas),
        }), 200
    except Exception as exc:
        _app_log.exception("cta_index failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─── MEME LORD v2 — meme historian + brand-fit recommender ─────────────

@functools.lru_cache(maxsize=4)
def _load_meme_knowledge(_cache_key=0):
    """Load and cache the meme_knowledge.json file. Data dir resolved per-call.

    The `_cache_key` argument is a sentinel so tests can call with different
    DATA_DIR envs and still get a fresh load. In normal operation we always
    call without arguments so the cache hits.
    """
    paths = _data_paths()
    candidate = os.path.join(paths['data_dir'], 'meme_knowledge.json')
    if not os.path.exists(candidate):
        # Fall back to bundled repo copy
        candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'meme_knowledge.json')
    try:
        with open(candidate, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"memes": [], "taxonomy": {"eras": [], "formats": [], "mechanisms": []}, "voice_bible": {}, "stats": {}}


def _score_meme_brand_fit(meme, voice='swing-shack', pillar='education', platform='instagram'):
    """Compute brand-fit score 0..100 for a meme given voice/pillar/platform.

    Heuristics (2026-aware — fresher is better):
      +20  voice matches
      +15  pillar matches
      +10  platform matches
      +10  still_works = True
      + 8  fatigue_risk = 'low'
      + 5  era ∈ {current, recent}  (NEW: prefer memes that aren't overplayed)
      + 4  has 3+ swingshack_fit_seeds
      - 5  era = 'classic' (2014-2017)  (these are overused by everyone)
      -10  era = 'mid' (2018-2020)
      - 5  fatigue_risk = 'medium'
      -15  fatigue_risk = 'high'
      -10  still_works = False
      - 3 per year of age beyond 2018 (peak_year decay)
    """
    import datetime
    score = 0
    reasons = []
    if voice and voice in (meme.get('voice_fit') or []):
        score += 20
        reasons.append(f'voice={voice} match (+20)')
    if pillar and pillar in (meme.get('pillar_fit') or []):
        score += 15
        reasons.append(f'pillar={pillar} match (+15)')
    if platform and platform in (meme.get('platform_fit') or []):
        score += 10
        reasons.append(f'platform={platform} match (+10)')
    if meme.get('still_works') is True:
        score += 10
        reasons.append('still_works=True (+10)')
    elif meme.get('still_works') is False:
        score -= 10
        reasons.append('still_works=False (−10)')
    fr = meme.get('fatigue_risk')
    if fr == 'low':
        score += 8
        reasons.append('fatigue_risk=low (+8)')
    elif fr == 'medium':
        score -= 5
        reasons.append('fatigue_risk=medium (−5)')
    elif fr == 'high':
        score -= 15
        reasons.append('fatigue_risk=high (−15)')
    era = (meme.get('era') or '').lower()
    if era in ('current', 'recent'):
        score += 5
        reasons.append(f'era={era} (fresh, +5)')
    elif era == 'mid':
        score -= 10
        reasons.append('era=mid (2018-2020, overused, −10)')
    elif era == 'classic':
        score -= 5
        reasons.append('era=classic (2014-2017, expected, −5)')
    peak = meme.get('peak_year')
    if isinstance(peak, int) and peak < 2026:
        age = 2026 - peak
        if age > 8:
            score -= min(15, age - 5)  # cap so we don't kill classics entirely
            reasons.append(f'peak_year {peak} (aged −{min(15, age-5)})')
    seeds = meme.get('swingshack_fit_seeds') or []
    n_seeds = min(len(seeds), 3)
    if n_seeds:
        bonus = min(4, n_seeds)
        score += bonus
        reasons.append(f'{n_seeds} fit-seeds (+{bonus})')
    score = max(0, min(100, score))
    return score, reasons


def _filter_memes(memes, era=None, fmt=None, mechanism=None, voice=None, pillar=None, platform=None,
                  only_still_works=False, search=None):
    """Apply faceted filters to the meme list."""
    out = list(memes)
    if era:
        out = [m for m in out if m.get('era') == era]
    if fmt:
        out = [m for m in out if m.get('format') == fmt]
    if mechanism:
        out = [m for m in out if m.get('mechanism') == mechanism]
    if voice:
        out = [m for m in out if voice in (m.get('voice_fit') or [])]
    if pillar:
        out = [m for m in out if pillar in (m.get('pillar_fit') or [])]
    if platform:
        out = [m for m in out if platform in (m.get('platform_fit') or [])]
    if only_still_works:
        out = [m for m in out if m.get('still_works') is True]
    if search:
        s = search.lower().strip()
        def _hit(m):
            hay = ' '.join([
                m.get('name', ''), m.get('why_it_works', ''),
                m.get('origin', ''), ' '.join(m.get('tags') or []),
                ' '.join(m.get('swingshack_fit_seeds') or []),
                m.get('format_hint', ''),
            ]).lower()
            return s in hay
        out = [m for m in out if _hit(m)]
    return out


@app.route('/api/intel/meme_knowledge', methods=['GET'])
def meme_knowledge_route():
    """GET /api/intel/meme_knowledge — full meme historian + facets + voice bible.

    Query params (all optional):
      era=classic|mid|recent|current
      format=<id>          e.g. reaction-image, two-panel-comparison
      mechanism=<id>       e.g. self-deprecating, ironic-corporate
      voice=<swing-shack|stick|bag-drop>
      pillar=<education|club-fitting|community|events>
      platform=<instagram|tiktok|twitter|facebook>
      only_still_works=1
      search=<substring>   free-text across name, why_it_works, tags, fit-seeds
      sort=brand_fit|name|peak_year
      voice_for_score=<voice>   voice used when sort=brand_fit (default swing-shack)
      pillar_for_score=<pillar> pillar used when sort=brand_fit (default education)
      platform_for_score=<platform> platform used when sort=brand_fit (default instagram)
      limit=N
    """
    kb = _load_meme_knowledge()
    memes = kb.get('memes', []) or []

    era = request.args.get('era')
    fmt = request.args.get('format')
    mechanism = request.args.get('mechanism')
    voice = request.args.get('voice')
    pillar = request.args.get('pillar')
    platform = request.args.get('platform')
    only_still_works = request.args.get('only_still_works') in ('1', 'true', 'yes')
    search = request.args.get('search') or request.args.get('q')
    sort = (request.args.get('sort') or 'brand_fit').lower()
    voice_score = request.args.get('voice_for_score', 'swing-shack')
    pillar_score = request.args.get('pillar_for_score', 'education')
    platform_score = request.args.get('platform_for_score', 'instagram')

    filtered = _filter_memes(
        memes,
        era=era, fmt=fmt, mechanism=mechanism,
        voice=voice, pillar=pillar, platform=platform,
        only_still_works=only_still_works, search=search,
    )

    # Compute brand_fit for every meme in the filtered set (used for sort + visibility)
    enriched = []
    for m in filtered:
        bf, reasons = _score_meme_brand_fit(m, voice=voice_score, pillar=pillar_score, platform=platform_score)
        enriched.append({**m, 'brand_fit': bf, 'brand_fit_reasons': reasons})

    if sort == 'name':
        enriched.sort(key=lambda x: (x.get('name') or '').lower())
    elif sort == 'peak_year':
        enriched.sort(key=lambda x: (x.get('peak_year') or 0), reverse=True)
    else:  # brand_fit (default)
        enriched.sort(key=lambda x: x.get('brand_fit', 0), reverse=True)

    try:
        limit = int(request.args.get('limit', '0')) or None
    except (TypeError, ValueError):
        limit = None
    if limit:
        enriched = enriched[:limit]

    return jsonify({
        "ok": True,
        "ts": _now_iso(),
        "summary": f"{len(enriched)} of {len(memes)} memes · voice={voice_score} pillar={pillar_score}",
        "taxonomy": kb.get('taxonomy', {}),
        "voice_bible": kb.get('voice_bible', {}),
        "stats": kb.get('stats', {}),
        "filters": {
            "era": era, "format": fmt, "mechanism": mechanism,
            "voice": voice, "pillar": pillar, "platform": platform,
            "only_still_works": only_still_works, "search": search,
            "sort": sort, "limit": limit,
            "voice_for_score": voice_score, "pillar_for_score": pillar_score,
            "platform_for_score": platform_score,
        },
        "total": len(enriched),
        "memes": enriched,
    }), 200


@app.route('/api/intel/meme_recommend', methods=['GET'])
def meme_recommend_route():
    """GET /api/intel/meme_recommend — top-N meme picks for a voice+pillar+platform.

    Query params:
      voice=<swing-shack|stick|bag-drop>   default swing-shack
      pillar=<education|club-fitting|community|events>   default education
      platform=<instagram|tiktok|twitter|facebook>       default instagram
      limit=N   default 10
      era=<classic|mid|recent|current>    optional
      format=<id>                          optional
      mechanism=<id>                       optional
      only_still_works=1                   optional
    """
    kb = _load_meme_knowledge()
    memes = kb.get('memes', []) or []

    voice = request.args.get('voice', 'swing-shack')
    pillar = request.args.get('pillar', 'education')
    platform = request.args.get('platform', 'instagram')
    era = request.args.get('era')
    fmt = request.args.get('format')
    mechanism = request.args.get('mechanism')
    only_still_works = request.args.get('only_still_works') in ('1', 'true', 'yes')

    try:
        limit = int(request.args.get('limit', '10'))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 50))

    filtered = _filter_memes(
        memes,
        era=era, fmt=fmt, mechanism=mechanism,
        voice=voice, pillar=pillar, platform=platform,
        only_still_works=only_still_works,
    )

    scored = []
    for m in filtered:
        bf, reasons = _score_meme_brand_fit(m, voice=voice, pillar=pillar, platform=platform)
        scored.append({**m, 'brand_fit': bf, 'brand_fit_reasons': reasons, 'recommendation': {
            'voice': voice,
            'pillar': pillar,
            'platform': platform,
            'fit_seed_suggestion': (m.get('swingshack_fit_seeds') or ['(no seed in knowledge base)'])[0],
        }})
    scored.sort(key=lambda x: x.get('brand_fit', 0), reverse=True)
    top = scored[:limit]

    return jsonify({
        "ok": True,
        "ts": _now_iso(),
        "summary": f"Top {len(top)} of {len(filtered)} memes for {voice}/{pillar}/{platform}",
        "criteria": {
            "voice": voice, "pillar": pillar, "platform": platform,
            "era": era, "format": fmt, "mechanism": mechanism,
            "only_still_works": only_still_works, "limit": limit,
        },
        "recommendations": top,
        "alternates": scored[limit:limit+5],
    }), 200


@app.route('/api/intel/meme_apply', methods=['POST'])
def meme_apply_route():
    """POST /api/intel/meme_apply — return a concrete caption template for a meme.

    Body (JSON):
      meme_id=<id>            required — id from meme_knowledge.json
      hook=<text>             optional — replace the caption with a Swing-Shack-specific hook
      voice=<swing-shack|stick|bag-drop>  default swing-shack
      platform=<instagram|tiktok|twitter|facebook> default instagram
      pillar=<education|club-fitting|community|events> default education
      pick_seed_index=<int>   optional — index into swingshack_fit_seeds (default 0)

    Response: a single ready-to-paste caption snippet + metadata.
    """
    body = request.get_json(silent=True) or {}
    meme_id = (body.get('meme_id') or '').strip()
    if not meme_id:
        return jsonify({"ok": False, "error": "meme_id required"}), 400

    kb = _load_meme_knowledge()
    memes = kb.get('memes', []) or []
    target = next((m for m in memes if m.get('id') == meme_id), None)
    if not target:
        return jsonify({"ok": False, "error": f"Unknown meme_id: {meme_id}"}), 404

    voice = body.get('voice', 'swing-shack')
    platform = body.get('platform', 'instagram')
    pillar = body.get('pillar', 'education')
    hook = (body.get('hook') or '').strip()
    try:
        pick_seed_index = int(body.get('pick_seed_index', 0))
    except (TypeError, ValueError):
        pick_seed_index = 0
    seeds = target.get('swingshack_fit_seeds') or []
    if seeds:
        seed = seeds[pick_seed_index % len(seeds)]
    else:
        seed = ''

    bf, reasons = _score_meme_brand_fit(target, voice=voice, pillar=pillar, platform=platform)

    # Build a caption suggestion. Three flavours: sarcastic, wholesome, hard-truth.
    sarcastic_hook = hook or f'{seed}? Deal with it. 🏌️'
    wholesome_hook = hook or f'PSA: {seed.lower()} 💚'
    hard_truth_hook = hook or f'Hard truth: {seed.lower()}.'

    voice_bible = (kb.get('voice_bible') or {}).get(voice, {})
    voice_rules = voice_bible.get('do', []) if isinstance(voice_bible, dict) else []

    return jsonify({
        "ok": True,
        "ts": _now_iso(),
        "meme": target,
        "applied": {
            "voice": voice,
            "pillar": pillar,
            "platform": platform,
            "fit_seed_used": seed,
            "user_hook": hook or None,
        },
        "brand_fit": {
            "score": bf,
            "reasons": reasons,
            "voice_bible": voice_bible,
            "voice_rules": voice_rules,
        },
        "captions": [
            {"flavour": "sarcastic", "text": sarcastic_hook, "platform_fit": platform},
            {"flavour": "wholesome", "text": wholesome_hook, "platform_fit": platform},
            {"flavour": "hard-truth", "text": hard_truth_hook, "platform_fit": platform},
        ],
        "format_hint": target.get('format_hint'),
        "why_it_works": target.get('why_it_works'),
    }), 200


# ─── HASHTAG & SEO PACK ENGINE — /api/intel/<verb> routes ─────────────

@functools.lru_cache(maxsize=4)
def _load_hashtag_seo(_cache_key=0):
    """Load hashtag_seo_pack.json with DATA_DIR + bundled fallback.

    The `_cache_key` sentinel lets tests force a fresh load when DATA_DIR is
    monkey-patched. In normal operation we always call without arguments so
    the cache hits.
    """
    paths = _data_paths()
    candidate = os.path.join(paths['data_dir'], 'hashtag_seo_pack.json')
    if not os.path.exists(candidate):
        candidate = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', 'data', 'hashtag_seo_pack.json'
        )
    try:
        with open(candidate, 'r', encoding='utf-8') as f:
            data = json.load(f)
            data.setdefault('voices', {})
            data.setdefault('pillars', {})
            data.setdefault('platforms', {})
            data.setdefault('trending_signals', [])
            data.setdefault('banned', [])
            data.setdefault('seo_templates', {})
            data.setdefault('brand', {})
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {
            "voices": {}, "pillars": {}, "platforms": {},
            "trending_signals": [], "banned": [], "seo_templates": {},
            "brand": {}, "stats": {}
        }


_VALID_PILLARS = {'education', 'club-fitting', 'community', 'events'}
_VALID_VOICES = {'swing-shack', 'stick', 'bag-drop'}
_VALID_PLATFORMS = {'instagram', 'tiktok', 'facebook', 'twitter', 'gmb'}


def _normalise_tag(tag):
    """Normalise a hashtag: lowercase, strip whitespace, ensure leading '#'."""
    if not isinstance(tag, str):
        return None
    t = tag.strip().lower()
    if not t:
        return None
    if not t.startswith('#'):
        t = '#' + t
    # strip duplicate leading '#'
    while t.startswith('##'):
        t = t[1:]
    # validate: only alnum + underscore after the '#'
    body = t[1:]
    if not body:
        return None
    return t


def _build_hashtag_set(pack, pillar, voice, platform, count, include_trending=True):
    """Compose a curated hashtag set for a (pillar, voice, platform) trio.

    Returns (ordered_list, by_category_dict). Order is:
      1) banned filter applied first
      2) brand/voice vocabulary seed (1 tag)
      3) pillar core (2-3)
      4) pillar long_tail (1-2)
      5) pillar local (1-2)
      6) pillar community (1)
      7) voice-specific (1 from vocabulary_seed)
      8) platform-specific (when recommended)
      9) trending signals that match pillar or voice
    The total list is then capped to `count`.
    """
    banned = {_normalise_tag(b['tag']) for b in pack.get('banned', []) if isinstance(b, dict)}

    pillar_obj = (pack.get('pillars') or {}).get(pillar) or {}
    voice_obj = (pack.get('voices') or {}).get(voice) or {}
    platform_obj = (pack.get('platforms') or {}).get(platform) or {}

    by_category = {
        'pillar_core': [],
        'pillar_long_tail': [],
        'pillar_local': [],
        'pillar_community': [],
        'voice_vocab': [],
        'trending': [],
        'brand': [],
    }

    # 1) Brand: Swing Shack's own markers
    for t in ('#swingshack',):
        nt = _normalise_tag(t)
        if nt and nt not in banned:
            by_category['brand'].append(nt)

    # 2) Pillar core / long-tail / local / community
    for cat_key, src_key in (
        ('pillar_core', 'core'),
        ('pillar_long_tail', 'long_tail'),
        ('pillar_local', 'local'),
        ('pillar_community', 'community'),
    ):
        for t in pillar_obj.get(src_key, []) or []:
            nt = _normalise_tag(t)
            if nt and nt not in banned:
                by_category[cat_key].append(nt)

    # 3) Voice vocabulary seed
    seed = voice_obj.get('vocabulary_seed') or []
    if seed:
        # build one voice tag from the first seed word + 'golf' suffix
        seed_word = str(seed[0]).strip().lower().replace(' ', '')
        if seed_word:
            vt = '#' + seed_word + 'golf'
            nt = _normalise_tag(vt)
            if nt and nt not in banned:
                by_category['voice_vocab'].append(nt)

    # 4) Trending signals filtered by pillar or voice
    if include_trending:
        for sig in pack.get('trending_signals', []) or []:
            if not isinstance(sig, dict):
                continue
            tag = _normalise_tag(sig.get('tag'))
            if not tag or tag in banned:
                continue
            sig_pillar = sig.get('pillar')
            sig_voice = sig.get('voice')
            if sig_pillar == pillar or sig_voice == voice:
                by_category['trending'].append(tag)

    # Compose ordered list — strict priority
    ordered = []
    seen = set()
    for key in ('brand', 'pillar_core', 'pillar_long_tail',
                'pillar_local', 'pillar_community', 'voice_vocab',
                'trending'):
        for tag in by_category[key]:
            if tag in seen:
                continue
            seen.add(tag)
            ordered.append(tag)

    # If we don't have enough, append unique pillar tags from other pillars
    if len(ordered) < count:
        for other_pillar, other_obj in (pack.get('pillars') or {}).items():
            if other_pillar == pillar:
                continue
            for src_key in ('core', 'long_tail', 'local'):
                for t in (other_obj.get(src_key) or [])[:1]:
                    nt = _normalise_tag(t)
                    if nt and nt not in seen and nt not in banned:
                        seen.add(nt)
                        ordered.append(nt)
                        if len(ordered) >= count:
                            break
                if len(ordered) >= count:
                    break
            if len(ordered) >= count:
                break

    # Cap to requested count (also respect platform max)
    platform_max = platform_obj.get('hashtag_count_max')
    cap = count
    if isinstance(platform_max, int) and platform_max > 0:
        cap = min(cap, platform_max)
    ordered = ordered[:max(1, cap)]

    # GMB returns empty (no hashtags there)
    if platform == 'gmb':
        ordered = []

    return ordered, by_category


def _score_hashtag_set(ordered_tags, by_category, platform_obj):
    """Compute a simple quality score 0..100 for a hashtag set.

    Heuristics:
      +20  has at least 1 brand tag
      +15  has 3+ pillar_core
      +15  has 1+ pillar_local
      +10  has 1+ trending
      +10  has 1+ voice_vocab
      +10  total count between platform recommended and max
      −15  total count > platform max
      −20  zero pillar_core (off-brand)
    """
    score = 0
    reasons = []
    if by_category.get('brand'):
        score += 20
        reasons.append('brand tag present (+20)')
    core = len(by_category.get('pillar_core', []))
    if core >= 3:
        score += 15
        reasons.append(f'{core} pillar core tags (+15)')
    elif core >= 1:
        score += 8
        reasons.append(f'{core} pillar core tag(s) (+8)')
    if by_category.get('pillar_local'):
        score += 15
        reasons.append('local tag present (+15)')
    if by_category.get('trending'):
        score += 10
        reasons.append('trending tag present (+10)')
    if by_category.get('voice_vocab'):
        score += 10
        reasons.append('voice tag present (+10)')
    n = len(ordered_tags)
    rec = (platform_obj or {}).get('hashtag_count_recommended')
    mx = (platform_obj or {}).get('hashtag_count_max')
    if isinstance(rec, int) and isinstance(mx, int) and rec <= n <= mx:
        score += 10
        reasons.append(f'count {n} within platform range ({rec}..{mx}) (+10)')
    if isinstance(mx, int) and mx > 0 and n > mx:
        score -= 15
        reasons.append(f'count {n} exceeds platform max {mx} (−15)')
    if core == 0:
        score -= 20
        reasons.append('no pillar core (−20)')
    score = max(0, min(100, score))
    return score, reasons


def _render_seo_pack(pack, pillar, voice, platform=None, custom_keyword=None):
    """Build a full SEO pack for a (pillar, voice, platform?) tuple.

    Returns dict with: page_title, meta_description, h1, slug, slug_rules,
    alt_text, alt_text_rules, og_description, schema_type, primary_keyword,
    secondary_keywords, score, reasons.
    """
    templates = pack.get('seo_templates') or {}
    brand = pack.get('brand') or {}
    primary_keywords = list(brand.get('primary_keywords') or [])

    # Choose a primary keyword by pillar: prefer the pillar keyword
    pillar_keyword_map = {
        'education': ['indoor golf johannesburg', 'golf lessons randburg', 'golf simulator johannesburg'],
        'club-fitting': ['club fitting johannesburg', 'custom clubs johannesburg', 'trackman johannesburg'],
        'community': ['indoor golf randburg', 'golf practice johannesburg'],
        'events': ['golf events gauteng'],
    }
    primary = custom_keyword or (
        (pillar_keyword_map.get(pillar) or primary_keywords[:1] or [''])[0]
    )
    secondary = [
        kw for kw in primary_keywords
        if kw and kw != primary
    ][:6]

    page_title = (templates.get('page_titles') or {}).get(pillar) or (
        f"{primary.title()} | Swing Shack"
    )
    meta_description = (templates.get('meta_descriptions') or {}).get(pillar) or (
        f"{primary.title()} at Swing Shack · Johannesburg's indoor golf bay."
    )
    h1 = (templates.get('h1') or {}).get(pillar) or primary.title()
    slug = (templates.get('slug_examples') or {}).get(pillar)
    if not slug:
        slug = (primary or 'swing-shack').lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug.strip())
        slug = re.sub(r'-+', '-', slug).strip('-')[:60]
    alt_text = (templates.get('alt_text_examples') or {}).get(pillar)
    og_description = (templates.get('og_description') or {}).get(pillar) or meta_description
    schema_type = (templates.get('schema_types') or {}).get(pillar) or 'LocalBusiness'

    # Score SEO pack quality
    score = 0
    reasons = []
    if page_title and len(page_title) <= 70:
        score += 15
        reasons.append('title ≤ 70 chars (+15)')
    elif page_title:
        score += 5
        reasons.append('title > 70 chars (+5)')
    if 110 <= len(meta_description) <= 160:
        score += 20
        reasons.append(f'meta description {len(meta_description)} chars in 110..160 (+20)')
    elif meta_description:
        score += 8
        reasons.append(f'meta description {len(meta_description)} chars out of range (+8)')
    if h1 and 20 <= len(h1) <= 70:
        score += 15
        reasons.append(f'h1 {len(h1)} chars (+15)')
    if slug and 20 <= len(slug) <= 60 and '-' in slug and ' ' not in slug:
        score += 15
        reasons.append('slug well-formed (+15)')
    if alt_text and 20 <= len(alt_text) <= 125:
        score += 15
        reasons.append('alt text present and sized (+15)')
    if primary and any(kw in (meta_description or '').lower() for kw in primary.split()[:2]):
        score += 10
        reasons.append('primary keyword appears in meta (+10)')
    if og_description and og_description != meta_description:
        score += 5
        reasons.append('og description distinct from meta (+5)')
    if schema_type:
        score += 5
        reasons.append('schema type set (+5)')
    score = max(0, min(100, score))

    return {
        'pillar': pillar,
        'voice': voice,
        'platform': platform,
        'page_title': page_title,
        'page_title_length': len(page_title or ''),
        'meta_description': meta_description,
        'meta_description_length': len(meta_description or ''),
        'h1': h1,
        'slug': slug,
        'slug_rules': list(templates.get('slug_rules') or []),
        'alt_text': alt_text,
        'alt_text_rules': list(templates.get('alt_text_rules') or []),
        'og_description': og_description,
        'schema_type': schema_type,
        'primary_keyword': primary,
        'secondary_keywords': secondary,
        'score': score,
        'reasons': reasons,
    }


@app.route('/api/intel/hashtags', methods=['GET'])
def intel_hashtags():
    """GET /api/intel/hashtags — curated hashtag set for (pillar, voice, platform).

    Query params:
      pillar=education|club-fitting|community|events (required)
      voice=swing-shack|stick|bag-drop (required)
      platform=instagram|tiktok|facebook|twitter|gmb (default instagram)
      count=N (1..30, default 8 — auto-respects platform max)
      include_trending=0|1 (default 1)
      search=<substring> (free-text filter across returned tags)
      banned_only=1 (return only banned tags filtered out — for diagnostics)

    Returns {ok, pillar, voice, platform, count, ordered, by_category, score,
             reasons, banned_filtered, platform_info, ts}
    """
    args = request.args
    pillar = (args.get('pillar') or '').strip()
    voice = (args.get('voice') or '').strip()
    platform = (args.get('platform') or 'instagram').strip()
    try:
        count = max(1, min(int(args.get('count', 8) or 8), 30))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "count must be an integer"}), 400
    include_trending = str(args.get('include_trending', '1')).lower() not in ('0', 'false', 'no')
    search = (args.get('search') or '').strip().lower()
    banned_only = str(args.get('banned_only', '0')).lower() in ('1', 'true', 'yes')

    if not pillar or pillar not in _VALID_PILLARS:
        return jsonify({
            "ok": False, "error": f"pillar must be one of {sorted(_VALID_PILLARS)}"
        }), 400
    if not voice or voice not in _VALID_VOICES:
        return jsonify({
            "ok": False, "error": f"voice must be one of {sorted(_VALID_VOICES)}"
        }), 400
    if platform not in _VALID_PLATFORMS:
        return jsonify({
            "ok": False, "error": f"platform must be one of {sorted(_VALID_PLATFORMS)}"
        }), 400

    pack = _load_hashtag_seo()
    if banned_only:
        banned = [_normalise_tag(b['tag']) for b in pack.get('banned', []) if isinstance(b, dict)]
        return jsonify({
            "ok": True,
            "banned_filtered": [t for t in banned if t],
            "ts": _now_iso(),
        }), 200

    ordered, by_category = _build_hashtag_set(
        pack, pillar, voice, platform, count, include_trending
    )
    if search:
        ordered = [t for t in ordered if search in t.lower()]

    platform_obj = (pack.get('platforms') or {}).get(platform) or {}
    score, reasons = _score_hashtag_set(ordered, by_category, platform_obj)

    return jsonify({
        "ok": True,
        "pillar": pillar,
        "voice": voice,
        "platform": platform,
        "count": len(ordered),
        "ordered": ordered,
        "by_category": by_category,
        "score": score,
        "reasons": reasons,
        "banned_filtered": [
            _normalise_tag(b['tag']) for b in pack.get('banned', [])
            if isinstance(b, dict) and _normalise_tag(b['tag'])
        ],
        "platform_info": {
            "label": platform_obj.get('label'),
            "hashtag_count_recommended": platform_obj.get('hashtag_count_recommended'),
            "hashtag_count_max": platform_obj.get('hashtag_count_max'),
            "placement": platform_obj.get('placement'),
            "tips": list(platform_obj.get('tips') or []),
        },
        "ts": _now_iso(),
    }), 200


@app.route('/api/intel/seo_pack', methods=['GET'])
def intel_seo_pack():
    """GET /api/intel/seo_pack — full SEO pack for (pillar, voice[, platform]).

    Query params:
      pillar=education|club-fitting|community|events (required)
      voice=swing-shack|stick|bag-drop (required)
      platform=<optional> — included in returned pack but doesn't gate it
      custom_keyword=<text> — override auto-chosen primary keyword

    Returns {ok, pillar, voice, platform, pack, ts}
    """
    args = request.args
    pillar = (args.get('pillar') or '').strip()
    voice = (args.get('voice') or '').strip()
    platform = (args.get('platform') or '').strip() or None
    custom_keyword = (args.get('custom_keyword') or '').strip() or None

    if not pillar or pillar not in _VALID_PILLARS:
        return jsonify({
            "ok": False, "error": f"pillar must be one of {sorted(_VALID_PILLARS)}"
        }), 400
    if not voice or voice not in _VALID_VOICES:
        return jsonify({
            "ok": False, "error": f"voice must be one of {sorted(_VALID_VOICES)}"
        }), 400

    pack = _load_hashtag_seo()
    seo = _render_seo_pack(pack, pillar, voice, platform=platform,
                           custom_keyword=custom_keyword)
    return jsonify({
        "ok": True,
        "pillar": pillar,
        "voice": voice,
        "platform": platform,
        "pack": seo,
        "ts": _now_iso(),
    }), 200


@app.route('/api/intel/seo_pack', methods=['POST'])
def intel_seo_pack_post():
    """POST /api/intel/seo_pack — alias that accepts JSON body for symmetry
    with caption/meme/image endpoints.

    Body: { pillar, voice, platform?, custom_keyword? }
    """
    body = request.get_json(silent=True) or {}
    pillar = str(body.get('pillar') or '').strip()
    voice = str(body.get('voice') or '').strip()
    platform = str(body.get('platform') or '').strip() or None
    custom_keyword = str(body.get('custom_keyword') or '').strip() or None

    if not pillar or pillar not in _VALID_PILLARS:
        return jsonify({
            "ok": False, "error": f"pillar must be one of {sorted(_VALID_PILLARS)}"
        }), 400
    if not voice or voice not in _VALID_VOICES:
        return jsonify({
            "ok": False, "error": f"voice must be one of {sorted(_VALID_VOICES)}"
        }), 400

    pack = _load_hashtag_seo()
    seo = _render_seo_pack(pack, pillar, voice, platform=platform,
                           custom_keyword=custom_keyword)
    return jsonify({
        "ok": True,
        "pillar": pillar,
        "voice": voice,
        "platform": platform,
        "pack": seo,
        "ts": _now_iso(),
    }), 200


@app.route('/api/intel/seo_index', methods=['GET'])
def intel_seo_index():
    """GET /api/intel/seo_index — manifest of pillars, voices, platforms,
    banned tags, trending signals, brand keywords. Used by the SPA picker.
    """
    pack = _load_hashtag_seo()
    return jsonify({
        "ok": True,
        "brand": pack.get('brand', {}),
        "voices": pack.get('voices', {}),
        "pillars": pack.get('pillars', {}),
        "platforms": pack.get('platforms', {}),
        "trending_signals": pack.get('trending_signals', []),
        "banned": pack.get('banned', []),
        "stats": pack.get('stats', {}),
        "ts": _now_iso(),
    }), 200


# ─── SEO AUDIT DETAIL (deep-dive on seo-audit.json + landing-page-fixes.json) ───

SEO_AUDIT_TYPES = ('missing_meta_description', 'missing_h1', 'title_too_short', 'missing_faq')
SEO_AUDIT_SEVERITIES = ('high', 'medium', 'low')
SEO_AUDIT_ACTION_MAP = {
    'missing_meta_description': 'Write a 110-160 char meta description with primary keyword + CTA hook',
    'missing_h1': 'Add a single H1 with primary keyword and a clear value proposition',
    'title_too_short': 'Expand the title to 50-60 chars with brand name + keyword + hook',
    'missing_faq': 'Add a 3-5 question FAQ section targeting long-tail keywords',
}


def _load_seo_audit():
    """Read seo-audit.json from DATA_DIR (or bundled fallback). Returns dict or {}."""
    paths = _data_paths()
    raw = _read_json_file(os.path.join(paths['data_dir'], 'seo-audit.json'))
    if isinstance(raw, dict):
        return raw
    return _read_json_file(os.path.join(BUNDLED_DATA_DIR, 'seo-audit.json')) or {}


def _load_landing_fixes():
    """Read landing-page-fixes.json from DATA_DIR (or bundled fallback). Returns dict or {}."""
    paths = _data_paths()
    raw = _read_json_file(os.path.join(paths['data_dir'], 'landing-page-fixes.json'))
    if isinstance(raw, dict):
        return raw
    return _read_json_file(os.path.join(BUNDLED_DATA_DIR, 'landing-page-fixes.json')) or {}


def _seo_audit_score(audit):
    """Compute a 0-100 SEO health score from audit findings.

    Penalises: high severity findings 15pts each, medium 8, low 3.
    Bonus: status==='OK' on every page gives +10.
    """
    if not audit:
        return 0
    score = 100
    recs = audit.get('recommendations') or []
    for rec in recs:
        sev = str(rec.get('severity') or '').lower()
        if sev == 'high':
            score -= 15
        elif sev == 'medium':
            score -= 8
        elif sev == 'low':
            score -= 3
    pages = audit.get('pages') or []
    if pages and all(str(p.get('status') or '').upper() == 'OK' for p in pages):
        score += 10
    return max(0, min(100, score))


def _seo_audit_group_by_page(audit):
    """Return [{page, url, status, findings:[{type, severity, message, action}], score}] sorted high→low."""
    pages = audit.get('pages') or []
    out = []
    for p in pages:
        if not isinstance(p, dict):
            continue
        findings = p.get('findings') or []
        normalised = []
        for f in findings:
            if not isinstance(f, dict):
                continue
            t = str(f.get('type') or '')
            normalised.append({
                'type': t,
                'severity': str(f.get('severity') or 'low'),
                'message': str(f.get('message') or ''),
                'action': SEO_AUDIT_ACTION_MAP.get(t, 'See audit for details'),
                'priority': 1 if str(f.get('severity') or '').lower() == 'high' else (2 if str(f.get('severity') or '').lower() == 'medium' else 3),
            })
        sev_counts = {'high': 0, 'medium': 0, 'low': 0}
        for f in normalised:
            s = f['severity'].lower()
            sev_counts[s] = sev_counts.get(s, 0) + 1
        out.append({
            'page': p.get('name') or 'Unknown',
            'url': p.get('url') or '',
            'status': p.get('status') or 'UNKNOWN',
            'findings': normalised,
            'counts': sev_counts,
            'score': max(0, 100 - sev_counts['high'] * 25 - sev_counts['medium'] * 10 - sev_counts['low'] * 3),
        })
    out.sort(key=lambda x: (-x['counts']['high'], -x['counts']['medium'], x['page']))
    return out


def _seo_fix_template(page, fix_type, custom_keyword=None):
    """Generate a ready-to-paste fix snippet for a finding type on a specific page.

    Returns {kind, snippet, character_count, character_limit, valid, notes}.
    """
    keyword = custom_keyword or 'indoor golf simulator Johannesburg'
    page_name = page.get('page') if isinstance(page, dict) else (page or 'Homepage')
    if fix_type == 'missing_meta_description':
        kw_title = keyword.title() if keyword else 'Indoor Golf Simulator Johannesburg'
        text = (f'{page_name} · {kw_title}. Book a TrackMan session at Swing Shack Johannesburg. '
                f'Open 24/7. From R250.')
        # Trim to fit 160 if necessary
        if len(text) > 160:
            text = text[:157].rstrip() + '...'
        return {
            'kind': 'meta_description',
            'snippet': text,
            'character_count': len(text),
            'character_limit': 160,
            'min_chars': 110,
            'valid': 110 <= len(text) <= 160,
            'notes': 'Should be 110-160 chars. Include primary keyword + brand + CTA.',
        }
    if fix_type == 'missing_h1':
        kw_proper = keyword.replace('johannesburg', 'Johannesburg').title() if keyword else 'Indoor Golf Simulator Johannesburg'
        text = f'Book Your {kw_proper} Session · Swing Shack'
        return {
            'kind': 'h1',
            'snippet': text,
            'character_count': len(text),
            'character_limit': 70,
            'min_chars': 20,
            'valid': 20 <= len(text) <= 70,
            'notes': 'One H1 per page. Should contain primary keyword and a value promise.',
        }
    if fix_type == 'title_too_short':
        kw_proper = keyword.title() if keyword else 'Indoor Golf Simulator Johannesburg'
        text = f'{page_name} | Swing Shack | {kw_proper}'
        # Trim to 60 if necessary
        if len(text) > 60:
            text = text[:57].rstrip() + '...'
        return {
            'kind': 'title',
            'snippet': text,
            'character_count': len(text),
            'character_limit': 60,
            'min_chars': 50,
            'valid': 50 <= len(text) <= 60,
            'notes': 'Title tags should be 50-60 chars. Include brand + keyword + hook.',
        }
    if fix_type == 'missing_faq':
        snippet = (
            'FAQ section — Suggested questions:\n'
            f'1. How much does a {keyword} session cost?\n'
            f'2. Do I need to bring my own clubs to Swing Shack Johannesburg?\n'
            '3. Can beginners use the TrackMan simulator?\n'
            '4. Is parking available at Swing Shack?\n'
            '5. How do I book a session at Swing Shack?'
        )
        return {
            'kind': 'faq_block',
            'snippet': snippet,
            'character_count': len(snippet),
            'character_limit': 2000,
            'min_chars': 200,
            'valid': 200 <= len(snippet) <= 2000,
            'notes': 'Add FAQPage schema markup. Each Q&A targets long-tail keywords.',
        }
    return {
        'kind': 'unknown',
        'snippet': '',
        'character_count': 0,
        'character_limit': 0,
        'min_chars': 0,
        'valid': False,
        'notes': f'No template available for type {fix_type}',
    }


@app.route('/api/intel/seo_audit_detail', methods=['GET'])
def intel_seo_audit_detail():
    """GET /api/intel/seo_audit_detail — deep-dive on seo-audit.json.

    Query params:
      page=Homepage|Membership|Coaching|Club Fitting   (filter to one page)
      type=missing_meta_description|missing_h1|title_too_short|missing_faq
      severity=high|medium|low
      only_fixable=true  (hide low/medium — only what needs immediate work)

    Returns:
      { ok, ts, site, updated, score, band, total_findings, by_severity,
        by_type, by_page, recommendations, top_priority_actions }
    """
    audit = _load_seo_audit()
    if not audit:
        return jsonify({
            "ok": False,
            "error": "No seo-audit.json available",
            "ts": _now_iso(),
        }), 404

    page_filter = (request.args.get('page') or '').strip()
    type_filter = (request.args.get('type') or '').strip()
    sev_filter = (request.args.get('severity') or '').strip().lower()
    only_fixable = str(request.args.get('only_fixable') or '').lower() in ('1', 'true', 'yes')

    if page_filter and page_filter not in [p.get('name') for p in (audit.get('pages') or [])]:
        return jsonify({
            "ok": False,
            "error": f"Unknown page '{page_filter}'. Valid: {[p.get('name') for p in (audit.get('pages') or [])]}",
            "valid_pages": [p.get('name') for p in (audit.get('pages') or [])],
        }), 400

    if type_filter and type_filter not in SEO_AUDIT_TYPES:
        return jsonify({
            "ok": False,
            "error": f"Unknown audit type '{type_filter}'. Valid: {list(SEO_AUDIT_TYPES)}",
            "valid_types": list(SEO_AUDIT_TYPES),
        }), 400

    if sev_filter and sev_filter not in SEO_AUDIT_SEVERITIES:
        return jsonify({
            "ok": False,
            "error": f"Unknown severity '{sev_filter}'. Valid: {list(SEO_AUDIT_SEVERITIES)}",
            "valid_severities": list(SEO_AUDIT_SEVERITIES),
        }), 400

    page_breakdown = _seo_audit_group_by_page(audit)

    if page_filter:
        page_breakdown = [p for p in page_breakdown if p['page'] == page_filter]

    by_type = {t: 0 for t in SEO_AUDIT_TYPES}
    for p in page_breakdown:
        for f in p['findings']:
            if f['type'] in by_type:
                by_type[f['type']] += 1

    recommendations = []
    for rec in (audit.get('recommendations') or []):
        if not isinstance(rec, dict):
            continue
        if page_filter and rec.get('page') != page_filter:
            continue
        if sev_filter and str(rec.get('severity') or '').lower() != sev_filter:
            continue
        if type_filter and rec.get('type') != type_filter:
            continue
        if only_fixable and str(rec.get('severity') or '').lower() not in ('high', 'medium'):
            continue
        recommendations.append({
            'type': rec.get('type'),
            'severity': str(rec.get('severity') or 'low').lower(),
            'message': rec.get('message') or '',
            'page': rec.get('page') or '',
            'action': rec.get('action') or SEO_AUDIT_ACTION_MAP.get(rec.get('type'), ''),
            'priority': rec.get('priority') or 99,
        })
    recommendations.sort(key=lambda r: (r['priority'], r['page']))

    # by_severity mirrors the recommendation filter set so the UX stays
    # consistent (filter by severity → only that severity in counts).
    by_severity = {'high': 0, 'medium': 0, 'low': 0}
    for r in recommendations:
        s = r['severity']
        by_severity[s] = by_severity.get(s, 0) + 1

    top_priority_actions = [r for r in recommendations if r['severity'] == 'high'][:8]

    score = _seo_audit_score(audit if not page_filter else {'pages': [p for p in (audit.get('pages') or []) if p.get('name') == page_filter]})
    if score >= 85:
        band = 'healthy'
    elif score >= 65:
        band = 'needs_attention'
    elif score >= 40:
        band = 'poor'
    else:
        band = 'critical'

    return jsonify({
        "ok": True,
        "ts": _now_iso(),
        "site": audit.get('site') or '',
        "updated": audit.get('updated'),
        "score": score,
        "band": band,
        "total_findings": audit.get('total_findings') or sum(by_severity.values()),
        "by_severity": by_severity,
        "by_type": by_type,
        "by_page": page_breakdown,
        "recommendations": recommendations,
        "top_priority_actions": top_priority_actions,
        "filters_applied": {
            "page": page_filter or None,
            "type": type_filter or None,
            "severity": sev_filter or None,
            "only_fixable": only_fixable,
        },
        "valid_types": list(SEO_AUDIT_TYPES),
        "valid_severities": list(SEO_AUDIT_SEVERITIES),
        "valid_pages": [p.get('name') for p in (audit.get('pages') or [])],
    }), 200


@app.route('/api/intel/seo_audit_fix_draft', methods=['POST'])
def intel_seo_audit_fix_draft():
    """POST /api/intel/seo_audit_fix_draft — generate a ready-to-paste fix snippet.

    Body (JSON):
      { page: 'Homepage',          # required
        type: 'missing_meta_description',  # required
        custom_keyword: 'indoor golf'  # optional override
      }

    Returns:
      { ok, ts, page, type, fix: {kind, snippet, character_count, character_limit,
                                   min_chars, valid, notes} }
    """
    body = request.get_json(silent=True) or {}
    page_name = str(body.get('page') or '').strip()
    fix_type = str(body.get('type') or '').strip()
    custom_keyword = body.get('custom_keyword')

    if not page_name:
        return jsonify({"ok": False, "error": "page is required"}), 400
    if not fix_type:
        return jsonify({"ok": False, "error": "type is required"}), 400
    if fix_type not in SEO_AUDIT_TYPES:
        return jsonify({
            "ok": False,
            "error": f"Unknown type '{fix_type}'. Valid: {list(SEO_AUDIT_TYPES)}",
            "valid_types": list(SEO_AUDIT_TYPES),
        }), 400

    # Verify page exists in audit
    audit = _load_seo_audit()
    pages = audit.get('pages') or []
    page_match = next((p for p in pages if isinstance(p, dict) and p.get('name') == page_name), None)
    if page_match is None:
        return jsonify({
            "ok": False,
            "error": f"Page '{page_name}' not in audit. Valid: {[p.get('name') for p in pages]}",
            "valid_pages": [p.get('name') for p in pages],
        }), 404

    if custom_keyword is not None and not isinstance(custom_keyword, str):
        return jsonify({"ok": False, "error": "custom_keyword must be a string"}), 400

    fix = _seo_fix_template({'page': page_name}, fix_type, custom_keyword=custom_keyword)
    return jsonify({
        "ok": True,
        "ts": _now_iso(),
        "page": page_name,
        "type": fix_type,
        "action": SEO_AUDIT_ACTION_MAP.get(fix_type, ''),
        "fix": fix,
    }), 200


@app.route('/api/intel/seo_audit_index', methods=['GET'])
def intel_seo_audit_index():
    """GET /api/intel/seo_audit_index — manifest of audit + landing-page-fixes.

    Used by SPA to populate filter dropdowns and summary cards.
    """
    audit = _load_seo_audit()
    fixes = _load_landing_fixes()
    pages = audit.get('pages') or []
    fix_list = fixes.get('fixes') or []
    score = _seo_audit_score(audit)
    return jsonify({
        "ok": True,
        "ts": _now_iso(),
        "site": audit.get('site') or '',
        "updated": audit.get('updated'),
        "score": score,
        "total_findings": audit.get('total_findings') or 0,
        "pages": [p.get('name') for p in pages if isinstance(p, dict)],
        "types": list(SEO_AUDIT_TYPES),
        "severities": list(SEO_AUDIT_SEVERITIES),
        "action_map": SEO_AUDIT_ACTION_MAP,
        "landing_fixes_summary": {
            "total": fixes.get('summary', {}).get('total_fixes') or len(fix_list),
            "high_severity": fixes.get('summary', {}).get('high_severity') or 0,
            "top_page": fixes.get('summary', {}).get('top_page'),
            "top_fix": fixes.get('summary', {}).get('top_fix'),
            "expected_lift": fixes.get('summary', {}).get('expected_lift'),
        },
        "landing_fixes": fix_list,
    }), 200


# ─── PLAN ROUTES ──────────────────────────────────────────────────────

@app.route('/api/plan/portfolio', methods=['GET'])
def plan_portfolio_route():
    """GET /api/plan/portfolio — full plan for every campaign."""
    if not _PLANNER_AVAILABLE:
        return jsonify({"ok": False, "error": "Planner unavailable"}), 503
    try:
        return jsonify(plan_portfolio()), 200
    except Exception as exc:
        _app_log.exception("plan_portfolio failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/plan/<campaign_id>', methods=['GET'])
def plan_campaign_route(campaign_id):
    """GET /api/plan/<campaign_id> — full marketing plan for one campaign."""
    if not _PLANNER_AVAILABLE:
        return jsonify({"ok": False, "error": "Planner unavailable"}), 503
    try:
        return jsonify(plan_campaign(campaign_id)), 200
    except Exception as exc:
        _app_log.exception("plan_campaign failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route('/api/plan/index', methods=['GET'])
def plan_index():
    """GET /api/plan/index — planner endpoint index."""
    return jsonify({
        "ok": True,
        "endpoints": ["portfolio", "campaign/<id>"],
        "available": _PLANNER_AVAILABLE,
        "usage": "GET /api/plan/portfolio | GET /api/plan/<campaign_id>",
    })


def _truth_store():
    """Construct a fresh EngagementStore pointed at DATA_DIR."""
    return EngagementStore(DATA_DIR)


@app.route('/api/engagement/ingest-publish-event', methods=['POST'])
def tc_ingest_publish_event():
    """POST /api/engagement/ingest-publish-event
    Body: { post_id, status, published_at, channel, metadata? }
    Server-side only. The browser does NOT call this directly — Postiz webhook does.
    """
    if not _TRUTH_COLLECTOR_AVAILABLE:
        return jsonify({"error": "Truth Collector unavailable"}), 503
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "JSON body required"}), 400
    result = truth_collector_ingest_publish_event(payload, _truth_store())
    status_code = 200 if result.get("ok") else 400
    if result.get("reason") == "credentials_missing":
        status_code = 503  # BLOCKED state
    return jsonify(result), status_code


@app.route('/api/engagement/ingest-cron-tick', methods=['POST'])
def tc_ingest_cron_tick():
    """POST /api/engagement/ingest-cron-tick
    Body: {} (or omitted). Iterates all published assets.
    Server-side only. The cron worker calls this.
    """
    if not _TRUTH_COLLECTOR_AVAILABLE:
        return jsonify({"error": "Truth Collector unavailable"}), 503
    data = load_data()
    result = truth_collector_ingest_cron_tick(_truth_store(), data)
    status_code = 200 if result.get("ok") else 500
    return jsonify(result), status_code


@app.route('/api/engagement/ingest-manual-trigger/<campaign_id>', methods=['POST'])
def tc_ingest_manual_trigger(campaign_id):
    """POST /api/engagement/ingest-manual-trigger/<campaign_id>
    Server-side only. Called by future Stage 5+ UI surface or direct dev call.
    """
    if not _TRUTH_COLLECTOR_AVAILABLE:
        return jsonify({"error": "Truth Collector unavailable"}), 503
    data = load_data()
    result = truth_collector_ingest_manual_trigger(campaign_id, _truth_store(), data)
    status_code = 200 if result.get("ok") else 404
    return jsonify(result), status_code


@app.route('/api/engagement/<asset_id>', methods=['GET'])
def tc_get_engagement_history(asset_id):
    """GET /api/engagement/<asset_id>
    Read-only accessor. Returns the append-only engagement history for an asset.
    Browser reads via this endpoint only — never bypasses.
    """
    if not _TRUTH_COLLECTOR_AVAILABLE:
        return jsonify({"error": "Truth Collector unavailable"}), 503
    history = truth_collector_get_engagement_history(asset_id, _truth_store())
    if history is None:
        return jsonify({"assetId": asset_id, "history": []}), 200
    return jsonify({"assetId": asset_id, "history": history, "count": len(history)}), 200


@app.route('/api/engagement/health', methods=['GET'])
def tc_health():
    """GET /api/engagement/health
    Truth Collector state. Reports credential presence (boolean only, no values).
    """
    if not _TRUTH_COLLECTOR_AVAILABLE:
        return jsonify({"available": False}), 503
    store = _truth_store()
    state = store._read()
    return jsonify({
        "available": True,
        "credentials": {
            "ga4": ga4_credentials_present(),
            "meta": meta_credentials_present(),
        },
        "historyCount": len(state.get("history", [])),
        "lastRunAt": state.get("lastRunAt"),
        "lastSuccessAt": state.get("lastSuccessAt"),
        "lastErrorAt": state.get("lastErrorAt"),
    }), 200


# ─── BRAND REGISTRY — multi-brand partition for Campaign OS ────────────
# Top-level partition: every campaign, asset, hook, meme, caption, GBP post,
# FAQ, scheduled item and published item belongs to exactly one brand.
# Brand selection (via ?brand_id= or X-Brand header) filters every endpoint.
# Default brand is "swing-shack" (the operational default).

BRANDS_FILE = os.path.join(BUNDLED_DATA_DIR, 'brands.json')


def load_brands_registry():
    """Load the canonical brand registry. Idempotent + cached."""
    if os.path.exists(BRANDS_FILE):
        with open(BRANDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "schema": "https://campaign-os/brands/v1",
        "version": "1.0",
        "default_brand_id": "swing-shack",
        "brands": {
            "swing-shack": {
                "id": "swing-shack", "display_name": "Swing Shack",
                "voice_id": "swing-shack", "icon": "⛳",
                "active": True, "order": 1, "short_label": "SS",
                "tagline": "Johannesburg's home of better golf.",
                "primary_color": "#0F766E", "accent_color": "#F59E0B",
            }
        }
    }


def get_brand_id():
    """Resolve the active brand from request headers or query string."""
    bid = request.headers.get('X-Brand') or request.args.get('brand_id') or request.args.get('brand')
    if bid:
        return bid
    registry = load_brands_registry()
    return registry.get('default_brand_id') or 'swing-shack'


def resolve_data_brand(brand_id: str) -> str:
    """For analytics endpoints, return the brand whose data files should be read.

    Sub-brands (Stick, Bag Drop, Takomo) delegate analytics to swing-shack so
    we don't need separate IG / GBP / GA4 files per brand. The brand_id is
    still used for voice/positioning/colour in the UI layer — only the
    analytics endpoints swap to the delegate source.
    """
    if not brand_id:
        return 'swing-shack'
    registry = load_brands_registry()
    brand = (registry.get('brands') or {}).get(brand_id) or {}
    delegate = brand.get('data_delegates_from')
    if delegate and isinstance(delegate, str):
        return delegate
    return brand_id


def brand_published_ids(brand_id):
    """Collect all asset IDs that belong to a brand. Used by filter helpers."""
    data = load_data()
    out = set()
    for cid, c in (data.get('campaigns') or {}).items():
        if c.get('brand_id') != brand_id:
            continue
        for aid in (c.get('assets') or {}).keys():
            out.add(aid)
    return out


@app.route('/api/brands', methods=['GET'])
def list_brands():
    """GET /api/brands — all registered brands with their voice + campaign counts."""
    registry = load_brands_registry()
    data = load_data()
    # Annotate each brand with the count of campaigns + assets that belong to it
    out = {}
    for bid, brand in (registry.get('brands') or {}).items():
        if not brand.get('active', True):
            continue
        campaigns = [c for c in (data.get('campaigns') or {}).values() if c.get('brand_id') == bid]
        asset_count = sum(len(c.get('assets') or {}) for c in campaigns)
        out[bid] = dict(brand)
        out[bid]['campaign_count'] = len(campaigns)
        out[bid]['asset_count'] = asset_count
    return jsonify({
        "default_brand_id": registry.get('default_brand_id'),
        "active_brand_id": get_brand_id(),
        "brands": out,
        "count": len(out),
    }), 200


@app.route('/api/brands/<brand_id>', methods=['GET'])
def get_brand(brand_id):
    """GET /api/brands/<id> — single brand full record."""
    registry = load_brands_registry()
    brand = (registry.get('brands') or {}).get(brand_id)
    if not brand:
        return jsonify({"error": "Brand not found", "brand_id": brand_id}), 404
    data = load_data()
    campaigns = [c for c in (data.get('campaigns') or {}).values() if c.get('brand_id') == brand_id]
    return jsonify({
        "brand": brand,
        "campaigns": [{"id": cid, "name": c.get('identity', {}).get('name', cid)}
                      for cid, c in (data.get('campaigns') or {}).items()
                      if c.get('brand_id') == brand_id],
        "asset_count": sum(len(c.get('assets') or {}) for c in campaigns),
        "voice_bible": _load_voice_bible_brand(brand_id),
    }), 200


def _load_voice_bible_brand(brand_id):
    """Read voice_bible.json#voices/<brand_id> for the given brand."""
    path = os.path.join(BUNDLED_DATA_DIR, 'voice_bible.json')
    try:
        with open(path) as f:
            bible = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return (bible.get('voices') or {}).get(brand_id)


@app.route('/api/brands/<brand_id>/bootstrap', methods=['POST'])
def bootstrap_brand(brand_id):
    """POST /api/brands/<id>/bootstrap — scaffold empty campaign-data partition for new brand.
    Idempotent: if a brand already has data, returns 200 with current state."""
    registry = load_brands_registry()
    if brand_id not in (registry.get('brands') or {}):
        return jsonify({"error": "Unknown brand", "brand_id": brand_id}), 404
    data = load_data()
    data.setdefault('brand_partitions', {})
    if data['brand_partitions'].get(brand_id, {}).get('bootstrapped'):
        return jsonify({"ok": True, "brand_id": brand_id, "already_bootstrapped": True,
                        "partition": data['brand_partitions'][brand_id]}), 200
    data['brand_partitions'][brand_id] = {
        "bootstrapped": True,
        "bootstrapped_at": _now_iso(),
        "campaign_count": sum(1 for c in (data.get('campaigns') or {}).values() if c.get('brand_id') == brand_id),
        "asset_count": sum(len(c.get('assets') or {}) for c in (data.get('campaigns') or {}).values() if c.get('brand_id') == brand_id),
    }
    save_data(data)
    return jsonify({"ok": True, "brand_id": brand_id,
                    "partition": data['brand_partitions'][brand_id]}), 200


@app.route('/api/brands/<brand_id>/select', methods=['POST'])
def select_brand(brand_id):
    """POST /api/brands/<id>/select — record the active brand selection (persisted preference).
    Used by the SPA brand switcher to remember which brand is open."""
    registry = load_brands_registry()
    if brand_id not in (registry.get('brands') or {}):
        return jsonify({"error": "Unknown brand", "brand_id": brand_id}), 404
    # Persisted preference lives in theme-preferences.json alongside the theme
    paths = _data_paths()
    state_path = os.path.join(paths['data_dir'], 'active-brand.json')
    os.makedirs(paths['data_dir'], exist_ok=True)
    with open(state_path, 'w') as f:
        json.dump({"brand_id": brand_id, "selected_at": _now_iso()}, f, indent=2)
    return jsonify({"ok": True, "brand_id": brand_id}), 200


@app.route('/api/brands/active', methods=['GET'])
def get_active_brand():
    """GET /api/brands/active — read the persisted brand preference (if any)."""
    paths = _data_paths()
    state_path = os.path.join(paths['data_dir'], 'active-brand.json')
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                pref = json.load(f)
                return jsonify({"brand_id": pref.get('brand_id', get_brand_id()),
                                "selected_at": pref.get('selected_at'),
                                "source": "preference"}), 200
        except (json.JSONDecodeError, OSError):
            pass
    return jsonify({"brand_id": get_brand_id(), "source": "default"}), 200


# ─── BRAND-AWARE DATA FILTER HELPER ─────────────────────────────────────

def _brand_filtered_campaigns(brand_id=None):
    """Return campaigns filtered by brand_id. Falls back to all if brand_id is None."""
    bid = brand_id or get_brand_id()
    data = load_data()
    out = {}
    for cid, c in (data.get('campaigns') or {}).items():
        if c.get('brand_id') == bid:
            out[cid] = c
    return out, bid


def _brand_filtered_assets(brand_id=None):
    """Return a flat list of all assets across campaigns, brand-scoped."""
    campaigns, bid = _brand_filtered_campaigns(brand_id)
    out = []
    for cid, c in campaigns.items():
        for aid, a in (c.get('assets') or {}).items():
            entry = dict(a)
            entry['_campaign_id'] = cid
            entry['_campaign_name'] = (c.get('identity') or {}).get('name', cid)
            entry['_brand_id'] = c.get('brand_id', bid)
            out.append(entry)
    return out


# ─── BRAND CONTEXT (used by SPA + generators to know which brand is active) ──

@app.route('/api/intel/brand-context', methods=['GET'])
def intel_brand_context():
    """GET /api/intel/brand-context — return the active brand + its voice bible + filters.
    Used by the SPA to render the brand switcher and by generators (captions/memes/CTAs) to
    scope to the active brand's voice + tone options."""
    bid = get_brand_id()
    registry = load_brands_registry()
    brand = (registry.get('brands') or {}).get(bid) or {}
    voice_bible = _load_voice_bible_brand(bid)
    data = load_data()
    campaigns = [c for c in (data.get('campaigns') or {}).values() if c.get('brand_id') == bid]
    return jsonify({
        "brand_id": bid,
        "brand": brand,
        "voice_bible": voice_bible,
        "tone_options": brand.get('tone_options', []) or [],
        "pillar_defaults": brand.get('pillar_defaults', []) or [],
        "campaigns": [{"id": cid, "name": (c.get('identity') or {}).get('name', cid)}
                      for cid, c in (data.get('campaigns') or {}).items()
                      if c.get('brand_id') == bid],
        "asset_count": sum(len(c.get('assets') or {}) for c in campaigns),
        "available_brands": [
            {"id": b.get('id'), "display_name": b.get('display_name'),
             "icon": b.get('icon'), "short_label": b.get('short_label'),
             "campaign_count": sum(1 for c in (data.get('campaigns') or {}).values() if c.get('brand_id') == b.get('id'))}
            for b in (registry.get('brands') or {}).values() if b.get('active', True)
        ],
    }), 200


# ─── WEEKLY MARKETING REPORT ────────────────────────────────────────────
# Generates a brand-aware weekly report matching the Stick layout:
#   • Hero with H1 + focus pills
#   • TL;DR (5 bullets, plain English, top of page)
#   • 4 metric cards (weekly snapshot)
#   • Comparison table vs previous week
#   • Facebook / Instagram 28-day tables
#   • Top content earning attention
#   • Website + acquisition (GA4)
#   • Google Ads (honest "not configured" if no token)
#   • What's working / Needs attention / This week's focus
#   • Footer with date windows + caveats
#
# Available as:
#   • GET  /api/weekly-report?brand=<id>&format=html|json|markdown
#   • GET  /weekly-report?brand=<id>              (HTML page with downloads)
#   • Cron /api/weekly-report/snapshot?brand=<id>  (archive current week)

WEEKLY_REPORT_DATA_DIR = os.path.join(DATA_DIR, 'weekly-snapshots')
os.makedirs(WEEKLY_REPORT_DATA_DIR, exist_ok=True)


def _weekly_brand_meta(bid):
    """Load brand meta + voice + pillars for report hero."""
    registry = load_brands_registry()
    brand = (registry.get('brands') or {}).get(bid) or {}
    voice = _load_voice_bible_brand(bid)
    return {
        'id': bid,
        'display_name': brand.get('display_name', bid),
        'tagline': brand.get('tagline', ''),
        'positioning': brand.get('positioning', ''),
        'primary_color': brand.get('primary_color', '#d7b46a'),
        'audience': brand.get('audience', ''),
        'pillar_defaults': brand.get('pillar_defaults', []) or [],
        'voice_label': brand.get('voice_label', ''),
        'voice_bible': voice,
    }


def _weekly_pct(curr, prev):
    """Compute % change between two numbers. Returns (pct_str, direction, raw_pct)."""
    try:
        c = float(curr)
        p = float(prev)
        if p == 0:
            if c == 0: return ('0.0%', 'neutral', 0.0)
            return ('n/a', 'up', None)
        raw = (c - p) / p * 100
        sign = '+' if raw > 0 else ''
        return (f'{sign}{raw:.1f}%', 'up' if raw > 0 else ('down' if raw < 0 else 'neutral'), raw)
    except (ValueError, TypeError):
        return ('n/a', 'neutral', None)


def _weekly_safe_div(a, b):
    try:
        return float(a) / float(b) if float(b) != 0 else 0
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


def _weekly_collect_current(bid):
    """Pull the current week's raw metrics from every data source we have.
    Returns a dict; every value has a source + window tag so the doc can cite honestly."""
    out = {
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'brand_id': bid,
        'sources': [],
        'weekly': {},    # last 7 days
        '28d': {},       # last 28 days
    }

    # 1) GA4 — last 7 days (resilient: missing keys → zero + tagged)
    # Try runtime DATA_DIR first; fall back to bundled repo copy.
    try:
        ga4_path = _resolve_data_path('ga4-metrics.json')
        if os.path.exists(ga4_path):
            ga = _read_json_file(ga4_path) or {}
            window = ga.get('data_window', 'unknown')
            out['sources'].append({'name': 'ga4', 'window': window, 'fetched_at': ga.get('fetched_at')})
            out['weekly']['ga4_sessions'] = ga.get('total_sessions', 0)
            # Top pages — collapse (pagePath, sessionSource) duplicates so the
            # homepage doesn't dominate the top-5 with one row per source.
            # Defence-in-depth: matches the aggregator in performance_view().
            raw_pages = ga.get('pages', []) or []
            by_path = {}
            for p in raw_pages:
                if not isinstance(p, dict):
                    continue
                pp = p.get('path', '')
                if not pp:
                    continue
                cur = by_path.get(pp) or {'sessions': 0, '_er_sum': 0.0, '_n': 0}
                cur['sessions'] += (p.get('sessions') or 0)
                try:
                    er_raw = p.get('engRate') or p.get('engagementRate') or 0
                    cur['_er_sum'] += float(str(er_raw).replace('%', '')) if er_raw else 0.0
                except (ValueError, TypeError):
                    pass
                cur['_n'] += 1
                by_path[pp] = cur
            agg = []
            for pp, v in by_path.items():
                n = v['_n'] or 1
                er = v['_er_sum'] / n
                agg.append({'path': pp, 'sessions': v['sessions'],
                            'engagement_rate': f"{er:.1f}%"})
            agg.sort(key=lambda x: x['sessions'], reverse=True)
            out['weekly']['ga4_top_pages'] = agg[:5]
            out['weekly']['ga4_sources'] = [{'source': s.get('source'), 'sessions': s.get('sessions', 0)} for s in (ga.get('sources') or [])[:6]]
    except Exception as e:
        out['sources'].append({'name': 'ga4', 'error': str(e)})

    # 2) Instagram analytics — last 28 days; fallback to bundled data dir
    try:
        ig_path = _resolve_data_path(os.path.join('analytics', 'instagram-analytics.json'))
        if os.path.exists(ig_path):
            ig = _read_json_file(ig_path) or {}
            top = ig.get('topPerformers', []) or []
            out['28d']['ig_top_performers'] = top[:5]
            # Aggregate engagement — defensive None-coalescing on every field
            # because the Instagram JSON sometimes stores null for like_count
            # / comments_count / shares / saves / follows depending on whether
            # the field was present at fetch time.
            posts = ig.get('posts', []) or []
            if posts:
                interactions = sum(((p.get('like_count') or 0) + (p.get('comments_count') or 0) + (p.get('shares') or 0) + (p.get('saves') or 0)) for p in posts)
                reach = sum((p.get('reach') or 0) for p in posts)
                followers = sum((p.get('follows') or 0) for p in posts)
                views = sum((p.get('views') or 0) for p in posts)
                out['28d']['ig_posts'] = len(posts)
                out['28d']['ig_interactions'] = interactions
                out['28d']['ig_reach'] = reach
                out['28d']['ig_follows'] = followers
                out['28d']['ig_views'] = views
            out['sources'].append({'name': 'instagram', 'fetched_at': ig.get('lastUpdated'), 'posts_tracked': ig.get('totalPostsTracked')})
        else:
            out['sources'].append({'name': 'instagram', 'error': 'instagram-analytics.json not found'})
    except Exception as e:
        out['sources'].append({'name': 'instagram', 'error': str(e)})

    # 3) Meta Graph API — for Facebook (last 28 days)
    # Honest "not configured" if tokens missing
    try:
        from meta_api import list_recent_posts  # local helper if available
        posts = list_recent_posts(days=28) or []
        if posts:
            out['sources'].append({'name': 'meta_graph', 'posts': len(posts)})
            out['28d']['fb_posts'] = len(posts)
            out['28d']['fb_top_posts'] = sorted(posts, key=lambda p: -(p.get('views') or p.get('like_count', 0)))[:5]
    except Exception:
        out['sources'].append({'name': 'meta_graph', 'configured': False})

    # 4) Google Ads — honest "not configured" if no token; fallback to bundled
    google_ads_path = _resolve_data_path('google-ads.json')
    if os.path.exists(google_ads_path):
        ga = _read_json_file(google_ads_path) or {}
        out['sources'].append({'name': 'google_ads', 'configured': True})
        out['weekly']['google_ads'] = ga
    else:
        out['sources'].append({'name': 'google_ads', 'configured': False})

    # 5) Booking events / closure / value model — brand-aware where possible
    try:
        bk = _read_json_file(os.path.join(DATA_DIR, 'booking-events.json')) or {}
        out['weekly']['bookings_total'] = (bk.get('summary') or {}).get('total', 0)
    except Exception:
        out['weekly']['bookings_total'] = 0

    # 6) Content published in last 7 days — derive from campaign-data.json
    try:
        data = load_data()
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
        created = 0
        for camp in (data.get('campaigns') or {}).values():
            if camp.get('brand_id') not in (bid, None):
                # Brand-agnostic count if no brand filter; else only matching
                if camp.get('brand_id') and camp.get('brand_id') != bid:
                    continue
            for aid, asset in (camp.get('assets') or {}).items():
                ts = asset.get('created_at') or asset.get('createdAt')
                if ts:
                    try:
                        if datetime.datetime.fromisoformat(ts.replace('Z', '+00:00')) > cutoff:
                            created += 1
                    except (ValueError, AttributeError):
                        pass
        out['weekly']['content_published'] = created
    except Exception:
        out['weekly']['content_published'] = 0

    # 7) Review queue depth — drafts waiting for human review
    try:
        rq = _read_json_file(os.path.join(DATA_DIR, 'approval-queue.json')) or {}
        out['weekly']['review_pending'] = rq.get('total', 0)
    except Exception:
        out['weekly']['review_pending'] = 0

    return out


def _weekly_prev_snapshot(bid):
    """Load the most recent previous snapshot for comparison. Returns None if first ever run.

    'Previous' = the latest snapshot archived in a week *earlier* than the current
    one. This avoids the case where archiving this week's snapshot makes it appear
    as 'previous' (always 0% delta) until next week."""
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        cur_year, cur_week, _ = now.isocalendar()
        snaps = sorted(
            [f for f in os.listdir(WEEKLY_REPORT_DATA_DIR) if f.startswith(f'{bid}_') and f.endswith('.json')],
            reverse=True
        )
        for f in snaps:
            # Filename: <bid>_<year>-W<week>.json — parse the week out
            try:
                stem = f[len(bid) + 1:-5]  # strip "<bid>_" and ".json"
                year_s, week_s = stem.split('-W')
                y, w = int(year_s), int(week_s)
                if (y, w) < (cur_year, cur_week):
                    return _read_json_file(os.path.join(WEEKLY_REPORT_DATA_DIR, f))
            except (ValueError, IndexError):
                continue
        return None
    except Exception:
        return None


def _weekly_save_snapshot(bid, current):
    """Archive the current snapshot under a week-stamped filename."""
    now = datetime.datetime.now(datetime.timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    fname = f'{bid}_{iso_year}-W{iso_week:02d}.json'
    fpath = os.path.join(WEEKLY_REPORT_DATA_DIR, fname)
    payload = dict(current)
    payload['archived_at'] = now.isoformat()
    payload['iso_year'] = iso_year
    payload['iso_week'] = iso_week
    try:
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, default=str)
        return fpath
    except Exception as e:
        return f'ERROR: {e}'


def _weekly_compute_metrics(bid):
    """Pull current + previous snapshot and produce all metric rows used in the doc."""
    current = _weekly_collect_current(bid)
    prev = _weekly_prev_snapshot(bid)

    c_weekly = current.get('weekly', {}) or {}
    c_28d = current.get('28d', {}) or {}
    p_weekly = (prev or {}).get('weekly', {}) or {}
    p_28d = (prev or {}).get('28d', {}) or {}

    # Build comparison table rows: (label, curr, prev, fmt)
    rows = [
        {
            'label': 'Content published',
            'current': c_weekly.get('content_published', 0),
            'previous': p_weekly.get('content_published', 0),
            'fmt': 'int',
        },
        {
            'label': 'Facebook reach',
            'current': c_28d.get('fb_reach', 0),
            'previous': p_28d.get('fb_reach', 0),
            'fmt': 'k',  # formatted as "1.2K"
        },
        {
            'label': 'Instagram reach',
            'current': c_28d.get('ig_reach', 0),
            'previous': p_28d.get('ig_reach', 0),
            'fmt': 'k',
        },
        {
            'label': 'Instagram interactions',
            'current': c_28d.get('ig_interactions', 0),
            'previous': p_28d.get('ig_interactions', 0),
            'fmt': 'int',
        },
        {
            'label': 'New contacts / leads',
            'current': c_weekly.get('leads', 0),
            'previous': p_weekly.get('leads', 0),
            'fmt': 'int',
        },
        {
            'label': 'Website sessions (GA4)',
            'current': c_weekly.get('ga4_sessions', 0),
            'previous': p_weekly.get('ga4_sessions', 0),
            'fmt': 'int',
        },
        {
            'label': 'Review queue depth',
            'current': c_weekly.get('review_pending', 0),
            'previous': p_weekly.get('review_pending', 0),
            'fmt': 'int',
        },
    ]

    # 28d tables (Facebook, Instagram)
    fb_rows = [
        {'label': 'Views', 'current': c_28d.get('fb_views', 0), 'previous': p_28d.get('fb_views', 0), 'fmt': 'k'},
        {'label': 'Reach', 'current': c_28d.get('fb_reach', 0), 'previous': p_28d.get('fb_reach', 0), 'fmt': 'k'},
        {'label': 'Link clicks', 'current': c_28d.get('fb_link_clicks', 0), 'previous': p_28d.get('fb_link_clicks', 0), 'fmt': 'k'},
        {'label': 'Interactions', 'current': c_28d.get('fb_interactions', 0), 'previous': p_28d.get('fb_interactions', 0), 'fmt': 'int'},
        {'label': 'Conversations started', 'current': c_28d.get('fb_conversations', 0), 'previous': p_28d.get('fb_conversations', 0), 'fmt': 'int'},
        {'label': 'New contacts', 'current': c_28d.get('fb_new_contacts', 0), 'previous': p_28d.get('fb_new_contacts', 0), 'fmt': 'int'},
    ]
    ig_rows = [
        {'label': 'Views', 'current': c_28d.get('ig_views', 0), 'previous': p_28d.get('ig_views', 0), 'fmt': 'k'},
        {'label': 'Reach', 'current': c_28d.get('ig_reach', 0), 'previous': p_28d.get('ig_reach', 0), 'fmt': 'k'},
        {'label': 'Interactions', 'current': c_28d.get('ig_interactions', 0), 'previous': p_28d.get('ig_interactions', 0), 'fmt': 'int'},
        {'label': 'Follows', 'current': c_28d.get('ig_follows', 0), 'previous': p_28d.get('ig_follows', 0), 'fmt': 'int'},
        {'label': 'Conversations started', 'current': c_28d.get('ig_conversations', 0), 'previous': p_28d.get('ig_conversations', 0), 'fmt': 'int'},
    ]

    # What's working / Needs attention — derived from deltas
    working, attention = [], []
    for r in rows + fb_rows + ig_rows:
        try:
            c = float(r['current']); p = float(r['previous'])
        except (ValueError, TypeError):
            continue
        if p == 0 and c == 0:
            continue
        if p == 0:
            continue
        delta = (c - p) / p
        if delta > 0.10 and r['label'] not in ('Review queue depth',):
            working.append(f"<strong>{r['label']}</strong> is up <span class=\"up\">{(c-p)/p*100:+.0f}%</span> vs last week.")
        elif delta < -0.10 and r['label'] != 'Review queue depth':
            attention.append(f"<strong>{r['label']}</strong> is down <span class=\"down\">{delta*100:+.0f}%</span> vs last week.")
    # If we have nothing flagged, give honest empty states
    if not working:
        working.append("<strong>Reach held steady</strong> — content volume and engagement landed within 10% of last week. No regression to chase this week.")
    if not attention:
        attention.append("<strong>No metric dropped more than 10%</strong> week-on-week. Clean week — focus on doubling down on what worked.")

    return {
        'current': current,
        'prev': prev,
        'rows': rows,
        'fb_rows': fb_rows,
        'ig_rows': ig_rows,
        'working': working[:5],
        'attention': attention[:5],
        'has_prev': prev is not None,
    }


def _weekly_format_num(n, fmt='int'):
    """Format a number for display. fmt ∈ {'int','k','pct','rand'}"""
    try:
        n = float(n)
    except (ValueError, TypeError):
        return str(n)
    if fmt == 'k':
        if abs(n) >= 1_000_000:
            return f'{n/1_000_000:.1f}M'
        if abs(n) >= 1000:
            return f'{n/1000:.1f}K'
        return f'{int(n)}'
    if fmt == 'rand':
        return f'R{n:,.0f}'
    if fmt == 'pct':
        return f'{n:.1f}%'
    return f'{int(n):,}'


def _weekly_render_html(bid, data_bid=None):
    """Render the full HTML page (same CSS as Stick report).

    bid         — used for brand_meta (voice/positioning/colour)
    data_bid    — used for metrics computation (defaults to bid; follows delegation)
    """
    meta = _weekly_brand_meta(bid)
    metrics = _weekly_compute_metrics(data_bid or bid)
    cur = metrics['current']
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime('%d %b %Y')
    week_start = (now - datetime.timedelta(days=7)).strftime('%d %b')
    week_end = (now - datetime.timedelta(days=1)).strftime('%d %b %Y')
    pcp_start = (now - datetime.timedelta(days=14)).strftime('%d %b')
    pcp_end = (now - datetime.timedelta(days=8)).strftime('%d %b %Y')

    # Helpers
    def change_html(row):
        c = row.get('current', 0)
        p = row.get('previous', 0)
        pct, direction, raw = _weekly_pct(c, p)
        cls = {'up':'up', 'down':'down', 'neutral':'neutral'}.get(direction, 'neutral')
        return f"<span class=\"{cls}\">{pct}</span>"

    def fmt_row(row):
        return _weekly_format_num(row['current'], row.get('fmt', 'int'))

    def prev_fmt_row(row):
        if metrics['has_prev']:
            return _weekly_format_num(row['previous'], row.get('fmt', 'int'))
        return '—'

    # TL;DR — top 5 bullets. Built from real deltas + brand voice.
    tldr_bullets = []
    weekly = cur.get('weekly', {}) or {}
    if weekly.get('content_published', 0) > 0:
        tldr_bullets.append(f"<strong>{weekly.get('content_published', 0)} pieces of content published</strong> this week for {meta['display_name']}.")
    if weekly.get('ga4_sessions', 0) > 0:
        tldr_bullets.append(f"<strong>Website traffic:</strong> {weekly.get('ga4_sessions', 0)} sessions in the last 7 days.")
    if weekly.get('review_pending', 0) > 0:
        tldr_bullets.append(f"<strong>{weekly.get('review_pending', 0)} drafts</strong> are sitting in Review waiting for your call.")
    if cur.get('28d', {}).get('ig_interactions', 0) > 0:
        tldr_bullets.append(f"<strong>Instagram (28d):</strong> {cur['28d'].get('ig_interactions', 0):,} interactions across {cur['28d'].get('ig_posts', 0)} posts.")
    if not tldr_bullets:
        tldr_bullets.append(f"<strong>No content published</strong> in the last 7 days for {meta['display_name']}. Worth a check-in — is the cadence working?")

    # Focus pills from brand pillars
    focus_pills = (meta.get('pillar_defaults') or [])[:5] or ['Brand voice', 'Top content', 'Lead flow', 'Web traffic', 'Reviews']

    # Build all the section HTML
    rows_html = ''.join(
        f"<tr><td>{r['label']}</td><td>{fmt_row(r)}</td><td>{prev_fmt_row(r)}</td><td>{change_html(r)}</td></tr>"
        for r in metrics['rows']
    )
    fb_rows_html = ''
    for r in metrics['fb_rows']:
        c, p = r.get('current', 0), r.get('previous', 0)
        if c == 0 and p == 0 and not metrics['has_prev']:
            continue  # skip empties on first ever run
        fb_rows_html += f"<tr><td>{r['label']}</td><td>{fmt_row(r)}</td><td>{prev_fmt_row(r)}</td><td>{change_html(r)}</td></tr>"

    ig_rows_html = ''
    for r in metrics['ig_rows']:
        c, p = r.get('current', 0), r.get('previous', 0)
        if c == 0 and p == 0 and not metrics['has_prev']:
            continue
        ig_rows_html += f"<tr><td>{r['label']}</td><td>{fmt_row(r)}</td><td>{prev_fmt_row(r)}</td><td>{change_html(r)}</td></tr>"

    # Meta config status
    meta_configured = any(s.get('name') == 'meta_graph' and s.get('posts') for s in (cur.get('sources') or []))
    meta_section_html = ''
    if meta_configured:
        meta_section_html = f'''
<section class="section">
  <h2>Facebook</h2>
  <p><span class="date-note">Current 28 days: {pcp_start}–{today} • Previous report: {pcp_start}–{pcp_end}</span></p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Metric</th><th>Current</th><th>Previous report</th><th>Movement</th></tr></thead>
      <tbody>{fb_rows_html or '<tr><td colspan="4" class="muted">No Facebook data returned yet</td></tr>'}</tbody>
    </table>
  </div>
</section>'''
    else:
        meta_section_html = '''
<section class="section">
  <h2>Facebook</h2>
  <div class="highlight warning">
    <strong>Meta data not configured.</strong> The 28-day Facebook table will appear here once the Meta Graph API token is added to Railway. The expected shape (views, reach, link clicks, interactions, conversations, new contacts) is already wired — drop a token in and it'll fill in.
  </div>
</section>'''

    # Top content — IG top performers
    top_performers = cur.get('28d', {}).get('ig_top_performers', []) or []
    top_content_html = ''
    if top_performers:
        items = ''.join(
            (lambda cap, likes, comments, reach, permalink, thumb:
                f"<li><strong>{(cap or permalink or 'Post')[:80]}</strong> — "
                f"{likes:,} likes, {comments:,} comments, {reach:,} reach"
                + (f'<br><a href="{permalink}" target="_blank" rel="noopener">'
                   f'<img src="{thumb}" loading="lazy" alt="post thumbnail" '
                   f'style="width:120px;height:120px;object-fit:cover;border-radius:6px;margin-top:.4rem;background:var(--bg-2)"/>'
                   f'</a>' if thumb else '')
                + "</li>"
            )(
                p.get('caption') or p.get('captionPreview') or '',
                p.get('like_count', p.get('likeCount', 0)) or 0,
                p.get('comments_count', p.get('commentsCount', 0)) or 0,
                p.get('reach') or 0,
                p.get('permalink') or '#',
                p.get('thumbnail_url') or p.get('thumbnailUrl') or p.get('media_url') or '',
            )
            for p in top_performers[:5]
        )
        top_content_html = f'''
<section class="section">
  <h2>Content that is earning attention</h2>
  <h3>Instagram top performers (28d)</h3>
  <ul>{items}</ul>
</section>'''

    # Google Ads section
    ga_configured = any(s.get('name') == 'google_ads' and s.get('configured') for s in (cur.get('sources') or []))
    ga_section_html = ''
    if ga_configured:
        ga_data = weekly.get('google_ads', {}) or {}
        spend = ga_data.get('spend', 0)
        impressions = ga_data.get('impressions', 0)
        clicks = ga_data.get('clicks', 0)
        conversions = ga_data.get('conversions', 0)
        ctr = _weekly_safe_div(clicks, impressions) * 100
        cpc = _weekly_safe_div(spend, clicks)
        ga_section_html = f'''
<section class="section">
  <h2>Google Ads this week</h2>
  <div class="grid">
    <div class="card span-3"><div class="metric-label">Spend</div><div class="metric-value">{_weekly_format_num(spend, "rand")}</div><div class="metric-note">Current week</div></div>
    <div class="card span-3"><div class="metric-label">Impressions</div><div class="metric-value">{_weekly_format_num(impressions, "int")}</div><div class="metric-note">CTR {ctr:.1f}%</div></div>
    <div class="card span-3"><div class="metric-label">Clicks</div><div class="metric-value">{_weekly_format_num(clicks, "int")}</div><div class="metric-note">CPC {_weekly_format_num(cpc, "rand")}</div></div>
    <div class="card span-3"><div class="metric-label">Conversions</div><div class="metric-value">{_weekly_format_num(conversions, "int")}</div><div class="metric-note">Tracked</div></div>
  </div>
</section>'''
    else:
        ga_section_html = '''
<section class="section">
  <h2>Google Ads this week</h2>
  <div class="highlight warning">
    <strong>Google Ads not configured.</strong> Drop a <code>data/google-ads.json</code> file with the shape <code>{spend, impressions, clicks, conversions}</code> and the spend / CTR / CPC cards will fill in here.
  </div>
</section>'''

    # GA4 top pages / sources
    top_pages = weekly.get('ga4_top_pages', []) or []
    sources = weekly.get('ga4_sources', []) or []
    pages_rows = ''.join(f"<tr><td>{p.get('path')}</td><td>{p.get('sessions', 0)}</td><td>{p.get('engagement_rate', '—')}</td></tr>" for p in top_pages)
    sources_rows = ''.join(f"<tr><td>{s.get('source')}</td><td>{s.get('sessions', 0)}</td></tr>" for s in sources)
    ga4_section_html = f'''
<section class="section">
  <h2>Website and acquisition</h2>
  <p><span class="date-note">Google Analytics • Current 7 days</span></p>
  <div class="grid">
    <div class="card span-3"><div class="metric-label">Sessions</div><div class="metric-value">{_weekly_format_num(weekly.get('ga4_sessions', 0), 'int')}</div><div class="metric-note">Last 7 days</div></div>
    <div class="card span-3"><div class="metric-label">Review queue</div><div class="metric-value">{_weekly_format_num(weekly.get('review_pending', 0), 'int')}</div><div class="metric-note">Drafts waiting</div></div>
    <div class="card span-3"><div class="metric-label">Content published</div><div class="metric-value">{_weekly_format_num(weekly.get('content_published', 0), 'int')}</div><div class="metric-note">Last 7 days</div></div>
    <div class="card span-3"><div class="metric-label">Brand</div><div class="metric-value" style="font-size:18px">{meta['display_name']}</div><div class="metric-note">{meta.get('voice_label', '')}</div></div>
  </div>
  {f'<h3>Top pages by sessions</h3><div class="table-wrap"><table><thead><tr><th>Path</th><th>Sessions</th><th>Engagement rate</th></tr></thead><tbody>{pages_rows}</tbody></table></div>' if pages_rows else '<p class="small">No page-level GA4 data yet.</p>'}
  {f'<h3>Top sources</h3><div class="table-wrap"><table><thead><tr><th>Source</th><th>Sessions</th></tr></thead><tbody>{sources_rows}</tbody></table></div>' if sources_rows else ''}
</section>'''

    # Working / attention / focus
    working_html = ''.join(f'<li>{w}</li>' for w in metrics['working'])
    attention_html = ''.join(f'<li>{a}</li>' for a in metrics['attention'])
    focus_pills_html = ''.join(f'<div class="pill">{esc_html(p)}</div>' for p in focus_pills)

    # Hero subtitle — derived from best delta
    subtitle_parts = []
    best_up = max(
        [(r['label'], _weekly_pct(r['current'], r['previous'])[2] or 0) for r in metrics['rows']],
        key=lambda x: x[1] or 0,
        default=(None, 0),
    )
    if best_up[0] and best_up[1] and best_up[1] > 5:
        subtitle_parts.append(f"<strong>{best_up[0]}</strong> is up this week ({best_up[1]:+.0f}%).")
    if weekly.get('review_pending', 0) > 5:
        subtitle_parts.append(f"{weekly['review_pending']} drafts are waiting on Review.")
    if weekly.get('content_published', 0) == 0:
        subtitle_parts.append("No content shipped in the last 7 days — worth a cadence check.")
    subtitle = ' '.join(subtitle_parts) or f"Weekly review for {meta['display_name']} — {today}."

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{meta['display_name']} Weekly Marketing Report | {today}</title>
<style>
:root {{
  --bg:#0b0f14; --card:#111821; --soft:#16212c; --text:#f4f7fb;
  --muted:#aeb8c5; --line:#273443; --green:#5dff9d; --blue:#63b3ff;
  --gold:{meta.get('primary_color', '#d7b46a')}; --red:#ff7a7a; --white:#fff;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:Arial,Helvetica,sans-serif;line-height:1.45}}
.page{{max-width:1120px;margin:0 auto;padding:28px 18px 60px}}
.hero,.section,.card{{border:1px solid var(--line);background:var(--card)}}
.hero{{background:linear-gradient(135deg,#101720 0%,#172230 55%,#0d1218 100%);border-radius:22px;padding:34px;margin-bottom:20px}}
.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:var(--gold);font-weight:700;margin-bottom:10px}}
h1,h2,h3{{margin:0}} h1{{font-size:clamp(32px,5vw,54px);line-height:1;letter-spacing:-.04em;margin-bottom:14px}}
h2{{font-size:24px;letter-spacing:-.02em;margin-bottom:14px}} h3{{font-size:17px;margin:18px 0 8px}}
p{{color:var(--muted);margin:0 0 12px}} strong{{color:var(--white)}}
.subtitle{{max-width:880px;color:var(--muted);font-size:17px}}
.focus-strip{{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}}
.pill{{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);border-radius:999px;padding:8px 12px;font-size:13px;font-weight:700}}
.section{{border-radius:22px;padding:26px;margin-bottom:18px}}
.grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;margin-bottom:18px}}
.card{{border-radius:18px;padding:20px}} .span-3{{grid-column:span 3}} .span-4{{grid-column:span 4}} .span-6{{grid-column:span 6}}
.metric-label{{color:var(--muted);font-size:13px;margin-bottom:6px}}
.metric-value{{font-size:34px;font-weight:800;letter-spacing:-.04em}}
.metric-note{{color:var(--muted);font-size:13px;margin-top:6px}}
.date-note{{display:inline-block;color:var(--gold);font-size:12px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;margin-bottom:10px}}
ul{{margin:8px 0 0;padding:0;list-style:none;display:grid;gap:8px}}
li{{color:var(--muted);padding-left:18px;position:relative}}
li:before{{content:"";width:6px;height:6px;border-radius:50%;background:var(--blue);position:absolute;left:0;top:.68em}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
.highlight{{border-left:4px solid var(--green);background:var(--soft);border-radius:14px;padding:16px;margin-top:14px;color:var(--text)}}
.gold{{border-left-color:var(--gold)}} .warning{{border-left-color:var(--red)}}
.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:14px;margin-top:10px}}
table{{width:100%;border-collapse:collapse;min-width:680px}}
th,td{{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--white);font-size:13px;background:rgba(255,255,255,.03)}}
td{{color:var(--muted);font-size:14px}} tr:last-child td{{border-bottom:none}}
.up{{color:var(--green);font-weight:700}} .down{{color:var(--red);font-weight:700}} .neutral{{color:var(--muted);font-weight:700}}
.muted{{color:var(--muted)}}
.small{{font-size:12px;color:var(--muted)}} .footer-note{{color:var(--muted);text-align:center;font-size:12px;margin-top:20px}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 16px}}
.toolbar button{{background:var(--bg-2,#1d2733);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:12px;font-weight:700;cursor:pointer}}
.toolbar button:hover{{background:var(--soft)}}
.toolbar select{{background:var(--bg-2,#1d2733);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:12px;font-weight:700}}
@media print {{ .toolbar{{display:none}} body{{background:#fff;color:#000}} .section,.card,.hero{{background:#fff;color:#000;border-color:#999}} h1,h2,h3,strong{{color:#000}} .subtitle,p,li,td,.metric-note{{color:#333}} .up{{color:#0a8}} .down{{color:#c33}} }}
@media(max-width:900px){{.span-3,.span-4,.span-6{{grid-column:span 12}}.two-col{{grid-template-columns:1fr}}.hero,.section{{padding:22px}}}}
</style>
</head>
<body>
<div class="page">

<div class="toolbar">
  <span class="muted" style="font-size:12px;line-height:32px;margin-right:auto">Brand:</span>
  <select onchange="window.location.href='/weekly-report?brand=' + this.value">
    <option value="swing-shack" {"selected" if bid=='swing-shack' else ""}>Swing Shack</option>
    <option value="stick" {"selected" if bid=='stick' else ""}>Stick</option>
    <option value="bag-drop" {"selected" if bid=='bag-drop' else ""}>Bag Drop</option>
  </select>
  <button onclick="downloadHTML()">⬇ HTML</button>
  <button onclick="downloadMarkdown()">⬇ Markdown</button>
  <button onclick="window.print()">⬇ PDF (print)</button>
  <button onclick="snapshotNow()">📸 Archive snapshot</button>
</div>

<section class="hero">
  <div class="eyebrow">{meta['display_name']} • Weekly Marketing Report • {today}</div>
  <h1>{esc_html(meta.get('tagline', f'Your {today} snapshot.'))}</h1>
  <p class="subtitle">{subtitle}</p>
  <div class="focus-strip">
    {focus_pills_html}
  </div>
</section>

<section class="section">
  <h2>TL;DR</h2>
  <ul>
    {"".join(f'<li>{b}</li>' for b in tldr_bullets)}
  </ul>
</section>

<section class="grid">
  <div class="card span-3"><div class="date-note">Weekly • {week_start}–{week_end}</div><div class="metric-label">Content published</div><div class="metric-value">{_weekly_format_num(weekly.get('content_published', 0), 'int')}</div><div class="metric-note">Last 7 days</div></div>
  <div class="card span-3"><div class="date-note">Weekly • {week_start}–{week_end}</div><div class="metric-label">Website sessions</div><div class="metric-value">{_weekly_format_num(weekly.get('ga4_sessions', 0), 'int')}</div><div class="metric-note">GA4 last 7 days</div></div>
  <div class="card span-3"><div class="date-note">Weekly • {week_start}–{week_end}</div><div class="metric-label">IG interactions (28d)</div><div class="metric-value">{_weekly_format_num(cur.get('28d', {}).get('ig_interactions', 0), 'int')}</div><div class="metric-note">{cur.get('28d', {}).get('ig_posts', 0)} posts tracked</div></div>
  <div class="card span-3"><div class="date-note">Weekly • {week_start}–{week_end}</div><div class="metric-label">Review queue</div><div class="metric-value">{_weekly_format_num(weekly.get('review_pending', 0), 'int')}</div><div class="metric-note">Drafts waiting</div></div>
</section>

<section class="section">
  <h2>Comparison with the previous {meta['display_name']} report</h2>
  <p><span class="date-note">Current weekly review: {week_start}–{week_end} • Previous report: {pcp_start}–{pcp_end}</span></p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Metric</th><th>Current</th><th>Previous report</th><th>Change</th></tr></thead>
      <tbody>{rows_html or '<tr><td colspan="4" class="muted">First run — no previous snapshot to compare yet. Archive a snapshot to start comparing.</td></tr>'}</tbody>
    </table>
  </div>
  {('' if metrics['has_prev'] else '<div class="highlight muted"><strong>First-ever run:</strong> no previous snapshot archived yet for this brand. Click <em>Archive snapshot</em> on a future report to start the comparison trail.</div>')}
  <div class="highlight gold"><strong>Read:</strong> comparison table above is the raw movement week-on-week. Anything in green is a real lift; anything in red is something to address in the next 7 days.</div>
</section>

{meta_section_html}

<section class="section">
  <h2>Instagram</h2>
  <p><span class="date-note">Current 28 days: {pcp_start}–{today} • Previous report: {pcp_start}–{pcp_end}</span></p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Metric</th><th>Current</th><th>Previous report</th><th>Movement</th></tr></thead>
      <tbody>{ig_rows_html or '<tr><td colspan="4" class="muted">No Instagram data available yet</td></tr>'}</tbody>
    </table>
  </div>
</section>

{top_content_html}

{ga4_section_html}

{ga_section_html}

<section class="section">
  <h2>What is working</h2>
  <ul>{working_html}</ul>
</section>

<section class="section">
  <h2>What needs attention</h2>
  <ul>{attention_html}</ul>
</section>

<section class="section">
  <h2>This week's focus</h2>
  <ul>
    {"".join(f'<li>Keep <strong>{esc_html(p)}</strong> content visible and on-cadence.</li>' for p in focus_pills)}
    <li>Clear the <strong>{weekly.get('review_pending', 0)} drafts</strong> sitting in Review.</li>
    <li>Check what worked last week and ship at least one more of it.</li>
  </ul>
</section>

<div class="footer-note">
Prepared for {meta['display_name']} • Weekly review uses {week_start}–{week_end} {now.year}. IG section uses the latest 28-day window through {today}. {f"Previous-report comparison uses the {meta['display_name']} report based on {pcp_start}–{pcp_end}." if metrics['has_prev'] else "First-ever run — no previous snapshot archived yet. Click 'Archive snapshot' to start the comparison trail."}
</div>

</div>

<script>
function downloadHTML(){{
  const html = document.documentElement.outerHTML;
  const blob = new Blob([html], {{type:'text/html'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '{meta["id"]}-weekly-report-{today.replace(" ","-")}.html';
  a.click();
}}
function downloadMarkdown(){{
  fetch('/api/weekly-report?brand={bid}&format=markdown').then(r=>r.text()).then(t=>{{
    const blob = new Blob([t], {{type:'text/markdown'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '{meta["id"]}-weekly-report-{today.replace(" ","-")}.md';
    a.click();
  }});
}}
function snapshotNow(){{
  fetch('/api/weekly-report/snapshot?brand={bid}', {{method:'POST'}}).then(r=>r.json()).then(j=>{{
    alert('Snapshot archived: ' + (j.path || JSON.stringify(j)));
    location.reload();
  }});
}}
</script>
</body>
</html>'''


def _md_strip_html(s):
    return (s.replace('<strong>', '**').replace('</strong>', '**')
             .replace('<span class="up">', '').replace('<span class="down">', '')
             .replace('</span>', ''))


def _weekly_render_markdown(bid, data_bid=None):
    """Render the same report as plain Markdown for Notion / Slack paste.

    bid         — used for brand_meta (voice/positioning/colour)
    data_bid    — used for metrics computation (defaults to bid; follows delegation)
    """
    meta = _weekly_brand_meta(bid)
    metrics = _weekly_compute_metrics(data_bid or bid)
    cur = metrics['current']
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime('%d %b %Y')

    lines = [f"# {meta['display_name']} — Weekly Marketing Report ({today})", ""]
    lines.append(f"**Brand:** {meta['display_name']}  ")
    lines.append(f"**Voice:** {meta.get('voice_label', '—')}  ")
    lines.append(f"**Tagline:** {meta.get('tagline', '—')}  ")
    lines.append("")
    lines.append("## TL;DR")
    lines.append("")
    weekly = cur.get('weekly', {}) or {}
    if weekly.get('content_published', 0) > 0:
        lines.append(f"- **{weekly.get('content_published', 0)} pieces of content published** this week.")
    if weekly.get('ga4_sessions', 0) > 0:
        lines.append(f"- **Website traffic:** {weekly.get('ga4_sessions', 0)} sessions in the last 7 days.")
    if weekly.get('review_pending', 0) > 0:
        lines.append(f"- **{weekly.get('review_pending', 0)} drafts** are waiting on Review.")
    if cur.get('28d', {}).get('ig_interactions', 0) > 0:
        lines.append(f"- **Instagram (28d):** {cur['28d'].get('ig_interactions', 0):,} interactions across {cur['28d'].get('ig_posts', 0)} posts.")
    if weekly.get('content_published', 0) == 0:
        lines.append(f"- **No content published** in the last 7 days. Worth a cadence check.")
    lines.append("")
    lines.append("## Comparison with previous report")
    lines.append("")
    lines.append("| Metric | Current | Previous | Change |")
    lines.append("|---|---|---|---|")
    for r in metrics['rows']:
        pct, direction, _ = _weekly_pct(r['current'], r['previous'])
        arrow = {'up':'↑', 'down':'↓', 'neutral':'—'}.get(direction, '—')
        prev_disp = _weekly_format_num(r['previous'], r.get('fmt', 'int')) if metrics['has_prev'] else '—'
        lines.append(f"| {r['label']} | {_weekly_format_num(r['current'], r.get('fmt', 'int'))} | {prev_disp} | {pct} {arrow} |")
    lines.append("")
    lines.append("## What is working")
    lines.append("")
    for w in metrics['working']:
        # Strip HTML for markdown
        lines.append(f"- {_md_strip_html(w)}")
    lines.append("")
    lines.append("## What needs attention")
    lines.append("")
    for a in metrics['attention']:
        lines.append(f"- {_md_strip_html(a)}")
    lines.append("")
    lines.append("---")
    lines.append(f"_Generated {now.isoformat()} • Sources: " + ", ".join(s.get('name','?') for s in (cur.get('sources') or [])) + "_")
    lines.append("")
    return "\n".join(lines)


def esc_html(s):
    if s is None: return ''
    s = str(s)
    return (s.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;')
             .replace('"', '&quot;'))


@app.route('/api/weekly-report', methods=['GET'])
def weekly_report_api():
    """GET /api/weekly-report?brand=swing-shack&format=html|json|markdown
    Returns the weekly report. Default format = html.

    Analytics delegate: when the requested brand has data_delegates_from set
    (e.g. stick → swing-shack), compute metrics against the delegate source
    while keeping the requested brand's voice/positioning for the hero.
    """
    bid = request.args.get('brand') or get_brand_id()
    fmt = request.args.get('format', 'html').lower()
    # Analytics source follows delegation; voice/positioning stay on the brand
    data_bid = resolve_data_brand(bid)
    if fmt == 'json':
        return jsonify({
            'brand_id': bid,
            'data_source_brand_id': data_bid,
            'brand_meta': _weekly_brand_meta(bid),
            'metrics': _weekly_compute_metrics(data_bid),
        }), 200
    if fmt == 'markdown':
        from flask import Response
        return Response(_weekly_render_markdown(bid, data_bid=data_bid), mimetype='text/markdown'), 200
    return _weekly_render_html(bid, data_bid=data_bid), 200


@app.route('/api/weekly-report/snapshot', methods=['POST', 'GET'])
def weekly_report_snapshot():
    """Archive the current week for the brand. Returns the saved path."""
    bid = request.args.get('brand') or get_brand_id()
    cur = _weekly_collect_current(bid)
    path = _weekly_save_snapshot(bid, cur)
    return jsonify({'brand_id': bid, 'path': path, 'iso_week': datetime.datetime.now(datetime.timezone.utc).isocalendar()[:2]}), 200


@app.route('/api/weekly-report/snapshots', methods=['GET'])
def weekly_report_snapshots():
    """List all archived snapshots for a brand."""
    bid = request.args.get('brand') or get_brand_id()
    try:
        snaps = []
        for f in sorted(os.listdir(WEEKLY_REPORT_DATA_DIR)):
            if f.startswith(f'{bid}_') and f.endswith('.json'):
                snaps.append(f)
        return jsonify({'brand_id': bid, 'snapshots': snaps}), 200
    except Exception as e:
        return jsonify({'brand_id': bid, 'snapshots': [], 'error': str(e)}), 200


@app.route('/weekly-report', methods=['GET'])
def weekly_report_page():
    """GET /weekly-report?brand=swing-shack
    Renders the weekly-report HTML page directly (same as /api/weekly-report?format=html).
    """
    bid = request.args.get('brand') or get_brand_id()
    data_bid = resolve_data_brand(bid)
    return _weekly_render_html(bid, data_bid=data_bid), 200


# ─── STARTUP ────────────────────────────────────────────────────────────


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
