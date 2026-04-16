#!/usr/bin/env node
/**
 * publish_github.js
 * Commits and pushes changed dashboard files to GitHub
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_DIR = __dirname; // this is scripts/, parent is repo root
const LOG_FILE = path.join(REPO_DIR, '..', 'logs', 'daily-run.log');

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  const existing = fs.existsSync(LOG_FILE) ? fs.readFileSync(LOG_FILE, 'utf8').split('\n').slice(-100).join('\n') : '';
  fs.writeFileSync(LOG_FILE, existing + '\n' + line);
}

function run() {
  try {
    // Check if there are changes
    const status = execSync('git status --porcelain', { cwd: path.join(REPO_DIR, '..'), encoding: 'utf8' });
    
    if (!status.trim()) {
      log('publish_github: No changes to commit');
      return;
    }
    
    const changed = status.trim().split('\n').map(l => l.trim().substring(2)).join(', ');
    log(`publish_github: Detected changes: ${changed}`);
    
    // Commit
    const timestamp = new Date().toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg' });
    execSync(`git add -A`, { cwd: path.join(REPO_DIR, '..') });
    execSync(`git commit -m "daily dashboard update ${timestamp}"`, { cwd: path.join(REPO_DIR, '..') });
    
    // Push
    execSync(`git push origin main`, { cwd: path.join(REPO_DIR, '..'), timeout: 30000 });
    
    log(`publish_github: ✅ Published successfully`);
  } catch (e) {
    const err = e.message.includes('nothing to commit') ? 'nothing to commit' : e.message.slice(-200);
    log(`publish_github: ⚠️ ${err}`);
  }
}

run();