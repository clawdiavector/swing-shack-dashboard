/**
 * validator.js
 * Validates each pipeline output before next stage runs
 * Marks each file as PASS / STALE / FAIL
 * Writes logs/validation-report.json every run
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const LOG_DIR = path.join(__dirname, '..', 'logs');
const REPORT_FILE = path.join(LOG_DIR, 'validation-report.json');

const CRITICAL_FILES = [
  { file: 'ig-analytics.json', label: 'IG Analytics' },
  { file: 'hook-bank.json', label: 'Hook Bank' },
  { file: 'content-ideas.json', label: 'Content Ideas' },
  { file: 'dashboard-summary.json', label: 'Dashboard Summary' },
];

const NON_CRITICAL_FILES = [
  { file: 'golf-news.json', label: 'Golf News' },
  { file: 'reddit-trends.json', label: 'Reddit Trends' },
  { file: 'ga4-metrics.json', label: 'GA4 Fetch' },
  { file: 'seo-rankings.json', label: 'SEO Rankings' },
  { file: 'seo-audit.json', label: 'SEO Audit' },
  { file: 'geo-audit.json', label: 'GEO Audit' },
  { file: 'ab-tests.json', label: 'A/B Test Input' },
  { file: 'used-items.json', label: 'Used Items' },
];

const REQUIRED_KEYS = {
  'ig-analytics.json': ['updated', 'posts'],
  'hook-bank.json': ['updated'],
  'content-ideas.json': ['updated', 'ideas'],
  'golf-news.json': ['updated'],
  'reddit-trends.json': ['updated'],
  'ga4-metrics.json': ['updated'],
  'seo-rankings.json': ['updated'],
  'seo-audit.json': ['updated'],
  'geo-audit.json': ['updated'],
  'ab-tests.json': ['updated'],
  'used-items.json': ['updated'],
};

function validateFile(name, label) {
  const { file } = name;
  const filepath = path.join(DATA_DIR, file);
  
  // 1. File exists?
  if (!fs.existsSync(filepath)) {
    return { file, label, status: 'FAIL', reason: 'File missing' };
  }
  
  // 2. Not empty?
  const stats = fs.statSync(filepath);
  if (stats.size === 0) {
    return { file, label, status: 'FAIL', reason: 'File is empty' };
  }
  
  // 3. Valid JSON?
  let data;
  try {
    data = JSON.parse(fs.readFileSync(filepath, 'utf8'));
  } catch (e) {
    return { file, label, status: 'FAIL', reason: 'Invalid JSON' };
  }
  
  // 4. Required keys present?
  const required = REQUIRED_KEYS[file] || [];
  const missing = required.filter(k => !data.hasOwnProperty(k));
  if (missing.length > 0) {
    return { file, label, status: 'FAIL', reason: `Missing keys: ${missing.join(', ')}` };
  }
  
  // 5. Timestamp fresh?
  const updated = data.updated;
  if (!updated || updated === 'never') {
    return { file, label, status: 'STALE', reason: 'Never updated - previous run used' };
  }
  
  const ageHours = (Date.now() - new Date(updated).getTime()) / 3600000;
  if (ageHours > 26) {
    return { file, label, status: 'STALE', reason: `${ageHours.toFixed(1)}h old (stale threshold 26h)` };
  }
  
  // 6. Not unexpectedly empty
  if (file === 'ig-analytics.json' && (!data.posts || data.posts.length === 0)) {
    return { file, label, status: 'STALE', reason: 'No posts in array' };
  }
  if (file === 'content-ideas.json' && (!data.ideas || data.ideas.length === 0)) {
    return { file, label, status: 'STALE', reason: 'No ideas generated' };
  }
  if (file === 'hook-bank.json' && (!data.proven_hooks && !data.hooks)) {
    return { file, label, status: 'STALE', reason: 'No hook data found' };
  }
  
  return { file, label, status: 'PASS', reason: `Valid - ${ageHours.toFixed(1)}h old`, age_hours: parseFloat(ageHours.toFixed(1)) };
}

function validateDashboard() {
  const dashPath = path.join(__dirname, '..', 'dashboard.html');
  
  if (!fs.existsSync(dashPath)) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', status: 'FAIL', reason: 'File missing' };
  }
  
  const stats = fs.statSync(dashPath);
  if (stats.size < 5000) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', status: 'FAIL', reason: 'File too small - likely broken' };
  }
  
  const content = fs.readFileSync(dashPath, 'utf8');
  if (!content.includes('Swing Shack') || !content.includes('Marketing Intelligence')) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', status: 'FAIL', reason: 'Missing expected content' };
  }
  
  // Find timestamp in content - look for SAST format
  const matches = content.match(/Last Build[\s\S]*?(\d{4}\/\d{2}\/\d{2},?\s*\d{2}:\d{2}:\d{2})/);
  if (!matches) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', status: 'STALE', reason: 'No timestamp found in dashboard' };
  }
  
  const lastBuild = matches[1];
  // Try to parse it
  const buildDate = new Date(lastBuild.replace(',', ''));
  if (isNaN(buildDate.getTime())) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', status: 'STALE', reason: 'Unparseable timestamp in dashboard' };
  }
  
  const ageHours = (Date.now() - buildDate.getTime()) / 3600000;
  if (ageHours > 26) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', status: 'STALE', reason: `Dashboard ${ageHours.toFixed(1)}h old`, age_hours: parseFloat(ageHours.toFixed(1)) };
  }
  
  return { file: 'dashboard.html', label: 'Dashboard HTML', status: 'PASS', reason: `Last build ${lastBuild}`, age_hours: parseFloat(ageHours.toFixed(1)), last_build: lastBuild };
}

function run() {
  const checks = [];
  
  // Validate critical files
  for (const item of CRITICAL_FILES) {
    checks.push(validateFile(item.file, item.label));
  }
  
  // Validate non-critical files
  for (const item of NON_CRITICAL_FILES) {
    checks.push(validateFile(item.file, item.label));
  }
  
  // Validate dashboard
  checks.push(validateDashboard());
  
  // Compute overall status
  const failures = checks.filter(c => c.status === 'FAIL');
  const stales = checks.filter(c => c.status === 'STALE');
  const passes = checks.filter(c => c.status === 'PASS');
  
  const overall = failures.length > 0 ? 'FAIL' : stales.length > 0 ? 'PARTIAL' : 'PASS';
  
  const report = {
    timestamp: new Date().toISOString(),
    overall_status: overall,
    summary: {
      pass: passes.length,
      stale: stales.length,
      fail: failures.length,
    },
    critical_failure: failures.length > 0,
    should_stop: failures.filter(c => CRITICAL_FILES.find(f => f.file === c.file)).length > 0,
    checks,
  };
  
  // Write report
  if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
  fs.writeFileSync(REPORT_FILE, JSON.stringify(report, null, 2));
  
  // Console output
  console.log('🔍 VALIDATION REPORT');
  console.log('═'.repeat(50));
  console.log(`Pipeline Status: ${overall}`);
  console.log(`PASS: ${passes.length} | STALE: ${stales.length} | FAIL: ${failures.length}`);
  console.log('');
  console.log('CRITICAL FILES:');
  for (const c of checks.filter(c => CRITICAL_FILES.find(f => f.file === c.file))) {
    const icon = c.status === 'PASS' ? '✅' : c.status === 'STALE' ? '⚠️' : '❌';
    console.log(`  ${icon} ${c.label}: ${c.status} — ${c.reason}`);
  }
  console.log('');
  console.log('NON-CRITICAL FILES:');
  for (const c of checks.filter(c => !CRITICAL_FILES.find(f => f.file === c.file))) {
    const icon = c.status === 'PASS' ? '✅' : c.status === 'STALE' ? '⚠️' : '❌';
    console.log(`  ${icon} ${c.label}: ${c.status} — ${c.reason}`);
  }
  console.log('');
  
  if (overall === 'FAIL') {
    console.log('🚫 STOPPING PIPELINE - Critical failure');
  } else if (overall === 'PARTIAL') {
    console.log('⚠️  CONTINUING - Some sources stale but critical files OK');
  } else {
    console.log('✅ ALL CLEAR - All sources fresh and valid');
  }
  
  return report;
}

module.exports = { run, validateFile, validateDashboard };

if (require.main === module) run();