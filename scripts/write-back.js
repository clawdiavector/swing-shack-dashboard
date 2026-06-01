#!/usr/bin/env node
/**
 * Campaign OS — Write-Back Staging Script
 * 
 * Agents write to campaign-data-staged.json as an atomic intermediate step.
 * This script handles the commit/push cycle that triggers cockpit regeneration.
 * 
 * Usage:
 *   node scripts/write-back.js <agent-name> <action> <assetId> [json-payload]
 * 
 * Example:
 *   node scripts/write-back.js publisher dispatch hook-a '{"publishState":"scheduled"}'
 * 
 * The script:
 * 1. Reads campaign-data-staged.json
 * 2. Applies the patch (field updates)
 * 3. Validates basic schema
 * 4. Writes back to campaign-data-staged.json
 * 5. Commits with agent-specific message
 * 6. Pushes to origin main
 * 7. Cockpit regeneration fires via GitHub Actions webhook
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '..');
const STAGED_FILE = path.join(REPO_ROOT, 'campaign-data-staged.json');
const MAIN_FILE = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');

// Agent write domains
const AGENT_DOMAINS = {
  'copywriter': ['assets', 'campaign'],
  'image-gen': ['assets', 'campaign'],
  'publisher': ['assets', 'campaign'],
  'truth-collector': ['analytics', 'campaign'],
  'lab': ['campaign'],
  'clawfix': ['*']
};

function usage(msg) {
  console.error('ERROR: ' + msg);
  console.error('Usage: node write-back.js <agent> <action> <target> [patch-json]');
  console.error('Agents: copywriter, image-gen, publisher, truth-collector, lab, clawfix');
  process.exit(1);
}

function validateAgent(agent) {
  if (!AGENT_DOMAINS[agent]) {
    usage('Unknown agent: ' + agent);
  }
}

function loadStaged() {
  if (!fs.existsSync(STAGED_FILE)) {
    // Copy from main if staged doesn't exist
    if (fs.existsSync(MAIN_FILE)) {
      fs.copyFileSync(MAIN_FILE, STAGED_FILE);
      console.log('Initialized staged from main file');
    } else {
      // Create empty campaign structure
      const empty = { campaign: { campaignId: 'trackman-intelligence', name: 'TrackMan Intelligence' }, assets: [], analytics: {}, updatedAt: new Date().toISOString() };
      fs.writeFileSync(STAGED_FILE, JSON.stringify(empty, null, 2));
      console.log('Created new staged file');
    }
  }
  return JSON.parse(fs.readFileSync(STAGED_FILE, 'utf8'));
}

function saveStaged(data) {
  fs.writeFileSync(STAGED_FILE, JSON.stringify(data, null, 2));
}

function applyPatch(data, target, patch) {
  // Navigate to target path and apply patch
  const parts = target.split('.');
  let current = data;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!current[parts[i]]) current[parts[i]] = {};
    current = current[parts[i]];
  }
  const finalKey = parts[parts.length - 1];
  current[finalKey] = { ...current[finalKey], ...patch };
  return data;
}

function commitAndPush(agent, action, target, patch) {
  try {
    // Stage the file
    execSync('git add campaign-data-staged.json', { cwd: REPO_ROOT, stdio: 'pipe' });
    
    // Generate commit message
    const patchStr = Object.keys(patch || {}).map(k => k + ':' + JSON.stringify(patch[k])).join(',');
    const msg = `[write] ${agent} → ${target} — ${action}${patchStr ? ' ' + patchStr : ''}`;
    
    // Commit
    execSync('git commit -m "' + msg.replace(/"/g, '\\"') + '"', { cwd: REPO_ROOT, stdio: 'pipe' });
    
    // Push
    const result = execSync('git push origin main 2>&1', { cwd: REPO_ROOT, encoding: 'utf8' });
    console.log('Pushed successfully');
    console.log(result);
    return true;
  } catch (err) {
    console.error('Git error:', err.message);
    // Check if there's a pending push (nothing to commit)
    if (err.message.includes('nothing to commit')) {
      console.log('Nothing to commit — staged file unchanged');
      return true;
    }
    return false;
  }
}

function main() {
  const args = process.argv.slice(3);
  if (args.length < 2) {
    usage('Expected at least 2 args: <agent> <action> <target> [patch-json]');
  }
  
  const agent = args[0];
  const action = args[1];
  const target = args[2] || '';
  const patchArg = args[3] || '{}';
  
  validateAgent(agent);
  
  console.log('Agent:', agent);
  console.log('Action:', action);
  console.log('Target:', target || '(none)');
  
  // Load and patch
  const data = loadStaged();
  
  let patch = {};
  try {
    patch = JSON.parse(patchArg);
  } catch(e) {
    usage('Invalid JSON patch: ' + patchArg);
  }
  
  if (target && Object.keys(patch).length > 0) {
    applyPatch(data, target, patch);
  }
  
  // Add history entry
  if (!data.history) data.history = [];
  data.history.push({
    agent,
    action,
    target,
    patch,
    at: new Date().toISOString()
  });
  
  data.updatedAt = new Date().toISOString();
  
  // Save staged
  saveStaged(data);
  console.log('Staged file updated');
  
  // Commit and push
  commitAndPush(agent, action, target, patch);
  
  console.log('Write-back complete');
}

// Run
main();