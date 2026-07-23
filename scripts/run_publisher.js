#!/usr/bin/env node
/**
 * run_publisher.js — publisher agent core script
 *
 * Reads: ready-for-approval, captions, content-blueprints, approval-queue, post-plan
 * Produces: publish-queue.json, published-items.json, scheduled-items.json, publish-failures.json
 *          (DRY_RUN mode — unchanged)
 *
 * LIVE mode (--live flag): for each approved item, makes a real Postiz API call,
 * persists the raw response to data/events/postiz/<sha256>.json, appends a
 * canonical publishing reference to campaigns[campaignId].publishing[] in
 * campaign-data.json, and auto-regenerates data/publishing-references.json.
 *
 * Rules:
 * - Only items with QA PASS + Brand PASS + Approval PASS publish
 * - Only publish items with: caption, platform, owner, hook_id
 * - DRY RUN is the default. Live mode requires --live flag explicitly.
 * - Live mode also requires POSTIZ_FIXTURE=true OR a valid POSTIZ_API_KEY
 *   (loaded via scripts/_lib/postiz-credentials.js — file path first, env var second)
 *
 * Postiz API: POST https://api.postiz.com/public/v1/posts
 * Schema: https://clawdia.io/agents/publisher/v1
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const https = require('https');
const { execSync } = require('child_process');
const { loadPostizApiKey } = require('./_lib/postiz-credentials');
const { regenerate: regenerateIndex } = require('./regenerate-publishing-index');
const { evaluateAsset, applyStateTransition, recordEvent } = require('./_lib/asset-state-engine');

const REPO_ROOT = path.join(__dirname, '..');
const DATA = path.join(REPO_ROOT, 'data');
const CANONICAL_PATH = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');
const EVENTS_DIR = path.join(DATA, 'events', 'postiz');

// ── Args ───────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const LIVE_MODE = args.includes('--live');

// FIXTURE_MODE and FIXTURE_PATH are read at call time (not module load) so
// tests can mutate them after require(). See getFixtureMode() / getFixturePath().
function isFixtureMode() {
  return !!process.env.POSTIZ_FIXTURE;
}
function getFixturePath() {
  return process.env.POSTIZ_FIXTURE_PATH ||
    path.join(__dirname, '_fixtures', 'postiz-create-response-success.json');
}

// ── Credential loader (only when needed) ──────────────────────────────────
// We load creds only when live mode + not fixture mode, to avoid noise in
// the default DRY_RUN path.
let POSTIZ_KEY = null;
if (LIVE_MODE && !isFixtureMode()) {
  const cred = loadPostizApiKey();
  POSTIZ_KEY = cred.apiKey;
  console.log(`[run_publisher] Live mode. Postiz credential: source=${cred.source}, length=${cred.length}`);
}

// ── Constants ──────────────────────────────────────────────────────────────
const INTEGRATIONS = {
  instagram: { id: 'cmnfoum2703e6ql0yiajgcg21', provider: 'instagram' },
  tiktok:    { id: 'cmmdgfz3b00s1o20ykrwau2o2', provider: 'tiktok' },
  gmb:       { id: 'cmmdgju7f00tppk0y6bne9zrk', provider: 'gmb' },
  facebook:  { id: 'cmmdg0bty00r6o20yvmzskvdw', provider: 'facebook' },
};

const CHANNEL_TO_PROVIDER = {
  instagram: 'instagram',
  tiktok: 'tiktok',
  gmb: 'gmb',
  facebook: 'facebook',
};

function readJson(n) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); }
  catch { return null; }
}

function uid(prefix = 'pub') {
  return `${prefix}-${Math.random().toString(36).substring(2, 10)}`;
}

function sha256OfString(s) {
  return crypto.createHash('sha256').update(s, 'utf8').digest('hex');
}

// ── Canonical read/write (atomic, with file lock) ─────────────────────────
let _canonical_lock_fd = null;

function acquireCanonicalLock() {
  const lockPath = CANONICAL_PATH + '.lock';
  let attempts = 0;
  while (attempts < 50) {
    try {
      _canonical_lock_fd = fs.openSync(lockPath, 'wx');
      fs.writeSync(_canonical_lock_fd, `${process.pid}\n`);
      return;
    } catch (e) {
      if (e.code === 'EEXIST') {
        // Lock held by another process; wait briefly
        const waitMs = 50 + Math.floor(Math.random() * 100);
        execSync(`sleep 0.${waitMs}`);
        attempts++;
        continue;
      }
      throw e;
    }
  }
  throw new Error('could not acquire canonical lock after 50 attempts');
}

function releaseCanonicalLock() {
  if (_canonical_lock_fd !== null) {
    const lockPath = CANONICAL_PATH + '.lock';
    try {
      fs.closeSync(_canonical_lock_fd);
      fs.unlinkSync(lockPath);
    } catch (e) { /* best-effort cleanup */ }
    _canonical_lock_fd = null;
  }
}

