#!/usr/bin/env node
/**
 * scripts/reconcile-asset-state.js
 *
 * CLI for the canonical Asset State Engine.
 *
 * Reads campaign-os/campaign-data.json, runs evaluateAsset on every asset,
 * applies the resulting state via applyStateTransition, and (unless --dry-run)
 * atomically persists the changes.
 *
 * Usage:
 *   node scripts/reconcile-asset-state.js                  # all campaigns, live
 *   node scripts/reconcile-asset-state.js --dry-run        # report only
 *   node scripts/reconcile-asset-state.js --campaign takomo-101t
 *   node scripts/reconcile-asset-state.js --json           # machine-readable output
 *   node scripts/reconcile-asset-state.js --canonical-path /path/to/canonical.json
 *
 * Exit codes:
 *   0 = success (no changes or dry-run or all changes applied)
 *   1 = error (file not found, lock contention, parse error)
 *   2 = success but only because the requested campaign was not found
 *
 * The CLI NEVER writes to asset.history. The engine itself never writes to
 * asset.history either — this CLI follows the same rule.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const eng = require('./_lib/asset-state-engine');

function parseArgs(argv) {
  const out = { dryRun: false, json: false, campaign: null, canonicalPath: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--dry-run') out.dryRun = true;
    else if (a === '--json') out.json = true;
    else if (a === '--campaign') out.campaign = argv[++i];
    else if (a === '--canonical-path') out.canonicalPath = argv[++i];
    else if (a === '--help' || a === '-h') {
      console.log(fs.readFileSync(__filename, 'utf8').match(/Usage:[\s\S]*?(?=\n \* Exit codes)/)[0].replace(/^\/\*\*\n \* /gm, '').trim());
      process.exit(0);
    }
    else {
      console.error(`Unknown flag: ${a}`);
      process.exit(1);
    }
  }
  return out;
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const cp = opts.canonicalPath || path.join(__dirname, '..', 'campaign-os', 'campaign-data.json');

  if (!fs.existsSync(cp)) {
    console.error(`canonical file not found: ${cp}`);
    process.exit(1);
  }

  let result;
  if (opts.campaign) {
    try {
      result = eng.reconcileCampaign(opts.campaign, cp, { dryRun: opts.dryRun });
      result.campaign = opts.campaign;
    } catch (e) {
      if (/campaign not found/.test(e.message)) {
        if (opts.json) {
          console.log(JSON.stringify({ error: 'campaign_not_found', campaign: opts.campaign }, null, 2));
        } else {
          console.error(`Campaign not found: ${opts.campaign}`);
        }
        process.exit(2);
      }
      throw e;
    }
  } else {
    result = eng.reconcileAll({ dryRun: opts.dryRun, canonicalPath: cp });
  }

  if (opts.json) {
    console.log(JSON.stringify({
      canonicalPath: cp,
      dryRun: result.dryRun,
      totalChanged: result.changed,
      summary: result.summary,
    }, null, 2));
  } else {
    console.log(`Reconcile ${result.dryRun ? '(DRY RUN)' : '(LIVE)'}: ${result.changed} asset(s) changed`);
    if (result.summary && result.summary.length > 0) {
      for (const s of result.summary) {
        const cid = s.campaignId || result.campaign || '?';
        console.log(`  ${cid}/${s.assetId}: ${s.fieldsChanged.join(', ')}`);
      }
    } else {
      console.log('  (no changes)');
    }
    console.log(`Canonical: ${cp}`);
  }
}

try {
  main();
} catch (e) {
  console.error(`Error: ${e.message}`);
  console.error(e.stack);
  process.exit(1);
}