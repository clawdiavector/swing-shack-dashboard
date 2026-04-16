/**
 * validator.js
 * Validates each pipeline output before next stage runs
 * Marks each file as PASS / STALE / FAIL
 * Writes logs/validation-report.json every run
 * 
 * Schema per file:
 * {
 *   file: "data/xxx.json",
 *   label: "Human Label",
 *   critical: true/false,
 *   data_status: "PASS | STALE | FAIL",        // data freshness
 *   script_status: "PASS | FAIL | N/A",   // did script succeed?
 *   fallback_used: true/false/null,
 *   age_hours: number,
 *   reason: "description",
 *   next_action: "what to do"
 * }
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const LOG_DIR = path.join(__dirname, '..', 'logs');
const REPORT_FILE = path.join(LOG_DIR, 'validation-report.json');

const CRITICAL_FILES = [
  { file: 'ig-analytics.json', label: 'IG Analytics', critical: true },
  { file: 'hook-bank.json', label: 'Hook Bank', critical: true },
  { file: 'content-ideas.json', label: 'Content Ideas', critical: true },
  { file: 'dashboard-summary.json', label: 'Dashboard Summary', critical: true },
];

const NON_CRITICAL_FILES = [
  { file: 'golf-news.json', label: 'Golf News', critical: false },
  { file: 'reddit-trends.json', label: 'Reddit Trends', critical: false },
  { file: 'ga4-metrics.json', label: 'GA4 Metrics', critical: false },
  { file: 'seo-rankings.json', label: 'SEO Rankings', critical: false },
  { file: 'seo-audit.json', label: 'SEO Audit', critical: false },
  { file: 'geo-audit.json', label: 'GEO Audit', critical: false },
  { file: 'ab-tests.json', label: 'A/B Test Input', critical: false },
  { file: 'used-items.json', label: 'Used Items', critical: false },
  { file: 'youtube-trends.json', label: 'YouTube Trends', critical: false },
  { file: 'youtube-ideas.json', label: 'YouTube Ideas', critical: false },
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
  'youtube-trends.json': ['updated'],
  'youtube-ideas.json': ['updated'],
};

function validateFile(file, label, critical) {
  const filepath = path.join(DATA_DIR, file);
  
  // 1. File exists?
  if (!fs.existsSync(filepath)) {
    return { 
      file, label, critical, 
      data_status: .FAIL., script_status: 'FAIL', fallback_used: null,
      age_hours: null, reason: 'File missing', next_action: `Create ${file} or restore from backup`
    };
  }
  
  // 2. Not empty?
  const stats = fs.statSync(filepath);
  if (stats.size === 0) {
    return { 
      file, label, critical,
      data_status: .FAIL., script_status: 'FAIL', fallback_used: null,
      age_hours: null, reason: 'File is empty', next_action: `Populate ${file}`
    };
  }
  
  // 3. Valid JSON?
  let data;
  try {
    data = JSON.parse(fs.readFileSync(filepath, 'utf8'));
  } catch (e) {
    return { 
      file, label, critical,
      data_status: .FAIL., script_status: 'FAIL', fallback_used: null,
      age_hours: null, reason: 'Invalid JSON', next_action: `Fix JSON syntax in ${file}`
    };
  }
  
  // Dashboard summary uses 'timestamp' not 'updated'
  if (file === 'dashboard-summary.json') {
    const ts = data.timestamp || data.updated;
    if (!ts || ts === 'never') {
      return { file, label, critical, status: 'STALE', script_status: 'N/A', fallback_used: false, age_hours: null, reason: 'No timestamp found', next_action: 'Run compile_dashboard.js' };
    }
    const ageHours = (Date.now() - new Date(ts).getTime()) / 3600000;
    if (ageHours > 26) {
      return { file, label, critical, status: 'STALE', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: `${ageHours.toFixed(1)}h old`, next_action: 'Recompile dashboard summary' };
    }
    return { file, label, critical, status: 'PASS', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: `Fresh - ${ageHours.toFixed(1)}h old`, next_action: 'No action needed', last_build: ts };
  }
  
  // 5. Timestamp check
  const updated = data.updated;
  if (!updated || updated === 'never') {
    // Script never ran or failed
    const scriptFailed = data.error || data._stale;
    return { 
      file, label, critical,
      data_status: .STALE., 
      script_status: scriptFailed ? 'FAIL' : 'N/A',
      fallback_used: !!(data._fallback_used || data._stale),
      age_hours: null, 
      reason: 'Never updated or script failed previously',
      next_action: data._no_previous_data ? `No fallback data - fix auth/script for ${file}` : `Run script to refresh ${file}`
    };
  }
  
  // 6. Age check
  const ageHours = (Date.now() - new Date(updated).getTime()) / 3600000;
  
  // If _stale flag is set, data_status is STALE regardless of timestamp
  // (script failed but kept old/fallback data with fresh timestamp)
  if (data._stale === true) {
    if (data._fallback_used || data._no_previous_data) {
      // Script failed AND no valid fallback = FAIL
      return { 
        file, label, critical,
        data_status: .FAIL., 
        script_status: 'FAIL',
        fallback_used: false,
        age_hours: parseFloat(ageHours.toFixed(1)), 
        reason: 'Script failed - no valid fallback data',
        next_action: data._stale_reason ? `Auth/script failed: ${data._stale_reason}` : `Fix ${file} script`
      };
    } else {
      // Script set _stale flag but had fallback
      return { 
        file, label, critical,
        data_status: .STALE., 
        script_status: 'FAIL',
        fallback_used: true,
        age_hours: parseFloat(ageHours.toFixed(1)), 
        reason: `Script failed - using stale fallback (${ageHours.toFixed(1)}h old)`,
        next_action: data._stale_reason ? `Auth failed: ${data._stale_reason}` : `Fix auth for ${file}`
      };
    }
  }
  
  if (ageHours > 26) {
    return { 
      file, label, critical,
      data_status: .STALE., 
      script_status: data._stale ? 'FAIL' : 'PASS',
      fallback_used: !!(data._fallback_used || data._stale),
      age_hours: parseFloat(ageHours.toFixed(1)), 
      reason: `${ageHours.toFixed(1)}h old (stale threshold 26h)`,
      next_action: data._stale_reason ? `Script previously failed: ${data._stale_reason}` : `Refresh ${file} - data is stale`
    };
  }
  
  // 7. Not unexpectedly empty
  if (file === 'ig-analytics.json' && (!data.posts || data.posts.length === 0)) {
    return { file, label, critical, status: 'STALE', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'No posts in array', next_action: 'Check sync_ig_analytics script' };
  }
  if (file === 'content-ideas.json' && (!data.ideas || data.ideas.length === 0)) {
    return { file, label, critical, status: 'STALE', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'No ideas generated', next_action: 'Check generate_content_ideas script' };
  }
  if (file === 'hook-bank.json' && (!data.proven_hooks && !data.hooks && !data.hooks_by_goal)) {
    return { file, label, critical, status: 'STALE', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'No hook data found', next_action: 'Check analyse_hooks script' };
  }
  
  return { 
    file, label, critical,
    data_status: .PASS., 
    script_status: 'PASS',
    fallback_used: false,
    age_hours: parseFloat(ageHours.toFixed(1)), 
    reason: `Fresh - ${ageHours.toFixed(1)}h old`,
    next_action: 'No action needed'
  };
}

function validateDashboard() {
  const dashPath = path.join(__dirname, '..', 'dashboard.html');
  
  if (!fs.existsSync(dashPath)) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, status: 'FAIL', script_status: 'FAIL', fallback_used: false, age_hours: null, reason: 'File missing', next_action: 'Run compile_dashboard.js' };
  }
  
  const stats = fs.statSync(dashPath);
  if (stats.size < 5000) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, status: 'FAIL', script_status: 'FAIL', fallback_used: false, age_hours: null, reason: 'File too small', next_action: 'Recompile dashboard' };
  }
  
  const content = fs.readFileSync(dashPath, 'utf8');
  if (!content.includes('Swing Shack') || !content.includes('Marketing Intelligence')) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, status: 'FAIL', script_status: 'FAIL', fallback_used: false, age_hours: null, reason: 'Missing expected content', next_action: 'Recompile dashboard' };
  }
  
  const matches = content.match(/Last Build[\s\S]*?(\d{4}\/\d{2}\/\d{2},?\s*\d{2}:\d{2}:\d{2})/);
  if (!matches) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, status: 'STALE', script_status: 'N/A', fallback_used: false, age_hours: null, reason: 'No timestamp found', next_action: 'Recompile dashboard' };
  }
  
  const lastBuild = matches[1];
  const buildDate = new Date(lastBuild.replace(',', ''));
  if (isNaN(buildDate.getTime())) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, status: 'STALE', script_status: 'N/A', fallback_used: false, age_hours: null, reason: 'Unparseable timestamp', next_action: 'Recompile dashboard' };
  }
  
  const ageHours = (Date.now() - buildDate.getTime()) / 3600000;
  if (ageHours > 26) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, status: 'STALE', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: `Dashboard ${ageHours.toFixed(1)}h old`, next_action: 'Recompile and republish' };
  }
  
  return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, status: 'PASS', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: `Last build ${lastBuild}`, next_action: 'No action needed', last_build: lastBuild };
}

function run() {
  const checks = [];
  
  for (const item of CRITICAL_FILES) {
    checks.push(validateFile(item.file, item.label, item.critical));
  }
  
  for (const item of NON_CRITICAL_FILES) {
    checks.push(validateFile(item.file, item.label, item.critical));
  }
  
  checks.push(validateDashboard());
  
  // Compute overall status
  const failures = checks.filter(c => c.data_status === 'FAIL');
  const stales = checks.filter(c => c.data_status === 'STALE');
  const passes = checks.filter(c => c.data_status === 'PASS');
  const scriptFailures = checks.filter(c => c.script_status === 'FAIL');
  const fallbacksUsed = checks.filter(c => c.fallback_used === true);
  
  const criticalFailures = failures.filter(c => c.critical);
  const overall = criticalFailures.length > 0 ? 'FAIL' : failures.length > 0 ? 'PARTIAL' : stales.length > 0 ? 'PARTIAL' : 'PASS';
  
  const report = {
    timestamp: new Date().toISOString(),
    overall_status: overall,
    summary: {
      pass: passes.length,
      stale: stales.length,
      fail: failures.length,
      script_failures: scriptFailures.length,
      fallbacks_used: fallbacksUsed.length,
    },
    critical_failure: failures.filter(c => c.critical).length > 0,
    should_stop: failures.filter(c => c.critical).length > 0,
    checks,
  };
  
  if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
  fs.writeFileSync(REPORT_FILE, JSON.stringify(report, null, 2));
  
  // Console output
  console.log('🔍 VALIDATION REPORT');
  console.log('═'.repeat(50));
  console.log(`Pipeline Status: ${overall}`);
  console.log(`PASS: ${passes.length} | STALE: ${stales.length} | FAIL: ${failures.length}`);
  console.log(`Script Failures: ${scriptFailures.length} | Fallbacks Used: ${fallbacksUsed.length}`);
  console.log('');
  console.log('CRITICAL FILES:');
  for (const c of checks.filter(c => c.critical)) {
    const icon = c.data_status === 'PASS' ? '✅' : c.data_status === 'STALE' ? '⚠️' : '❌';
    const script = c.script_status === 'FAIL' ? ' [SCRIPT FAILED]' : '';
    console.log(`  ${icon} ${c.label}: ${c.data_status}${script} — ${c.reason}`);
    if (c.next_action !== 'No action needed') {
      console.log(`     → ${c.next_action}`);
    }
  }
  console.log('');
  console.log('NON-CRITICAL FILES:');
  for (const c of checks.filter(c => !c.critical)) {
    const icon = c.data_status === 'PASS' ? '✅' : c.data_status === 'STALE' ? '⚠️' : '❌';
    const fallback = c.fallback_used ? ' [fallback]' : '';
    const script = c.script_status === 'FAIL' ? ' [SCRIPT FAILED]' : '';
    console.log(`  ${icon} ${c.label}: ${c.data_status}${fallback}${script} — ${c.reason}`);
  }
  console.log('');
  
  if (overall === 'FAIL') {
    console.log('🚫 STOPPING PIPELINE - Critical failure');
  } else if (overall === 'PARTIAL') {
    console.log('⚠️  CONTINUING - Some sources stale');
  } else {
    console.log('✅ ALL CLEAR - All sources fresh and valid');
  }
  
  return report;
}

module.exports = { run, validateFile, validateDashboard };

if (require.main === module) run();