function readCanonical() {
  const raw = fs.readFileSync(CANONICAL_PATH, 'utf8');
  return JSON.parse(raw);
}

function writeCanonicalAtomic(data) {
  // Atomic: write to .tmp, fsync, rename
  const tmp = CANONICAL_PATH + '.tmp';
  const payload = JSON.stringify(data, null, 2);
  const fd = fs.openSync(tmp, 'w');
  try {
    fs.writeSync(fd, payload);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(tmp, CANONICAL_PATH);
}

// ── Postiz API call (live) ────────────────────────────────────────────────
function callPostizAPI(payload, key) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload);
    const req = https.request({
      hostname: 'api.postiz.com',
      path: '/public/v1/posts',
      method: 'POST',
      headers: {
        'Authorization': key,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
      timeout: 20000,
    }, (res) => {
      let buf = '';
      res.on('data', (c) => { buf += c; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(buf);
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve({ ok: true, status: res.statusCode, body: parsed });
          } else {
            resolve({ ok: false, status: res.statusCode, body: parsed, raw: buf });
          }
        } catch (e) {
          resolve({ ok: false, status: res.statusCode, body: null, raw: buf, parseError: e.message });
        }
      });
    });
    req.on('error', (e) => reject(e));
    req.on('timeout', () => { req.destroy(new Error('timeout')); });
    req.write(body);
    req.end();
  });
}

// ── Fixture response loader ───────────────────────────────────────────────
// fixturePath comes from getFixturePath() above (module-level).
function loadFixtureResponse() {
  const fixturePath = getFixturePath();
  if (!fs.existsSync(fixturePath)) {
    throw new Error(`POSTIZ_FIXTURE=true but fixture not found at ${fixturePath}`);
  }
  const raw = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  if (!raw._fixture) {
    throw new Error(
      `fixture at ${fixturePath} is missing _fixture:true marker — refusing to load. ` +
      `Production fixture files must declare _fixture:true so they cannot be confused with real responses.`
    );
  }
  if (!raw.id || !raw.id.startsWith('cmFIXTURE')) {
    throw new Error(
      `fixture at ${fixturePath} has post id '${raw.id}' that does not start with cmFIXTURE. ` +
      `All fixture post IDs must start with cmFIXTURE so the truth_collector guard can reject them.`
    );
  }
  return raw;
}

// Build a fixture response with a unique post ID. Used for tests that need
// to run multiple live publishes in sequence without colliding on duplicate
// postizPostId. Caller provides the suffix (e.g., a timestamp).
function buildFixtureResponse(suffix) {
  const base = loadFixtureResponse();
  return {
    ...base,
    id: `cmFIXTURE${suffix.padEnd(27, '0')}`.substring(0, 32),
    // Keep _fixture, _note, _captured_from from base
  };
}

// ── Persist raw response ──────────────────────────────────────────────────
function persistRawResponse(rawResponse) {
  const json = JSON.stringify(rawResponse, null, 2);
  const hash = sha256OfString(json);
  fs.mkdirSync(EVENTS_DIR, { recursive: true });
  const filePath = path.join(EVENTS_DIR, `${hash}.json`);
  // Atomic write — never overwrite; throw if file exists with different content
  if (fs.existsSync(filePath)) {
    const existing = fs.readFileSync(filePath, 'utf8');
    if (existing === json) {
      return { hash, path: filePath, alreadyExisted: true };
    }
    // Hash collision on different content — extremely unlikely, but treat as integrity failure
    throw new Error(`hash collision in events dir: ${hash} exists with different content`);
  }
  const tmp = filePath + '.tmp';
  fs.writeFileSync(tmp, json);
  fs.renameSync(tmp, filePath);
  return { hash, path: filePath, alreadyExisted: false };
}

