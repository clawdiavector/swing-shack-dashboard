#!/usr/bin/env node
/**
 * scripts/regenerate-publishing-index.js
 *
 * Regenerates data/publishing-references.json from the canonical campaign-data.json.
 *
 * INVARIANTS (Step 78 spec):
 *   - campaigns[cid].publishing[] is the SOLE canonical durable source.
 *   - data/publishing-references.json is a generated lookup index only.
 *   - Index MUST be fully rebuildable from campaign-data.json.
 *   - Index MUST NOT contain facts absent from campaign-data.json.
 *   - Index MUST carry sourceCampaignSha256 (external hash from data/state.json).
 *   - Index regeneration MUST fail loudly on error (exit code 1, stderr).
 *   - Index write MUST be atomic (temp file → rename).
 *
 * INVARIANTS (final amendments):
 *   - No contentHash or contentVersion INSIDE campaign-data.json.
 *   - External hash lives in data/state.json (NOT a sibling .sha256 file).
 *   - Data events directory: data/events/postiz/ (renamed from data/postiz-events/).
 *
 * USAGE:
 *   node scripts/regenerate-publishing-index.js            # write the index
 *   node scripts/regenerate-publishing-index.js --dry-run  # report what would change
 *
 * MODULE API (used by run_publisher.js):
 *   const { regenerate } = require('./regenerate-publishing-index');
 *   const result = regenerate({ canonicalPath, outputPath, statePath, eventsDir, dryRun });
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ── Paths (defaults; override via options) ──────────────────────────────────
const REPO_ROOT = path.join(__dirname, '..');
const DEFAULT_CANONICAL = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');
const DEFAULT_OUTPUT = path.join(REPO_ROOT, 'data', 'publishing-references.json');
const DEFAULT_STATE = path.join(REPO_ROOT, 'data', 'state.json');
const DEFAULT_EVENTS_DIR = path.join(REPO_ROOT, 'data', 'events', 'postiz');

// ── Crypto helper ───────────────────────────────────────────────────────────
function sha256OfString(s) {
  return crypto.createHash('sha256').update(s, 'utf8').digest('hex');
}

function sha256OfFile(p) {
  return sha256OfString(fs.readFileSync(p, 'utf8'));
}

// ── State file (external hash store) ────────────────────────────────────────
function readStateFile(statePath) {
  if (!fs.existsSync(statePath)) {
    return { canonicalSha256: null, updatedAt: null, contentHashHistory: [] };
  }
  try {
    return JSON.parse(fs.readFileSync(statePath, 'utf8'));
  } catch (e) {
    throw new Error(`state file is malformed: ${e.message}`);
  }
}

function writeStateFile(statePath, newSha256, updatedAt) {
  const current = readStateFile(statePath);
  const history = (current.contentHashHistory || []).slice(-99); // keep last 100
  history.push({ sha256: newSha256, updatedAt });
  const next = {
    schema: 'https://clawdia.io/agents/publisher/state/v1',
    canonicalSha256: newSha256,
    updatedAt,
    contentHashHistory: history,
  };
  const tmp = statePath + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(next, null, 2));
  fs.renameSync(tmp, statePath);
}

// ── Reference projection ────────────────────────────────────────────────────
// STRICT projection: every field is read directly from the canonical record.
// No computed fields. No transformations. No inference.
function projectReference(campaignId, ref) {
  return {
    publishingId: ref.publishingId,
    assetId: ref.assetId,
    campaignId,
    postizPostId: ref.postizPostId,
    integrationId: ref.integrationId,
    integrationProvider: ref.integrationProvider,
    channel: ref.channel,
    releaseURL: ref.releaseURL,
    releaseId: ref.releaseId,
    platformMediaId: ref.platformMediaId,
    currentStatus: ref.currentStatus,
    createdAt: ref.createdAt,
    scheduledAt: ref.scheduledAt,
    publishedAt: ref.publishedAt,
    provenance: ref.provenance,
  };
}

// ── Main regeneration ──────────────────────────────────────────────────────
function regenerate(options = {}) {
  const canonicalPath = options.canonicalPath || DEFAULT_CANONICAL;
  const outputPath = options.outputPath || DEFAULT_OUTPUT;
  const statePath = options.statePath || DEFAULT_STATE;
  const dryRun = !!options.dryRun;

  if (!fs.existsSync(canonicalPath)) {
    throw new Error(`canonical file not found: ${canonicalPath}`);
  }

  // Compute canonical SHA-256 from the FILE BYTES, not the parsed JSON.
  // This catches every byte-level modification including whitespace.
  const canonicalBytes = fs.readFileSync(canonicalPath);
  const canonicalSha256 = crypto.createHash('sha256').update(canonicalBytes).digest('hex');

  // Read state BEFORE parsing canonical, so we can report staleness.
  const stateBefore = readStateFile(statePath);

  let data;
  try {
    data = JSON.parse(canonicalBytes.toString('utf8'));
  } catch (e) {
    throw new Error(`canonical file is not valid JSON: ${e.message}`);
  }

  const references = [];
  const campaigns = data.campaigns || {};
  for (const campaignId of Object.keys(campaigns)) {
    const campaign = campaigns[campaignId];
    const publishing = campaign.publishing || [];
    if (!Array.isArray(publishing)) {
      throw new Error(`campaigns[${campaignId}].publishing is not an array`);
    }
    for (const ref of publishing) {
      // Validate required fields exist (truthful — don't write a partial index)
      for (const k of ['publishingId', 'assetId', 'postizPostId', 'integrationId',
                       'channel', 'currentStatus', 'createdAt', 'provenance']) {
        if (ref[k] === undefined || ref[k] === null) {
          throw new Error(
            `campaigns[${campaignId}].publishing[] missing required field: ${k} ` +
            `(publishingId=${ref.publishingId || '?'})`
          );
        }
      }
      references.push(projectReference(campaignId, ref));
    }
  }

  const updatedAt = new Date().toISOString();

  const indexPayload = {
    schema: 'https://clawdia.io/agents/publisher/publishing-references/v1',
    generated: updatedAt,
    sourceCampaignSha256: canonicalSha256,
    sourceCampaignFile: path.relative(REPO_ROOT, canonicalPath),
    regenerationMode: options.mode || 'full',
    count: references.length,
    references,
  };

  if (dryRun) {
    return {
      ok: true,
      dryRun: true,
      canonicalSha256,
      previousSha256: stateBefore.canonicalSha256,
      sha256Changed: canonicalSha256 !== stateBefore.canonicalSha256,
      referenceCount: references.length,
      outputPath,
    };
  }

  // Atomic write: temp file → rename. No partial writes possible.
  const tmpOutput = outputPath + '.tmp';
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(tmpOutput, JSON.stringify(indexPayload, null, 2));
  fs.renameSync(tmpOutput, outputPath);

  // Update external state file with new SHA-256
  writeStateFile(statePath, canonicalSha256, updatedAt);

  return {
    ok: true,
    dryRun: false,
    canonicalSha256,
    previousSha256: stateBefore.canonicalSha256,
    sha256Changed: canonicalSha256 !== stateBefore.canonicalSha256,
    referenceCount: references.length,
    outputPath,
    statePath,
  };
}

// ── CLI ─────────────────────────────────────────────────────────────────────
if (require.main === module) {
  const dryRun = process.argv.includes('--dry-run');
  try {
    const result = regenerate({ dryRun });
    if (dryRun) {
      console.log(`[dry-run] canonical sha256: ${result.canonicalSha256}`);
      console.log(`[dry-run] previous sha256:  ${result.previousSha256 || '(none)'}`);
      console.log(`[dry-run] sha256 changed:   ${result.sha256Changed}`);
      console.log(`[dry-run] would write:      ${result.referenceCount} references → ${result.outputPath}`);
    } else {
      console.log(
        `✅ Index regenerated: ${result.referenceCount} references, ` +
        `sha256 ${result.canonicalSha256.substring(0, 12)}…, ` +
        `changed=${result.sha256Changed}`
      );
    }
  } catch (e) {
    console.error(`❌ Index regeneration FAILED: ${e.message}`);
    process.exit(1);
  }
}

module.exports = { regenerate, sha256OfFile, sha256OfString, readStateFile, writeStateFile };