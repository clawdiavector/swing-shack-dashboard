#!/usr/bin/env node
/**
 * dashboard_pipeline.js
 * Master daily pipeline: fetch all sources → compile → publish
 * Run at 07:00 SAST weekdays
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const LOG = path.join(__dirname, '..', 'logs', 'daily-run.log');
const REPO = path.join(__dirname, '..');

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  try {
    const existing = fs.existsSync(LOG) ? fs.readFileSync(LOG, 'utf8').split('\n').slice(-200).join('\n') : '';
    fs.writeFileSync(LOG, existing + '\n' + line);
  } catch(e) {}
}

function runCmd(name, cmd) {
  log(`Starting: ${name}`);
  try {
    const out = execSync(cmd, { cwd: REPO, encoding: 'utf8', timeout: 60000 });
    log(`✅ ${name}`);
    return true;
  } catch(e) {
    log(`⚠️ ${name}: ${e.message.slice(-100)}`);
    return false;
  }
}

function run() {
  log('=== DASHBOARD PIPELINE STARTED ===');
  
  // Step 1: Sync IG analytics from existing tracker
  runCmd('sync_ig_analytics', 'node scripts/sync_ig_analytics.js');
  
  // Step 2: Golf news (lightweight, runs independently)
  runCmd('fetch_golf_news', 'node scripts/fetch_golf_news.js');
  
  // Step 3: Generate content ideas from hook data
  runCmd('generate_content_ideas', 'node scripts/generate_content_ideas.js');
  
  // Step 4: Analyse hooks from IG data
  runCmd('analyse_hooks', 'node scripts/analyse_hooks.js');
  
  // Step 5: Compile dashboard HTML
  runCmd('compile_dashboard', 'node scripts/compile_dashboard.js');
  
  // Step 6: Publish to GitHub
  runCmd('publish_github', 'node scripts/publish_github.js');
  
  log('=== DASHBOARD PIPELINE COMPLETE ===');
}

run();