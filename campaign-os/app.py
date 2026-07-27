"""
CampaignOS v0.1 — Railway Backend
Flask app serving Campaign OS cockpit + campaign data API.
Data lives on Railway disk. GitHub is backup/version history.
"""
import os
import json
import datetime
import subprocess
import shutil
import logging
from flask import Flask, jsonify, request, send_from_directory, g
from flask_cors import CORS

app = Flask(__name__, static_folder='.')
CORS(app)

# Directory where we store campaign data (Railway persistent disk)
DATA_DIR = os.environ.get('DATA_DIR', '/data')
CAMPAIGN_FILE = os.path.join(DATA_DIR, 'campaign-data.json')
REPO_DIR = os.path.join(DATA_DIR, 'repo')
GIT_REMOTE = os.environ.get('GIT_REMOTE', 
 'https://x-access-token:${GITHUB_TOKEN}@github.com/clawdiavector/swing-shack-dashboard.git')
BRANCH = 'main'

# ─── HELPERS ────────────────────────────────────────────────────────────

def load_data():
    """Load campaign data, falling back to bundled campaign-os/campaign-data.json, then embedded default."""
    # Primary: Railway persistent disk (DATA_DIR/campaign-data.json)
    if os.path.exists(CAMPAIGN_FILE):
        with open(CAMPAIGN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    # Fallback 1: bundled canonical campaign data shipped with the deploy
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'campaign-data.json')
    if os.path.exists(bundled):
        with open(bundled, 'r', encoding='utf-8') as f:
            return json.load(f)
    # Fallback 2: minimal empty structure
    return {"campaigns": {}, "activeCampaignId": None, "portfolioMetadata": {}}

def save_data(data):
    """Save campaign data to Railway disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CAMPAIGN_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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

# ─── STATIC FILES ─────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'home.html')

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