// ── Status transition validator (matches Step 78 spec) ──────────────────
const ALLOWED_TRANSITIONS = {
  null: ['draft'],
  draft: ['scheduled', 'failed'],
  scheduled: ['published', 'failed'],
  published: [],
  failed: [],
};

function validateStatusTransition(currentStatus, nextAction) {
  const nextStatus = ACTION_TO_STATUS[nextAction];
  if (!nextStatus) {
    throw new Error(`unknown action: ${nextAction}`);
  }
  const allowed = ALLOWED_TRANSITIONS[currentStatus] || [];
  if (!allowed.includes(nextStatus)) {
    throw new InvalidStatusTransitionError(
      `cannot transition from ${currentStatus || 'null'} to ${nextStatus} via action '${nextAction}'`
    );
  }
}

const ACTION_TO_STATUS = {
  created: 'draft',
  scheduled: 'scheduled',
  published: 'published',
  failed: 'failed',
  media_id_resolved: null, // doesn't change currentStatus
};

class InvalidStatusTransitionError extends Error {
  constructor(msg) { super(msg); this.name = 'InvalidStatusTransition'; }
}

// ── Build publishing reference from Postiz response ──────────────────────
function buildPublishingReference({
  assetId, campaignId, response, fixture, runId, actor,
}) {
  // The postiz response is the source of truth for post-side facts.
  // We project to our canonical reference shape; null where the upstream
  // did not supply a value.
  const stateRaw = (response.state || '').toString().toUpperCase();
  const stateToCanonical = {
    DRAFT: 'draft',
    SCHEDULED: 'scheduled',
    PUBLISHED: 'published',
    FAILED: 'failed',
  };
  const currentStatus = stateToCanonical[stateRaw] || 'draft';

  const integrationId = response.integration?.id || fixture?.integrationId || null;
  const integrationProvider =
    response.integration?.providerIdentifier || fixture?.integrationProvider || null;

  if (!integrationId) {
    throw new Error('Postiz response missing integration.id');
  }

  // Derive channel from integrationProvider
  const channel = CHANNEL_TO_PROVIDER[integrationProvider];
  if (!channel) {
    throw new Error(`unknown integration provider: ${integrationProvider}`);
  }

  // Persist the raw response (per Amendment 4 — never in campaign-data.json)
  const rawRef = persistRawResponse(response);

  const now = new Date().toISOString();
  const publishingId = uid('pub');

  // Map Postiz timestamps to canonical fields
  const publishDateIso = response.publishDate || now;
  const isPublished = currentStatus === 'published';
  const isScheduled = currentStatus === 'scheduled' || currentStatus === 'draft';

  return {
    publishingId,
    assetId,
    campaignId,  // canonical self-describing reference; needed for engine writeback
    postizPostId: response.id,
    integrationId,
    integrationProvider,
    channel,
    releaseURL: response.releaseURL ?? null,
    releaseId: response.releaseId ?? null,
    platformMediaId: null,  // ALWAYS null at write time — Amendment 3
    currentStatus,
    createdAt: now,
    scheduledAt: isScheduled ? publishDateIso : null,
    publishedAt: isPublished ? publishDateIso : null,
    provenance: {
      source: LIVE_MODE ? 'publisher' : 'publisher-fixture',
      runId,
      actor,
      publishedVia: isFixtureMode() ? 'fixture' : 'postiz-api',
      chain: [isFixtureMode() ? 'publisher-fixture' : 'publisher', 'postiz-api'],
      rawResponseRef: {
        hash: rawRef.hash,
        path: path.relative(REPO_ROOT, rawRef.path),
        capturedAt: now,
      },
    },
    history: [
      {
        action: 'created',
        at: now,
        by: actor,
        reason: currentStatus === 'draft' ? 'draft_created'
              : currentStatus === 'published' ? 'direct_publish'
              : null,
        rawResponseHash: rawRef.hash,
      },
    ],
  };
}

