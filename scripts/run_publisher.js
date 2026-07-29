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
const visibilityGuard = require('./_lib/visibility-guard');

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

// Provider-specific Postiz `settings` shape (Step 94). Each provider must
// declare its own object so platforms do not blindly reuse the Instagram
// settings. Settings must include `__type` and `post_type` per Postiz API
// contract. Optional fields default sensibly.
const PROVIDER_SETTINGS = {
  instagram: ({ post_type = 'post' } = {}) => ({
    __type: 'instagram',
    post_type,
    is_trial_reel: false,
    collaborators: [],
  }),
  tiktok: () => ({
    __type: 'tiktok',
    post_type: 'post',
    is_trial_reel: false,
    collaborators: [],
  }),
  gmb: () => ({
    __type: 'gmb',
    post_type: 'post',
    is_trial_reel: false,
    collaborators: [],
  }),
  facebook: () => ({
    __type: 'facebook',
    post_type: 'post',
    is_trial_reel: false,
    collaborators: [],
  }),
};

// ── Postiz upload endpoint (media upload helper) ──────────────────────────
//
// Step 94: real media is required for Instagram posts. Postiz exposes a
// dedicated upload endpoint that returns { id, path } which must be referenced
// from posts[].value[].image[]. The helper below is HTTP-agnostic: it returns
// a normalized { ok, id, path, status, body, raw } envelope. The caller decides
// what to do with the result.
//
// CRITICAL: this function is network-touching. Callers MUST guard it:
//   - fixture mode MUST NOT call it (use the upload fixture instead)
//   - live mode MUST wrap it in try/catch and log failures for reconciliation
//   - secrets MUST NOT be printed in any error path

function postizUpload({ filePath, key, mimeType }) {
  return new Promise((resolve, reject) => {
    if (!filePath || !fs.existsSync(filePath)) {
      return resolve({ ok: false, status: 0, error: 'missing_local_file', filePath });
    }
    const fileBuf = fs.readFileSync(filePath);
    const filename = path.basename(filePath);
    const boundary = '----PostizBoundary' + Math.random().toString(36).slice(2);
    const mime = mimeType || (filePath.toLowerCase().endsWith('.jpg') || filePath.toLowerCase().endsWith('.jpeg') ? 'image/jpeg' : 'application/octet-stream');

    const parts = [];
    parts.push(`--${boundary}\r\n`);
    parts.push(`Content-Disposition: form-data; name="file"; filename="${filename}"\r\n`);
    parts.push(`Content-Type: ${mime}\r\n\r\n`);
    const head = Buffer.from(parts.join(''), 'utf8');
    const tail = Buffer.from(`\r\n--${boundary}--\r\n`, 'utf8');
    const body = Buffer.concat([head, fileBuf, tail]);

    const req = https.request({
      hostname: 'api.postiz.com',
      path: '/public/v1/upload',
      method: 'POST',
      headers: {
        'Authorization': key,
        'Content-Type': `multipart/form-data; boundary=${boundary}`,
        'Content-Length': body.length,
      },
      timeout: 30000,
    }, (res) => {
      let buf = '';
      res.on('data', (c) => { buf += c; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(buf);
          if (res.statusCode >= 200 && res.statusCode < 300) {
            // Normalized envelope — Postiz returns { id, path } (and possibly other fields)
            resolve({
              ok: true,
              status: res.statusCode,
              id: parsed.id || null,
              path: parsed.path || null,
              body: parsed,
              raw: buf,
            });
          } else {
            resolve({ ok: false, status: res.statusCode, body: parsed, raw: buf, error: 'http_error' });
          }
        } catch (e) {
          resolve({ ok: false, status: res.statusCode, body: null, raw: buf, parseError: e.message, error: 'parse_error' });
        }
      });
    });
    req.on('error', (e) => reject(e));
    req.on('timeout', () => { req.destroy(new Error('timeout')); });
    req.write(body);
    req.end();
  });
}

