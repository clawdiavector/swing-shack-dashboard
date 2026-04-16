/**
 * validator.js
 * Validates each pipeline output before next stage runs
 * Marks each file as PASS / STALE / FAIL
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const LOG_DIR = path.join(__dirname, '..', 'logs');
const REPORT_FILE = path.join(LOG_DIR, 'validation-report.json');

const CRITICAL_FILES = [
  'ig-analytics.json',
  'hook-bank.json',
  'content-ideas.json',
  'dashboard-summary.json',
];

const NON_CRITICAL_FILES = [
  'golf-news.json',
  'reddit-trends.json',
  'ga4-metrics.json',
  'seo-rankings.json',
  'seo-audit.json',
  'ab-tests.json',
  'used-items.json',
];

const REQUIRED_KEYS = {
  'ig-analytics.json': ['updated', 'posts'],
  'hook-bank.json': ['updated', 'proven_hooks'],
  'content-ideas.json': ['updated', 'ideas'],
  'golf-news.json': ['updated'],
  'reddit-trends.json': ['updated'],
  'ga4-metrics.json': ['updated'],
  'seo-rankings.json': ['updated'],
  'seo-audit.json': ['updated'],
  'ab-tests.json': ['updated'],
  'used-items.json': ['updated'],
};

function validateFile(filename) {
  const filepath = path.join(DATA_DIR, filename);
  
  // Check exists
  if (!fs.existsSync(filepath)) {
    return { file: filename, status: 'FAIL', reason: 'file missing' };
  }
  
  // Check not empty
  const stats = fs.statSync(filepath);
  if (stats.size === 0) {
    return { file: filename, status: 'FAIL', reason: 'file is empty' };
  }
  
  // Check JSON validity
  let data;
  try {
    data = JSON.parse(fs.readFileSync(filepath, 'utf8'));
  } catch (e) {
    return { file: filename, status: 'FAIL', reason: 'invalid JSON' };
  }
  
  // Check required keys
  const required = REQUIRED_KEYS[filename] || [];
  const missing = required.filter(k => !data.hasOwnProperty(k));
  if (missing.length > 0) {
    return { file: filename, status: 'FAIL', reason: `missing keys: ${missing.join(', ')}` };
  }
  
  // Check timestamp freshness (within 26 hours = stale threshold)
  const updated = data.updated;
  if (!updated || updated === 'never') {
    return { file: filename, status: 'STALE', reason: 'no timestamp' };
  }
  
  const ageHours = (Date.now() - new Date(updated).getTime()) / 3600000;
  if (ageHours > 26) {
    return { file: filename, status: 'STALE', reason: `${ageHours.toFixed(1)}h old` };
  }
  
  // Special check for arrays that should have items
  if (filename === 'ig-analytics.json' && (!data.posts || data.posts.length === 0)) {
    return { file: filename, status: 'STALE', reason: 'empty posts array' };
  }
  
  if (filename === 'content-ideas.json' && (!data.ideas || data.ideas.length === 0)) {
    return { file: filename, status: 'STALE', reason: 'empty ideas array' };
  }
  
  return { file: filename, status: 'PASS', reason: 'valid', age_hours: ageHours.toFixed(1) };
}

function validateDashboard() {
  const dashPath = path.join(__dirname, '..', 'dashboard.html');
  if (!fs.existsSync(dashPath)) {
    return { file: 'dashboard.html', status: 'FAIL', reason: 'file missing' };
  }
  const stats = fs.statSync(dashPath);
  if (stats.size < 1000) {
    return { file: 'dashboard.html', status: 'FAIL', reason: 'file too small' };
  }
  const content = fs.readFileSync(dashPath, 'utf8');
  if (!content.includes('Swing Shack') || !content.includes('Marketing Intelligence')) {
    return { file: 'dashboard.html', status: 'FAIL', reason: 'missing expected content' };
  }
  // Check timestamp is recent
  const match = content.match(/Last Build.*?(\d{4}\/\d{2}\/\d{2}, \d{2}:\d{2}:\d{2})/);
  if (!match) {
    return { file: 'dashboard.html', status: 'STALE', reason: 'no timestamp found' };
  }
  return { file: 'dashboard.html', status: 'PASS', reason: 'valid dashboard', last_build: match[1] };
}

function run() {
  const results = [];
  
  // Validate critical files
  for (const f of CRITICAL_FILES) {
    const result = validateFile(f);
    result.critical = true;
    result.action = result.status === 'FAIL' ? 'STOP_PIPELINE' : 'continue';
    results.push(result);
  }
  
  // Validate non-critical files
  for (const f of NON_CRITICAL_FILES) {
    const result = validateFile(f);
    result.critical = false;
    result.action = result.status === 'FAIL' ? 'MARK_STALE' : 'continue';
    results.push(result);
  }
  
  // Validate dashboard
  const dashResult = validateDashboard();
  dashResult.critical = true;
  dashResult.action = dashResult.status === 'FAIL' ? 'STOP_PIPELINE' : 'continue';
  results.push(dashResult);
  
  // Summary
  const passed = results.filter(r => r.status === 'PASS').length;
  const stale = results.filter(r => r.status === 'STALE').length;
  const failed = results.filter(r => r.status === 'FAIL').length;
  const criticalFailed = results.filter(r => r.critical && r.status === 'FAIL').length;
  
  const report = {
    timestamp: new Date().toISOString(),
    summary: { pass: passed, stale, fail: failed },
    pipeline_status: criticalFailed > 0 ? 'FAIL' : stale > 0 ? 'PARTIAL' : 'PASS',
    critical_failure: criticalFailed > 0,
    should_stop: criticalFailed > 0,
    results,
  };
  
  fs.writeFileSync(REPORT_FILE, JSON.stringify(report, null, 2));
  
  // Console output
  console.log('🔍 VALIDATION REPORT');
  console.log('='.repeat(50));
  console.log(`Pipeline Status: ${report.pipeline_status}`);
  console.log(`PASS: ${passed} | STALE: ${stale} | FAIL: ${failed}`);
  console.log('');
  for (const r of results) {
    const icon = r.status === 'PASS' ? '✅' : r.status === 'STALE' ? '⚠️' : '❌';
    const crit = r.critical ? '🔴' : '🟡';
    console.log(`${icon} ${r.file} (${r.status}) ${crit} - ${r.reason}`);
  }
  console.log('');
  console.log(criticalFailed > 0 ? '🚫 STOPPING PIPELINE - Critical failure' : stale > 0 ? '⚠️  CONTINUING - Non-critical stale data' : '✅ ALL CLEAR');
  
  return report;
}

module.exports = { run, validateFile, validateDashboard };

if (require.main === module) {
  run();
}