// ── Append reference to canonical ─────────────────────────────────────────
function appendReferenceToCanonical(ref, campaignId) {
  acquireCanonicalLock();
  try {
    const canonical = readCanonical();
    if (!canonical.campaigns) {
      throw new Error('canonical file missing campaigns dict');
    }
    const campaign = canonical.campaigns[campaignId];
    if (!campaign) {
      throw new Error(`campaign not found in canonical: ${campaignId}`);
    }
    if (!Array.isArray(campaign.publishing)) {
      campaign.publishing = [];
    }
    // Uniqueness: postizPostId globally unique across all publishing[]
    for (const cid of Object.keys(canonical.campaigns)) {
      for (const existing of (canonical.campaigns[cid].publishing || [])) {
        if (existing.postizPostId === ref.postizPostId) {
          throw new DuplicatePostizPostIdError(
            `postizPostId ${ref.postizPostId} already exists in campaigns[${cid}].publishing`
          );
        }
      }
    }
    campaign.publishing.push(ref);
    writeCanonicalAtomic(canonical);
  } finally {
    releaseCanonicalLock();
  }
}

class DuplicatePostizPostIdError extends Error {
  constructor(msg) { super(msg); this.name = 'DuplicatePostizPostId'; }
}

// ── Engine integration: derive 5 publishing-state fields after live Postiz ──
//
// Step 87 Publisher integration:
//   1. Append a `publish-confirmed` history event (real event, by 'publisher')
//   2. evaluateAsset(asset, asset.history, externalSignals) — pure projection
//   3. applyStateTransition(asset, desired) — field-only mutator
//   4. Persist the updated asset atomically (lock + atomic rename)
//
// Engine failures are logged but DO NOT block the publishing reference write.
// The reference is canonical; the state fields are derived. If the engine
// crashes, the next reconcile run will project the correct state anyway.

function derivePublishingStateAfterPostiz(ref, postizStatus) {
  let outcome = { changed: false, fieldsChanged: [], error: null };
  acquireCanonicalLock();
  try {
    const canonical = readCanonical();
    const campaign = canonical.campaigns && canonical.campaigns[ref.campaignId];
    if (!campaign) throw new Error(`campaign not found: ${ref.campaignId}`);
    const asset = campaign.assets && campaign.assets[ref.assetId];
    if (!asset) throw new Error(`asset not found: ${ref.assetId}`);

    // Step 1: record real event
    if (!Array.isArray(asset.history)) asset.history = [];
    const isSuccess = postizStatus === 'live' || postizStatus === 'scheduled' || postizStatus === 'published';
    recordEvent(asset.history, isSuccess ? 'publish-confirmed' : 'publish-failed', {
      by: 'publisher',
      postizPostId: ref.postizPostId,
      releaseURL: ref.releaseURL || null,
      releaseId: ref.releaseId || null,
      currentStatus: ref.currentStatus,
      reason: isSuccess ? 'postiz_call_succeeded' : 'postiz_call_failed',
    });

    // Step 2: pure projection
    const desired = evaluateAsset(asset, asset.history, {
      postizConfirmations: [{
        assetId: ref.assetId,
        status: isSuccess ? 'live' : 'failed',
        postizPostId: ref.postizPostId,
        releaseURL: ref.releaseURL || null,
      }],
    });

    // Step 3: apply (fields only — engine never touches history)
    const applyResult = applyStateTransition(asset, desired);
    outcome = {
      changed: applyResult.changed,
      fieldsChanged: applyResult.fieldsChanged,
      error: null,
    };

    // Step 4: persist
    writeCanonicalAtomic(canonical);
  } catch (e) {
    outcome.error = e.message;
    console.warn(`[run_publisher] engine integration failed for ${ref.assetId}: ${e.message}`);
  } finally {
    releaseCanonicalLock();
  }
  return outcome;
}

// ── Lookup asset from ready-for-approval item ─────────────────────────────
// Maps a publish-queue item back to (campaignId, assetId) using current
// campaign-data.json assets. Returns null if no match — caller skips the item.
function resolveAssetForItem(item) {
  const canonical = readCanonical();
  // The ready-for-approval items reference item_id which may map to an asset
  // via linked_blueprint_id, linked_caption_id, or directly. We try the most
  // specific path first.
  for (const cid of Object.keys(canonical.campaigns || {})) {
    const campaign = canonical.campaigns[cid];
    const assets = campaign.assets || {};
    for (const aid of Object.keys(assets)) {
      const asset = assets[aid];
      if (asset.assetId === item.item_id) return { campaignId: cid, assetId: aid };
      if (asset.assetId === item.linked_blueprint_id) return { campaignId: cid, assetId: aid };
      // Caption match — items sometimes carry caption_id, not asset_id
      if (Array.isArray(asset.history)) {
        for (const h of asset.history) {
          if (h?.relatedAssetId === item.item_id) return { campaignId: cid, assetId: aid };
        }
      }
    }
  }
  return null;
}

