#!/usr/bin/env node
/**
 * Campaign OS — Create Campaign Object (V2 Schema)
 *
 * Reads pending form data from campaign-data-staged.json,
 * builds a V2-compliant campaign object, writes to campaign-data.json,
 * commits and pushes to GitHub.
 *
 * Outputs structured JSON to stdout:
 *   {success: true,  campaignId: "..."}  on success
 *   {success: false, error: "..."}       on failure
 *
 * Exits 0 on success, non-zero on failure.
 *
 * Usage: node scripts/create-campaign.js
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT    = path.join(__dirname, '..');
const DATA_FILE    = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');
const STAGED_FILE  = path.join(REPO_ROOT, 'campaign-os', 'campaign-data-staged.json');

function output(result) {
  console.log(JSON.stringify(result));
}

function main() {
  // Read staged form data
  if (!fs.existsSync(STAGED_FILE)) {
    output({ success: false, error: 'staged-file-not-found' });
    process.exit(1);
  }

  let staged;
  try {
    staged = JSON.parse(fs.readFileSync(STAGED_FILE, 'utf8'));
  } catch(e) {
    output({ success: false, error: 'staged-parse-error: ' + e.message });
    process.exit(1);
  }

  if (!staged._pending) {
    output({ success: false, error: 'not-pending' });
    process.exit(1);
  }

  const formData = staged.formData || staged;

  // ── Generate campaignId ──────────────────────────────────────────────────
  const id = formData.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') +
    '-' + Date.now().toString(36);

  // ── Build V2 campaign object ────────────────────────────────────────────────
  const campaign = {
    identity: {
      campaignId:    id,
      name:          formData.name,
      campaignType:  formData.type,
      status:        'draft',
      primaryGoal:   formData.primaryGoal   || '',
      healthScore:   null,
      healthState:   'unknown',
      priority:      formData.priority      || 'medium',
      duration:      formData.duration      || '4-weeks',
      owner:         'Christelle',
      platforms:     formData.platforms      || [],
      campaignSource: {
        type:      formData.sourceType  || 'Manual',
        reference: formData.sourceRef   || id,
        createdBy: 'Christelle'
      }
    },
    brief: {
      audience:      formData.targetAudience || '',
      goalNotes:     formData.notes          || '',
      successTarget: formData.successTarget  || '',
      context:       formData.context        || ''
    },
    strategy: {
      primaryOffer:  formData.primaryOffer   || ''
    },
    assets:          {},
    dna:             {},
    visualDirection: {},
    memory: { notes: [] },
    pipeline: {
      status:       'generatingBlueprint',
      currentStep:  0,
      totalSteps:   4,
      currentAgent: null
    }
  };

  // ── Write to campaign-data.json ─────────────────────────────────────────
  let data;
  try {
    data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  } catch(e) {
    output({ success: false, error: 'campaign-data-parse-error: ' + e.message });
    process.exit(1);
  }

  // ── Safety: reject duplicate campaignId ──────────────────────────────
  if (data.campaigns && data.campaigns[id]) {
    output({ success: false, error: 'campaign-id-exists: ' + id });
    process.exit(1);
  }

  if (!data.campaigns) data.campaigns = {};
  data.campaigns[id] = campaign;
  data.updatedAt = new Date().toISOString();

  try {
    fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2) + '\n');
  } catch(e) {
    output({ success: false, error: 'campaign-data-write-error: ' + e.message });
    process.exit(1);
  }

  // ── Git commit and push (staged file cleared ONLY on success) ────────────
  let pushFailed = false;
  let gitError   = null;

  try {
    execSync('git add campaign-os/campaign-data.json campaign-os/campaign-data-staged.json', {
      cwd: REPO_ROOT, stdio: 'pipe'
    });
    execSync(
      'git commit -m "feat: create campaign \\"' + campaign.identity.name + '\\" [gate-4]"',
      { cwd: REPO_ROOT, stdio: 'pipe' }
    );
    execSync('git push origin main', { cwd: REPO_ROOT, stdio: 'pipe' });
  } catch (err) {
    pushFailed = true;
    gitError   = err.message || String(err);
    // Do NOT clear staged file — keep it so poll script can detect failure and surface it
  }

  if (pushFailed) {
    // Keep staged file so retry is possible
    output({ success: false, error: 'git-push-failed: ' + gitError.slice(0, 300) });
    process.exit(1);
  }

  // ── Push succeeded — clear staged file ────────────────────────────────────
  try {
    fs.writeFileSync(STAGED_FILE, JSON.stringify({}) + '\n');
  } catch(e) {
    // Staged clear failed but push succeeded — log warning, campaign is safe
    console.error('WARNING: could not clear staged file:', e.message);
  }

  output({ success: true, campaignId: id, name: campaign.identity.name });
  process.exit(0);
}

main();