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
from flask import Flask, jsonify, request, send_from_directory, g
from flask_cors import CORS

app = Flask(__name__, static_folder='.')
CORS(app)
_app_log = logging.getLogger("campaign-os")

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

@app.route('/api/campaigns', methods=['GET'])
def list_campaigns():
    """Return all campaigns."""
    data = load_data()
    return jsonify({
        "campaigns": data.get("campaigns", {}),
        "activeCampaignId": data.get("activeCampaignId"),
        "portfolioMetadata": data.get("portfolioMetadata", {})
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
    if 'caption' in body:
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

@app.route('/cockpit.html')
def cockpit_alias():
    return send_from_directory('.', 'campaign-os.html')

@app.route('/cockpit-operational.html')
def cockpit():
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
    try:
        if name == 'calendar':
            days = int(request.args.get('days', 14))
            start = request.args.get('start') or None
            return _intel_module.calendar_view(days=days, start=start), 200
        return fn(), 200
    except Exception as exc:
        _app_log.exception("Intel %s failed", name)
        return {"ok": False, "error": str(exc), "view": name}, 500


@app.route('/api/intel/<name>', methods=['GET'])
def intel_dispatch(name):
    """GET /api/intel/<view-name> — see INTELLIGENCE_FUNCS for the index."""
    if name == 'trends_v2':
        return trends_v2()
    payload, status = _intel(name)
    return jsonify(payload), status


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
            "error": f"Invalid theme — must be a string. Supported: {', '.join(THEME_VALID_VALUES)}",
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

    Returns {ok, ...} envelope with:
      - full prompt text per provider
      - negative prompt
      - platform aspect ratio config
      - color keywords
      - composition notes

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

    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        result = generate_image(
            asset_id,
            pillar_override=pillar,
            platform_override=platform,
        )

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

    Body: { assetId?, n?, voice?, tone? }
      assetId: campaign asset ID (optional — generates standalone hooks if absent)
      n:       number of variants 1-20 (default 5)
      voice:   'swing-shack' | 'stick' | 'bag-drop' (from voice_bible.json)
      tone:    'educational' | 'confident' | 'funny' | 'relatable' | 'provocative' | 'sarcastic'

    Returns: {ok, asset, variants, count, _voice, _tone, ts}
    """
    if not _INTELLIGENCE_AVAILABLE:
        return jsonify({"ok": False, "error": "Intelligence unavailable"}), 503
    try:
        body = request.get_json(silent=True) or {}
        asset_id = str(body.get('assetId', '') or '').strip() or None
        n = min(max(int(body.get('n', 5) or 5), 1), 20)
        voice = str(body.get('voice', '') or '').strip() or None
        tone = str(body.get('tone', '') or '').strip() or None
        result = generate_captions(asset_id, n, voice=voice, tone=tone)
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

    Heuristics:
      +30  voice matches any meme voice_fit
      +20  pillar matches any meme pillar_fit
      +15  platform matches any meme platform_fit
      +10  still_works = True
      +10  fatigue_risk in {'low', 'medium'}
      +15  has ≥3 swingshack_fit_seeds (max +15)
      −20  fatigue_risk = 'high'
      −10  still_works = False
    """
    score = 0
    reasons = []
    if voice and voice in (meme.get('voice_fit') or []):
        score += 30
        reasons.append(f'voice={voice} match (+30)')
    if pillar and pillar in (meme.get('pillar_fit') or []):
        score += 20
        reasons.append(f'pillar={pillar} match (+20)')
    if platform and platform in (meme.get('platform_fit') or []):
        score += 15
        reasons.append(f'platform={platform} match (+15)')
    if meme.get('still_works') is True:
        score += 10
        reasons.append('still_works=True (+10)')
    elif meme.get('still_works') is False:
        score -= 10
        reasons.append('still_works=False (−10)')
    fr = meme.get('fatigue_risk')
    if fr == 'low':
        score += 10
        reasons.append('fatigue_risk=low (+10)')
    elif fr == 'high':
        score -= 20
        reasons.append('fatigue_risk=high (−20)')
    seeds = meme.get('swingshack_fit_seeds') or []
    n_seeds = min(len(seeds), 3)
    if n_seeds:
        bonus = 5 * n_seeds
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


# ─── STARTUP ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)