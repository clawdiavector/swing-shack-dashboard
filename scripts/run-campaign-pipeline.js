// Campaign creation pipeline — runs on cron
// Step 1: create-campaign.js — creates V2 campaign object from staged data
// Step 2: generate-blueprint.js — populates DNA, visualDirection, strategy, memory

const { execSync } = require('child_process');
const path = require('path');

const REPO_ROOT = path.join(__dirname, '..');

function run(script, label) {
  console.log('Running:', label);
  try {
    execSync('node ' + script, { cwd: REPO_ROOT, stdio: 'inherit' });
    console.log(label, 'complete');
  } catch(e) {
    console.error(label, 'failed:', e.message);
    process.exit(1);
  }
}

// Run step 1: create campaign object from staged JSON
run('scripts/create-campaign.js', 'create-campaign');

// Run step 2: generate blueprint for each campaign in generatingBlueprint state
run('scripts/generate-blueprint.js', 'generate-blueprint');

console.log('Campaign pipeline complete');
