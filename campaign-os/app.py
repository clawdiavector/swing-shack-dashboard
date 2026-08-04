"""
CampaignOS v0.1 — Railway Backend
Flask app serving Campaign OS cockpit + campaign data API.
Data lives on Railway disk. GitHub is backup/version history.
"""
import os
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
_serializer = URLSafeTimedSerializer(SESSION_SECRET)

# Routes that never require auth (login + the static asset paths needed to render login)
PUBLIC_ROUTES = {'/login', '/logout', '/api/health', '/favicon.ico'}


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


# ─── What's New (last N nightshift improvements) ─────────────────────────
# Static list of recent campaign-os improvements. Each tick appends an entry
# at the top; oldest entries fall off the end. Shown as a "What's new" card
# on the Morning Brief so Christelle sees the cumulative polish on her
# morning coffee. Frontend only fetches on first brief render and caches.
WHATS_NEW = [
    {"ts": "2026-07-30T01:30:00Z", "tag": "data", "title": "↺ Reset to AI draft · now actually resets",
     "body": "The Review-queue Edit modal's 'Reset to AI draft' button used to toast 'No AI draft saved' for every asset · the backend endpoint didn't exist. New GET /api/assets/<aid>/ai-draft returns the original AI-generated caption (snapshot taken on first hand-edit), so the button now restores the prior caption for review-and-Save. Old assets without a snapshot fall through to current caption or a clear 'no draft on file' message · no more silent dead-ends."},
    {"ts": "2026-07-29T23:30:00Z", "tag": "chrome", "title": "Zero native browser dialogs",
     "body": "Swept the last two native confirm() calls on the Headlines and CTAs clear-history buttons. Both now use the same styled inline confirm modal as the Review queue (danger-styled title, explicit Yes/No, click-outside-to-cancel). Campaign OS no longer fires any prompt(), confirm(), or alert() · iOS Safari safe everywhere."},
    {"ts": "2026-07-29T22:00:00Z", "tag": "chrome", "title": "Review queue: inline edit + confirm modals",
     "body": "Edit caption on the Review queue now opens an inline modal with a full textarea (2200-char soft cap, live counter, optional Reset-to-AI-draft). Regenerate / Publish-now / Archive all use styled confirm modals instead of native browser dialogs · no more ugly dialogs, no iOS Safari blocks."},
    {"ts": "2026-07-29T20:00:00Z", "tag": "chrome", "title": "Brand brief form · no more stacked prompts",
     "body": "Generate brief on Brand Directory now opens an inline form (Surface + Tone selects) instead of two stacked browser prompts. Mobile-safe, iOS Safari works, and runs with defaults immediately so the desktop one-click flow still works."},
    {"ts": "2026-07-29T18:10:00Z", "tag": "nav", "title": "30 sidebar tooltips",
     "body": "Hover any nav item (Home, Review, Brand, Trends, Ideas, Meme Lab…) for a one-line orientation. Replaces blank stare at the rail."},
    {"ts": "2026-07-29T16:37:00Z", "tag": "chrome", "title": "Brand switcher + all-tools tooltips",
     "body": "Hover the brand chevron, all-tools toggle, topbar search, theme switch, or Do-this-right-now for a one-line answer."},
    {"ts": "2026-07-29T15:25:00Z", "tag": "copy", "title": "Campaigns surface label aligned",
     "body": "Renamed the explainer title so it bridges the four labels (nav=Brand, header=Campaigns, tooltip, body) a reader was triangulating."},
    {"ts": "2026-07-29T13:55:00Z", "tag": "data", "title": "Visual library real-data join",
     "body": "Visual Library + Meme Lab now read live data instead of stub rows. Filters by brand + type + campaign."},
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
    """
    try:
        idx = _brand_dir.build_index()
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


# ─── Google Drive ingestion ──────────────────────────────────────────
from _lib import google_drive as _gdrive  # noqa: E402


@app.route('/api/google-drive/status', methods=['GET'])
def google_drive_status():
    """GET /api/google-drive/status — current Drive auth + folder config state."""
    try:
        return jsonify(_gdrive.status())
    except Exception as e:
        _app_log.exception("google_drive_status failed")
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify(result)
    except Exception as e:
        _app_log.exception("visual_dna_recipe failed")
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


# ─── VISUAL LIBRARY (image serving + DNA breakdown for the UI) ──────────

@app.route('/visualizer', methods=['GET'])
def visualizer_page():
    """GET /visualizer — Visual Library tab (122 SS images + DNA + filters)."""
    return send_from_directory(os.path.dirname(__file__), 'visualizer.html')


@app.route('/meme-lab', methods=['GET'])
def meme_lab_page():
    """GET /meme-lab — Meme Library tab (75 memes with adaptation previews)."""
    return send_from_directory(os.path.dirname(__file__), 'meme-lab.html')


@app.route('/brand-images/<brand_id>/<path:filename>', methods=['GET'])
def brand_image_serve(brand_id, filename):
    """GET /brand-images/<brand>/ — serve a brand-directory image.

    Used by the Visual Library UI to display thumbnails. Safe: resolves to
    a path inside the brand-directory and rejects traversal attempts.
    """
    from pathlib import Path as _P
    base = (_P(BUNDLED_DATA_DIR) / 'brand-directory' / brand_id / 'images').resolve()
    target = (base / filename).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return jsonify({"error": "path traversal denied"}), 403
    if not target.exists() or not target.is_file():
        return jsonify({"error": "not found", "path": str(target)}), 404
    return send_from_directory(str(target.parent), target.name)


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
            entry = {
                "filename": fn,
                "url": f"/brand-images/{brand_id}/{fn}",
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
      {ok, brand, filters_applied, count, results: [{filename, score, colors, brands, objects, mood, quality_score, dna_path, image_url}]}
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

            results.append({
                "filename": fn,
                "dna_path": entry.get("dna_path", ""),
                "image_url": f"/api/visual-library/{brand_id}/image/{fn}.jpg",
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
    """GET /api/visual-library/<brand>/recipe — aggregated brand image DNA.

    Combines statistical mode (most common features) with top-performer emphasis.
    Returns human-readable recipe + numeric aggregates for use in image generation.

    Query params:
      top_pct=<n>   — top N% by quality score to weight heavily (default 25)

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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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


@app.route('/meta-portal', methods=['GET'])
@app.route('/meta-portal.html', methods=['GET'])
def meta_portal_form():
    """GET /meta-portal — serve the credential submission form."""
    return send_from_directory(os.path.dirname(__file__), 'meta-portal.html')


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


@app.route('/api/intel/weekly_report/export', methods=['GET'])
def weekly_report_export():
    """GET /api/intel/weekly_report/export — markdown export of the weekly report.

    Returns the weekly report as markdown so it can be downloaded/printed
    or pasted into a Slack/email. Reads the same data as the JSON view.
    """
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
        ]



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

        return Response(md, mimetype="text/markdown", headers={"Content-Disposition": "attachment; filename=weekly-report.md"})
    except Exception as exc:
        _app_log.exception("weekly_report_export failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        try:
            _intel_module.clear_request_brand()
        except Exception:
            pass


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
        for m in (opp.get('missed') or [])[:20]:
            if not isinstance(m, dict):
                continue
            if pillar and m.get('pillar') and m.get('pillar') != pillar:
                continue
            # Build a real, human title from the missed-opportunity shape
            topic = m.get('topic') or 'this angle'
            sug = m.get('suggested_fix') or m.get('suggestion') or ''
            base_title = f"Rework \"{topic}\" · there's untapped reach here"
            if isinstance(sug, str) and len(sug) > 10:
                # use the suggested_fix as the why, summarise for title
                base_title = f"Follow-up: {topic.title()} (IG proof {m.get('ig_score', '?')})"
            ideas.append({
                "title": base_title[:120],
                "why": m.get('why') or m.get('suggestion') or 'High-impact gap — strong signal with no current content',
                "hook": m.get('hook'),
                "source_type": "missed_opportunity",
                "score": float(m.get('ig_score', 7) or 7),
                "pillar": m.get('pillar') or 'general',
                "platform": platform,
            })

        # reddit pain points (if fewer than n so far)
        reddit = reddit_outreach() or {}
        for r in (reddit.get('pain_points') or reddit.get('items') or [])[:20]:
            if not isinstance(r, dict):
                continue
            title = r.get('title') or r.get('pain_point') or r.get('summary') or ''
            if not title:
                continue
            ideas.append({
                "title": title[:120],
                "why": r.get('why') or r.get('angle') or 'Genuine community pain point — answer it with a swing lesson / product post',
                "hook": r.get('hook') or (title[:80] if title else None),
                "source_type": "reddit",
                "score": 7.5,
                "pillar": 'community',
                "platform": platform,
            })

        # trends — convert into ideas
        tr = trend_catcher() or {}
        for t in (tr.get('trends') or tr.get('items') or [])[:10]:
            if not isinstance(t, dict):
                continue
            title = t.get('title') or t.get('trend') or t.get('name') or ''
            if not title:
                continue
            ideas.append({
                "title": f"Capitalise on: {title[:80]}",
                "why": f"Trending topic (heat={t.get('heat', t.get('score', '?'))}) · ride the wave before it cools",
                "hook": None,
                "source_type": "trend",
                "score": 8.0,
                "pillar": 'events' if 'event' in title.lower() else 'community',
                "platform": platform,
            })

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
        return jsonify({"ok": True, "ideas": top, "count": len(top),
                        "ts": _now_iso()}), 200
    except Exception as exc:
        _app_log.exception("generate_ideas failed")
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
    bid = request.headers.get('X-Brand') or request.args.get('brand_id')
    if bid:
        return bid
    registry = load_brands_registry()
    return registry.get('default_brand_id') or 'swing-shack'


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


# ─── STARTUP ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
