#!/usr/bin/env node
/**
 * Campaign OS — Write to campaign-data.json
 * 
 * Usage:
 *   node scripts/write-campaign.js <agent> <field-path> <json-value>
 * 
 * Example — update health score:
 *   node scripts/write-campaign.js lab "campaign.healthScore" 72
 * 
 * Example — update asset status:
 *   node scripts/write-campaign.js publisher "assets.hook-a.publishState" "\"live\""
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '..');
const DATA_FILE = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');

const AGENTS = ['copywriter', 'image-gen', 'publisher', 'truth-collector', 'lab', 'clawfix', 'gremlin', 'scout', 'memories'];

function main() {
  const args = process.argv.slice(3);
  
  if (args.length < 2) {
    console.log('Usage: node write-campaign.js <agent> <field-path> <json-value>');
    console.log('Example: node write-campaign.js lab "campaign.healthScore" 72');
    process.exit(1);
  }
  
  const agent = args[0];
  const fieldPath = args[1];
  const rawValue = args[2] || 'null';
  
  if (!AGENTS.includes(agent)) {
    console.error('Unknown agent:', agent);
    process.exit(1);
  }
  
  // Parse value
  let value;
  try {
    value = JSON.parse(rawValue);
  } catch {
    // Try as plain string if JSON parse fails
    value = rawValue;
  }
  
  // Load current data
  const data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  
  // Navigate to field path and set value
  const parts = fieldPath.split('.');
  let current = data;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!current[parts[i]]) current[parts[i]] = {};
    current = current[parts[i]];
  }
  current[parts[parts.length - 1]] = value;
  
  data.updatedAt = new Date().toISOString();
  
  // Write back
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2) + '\n');
  console.log('Written:', fieldPath, '=', JSON.stringify(value));
  
  // Git commit and push
  try {
    execSync('git add campaign-os/campaign-data.json', { cwd: REPO_ROOT, stdio: 'pipe' });
    const commitMsg = `[write] ${agent} → ${fieldPath} = ${JSON.stringify(value)}`;
    execSync('git commit -m "' + commitMsg.replace(/"/g, '\\"') + '"', { cwd: REPO_ROOT, stdio: 'pipe' });
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