// Build the canonical Postiz v1 payload for a single (provider, asset) pair.
// Pure function: same inputs produce same outputs. No I/O, no globals, no
// randomness. The caption must be the full canonical caption (truth) — the
// queue's hook_text is a 220-char preview and is intentionally ignored.
//
// `imageRefs` is an array of { id, path } objects from the upload step.
// Empty array means text-only (allowed by Postiz; required for non-IG).
function buildPostizPayload({ provider, integrationId, date, caption, tags = [], imageRefs = [] }) {
  if (!provider || !integrationId || !caption) {
    throw new Error('buildPostizPayload requires provider, integrationId, caption');
  }
  const settingsBuilder = PROVIDER_SETTINGS[provider];
  if (!settingsBuilder) {
    throw new Error(`unknown provider: ${provider}`);
  }
  const value = [{
    content: caption,
    image: imageRefs.map(ref => ({ id: ref.id, path: ref.path })),
  }];
  return {
    type: 'draft',
    date,
    shortLink: false,
    tags: Array.isArray(tags) ? tags : [],
    posts: [{
      integration: { id: integrationId },
      value,
      settings: settingsBuilder(),
    }],
  };
}

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
  assetId, campaignId, response, fixture, runId, actor, isReconciliation,
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
      source: isReconciliation ? 'publisher-reconciliation' : (LIVE_MODE ? 'publisher' : 'publisher-fixture'),
      runId,
      actor,
      publishedVia: isReconciliation ? 'reconciliation' : (isFixtureMode() ? 'fixture' : 'postiz-api'),
      chain: isReconciliation ? ['publisher-reconciliation'] : [isFixtureMode() ? 'publisher-fixture' : 'publisher', 'postiz-api'],
      rawResponseRef: {
        hash: rawRef.hash,
        path: path.relative(REPO_ROOT, rawRef.path),
        capturedAt: now,
      },
      // Step 95: when the canonical entry was reconciled from an existing Postiz
      // orphan (no fresh API call), record the source run + draft ID so the
      // audit trail is unambiguous.
      reconciledFrom: isReconciliation ? {
        orphanPostizPostId: response.id,
        sourceRunId: typeof fixture?.runId === 'string' ? fixture.runId : null,
        reconciledAt: now,
      } : undefined,
    },
    history: [
      {
        action: 'created',
        at: now,
        by: actor,
        reason: isReconciliation ? 'orphan_reconciled'
              : currentStatus === 'draft' ? 'draft_created'
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
// Step 87 Publisher integration + Step 94b event split:
//   1. Append a truthful history event based on Postiz's response state:
//        live/published → 'publish-confirmed' (only path that may flip
//                        publishStatus to 'live')
//        scheduled     → 'publish-scheduled'
//        draft         → 'publish-draft-created'  (default for type=draft)
//        failed        → 'publish-failed'
//   2. evaluateAsset(asset, asset.history, externalSignals) — pure projection
//   3. applyStateTransition(asset, desired) — field-only mutator
//   4. Persist the updated asset atomically (lock + atomic rename)
//
// The reference is canonical; the state fields are derived. If the engine
// crashes, the next reconcile run will project the correct state anyway.
//
// Helper that maps Postiz response.state (or .currentStatus) to:
//   - the history event action to emit
//   - the external postizConfirmations[].status to feed to the engine
// Both are needed so that:
//   (a) history is truthful (draft != live)
//   (b) the engine's evaluation path stays the same (no event-string coupling
//       inside evaluatePublishStatus — the only live-trigger is the ext signal)
function eventAndSignalForPostizStatus(rawStatus) {
  const s = (rawStatus || '').toString().toUpperCase();
  switch (s) {
    case 'LIVE':
    case 'PUBLISHED':
      return { action: 'publish-confirmed', externalStatus: 'live' };
    case 'SCHEDULED':
    case 'QUEUE':
      return { action: 'publish-scheduled', externalStatus: 'scheduled' };
    case 'DRAFT':
      return { action: 'publish-draft-created', externalStatus: 'draft' };
    case 'FAILED':
    case 'ERROR':
      return { action: 'publish-failed', externalStatus: 'failed' };
    default:
      // Unknown / null state from Postiz: treat as draft (safest truth)
      return { action: 'publish-draft-created', externalStatus: 'draft' };
  }
}

function derivePublishingStateAfterPostiz(ref, postizStatus) {
  let outcome = { changed: false, fieldsChanged: [], error: null };
  acquireCanonicalLock();
  try {
    const canonical = readCanonical();
    const campaign = canonical.campaigns && canonical.campaigns[ref.campaignId];
    if (!campaign) throw new Error(`campaign not found: ${ref.campaignId}`);
    const asset = campaign.assets && campaign.assets[ref.assetId];
    if (!asset) throw new Error(`asset not found: ${ref.assetId}`);

    // Step 1: record truthful history event (Step 94b).
    if (!Array.isArray(asset.history)) asset.history = [];
    const { action, externalStatus } = eventAndSignalForPostizStatus(postizStatus);
    const eventPayload = {
      by: 'publisher',
      postizPostId: ref.postizPostId,
      releaseURL: ref.releaseURL || null,
      releaseId: ref.releaseId || null,
      currentStatus: ref.currentStatus,
    };
    if (action === 'publish-confirmed') {
      eventPayload.reason = 'postiz_returned_live';
    } else if (action === 'publish-scheduled') {
      eventPayload.reason = 'postiz_returned_scheduled';
    } else if (action === 'publish-draft-created') {
      eventPayload.reason = 'postiz_returned_draft';
    } else if (action === 'publish-failed') {
      eventPayload.reason = 'postiz_returned_failed';
    }
    recordEvent(asset.history, action, eventPayload);

    // Step 2: pure projection — only 'live'/'published' external status
    // is allowed to flip publishStatus to 'live'. Draft/scheduled/failed
    // statuses leave publishStatus where eligibility puts it.
    const desired = evaluateAsset(asset, asset.history, {
      postizConfirmations: [{
        assetId: ref.assetId,
        status: externalStatus,
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

// ── Partial-write duplicate protection (Step 94b) ─────────────────────────
//
// If a prior run uploaded + created a Postiz draft but failed to write the
// canonical publishing reference, the Postiz draft exists externally while
// Campaign OS has no record of it. On retry, we must:
//   1. Look up prior reconciliation entries in data/live-publish-runs/*.json
//   2. If a proven draft exists for this (assetId, integrationId), do NOT
//      call Postiz again — instead, reconcile by writing the canonical
//      publishing reference using the known draft ID.
//   3. Only call POST /public/v1/posts when no proven prior draft exists.
//
// Duplicate detection uses assetId+integrationId+postizPostId (NOT caption
// similarity — the spec explicitly forbids that).

function findPriorDraftForAsset({ assetId, integrationId }) {
  const runsDir = path.join(DATA, 'live-publish-runs');
  if (!fs.existsSync(runsDir)) return null;
  // Build (mtimeMs, filename) tuples, sort newest-first by mtime. Filename
  // sort is a fallback tie-breaker. mtime is the source of truth for
  // "most recent" — file mtimes are reliable across platforms, whereas
  // filename prefixes are random.
  const allFiles = fs.readdirSync(runsDir).filter(fn => fn.endsWith('.json'));
  const filesWithMtime = allFiles.map(fn => {
    let mtimeMs = 0;
    try {
      const st = fs.statSync(path.join(runsDir, fn));
      mtimeMs = st.mtimeMs || 0;
    } catch (_) { /* ignore */ }
    return { fn, mtimeMs };
  });
  filesWithMtime.sort((a, b) => {
    if (b.mtimeMs !== a.mtimeMs) return b.mtimeMs - a.mtimeMs;
    return b.fn.localeCompare(a.fn);
  });
  const files = filesWithMtime.map(x => x.fn);
  for (const fn of files) {
    try {
      const runLog = JSON.parse(fs.readFileSync(path.join(runsDir, fn), 'utf8'));
      // Reconciliation entries live on failures[].reconciliation when stage
      // is 'canonical_write_after_create'. Also look at successes[] for the
      // postizPostId in case the canonical write succeeded in a prior run.
      const candidates = [];
      if (Array.isArray(runLog.successes)) {
        for (const s of runLog.successes) {
          if (s.assetId === assetId && s.integrationId === integrationId) {
            candidates.push({
              postizPostId: s.postizPostId,
              rawResponseHash: s.rawResponseHash,
              source: 'successes',
              runId: runLog.runId,
              at: runLog.startedAt,
              stage: 'success',
            });
          }
        }
      }
      if (Array.isArray(runLog.failures)) {
              for (const f of runLog.failures) {
                if (f.item_id === assetId && f.reconciliation &&
                    f.reconciliation.stage === 'canonical_write_after_create' &&
                    Array.isArray(f.reconciliation.imageRefs) &&
                    f.reconciliation.imageRefs.length > 0) {
                  // Step 94b duplicate detection uses assetId+integrationId
                  // (NOT caption similarity). The integration id is captured
                  // implicitly via the imageRefs[] entry's source — but at the
                  // point of canonical_write_after_create we don't store it
                  // explicitly on the reconciliation entry. Instead, we rely
                  // on the caller to filter by integrationId, and we keep
                  // the entry's imageRefs so the caller can match against
                  // its own integration-id-keyed cache.
                  //
                  // The stage=canonical_write_after_create presence plus non-empty
                  // imageRefs proves the create succeeded. The postizPostId may or
                  // may not be present (it is set by derivePublishingStateAfterPostiz
                  // after a successful create response); we treat its absence as a
                  // soft signal — keep the entry but mark postizPostId=null so the
                  // caller can decide whether to retry.
                  candidates.push({
                    postizPostId: f.reconciliation.postizPostId || null,
                    imageRefs: f.reconciliation.imageRefs,
                    createResponseHash: f.reconciliation.createResponseHash || null,
                    stage: 'canonical_write_after_create',
                    runId: runLog.runId,
                    at: runLog.startedAt,
                  });
                }
              }
            }
      // Integration-id match (Step 94b: assetId + integrationId is the key,
      // NOT caption similarity). If the candidate's imageRefs[0] doesn't
      // belong to this integrationId, drop it.
      if (integrationId) {
        for (let i = candidates.length - 1; i >= 0; i--) {
          const c = candidates[i];
          if (c.imageRefs && c.imageRefs[0] && c.imageRefs[0].integrationId &&
              c.imageRefs[0].integrationId !== integrationId) {
            candidates.splice(i, 1);
          }
        }
      }
      if (candidates.length > 0) return candidates[0];
    } catch (_) {
      // ignore unparseable run files
    }
  }
  return null;
}

// Synthesise a minimal Postiz response shape from a prior reconciliation
// entry. The downstream code only needs id, integration, state — so we
// rebuild enough for buildPublishingReference to succeed.
function responseFromReconciliation(recon) {
  // Synthesise a Postiz-shaped response from a reconciliation record so the
  // publisher can call buildPublishingReference without making a real Postiz
  // API call. The synthesised response MUST include providerIdentifier so
  // buildPublishingReference's `CHANNEL_TO_PROVIDER[integrationProvider]`
  // lookup doesn't throw "unknown integration provider: null".
  //
  // Field name is `postizPostId` to match the canonical reconciliation record
  // shape produced by the runLive catch handler and the
  // findPriorDraftForAsset helper (both use `postizPostId`).
  const integrationId = recon.imageRefs?.[0]?.integrationId || '';
  const providerIdentifier = inferProviderFromIntegration(integrationId);
  const draftId = recon.postizPostId;
  return {
    id: draftId,
    state: 'DRAFT', // most likely case; original was a draft creation
    releaseURL: null,
    releaseId: null,
    content: '',
    integration: { id: integrationId, providerIdentifier },
    publishDate: recon.at || new Date().toISOString(),
  };
}

// Infer a Postiz providerIdentifier from an integrationId. The Postiz
// integrations list endpoint returns the canonical id → provider mapping.
// We hardcode the known Swing Shack integrations here; this could be lifted
// to a cached lookup against the integrations endpoint.
function inferProviderFromIntegration(integrationId) {
  const known = {
    cmnfoum2703e6ql0yiajgcg21: 'instagram',
    cmmdgfz3b00s1o20ykrwau2o2: 'tiktok',
    cmmdgju7f00tppk0y6bne9zrk: 'gmb',
    cmmdg0bty00r6o20yvmzskvdw: 'facebook',
  };
  return known[integrationId] || 'instagram'; // safe default for this brand
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

    // Step 0.5: Partial-write duplicate protection (Step 94b).
    //
    // If a prior run uploaded + created a Postiz draft but failed to write
    // the canonical publishing reference, the draft exists on Postiz but not
    // in Campaign OS. Before we call Postiz again, check whether a proven
    // prior draft exists for this (assetId, integrationId). If yes, attempt
    // canonical reconciliation using the known draft ID instead of creating
    // a second draft.
    //
    // This check runs ONLY in LIVE mode (not fixture). Fixture mode is for
    // tests where the reconciliation record is fake.
    let reconciliationContext = null;
    if (!isFixtureMode()) {
      const priorDraft = findPriorDraftForAsset({
        assetId,
        integrationId: integration.id,
      });
      if (priorDraft && priorDraft.postizPostId) {
        const operatorState = (process.env.VISIBILITY_DISPUTES ? (JSON.parse(process.env.VISIBILITY_DISPUTES)[assetId]) : null) || 'unknown';
        const guard = visibilityGuard.assertNoVisibilityDispute({ apiState: 'exists', canonicalState: 'exists', operatorVisibilityState: operatorState });
        if (!visibilityGuard.blocksAction(guard, 'duplicate-skip')) {
          reconciliationContext = priorDraft;
          console.log(`[run_publisher] partial-write recovery: found prior draft ${priorDraft.postizPostId} for asset ${assetId}; reconciling instead of recreating.`);
        } else {
          console.log(`[run_publisher] partial-write recovery SKIPPED for asset ${assetId}: guard=${guard.state} (${guard.reason}).`);
        }
      }
    }

    // Step 1.5: Media upload (Step 94 contract)
    // Instagram requires real media via /public/v1/upload; the response {id, path}
    // is referenced from posts[].value[].image[]. Missing local file or failed
    // upload blocks the draft creation. Fixture mode skips the real upload.
    let imageRefs = [];
    const localMediaPath = asset && typeof asset.filePath === 'string' ? asset.filePath : null;
    const needsUpload = !isFixtureMode() && localMediaPath;
    if (needsUpload) {
      try {
        const uploadResult = await postizUpload({ filePath: localMediaPath, key: POSTIZ_KEY });
        if (!uploadResult.ok || !uploadResult.id || !uploadResult.path) {
          failures.push({
            item_id: item.item_id,
            reason: 'postiz_upload_failed',
            excerpt: `status=${uploadResult.status} error=${uploadResult.error || 'unknown'} filePath=${localMediaPath}`,
            reconciliation: { stage: 'upload', assetId, campaignId, localMediaPath },
          });
          continue;
        }
        imageRefs = [{ id: uploadResult.id, path: uploadResult.path }];
      } catch (e) {
        failures.push({
          item_id: item.item_id,
          reason: 'postiz_upload_network_error',
          excerpt: e.message.substring(0, 400),
          reconciliation: { stage: 'upload', assetId, campaignId, localMediaPath },
        });
        continue;
      }
    } else if (!isFixtureMode() && !localMediaPath) {
      // Live mode without media: block the request — Postiz rejects empty image[]
      // for providers that require media. (For non-IG providers we may allow text-only
      // later; for now, block all live publishes without media.)
      failures.push({
        item_id: item.item_id,
        reason: 'missing_media',
        excerpt: `asset.filePath is missing or not a string; live publish requires media`,
      });
      continue;
    }

    // Build the canonical Postiz v1 payload via the shared helper (Step 94 contract)
    const payload = buildPostizPayload({
      provider: integration.provider,
      integrationId: integration.id,
      date: planEntry?.scheduled_date ? new Date(planEntry.scheduled_date).toISOString() : new Date().toISOString(),
      caption: captionText,
      tags: [], // Per Step 94 spec: tags is an object array or []
      imageRefs,
    });

    // Step 2: Call Postiz (real, fixture, or reconciliation)
    let response;
    let usedFixture = false;
    let usedReconciliation = false;
    if (reconciliationContext) {
      const operatorState = (process.env.VISIBILITY_DISPUTES ? (JSON.parse(process.env.VISIBILITY_DISPUTES)[item.item_id]) : null) || 'unknown';
      const guard = visibilityGuard.assertNoVisibilityDispute({ apiState: 'unknown', canonicalState: 'exists', operatorVisibilityState: operatorState });
      if (visibilityGuard.blocksAction(guard, 'reconcile')) {
        console.log(`[run_publisher] --live (RECONCILE) BLOCKED: guard=${guard.state} (${guard.reason}). Falling back.`);
        reconciliationContext = null;
      } else {
        console.log(`[run_publisher] --live (RECONCILE): reusing prior draft ${reconciliationContext.postizPostId} for ${item.item_id}`);
        response = responseFromReconciliation(reconciliationContext);
        usedReconciliation = true;
      }
    } else if (isFixtureMode()) {
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
            // If we already uploaded media but Postiz rejected the create, record
            // the reconciliation entry so an operator can clean up the orphan upload.
            reconciliation: imageRefs.length > 0 ? {
              stage: 'create_after_upload',
              assetId, campaignId, imageRefs, status: result.status,
            } : null,
          });
          continue;
        }
        response = result.body;
      } catch (e) {
        failures.push({
          item_id: item.item_id,
          reason: 'postiz_network_error',
          excerpt: e.message.substring(0, 400),
          reconciliation: imageRefs.length > 0 ? {
            stage: 'create_after_upload_network',
            assetId, campaignId, imageRefs,
          } : null,
        });
        continue;
      }
    }

    // Step 3: Build + append reference (atomic, with lock)
    // TDZ FIX (Phase 1, Item 1): ref is declared with `let` outside the try
    // block so the catch handler can reference it even if buildPublishingReference
    // throws before assignment. This preserves the original error in `e` while
    // letting the catch produce a complete reconciliation record.
    let ref = null;
    try {
      ref = buildPublishingReference({
        assetId,
        campaignId,
        response,
        fixture: usedFixture ? response : null,
        runId,
        actor,
        isReconciliation: usedReconciliation,
      });
      appendReferenceToCanonical(ref, campaignId);

      // Step 3.5: derive 5 publishing-state fields via Asset State Engine.
      // (Step 94b: event action is split by Postiz state — draft → publish-
      // draft-created, scheduled → publish-scheduled, live/published →
      // publish-confirmed. Only publish-confirmed may flip publishStatus to
      // 'live'.)
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
        // Step 94b: when canonical write fails AFTER upload + create succeeded,
        // the Postiz draft exists externally but Campaign OS has no reference.
        // Record the reconciliation context so the next retry can recover.
        // The integrationId is attached to imageRefs[0] so findPriorDraftForAsset
        // can filter candidates by integrationId (NOT caption similarity).
        //
        // TDZ FIX: ref is now `let`-declared above. It is null only when
        // buildPublishingReference itself threw; otherwise it carries the
        // partially-built ref so postizPostId + provenance can be preserved.
        //
        // Field name is `postizPostId` to match the existing
        // test_step94b_event_semantics_and_recovery.js contract
        // (which checks the source literal `postizPostId:`).
        const postizDraftId = (ref && typeof ref === 'object' && ref.postizPostId) ? ref.postizPostId : null;
        const createResponseHashValue = (ref && ref.provenance && ref.provenance.rawResponseRef && ref.provenance.rawResponseRef.hash)
          ? ref.provenance.rawResponseRef.hash
          : null;
        const reconImageRefs = (imageRefs || []).map(r => ({
          id: r.id,
          path: r.path,
          integrationId: integration.id,
        }));
        failures.push({
          item_id: item.item_id,
          reason: 'canonical_write_failed',
          // Preserve the ORIGINAL error — name, message, and stack — so the
          // underlying failure is always visible in the audit record.
          excerpt: e.message.substring(0, 400),
          originalError: {
            name: e.name || 'Error',
            message: e.message,
            stack: typeof e.stack === 'string' ? e.stack.split('\n').slice(0, 8).join('\n') : null,
          },
          reconciliation: {
            stage: 'canonical_write_after_create',
            assetId,
            campaignId,
            integrationId: integration.id,
            imageRefs: reconImageRefs,
            postizPostId: postizDraftId,
            createResponseHash: createResponseHashValue,
            // Did buildPublishingReference itself throw? If so, ref is null
            // and we have no postizPostId from the ref. Surface that signal
            // explicitly so the failure is not silently downgraded.
            refBuilt: ref !== null,
            at: new Date().toISOString(),
          },
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
  // Step 94 exports
  buildPostizPayload,
  PROVIDER_SETTINGS,
  postizUpload,
  // Step 94b exports
  eventAndSignalForPostizStatus,
  findPriorDraftForAsset,
  responseFromReconciliation,
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