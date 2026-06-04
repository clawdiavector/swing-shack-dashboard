#!/usr/bin/env node
/**
 * Gate 4: Create Campaign Object
 * Reads 13 fields from modal form submission, creates a campaign object,
 * writes to campaign-data.json, commits and pushes via git.
 *
 * Usage: node scripts/create-campaign.js <JSON-string-of-form-data>
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '..');
const DATA_FILE = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');
const HTML_FILE = path.join(REPO_ROOT, 'campaign-os', 'cockpit-operational.html');

function main() {
  const raw = process.argv[2];
  if (!raw) {
    console.error('Usage: node create-campaign.js <JSON-string-of-form-data>');
    process.exit(1);
  }

  let formData;
  try {
    formData = JSON.parse(raw);
  } catch (e) {
    console.error('Invalid JSON input:', e.message);
    process.exit(1);
  }

  // Load existing data
  const data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));

  // Generate ID from name
  const id = formData.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') +
    '-' + Date.now().toString(36);

  // Build campaign object from 13 fields
  const campaign = {
    name: formData.name,
    type: formData.type,
    status: 'briefSubmitted',
    identity: {
      primaryGoal: formData.primaryGoal || '',
      targetAudience: formData.targetAudience || '',
      primaryOffer: formData.primaryOffer || '',
      successTarget: formData.successTarget || ''
    },
    priority: formData.priority || 'medium',
    duration: formData.duration || '4-weeks',
    platforms: formData.platforms || [],
    context: formData.context || '',
    notes: formData.notes || '',
    campaignSource: {
      type: formData.sourceType || 'manual',
      reference: formData.sourceRef || id,
      createdBy: 'Christelle'
    },
    owner: 'Christelle',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    pipeline: { status: 'idle' },
    assets: {}
  };

  // Write to campaign-data.json
  if (!data.campaigns) data.campaigns = {};
  data.campaigns[id] = campaign;
  data.updatedAt = new Date().toISOString();

  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2) + '\n');
  console.log('Campaign created:', id, '—', campaign.name);

  // Git commit and push
  try {
    execSync('git add campaign-os/campaign-data.json', { cwd: REPO_ROOT, stdio: 'pipe' });
    execSync('git commit -m "feat: create campaign \\"' + campaign.name + '\\" [gate-4]"', { cwd: REPO_ROOT, stdio: 'pipe' });
    execSync('git push origin main', { cwd: REPO_ROOT, stdio: 'pipe' });
    console.log('Committed and pushed');
  } catch (err) {
    if (err.message.includes('nothing to commit')) {
      console.log('No changes to commit');
    } else {
      console.error('Git error:', err.message);
    }
  }

  return id;
}

main();