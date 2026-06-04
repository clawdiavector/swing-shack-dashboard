#!/usr/bin/env node
/**
 * Campaign OS — Create Campaign Object (V2 Schema)
 *
 * Reads pending form data from campaign-data-staged.json,
 * builds a V2-compliant campaign object, writes to campaign-data.json.
 *
 * Usage: node scripts/create-campaign.js
 * (Reads staged JSON — no CLI args needed for normal operation)
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '..');
const DATA_FILE  = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');
const STAGED_FILE = path.join(REPO_ROOT, 'campaign-os', 'campaign-data-staged.json');

function main() {
  // Read staged form data
  if (!fs.existsSync(STAGED_FILE)) {
    console.log('No pending campaign submissions found.');
    return;
  }

  const staged = JSON.parse(fs.readFileSync(STAGED_FILE, 'utf8'));

  if (!staged._pending) {
    console.log('No pending campaign to process.');
    return;
  }

  const formData = staged;

  // ── Generate campaignId ──────────────────────────────────────────────────
  const id = formData.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') +
    '-' + Date.now().toString(36);

  // ── Build V2 campaign object ────────────────────────────────────────────
  const campaign = {
    identity: {
      campaignId:    id,
      name:          formData.name,
      campaignType:  formData.type,
      status:        'briefSubmitted',
      primaryGoal:   formData.primaryGoal   || '',
      priority:      formData.priority      || 'medium',
      duration:      formData.duration       || '4-weeks',
      owner:         'Christelle',
      platforms:     formData.platforms       || [],
      campaignSource: {
        type:       formData.sourceType  || 'Manual',
        reference:  formData.sourceRef   || id,
        createdBy:  'Christelle'
      }
    },
    brief: {
      audience:      formData.targetAudience || '',
      goalNotes:     formData.notes          || '',
      successTarget: formData.successTarget  || ''
    },
    strategy: {
      primaryOffer:  formData.primaryOffer   || ''
    },
    assets:          {},
    dna:             {},
    visualDirection: {},
    memory: {
      notes:         []
    },
    pipeline: {
      status:        'generatingBlueprint',
      currentStep:   0,
      totalSteps:    4,
      currentAgent:  null
    }
  };

  // ── Write to campaign-data.json ─────────────────────────────────────────
  const data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));

  if (!data.campaigns) data.campaigns = {};
  data.campaigns[id] = campaign;
  data.updatedAt = new Date().toISOString();

  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2) + '\n');
  console.log('Campaign created:', id, '—', campaign.identity.name);

  // ── Clear staged file ────────────────────────────────────────────────────
  fs.writeFileSync(STAGED_FILE, JSON.stringify({}) + '\n');

  // ── Git commit and push ──────────────────────────────────────────────────
  try {
    execSync('git add campaign-os/campaign-data.json campaign-os/campaign-data-staged.json', {
      cwd: REPO_ROOT, stdio: 'pipe'
    });
    execSync(
      'git commit -m "feat: create campaign \\"' + campaign.identity.name + '\\" [gate-4]"',
      { cwd: REPO_ROOT, stdio: 'pipe' }
    );
    execSync('git push origin main', { cwd: REPO_ROOT, stdio: 'pipe' });
    console.log('Committed and pushed');
  } catch (err) {
    if (err.message.includes('nothing to commit')) {
      console.log('No changes to commit');
    } else {
      console.error('Git error:', err.message);
    }
  }
}

main();