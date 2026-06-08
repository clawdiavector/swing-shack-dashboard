#!/usr/bin/env node
/**
 * Gate 6: M4 Blueprint Generator (M5 Improved)
 *
 * Calls the campaign-specific blueprint generator (Python/MiniMax-M2.7)
 * to produce DNA, pillars, visual direction, and content mix that are
 * genuinely specific to this campaign's brief, theme, and context.
 *
 * No generic templates. No campaign-type assumptions.
 * Every field reflects this campaign and no other.
 *
 * Usage: node scripts/generate-blueprint.js <campaignId>
 */
const fs   = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '..');
const DATA_FILE = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');

function main() {
  const campaignId = process.argv[2];
  if (!campaignId) {
    console.log('Usage: node generate-blueprint.js <campaignId>');
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  const campaign = data.campaigns && data.campaigns[campaignId];

  if (!campaign) {
    console.error('Campaign not found:', campaignId);
    process.exit(1);
  }

  // Run the campaign-specific blueprint generator (MiniMax-M2.7 reasoning)
  console.log(`Calling campaign-specific blueprint generator for: ${campaignId}`);
  try {
    execSync(
      '/opt/homebrew/bin/python3 scripts/generate-blueprint.py ' + campaignId,
      { cwd: REPO_ROOT, encoding: 'utf8', timeout: 120000 }
    );
  } catch (err) {
    console.error('Blueprint generation failed:', err.message);
    process.exit(1);
  }

  // Re-read the updated campaign
  const updated = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  const refreshed = updated.campaigns[campaignId];

  // Verify blueprint was applied
  const pillars = refreshed.strategy && refreshed.strategy.pillars;
  const dna     = refreshed.dna;

  if (!pillars || !pillars.length || !dna || !dna.tone) {
    console.error('Blueprint not applied — missing pillars or DNA');
    process.exit(1);
  }

  console.log(`Blueprint generated for: ${campaignId}`);
  console.log(`  Pillars: ${pillars.map(p => p.name).join(', ')}`);
  console.log(`  Tone: ${dna.tone.slice(0, 60)}...`);

  // Git commit and push
  try {
    execSync('git add campaign-os/campaign-data.json', { cwd: REPO_ROOT, stdio: 'pipe' });
    execSync(
      'git commit -m "feat: generate blueprint for ' + campaignId + ' [gate-6]"',
      { cwd: REPO_ROOT, stdio: 'pipe' }
    );
    execSync('git push origin main', { cwd: REPO_ROOT, stdio: 'pipe' });
    console.log('Committed and pushed — GitHub Actions will regenerate cockpit');
  } catch (err) {
    if (err.message.includes('nothing to commit')) {
      console.log('No changes to commit');
    } else {
      console.error('Git error:', err.message);
    }
  }
}

main();