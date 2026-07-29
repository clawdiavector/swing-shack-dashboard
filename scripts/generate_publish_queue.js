#!/usr/bin/env node
/**
 * scripts/generate_publish_queue.js
 *
 * Step 89 — Canonical publish queue generator.
 *
 * Campaign OS is the queue PRODUCER. Publisher is the queue CONSUMER.
 * This generator translates:
 *
 *   campaign-data.json
 *           |
 *           v
 *   ready-for-approval.json
 *
 * The output preserves the legacy `qa-inspector/v1` schema so Publisher
 * consumes it exactly as before. Legacy items that have NO Campaign OS
 * match are preserved (so the legacy pipeline keeps working until
 * formally retired).
 *
 * Filter pipeline (for Campaign OS-derived items):
 *   1. asset.publishStatus === 'scheduled'   (engine-projected)
 *   2. campaign.identity.status === 'active'
 *   3. asset.platform is non-empty
 *   4. asset.assetId NOT in data/published-items.json
 *   5. No publishing[] entry exists for this assetId in any campaign
 *
 * Deduplication: items sorted by item_id, no duplicates.
 * Determinism: same canonical -> byte-identical output.
 * Idempotence: re-run with no canonical changes -> identical output.
 *
 * NO mutation of campaign-data.json. NO synthetic IDs.
 *
 * Usage:
 *   node scripts/generate_publish_queue.js                  # writes data/ready-for-approval.json
 *   node scripts/generate_publish_queue.js --dry-run        # report only
 *   node scripts/generate_publish_queue.js --json           # machine-readable output
 *   node scripts/generate_publish_queue.js --canonical-path <p>
 *
 * Exit codes:
 *   0 = success (writes + report)
 *   1 = error (file not found, parse error)
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const { evaluateAsset } = require('./_lib/asset-state-engine');

const DEFAULT_CANONICAL = path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');
const DATA_DIR = path.join(__dirname, '..', 'data');
const READY_FOR_APPROVAL_PATH = path.join(DATA_DIR, 'ready-for-approval.json');
const PUBLISHED_ITEMS_PATH = path.join(DATA_DIR, 'published-items.json');
const LEGACY_SCHEMA = 'https://clawdia.io/agents/qa-inspector/v1';

// Mirror of scripts/run_publisher.js INTEGRATIONS map. Single source of
// integration IDs (also exported from run_publisher.js in LIVE mode, but
// we duplicate here so the generator stays a standalone script).
const INTEGRATIONS = {
  instagram: 'cmnfoum2703e6ql0yiajgcg21',
  tiktok:    'cmmdgfz3b00s1o20ykrwau2o2',
  gmb:       'cmmdgju7f00tppk0y6bne9zrk',
  facebook:  'cmmdg0bty00r6o20yvmzskvdw',
};

function parseArgs(argv) {
  const out = { dryRun: false, json: false, canonicalPath: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--dry-run') out.dryRun = true;
    else if (a === '--json') out.json = true;
    else if (a === '--canonical-path') out.canonicalPath = argv[++i];
    else if (a === '--help' || a === '-h') {
      console.log('Usage: node scripts/generate_publish_queue.js [--dry-run] [--json] [--canonical-path <p>]');
      process.exit(0);
    } else {
      console.error(`Unknown flag: ${a}`);
      process.exit(1);
    }
  }
  return out;
}

// Deterministic slug from asset name. Lowercase, replace non-alnum with -.
function slugify(name) {
  if (typeof name !== 'string') return null;
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .substring(0, 80) || null;
}

// Pick the first platform from a comma-separated string. Returns null if
// the string is empty/undefined.
function firstPlatform(platformField) {
  if (typeof platformField !== 'string') return null;
  const parts = platformField.split(',').map(p => p.trim()).filter(Boolean);
  return parts[0] || null;
}

// Read JSON file or return null. Never throws.
function readJsonSafe(p) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) { return null; }
}

// Load the set of item_ids that have already been published, so the
// generator never re-emits an already-published item.
function loadPublishedItemIds() {
  const pub = readJsonSafe(PUBLISHED_ITEMS_PATH);
  if (!pub || !Array.isArray(pub.published)) return new Set();
  return new Set(pub.published.map(p => p.item_id).filter(Boolean));
}

// Load the set of assetIds that already have a publishing[] reference
// in the canonical. Prevents double-emission.
function loadPublishedAssetIdsFromCanonical(canonical) {
  const ids = new Set();
  for (const campaign of Object.values(canonical.campaigns || {})) {
    for (const ref of (campaign.publishing || [])) {
      if (ref && ref.assetId) ids.add(ref.assetId);
    }
  }
  return ids;
}

// Build a legacy-shaped item from a Campaign OS asset that has cleared
// the filter pipeline. Deterministic: no Date.now() per item, no random.
function buildQueueItem(asset, campaignId, generatedAt) {
  const platform = firstPlatform(asset.platform);
  return {
    item_id: asset.assetId,                                      // canonical
    linked_blueprint_id: asset.assetId,                          // publisher's resolveAssetForItem keys on this
    linked_hook_id: slugify(asset.name) || asset.assetId,        // deterministic slug
    item_type: asset.assetType || 'caption',
    platform,
    format_type: 'static',
    hook_text: typeof asset.caption === 'string'
      ? asset.caption.substring(0, 220)
      : '',
    verdict: 'pass',                                              // all 4 gates satisfied
    issues: [],
    passed_checks: 4,
    total_checks: 4,
    owner: asset.owner || 'clawdia',
    days_in_queue: 0,
    priority: 'normal',
    queue_owner: 'campaign-os-generator',
    generated_at: generatedAt,
    source: 'campaign-os',                                        // provenance
    campaign_id: campaignId,                                      // extra context (publisher ignores unknown fields)
  };
}

// Run the engine over all assets and collect scheduled ones in active
// campaigns. Read-only — does not mutate campaign-data.json.
function collectScheduledAssets(canonical) {
  const results = [];
  for (const [campaignId, campaign] of Object.entries(canonical.campaigns || {})) {
    if (!campaign || typeof campaign !== 'object') continue;
    const status = campaign.identity && campaign.identity.status;
    if (status !== 'active') continue;
    const assets = campaign.assets || {};
    for (const [assetId, asset] of Object.entries(assets)) {
      if (!asset || typeof asset !== 'object') continue;
      const history = Array.isArray(asset.history) ? asset.history : [];
      const r = evaluateAsset(asset, history, {});
      if (r.publishStatus !== 'scheduled') continue;
      results.push({ campaignId, asset, assetId, projected: r });
    }
  }
  // Deterministic sort by (campaignId, assetId)
  results.sort((a, b) => {
    if (a.campaignId !== b.campaignId) return a.campaignId < b.campaignId ? -1 : 1;
    return a.assetId < b.assetId ? -1 : a.assetId > b.assetId ? 1 : 0;
  });
  return results;
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const canonicalPath = opts.canonicalPath || DEFAULT_CANONICAL;

  if (!fs.existsSync(canonicalPath)) {
    console.error(`canonical file not found: ${canonicalPath}`);
    process.exit(1);
  }
  const canonical = JSON.parse(fs.readFileSync(canonicalPath, 'utf8'));

  // Deterministic generated timestamp — use canonical's updatedAt if
  // present, else current time. (Determinism test: same canonical
  // produced at the same logical time yields byte-identical output.)
  const generatedAt = (canonical && canonical.updatedAt) || new Date().toISOString();

  // Step 1: collect Campaign OS assets that pass the filter
  const scheduled = collectScheduledAssets(canonical);

  // Step 2: filter out already-published items
  const publishedIds = loadPublishedItemIds();
  const publishingIds = loadPublishedAssetIdsFromCanonical(canonical);
  const eligible = scheduled.filter(({ asset, assetId }) => {
    if (publishedIds.has(assetId)) return false;
    if (publishingIds.has(assetId)) return false;
    if (!firstPlatform(asset.platform)) return false;
    return true;
  });

  // Step 3: build queue items
  const campaignOsItems = eligible.map(({ asset, campaignId }) =>
    buildQueueItem(asset, campaignId, generatedAt)
  );

  // Step 4: merge with existing legacy items (preserve any not superseded)
  const existing = readJsonSafe(READY_FOR_APPROVAL_PATH) || { items: [] };
  const campaignOsItemIds = new Set(campaignOsItems.map(i => i.item_id));
  const preservedLegacy = (Array.isArray(existing.items) ? existing.items : [])
    .filter(item => item && item.item_id && !campaignOsItemIds.has(item.item_id));

  // Step 5: dedupe and sort (final list)
  const allItems = [...campaignOsItems, ...preservedLegacy];
  const seen = new Set();
  const deduped = [];
  for (const item of allItems) {
    if (!item || !item.item_id || seen.has(item.item_id)) continue;
    seen.add(item.item_id);
    deduped.push(item);
  }
  deduped.sort((a, b) => (a.item_id < b.item_id ? -1 : a.item_id > b.item_id ? 1 : 0));

  // Step 6: build output
  const output = {
    schema: LEGACY_SCHEMA,
    generated: generatedAt,
    source: 'campaign-os+legacy-merge',
    count: deduped.length,
    campaignOsCount: campaignOsItems.length,
    legacyCount: preservedLegacy.length,
    skipped: {
      alreadyPublished: scheduled.length - eligible.length,
      totalScheduled: scheduled.length,
    },
    items: deduped,
  };

  // Step 7: atomic write or report
  if (!opts.dryRun) {
    const tmp = READY_FOR_APPROVAL_PATH + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(output, null, 2));
    fs.renameSync(tmp, READY_FOR_APPROVAL_PATH);
  }

  // Step 8: report
  if (opts.json) {
    console.log(JSON.stringify({
      canonicalPath,
      dryRun: opts.dryRun,
      outputPath: READY_FOR_APPROVAL_PATH,
      generatedAt,
      eligibleFromCampaignOs: campaignOsItems.length,
      preservedLegacy: preservedLegacy.length,
      totalItems: deduped.length,
      items: deduped.map(i => ({ item_id: i.item_id, platform: i.platform, source: i.source || 'legacy' })),
    }, null, 2));
  } else {
    console.log(`Publish queue generator (${opts.dryRun ? 'DRY RUN' : 'LIVE'})`);
    console.log(`  Canonical:   ${canonicalPath}`);
    console.log(`  Output:      ${READY_FOR_APPROVAL_PATH}`);
    console.log(`  Scheduled assets in active campaigns: ${scheduled.length}`);
    console.log(`  Eligible after already-published filter: ${eligible.length}`);
    console.log(`  Campaign OS items emitted:   ${campaignOsItems.length}`);
    console.log(`  Preserved legacy items:      ${preservedLegacy.length}`);
    console.log(`  Total items in queue:        ${deduped.length}`);
    if (campaignOsItems.length > 0) {
      console.log(`\n  Campaign OS items:`);
      for (const item of campaignOsItems) {
        console.log(`    ${item.item_id} (platform=${item.platform})`);
      }
    }
    if (!opts.dryRun) {
      console.log(`\n✓ Wrote ${READY_FOR_APPROVAL_PATH} (${deduped.length} items)`);
    } else {
      console.log(`\n(dry run — no file written)`);
    }
  }
}

try {
  main();
} catch (e) {
  console.error(`Error: ${e.message}`);
  console.error(e.stack);
  process.exit(1);
}