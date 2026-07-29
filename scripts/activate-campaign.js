#!/usr/bin/env node
/**
 * scripts/activate-campaign.js
 *
 * CLI for the canonical campaign lifecycle engine.
 *
 * Usage:
 *   node scripts/activate-campaign.js --campaign <id> --dry-run
 *   node scripts/activate-campaign.js --campaign <id> --by <actor> --reason <text>
 *   node scripts/activate-campaign.js --campaign <id> --json
 *
 * Flags:
 *   --campaign <id>   Required. campaignId to activate.
 *   --by <actor>      Optional. Defaults to "christelle".
 *   --reason <text>   Optional. Defaults to "Campaign activation approved".
 *   --canonical-path <p>  Optional. Override default canonical path.
 *   --dry-run         Evaluate only, do not write.
 *   --json            Machine-readable output (one JSON document, exit code 0).
 *   --help            Show usage.
 *
 * Exit codes:
 *   0  activation succeeded OR idempotent no-op OR dry-run
 *   1  activation failed (not-ready, illegal transition, missing campaign, error)
 */

'use strict';

const path = require('path');
const { activateCampaign, isTerminalStatus } = require('./_lib/campaign-state-engine');

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const tok = argv[i];
    if (tok === '--help' || tok === '-h') args.help = true;
    else if (tok === '--dry-run') args.dryRun = true;
    else if (tok === '--json') args.json = true;
    else if (tok === '--campaign') { args.campaignId = argv[++i]; }
    else if (tok === '--by') { args.by = argv[++i]; }
    else if (tok === '--reason') { args.reason = argv[++i]; }
    else if (tok === '--canonical-path') { args.canonicalPath = argv[++i]; }
    else if (tok.startsWith('--')) { args[tok.slice(2)] = argv[++i]; }
  }
  return args;
}

function usage() {
  const lines = [
    'Usage:',
    '  node scripts/activate-campaign.js --campaign <id> [--dry-run]',
    '  node scripts/activate-campaign.js --campaign <id> [--by <actor>] [--reason <text>] [--json]',
    '',
    'Examples:',
    '  node scripts/activate-campaign.js --campaign use-the-right-equipment-mq5l90bk --dry-run',
    '  node scripts/activate-campaign.js --campaign use-the-right-equipment-mq5l90bk \\',
    '    --by christelle --reason "Campaign activation approved after readiness proof"',
    ''
  ];
  return lines.join('\n');
}

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.help) {
    process.stdout.write(usage());
    return 0;
  }

  if (!args.campaignId) {
    process.stderr.write('ERROR: --campaign <id> required\n\n' + usage());
    return 1;
  }

  const opts = {
    campaignId: args.campaignId,
    by: args.by || 'christelle',
    reason: args.reason || 'Campaign activation approved',
    canonicalPath: args.canonicalPath,
    dryRun: args.dryRun === true
  };

  const result = activateCampaign(args.campaignId, opts);

  if (args.json) {
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } else {
    if (result.ok) {
      if (result.changed) {
        process.stdout.write(`✓ Activated ${args.campaignId}: ${result.fromStatus} -> ${result.toStatus}\n`);
        process.stdout.write(`  Event written: action=${result.event.action} by=${result.event.by} at=${result.event.at}\n`);
        process.stdout.write(`  Scheduled assets: ${result.scheduledAssetIds.join(', ')}\n`);
      } else {
        process.stdout.write(`= ${args.campaignId}: no-op (${result.reason})\n`);
        if (result.scheduledAssetIds.length > 0) {
          process.stdout.write(`  Scheduled assets: ${result.scheduledAssetIds.join(', ')}\n`);
        }
      }
    } else {
      process.stdout.write(`✗ Activation failed for ${args.campaignId}: ${result.reason}\n`);
      if (result.blockers.length > 0) {
        for (const b of result.blockers) process.stdout.write(`  - ${b}\n`);
      }
    }
  }

  return result.ok ? 0 : 1;
}

if (require.main === module) {
  process.exit(main());
}

module.exports = { main, parseArgs };