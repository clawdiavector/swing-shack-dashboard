#!/usr/bin/env node
/**
 * Gate 6: Blueprint Generator — M5 + M6 (Blueprint Versioning)
 *
 * Calls the campaign-specific blueprint generator (Python/MiniMax-M2.7).
 * Supports versioning: archive previous, generate new, accept, regenerate.
 *
 * Usage:
 *   node generate-blueprint.js <campaignId> # v1 (first run or overwrite v1)
 *   node generate-blueprint.js <campaignId> --new # force new v+1 version
 *   node generate-blueprint.js <campaignId> --accept     # accept current version
 *   node generate-blueprint.js <campaignId> --regenerate # archive + generate new v+1
 *
 * Output: {success, version, pillars, tone, diffSummary}
 */
const fs   = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '..');
const DATA_FILE = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');

function main() {
  const args = process.argv.slice(2);
  const campaignId = args[0];
  if (!campaignId) {
    console.log('Usage: node generate-blueprint.js <campaignId> [--new|--accept|--regenerate]');
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  const campaign = data.campaigns && data.campaigns[campaignId];
  if (!campaign) {
    console.error('Campaign not found:', campaignId);
    process.exit(1);
  }

  // Build Python command with appropriate flags
  const pyArgs = [campaignId];
  if (args.includes('--accept'))     pyArgs.push('--accept');
  else if (args.includes('--regenerate')) pyArgs.push('--regenerate');
  else if (args.includes('--new'))   pyArgs.push('--regenerate'); // --new is alias for --regenerate

  const pyCmd = `/opt/homebrew/bin/python3 scripts/generate-blueprint.py ${pyArgs.join(' ')}`;

  const isMeta = args.includes('--accept');
  console.log(isMeta
    ? `Accepting blueprint for: ${campaignId}`
    : `Generating blueprint for: ${campaignId}`);

  let stdout = '';
  try {
    stdout = execSync(pyCmd, { cwd: REPO_ROOT, encoding: 'utf8', timeout: 120000 });
    console.log(stdout.trim());
  } catch (err) {
    console.error('Blueprint script error:', err.message);
    if (err.stdout) console.error(err.stdout);
    process.exit(1);
  }

  // Read back updated campaign
  const updated = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  const refreshed = updated.campaigns[campaignId];

  // Meta operations (--accept) don't generate a new blueprint
  if (isMeta) {
    const v = refreshed.blueprintVersion || 0;
    console.log(`Blueprint v${v} ${args.includes('--accept') ? 'accepted' : 'updated'} for: ${campaignId}`);
    process.exit(0);
  }

  // Verify blueprint was written
  const bp = refreshed && {
    blueprintVersion: refreshed.blueprintVersion,
    generatedAt:      refreshed.generatedAt,
    modelUsed:        refreshed.modelUsed,
    dna:              refreshed.dna,
    visualDirection:  refreshed.visualDirection,
    pillars:          refreshed.strategy && refreshed.strategy.pillars
  };

  if (!bp || !bp.blueprintVersion) {
    console.error('Blueprint not applied — no version info');
    process.exit(1);
  }

  console.log(`Blueprint v${bp.blueprintVersion} complete for: ${campaignId}`);

  // Build diff summary from memory
  let diffSummary = 'initial version';
  const versions = refreshed.memory && refreshed.memory.blueprintVersions || [];
  const thisVer = versions.find(v => v.version === bp.blueprintVersion);
  if (thisVer && thisVer.diffSummary) diffSummary = thisVer.diffSummary;

  // Git commit and push (only for generate, not --accept)
  try {
    execSync('git add campaign-os/campaign-data.json', { cwd: REPO_ROOT, stdio: 'pipe' });
    const msg = args.includes('--regenerate')
      ? `feat: regenerate blueprint v${bp.blueprintVersion} for ${campaignId} [m6]`
      : `feat: generate blueprint v${bp.blueprintVersion} for ${campaignId} [gate-6-m5]`;
    execSync(`git commit -m "${msg}"`, { cwd: REPO_ROOT, stdio: 'pipe' });
    execSync('git push origin main', { cwd: REPO_ROOT, stdio: 'pipe' });
    console.log('Committed and pushed — GitHub Actions will regenerate cockpit');
  } catch (err) {
    if (!err.message.includes('nothing to commit')) {
      console.error('Git error:', err.message);
    }
  }

  console.log(JSON.stringify({
    success:      true,
    campaignId,
    version:      bp.blueprintVersion,
    generatedAt:  bp.generatedAt,
    modelUsed:    bp.modelUsed,
    pillars:      (bp.pillars || []).map(p => p.name),
    tone:         (bp.dna || {}).tone,
    diffSummary
  }));
}

main();