// ── DRY_RUN path (UNCHANGED — preserves current behavior) ─────────────────
function runDry() {
  const ready    = readJson('ready-for-approval.json') || {};
  const caps     = readJson('captions.json') || {};
  const bps      = readJson('content-blueprints.json') || {};
  const plan     = readJson('post-plan.json') || {};

  const approvedItems = (ready.items || []).filter(item => {
    if (item.verdict !== 'pass') return false;
    if (!item.hook_text && !item.linked_blueprint_id) return false;
    return true;
  });

  const publishQueue = [];
  approvedItems.forEach(item => {
    const cap = caps.captions?.find(c => c.caption_id === item.item_id) ||
                caps.captions?.find(c => c.caption_id === item.linked_caption_id) ||
                caps.captions?.find(c => c.caption_id === item.linked_blueprint_id);
    const blueprint = (bps.blueprints || []).find(b => b.blueprint_id === item.linked_blueprint_id);
    const planEntry = (plan.plan || []).find(p => p.hook_id === item.linked_blueprint_id || p.hook === item.hook_text);

    const platform = item.platform || 'instagram';
    const integrationId = INTEGRATIONS[platform]?.id || INTEGRATIONS.instagram.id;

    const captionText = cap?.medium_caption || cap?.short_caption ||
                        `${item.hook_text || blueprint?.hook_overlay_text || ''}\n\nSwing Shack\nLink in bio · Book your session`;

    const payload = {
      type: planEntry?.scheduled_date ? 'schedule' : 'now',
      date: planEntry?.scheduled_date ? new Date(planEntry.scheduled_date).toISOString() : new Date().toISOString(),
      shortLink: false,
      tags: ['SwingShack', 'IndoorGolf', 'TrackMan'],
      posts: [{
        integration: { id: integrationId },
        settings: { message: captionText.substring(0, 2200) },
      }],
    };

    const publishEntry = {
      publish_id: uid(),
      schema: 'https://clawdia.io/agents/publisher/v1',
      generated: new Date().toISOString(),
      item_id: item.item_id,
      item_type: item.item_type,
      linked_blueprint_id: item.linked_blueprint_id,
      linked_hook_id: item.linked_hook_id || blueprint?.source_hook_id || null,
      platform,
      integration_id: integrationId,
      caption_preview: captionText.substring(0, 120),
      owner: item.owner || 'clawdia',
      cta_type: cap?.cta_type || blueprint?.cta_type || 'booking',
      landing_page: 'swingshack.co.za',
      recommendation_id: item.item_id,
      scheduled_date: planEntry?.scheduled_date || null,
      status: 'queued',
      publish_timestamp: null,
      postiz_post_id: null,
      mode: planEntry?.scheduled_date ? 'schedule' : 'immediate',
      payload_size: JSON.stringify(payload).length,
    };
    publishQueue.push(publishEntry);
  });

  const publishedItems = publishQueue.filter(p => p.mode === 'immediate');
  const schedItems = publishQueue.filter(p => p.mode === 'schedule');

  fs.writeFileSync(path.join(DATA, 'publish-queue.json'), JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    mode: 'DRY_RUN',
    note: 'Publisher runs in DRY RUN mode — does not actually post to Postiz. Use --live flag to enable live publishing.',
    total: publishQueue.length,
    by_platform: {
      instagram: publishQueue.filter(p => p.platform === 'instagram').length,
      tiktok: publishQueue.filter(p => p.platform === 'tiktok').length,
    },
    queued: publishQueue,
  }, null, 2));

  fs.writeFileSync(path.join(DATA, 'published-items.json'), JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    mode: 'DRY_RUN',
    total: publishedItems.length,
    published: publishedItems.map(p => ({ ...p, status: 'published_dry' })),
  }, null, 2));

  fs.writeFileSync(path.join(DATA, 'scheduled-items.json'), JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    total: schedItems.length,
    scheduled: schedItems,
  }, null, 2));

  fs.writeFileSync(path.join(DATA, 'publish-failures.json'), JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    mode: 'DRY_RUN',
    total: 0,
    failures: [],
  }, null, 2));

  console.log(`✅ Publisher: ${publishQueue.length} items queued for publish`);
  console.log(`   Mode: DRY RUN (use --live flag to enable live publishing)`);
  console.log(`   Immediate: ${publishedItems.length} | Scheduled: ${schedItems.length}`);
  return { ok: true, mode: 'DRY_RUN', queued: publishQueue.length };
}

// ── LIVE path ─────────────────────────────────────────────────────────────
async function runLive() {
  const ready = readJson('ready-for-approval.json') || {};
  const caps = readJson('captions.json') || {};
  const bps = readJson('content-blueprints.json') || {};
  const plan = readJson('post-plan.json') || {};

  const approvedItems = (ready.items || []).filter(item => {
    if (item.verdict !== 'pass') return false;
    if (!item.hook_text && !item.linked_blueprint_id) return false;
    return true;
  });

  if (approvedItems.length === 0) {
    console.log(`[run_publisher] --live: no approved items to publish`);
    return { ok: true, mode: 'live', published: 0, skipped: 0, failed: 0 };
  }

  const runId = uid('run');
  const actor = process.env.PUBLISHER_ACTOR || 'publisher';

  const failures = [];
  const successes = [];
  const skips = [];

  for (const item of approvedItems) {
    // Step 1: Resolve asset FIRST so we can read the canonical caption directly.
    // The queue's hook_text is a 220-char preview and would truncate the published
    // caption — the canonical asset.caption is the single source of truth.
    const assetMatch = resolveAssetForItem(item);
    if (!assetMatch) {
      skips.push({ item_id: item.item_id, reason: 'asset_not_found_in_canonical' });
      continue;
    }
    const { campaignId, assetId } = assetMatch;

    const canonical = readCanonical();
    const campaign = canonical.campaigns && canonical.campaigns[campaignId];
    const asset = campaign && campaign.assets && campaign.assets[assetId];
    const canonicalCaption = asset && typeof asset.caption === 'string' ? asset.caption : null;

    const cap = caps.captions?.find(c => c.caption_id === item.item_id) ||
                caps.captions?.find(c => c.caption_id === item.linked_caption_id) ||
                caps.captions?.find(c => c.caption_id === item.linked_blueprint_id);
    const blueprint = (bps.blueprints || []).find(b => b.blueprint_id === item.linked_blueprint_id);
    const planEntry = (plan.plan || []).find(p => p.hook_id === item.linked_blueprint_id || p.hook === item.hook_text);

    const platform = item.platform || 'instagram';
    const integration = INTEGRATIONS[platform] || INTEGRATIONS.instagram;
    const channel = CHANNEL_TO_PROVIDER[integration.provider] || platform;

    // Caption precedence: canonical asset.caption (truth) > caption record > fallback.
    // This ensures Postiz receives the full approved caption, not the 220-char queue preview.
    const captionText = canonicalCaption
      || cap?.medium_caption
      || cap?.short_caption
      || `${item.hook_text || blueprint?.hook_overlay_text || ''}\n\nSwing Shack\nLink in bio · Book your session`;

    const payload = {
      type: 'draft',  // Step 78: only "draft" or "schedule" per Postiz API
      date: planEntry?.scheduled_date ? new Date(planEntry.scheduled_date).toISOString() : new Date().toISOString(),
      shortLink: false,
      tags: ['SwingShack', 'IndoorGolf', 'TrackMan'],
      posts: [{
        integration: { id: integration.id },
        settings: { message: captionText.substring(0, 2200) },
      }],
    };

    // Step 2: Call Postiz (real or fixture)
    let response;
    let usedFixture = false;
    if (isFixtureMode()) {
      console.log(`[run_publisher] --live (FIXTURE): using fixture for item ${item.item_id}`);
      // Use a unique fixture per item so multiple live publishes don't collide
      // on duplicate postizPostId. The base fixture is the canonical shape;
      // we override only the id to make it unique.
      response = buildFixtureResponse(`${runId}-${uid('item').substring(4)}`);
      usedFixture = true;
    } else {
      try {
        const result = await callPostizAPI(payload, POSTIZ_KEY);
        if (!result.ok) {
          failures.push({
            item_id: item.item_id,
            reason: `postiz_${result.status}`,
            excerpt: JSON.stringify(result.body || result.raw || '').substring(0, 400),
          });
          continue;
        }
        response = result.body;
      } catch (e) {
        failures.push({
          item_id: item.item_id,
          reason: 'postiz_network_error',
          excerpt: e.message.substring(0, 400),
        });
        continue;
      }
    }

    // Step 3: Build + append reference (atomic, with lock)
    try {
      const ref = buildPublishingReference({
        assetId,
        campaignId,
        response,
        fixture: usedFixture ? response : null,
        runId,
        actor,
      });
      appendReferenceToCanonical(ref, campaignId);

      // Step 3.5: derive 5 publishing-state fields via Asset State Engine
      // (records publish-confirmed history event, evaluates, applies fields only)
      const engineOutcome = derivePublishingStateAfterPostiz(ref, response.state || response.currentStatus);

      // Step 4: Auto-regenerate the index (Amendment 5)
      const regenResult = regenerateIndex({ mode: 'incremental-after-write' });

      successes.push({
        publishingId: ref.publishingId,
        postizPostId: ref.postizPostId,
        assetId,
        campaignId,
        rawResponseHash: ref.provenance.rawResponseRef.hash,
        indexRegenerated: regenResult.ok,
        stateEngineChanged: engineOutcome.changed,
        stateEngineFields: engineOutcome.fieldsChanged,
        stateEngineError: engineOutcome.error,
      });
    } catch (e) {
      if (e instanceof DuplicatePostizPostIdError) {
        skips.push({ item_id: item.item_id, reason: 'duplicate_postizPostId', excerpt: e.message });
      } else {
        failures.push({
          item_id: item.item_id,
          reason: 'canonical_write_failed',
          excerpt: e.message.substring(0, 400),
        });
      }
    }
  }

  // Persist publish-failures.json with LIVE-mode results (extends DRY_RUN file)
  const failuresPath = path.join(DATA, 'publish-failures.json');
  let existingFailures = { failures: [] };
  if (fs.existsSync(failuresPath)) {
    try { existingFailures = JSON.parse(fs.readFileSync(failuresPath, 'utf8')); } catch {}
  }
  fs.writeFileSync(failuresPath, JSON.stringify({
    schema: 'https://clawdia.io/agents/publisher/v1',
    generated: new Date().toISOString(),
    mode: 'live',
    total: failures.length,
    failures: [...(existingFailures.failures || []), ...failures],
  }, null, 2));

  // Also emit a live-mode audit log: data/live-publish-runs/<runId>.json
  const runLog = {
    runId,
    mode: 'live',
    fixture: isFixtureMode(),
    startedAt: new Date().toISOString(),
    successes,
    skips,
    failures,
  };
  const runsDir = path.join(DATA, 'live-publish-runs');
  fs.mkdirSync(runsDir, { recursive: true });
  fs.writeFileSync(path.join(runsDir, `${runId}.json`), JSON.stringify(runLog, null, 2));

  console.log(`\n[run_publisher] --live run complete (runId=${runId})`);
  console.log(`   Published: ${successes.length}`);
  console.log(`   Skipped:   ${skips.length}`);
  console.log(`   Failed:    ${failures.length}`);
  if (isFixtureMode()) {
    console.log(`   ⚠️  POSTIZ_FIXTURE=true — all responses were synthetic. cmFIXTURE* IDs are not real Postiz posts.`);
  }

  return { ok: true, mode: 'live', runId, published: successes.length, skipped: skips.length, failed: failures.length };
}

// ── Entry point ──────────────────────────────────────────────────────────
async function run() {
  if (LIVE_MODE) {
    return await runLive();
  }
  return runDry();
}

module.exports = {
  run,
  runDry,
  runLive,
  // Exported for tests
  buildPublishingReference,
  appendReferenceToCanonical,
  persistRawResponse,
  validateStatusTransition,
  loadFixtureResponse,
  buildFixtureResponse,
  resolveAssetForItem,
  ALLOWED_TRANSITIONS,
  ACTION_TO_STATUS,
  InvalidStatusTransitionError,
  DuplicatePostizPostIdError,
};

if (require.main === module) {
  run().then((result) => {
    process.exit(result.failed > 0 ? 1 : 0);
  }).catch((e) => {
    console.error(`[run_publisher] FATAL: ${e.message}`);
    console.error(e.stack);
    process.exit(2);
  });
}