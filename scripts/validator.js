/**
 * validator.js
 * Validates each pipeline output before next stage runs
 * Marks each file as PASS / STALE / FAIL
 * Writes logs/validation-report.json every run
 *
 * Schema per file:
 * {
 *   file: "data/xxx.json",
 *   critical: true/false,
 *   data_status: "PASS | STALE | FAIL",  // data freshness
 *   script_status: "PASS | FAIL | N/A",    // did script succeed?
 *   fallback_used: true/false/null,
 *   age_hours: number,
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
  { file: 'website-insights.json', label: 'Website Insights', critical: false },
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
  'website-insights.json': ['updated'],
};

function validateFile(file, label, critical) {
  const filepath = path.join(DATA_DIR, file);

  // 1. File exists?
  if (!fs.existsSync(filepath)) {
    return {
      file, label, critical,
      data_status: 'FAIL', qa_warnings: [], source_mode: 'FAILED', script_status: 'FAIL', fallback_used: null,
      age_hours: null, reason: 'File missing', next_action: 'Create ' + file + ' or restore from backup'
    };
  }

  // 2. Not empty?
  const stats = fs.statSync(filepath);
  if (stats.size === 0) {
    return {
      file, label, critical,
      data_status: 'FAIL', qa_warnings: [], source_mode: 'FAILED', script_status: 'FAIL', fallback_used: null,
      age_hours: null, reason: 'File is empty', next_action: 'Populate ' + file
    };
  }

  // 3. Valid JSON?
  let data;
  try {
    data = JSON.parse(fs.readFileSync(filepath, 'utf8'));
  } catch (e) {
    return {
      file, label, critical,
      data_status: 'FAIL', qa_warnings: [], source_mode: 'FAILED', script_status: 'FAIL', fallback_used: null,
      age_hours: null, reason: 'Invalid JSON', next_action: 'Fix JSON syntax in ' + file
    };
  }

  // Dashboard summary uses 'timestamp' not 'updated'
  if (file === 'dashboard-summary.json') {
    const ts = data.timestamp || data.updated;
    if (!ts || ts === 'never') {
      return { file, label, critical, data_status: 'STALE', qa_warnings: [], script_status: 'N/A', fallback_used: false, age_hours: null, reason: 'No timestamp found', next_action: 'Run compile_dashboard.js' };
    }
    const ageHours = (Date.now() - new Date(ts).getTime()) / 3600000;
    if (ageHours > 26) {
      return { file, label, critical, data_status: 'STALE', qa_warnings: [], script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: ageHours.toFixed(1) + 'h old', next_action: 'Recompile dashboard summary' };
    }
    return { file, label, critical, data_status: 'PASS', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'Fresh - ' + ageHours.toFixed(1) + 'h old', next_action: 'No action needed', last_build: ts };
  }

  // 4. Required keys present?
  const required = REQUIRED_KEYS[file] || [];
  const missing = required.filter(k => !data.hasOwnProperty(k));
  if (missing.length > 0) {
    return {
      file, label, critical,
      data_status: 'FAIL', qa_warnings: [], source_mode: 'FAILED', script_status: 'FAIL', fallback_used: null,
      age_hours: null, reason: 'Missing keys: ' + missing.join(', '), next_action: 'Add missing keys to ' + file
    };
  }

  // 5. Timestamp check
  const updated = data.updated;
  if (!updated || updated === 'never') {
    const scriptFailed = data.error || data._stale;
    return {
      file, label, critical,
      data_status: 'STALE', qa_warnings: [],
      script_status: scriptFailed ? 'FAIL' : 'N/A',
      fallback_used: !!(data._fallback_used || data._stale),
      age_hours: null,
      reason: 'Never updated or script failed previously',
      next_action: data._no_previous_data ? 'No fallback data - fix auth/script for ' + file : 'Run script to refresh ' + file
    };
  }

  // 6. Age check
  const ageHours = (Date.now() - new Date(updated).getTime()) / 3600000;

  // If _stale flag is set, data_status is STALE regardless of timestamp
  if (data._stale === true) {
    if (data._fallback_used || data._no_previous_data) {
      return {
        file, label, critical,
        data_status: 'FAIL', qa_warnings: [], source_mode: 'FAILED',
        script_status: 'FAIL',
        fallback_used: false,
        age_hours: parseFloat(ageHours.toFixed(1)),
        reason: 'Script failed - no valid fallback data',
        next_action: data._stale_reason ? 'Auth/script failed: ' + data._stale_reason.slice(-60) : 'Fix ' + file + ' script'
      };
    } else {
      return {
        file, label, critical,
        data_status: 'STALE', qa_warnings: [],
        script_status: 'FAIL',
        fallback_used: true,
        age_hours: parseFloat(ageHours.toFixed(1)),
        reason: 'Script failed - using stale fallback (' + ageHours.toFixed(1) + 'h old)',
        next_action: data._stale_reason ? 'Auth failed: ' + data._stale_reason.slice(-60) : 'Fix auth for ' + file
      };
    }
  }

  if (ageHours > 26) {
    return {
      file, label, critical,
      data_status: 'STALE', qa_warnings: [],
      script_status: 'PASS',
      fallback_used: false,
      age_hours: parseFloat(ageHours.toFixed(1)),
      reason: ageHours.toFixed(1) + 'h old (stale threshold 26h)',
      next_action: 'Refresh ' + file + ' - data is stale'
    };
  }

  // 7. Not unexpectedly empty
  if (file === 'ig-analytics.json' && (!data.posts || data.posts.length === 0)) {
    return { file, label, critical, data_status: 'STALE', qa_warnings: [], script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'No posts in array', next_action: 'Check sync_ig_analytics script', qa_warnings: [] };
  }
  if (file === 'content-ideas.json' && (!data.ideas || data.ideas.length === 0)) {
    return { file, label, critical, data_status: 'STALE', qa_warnings: [], script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'No ideas generated', next_action: 'Check generate_content_ideas script', qa_warnings: [] };
  }
  if (file === 'hook-bank.json' && (!data.proven_hooks && !data.hooks && !data.hooks_by_goal)) {
    return { file, label, critical, data_status: 'STALE', qa_warnings: [], script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'No hook data found', next_action: 'Check analyse_hooks script', qa_warnings: [] };
  }
  if (file === 'youtube-trends.json' && (!data.videos_found || data.videos_found === 0)) {
    return { file, label, critical, data_status: 'STALE', qa_warnings: [], script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'No YouTube videos found', next_action: 'Check fetch_youtube_trends script', qa_warnings: [] };
  }
  if (file === 'youtube-ideas.json' && (!data.ideas || data.ideas.length === 0)) {
    return { file, label, critical, data_status: 'STALE', qa_warnings: [], script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'No YouTube ideas generated', next_action: 'Check generate_youtube_ideas script', qa_warnings: [] };
  }
  
  // 8. GA4-specific sanity checks (QA layer - doesn't change PASS/STALE status)
  const qa_warnings = [];
  if (file === 'ga4-metrics.json') {
    if (data.total_sessions === 0 && data.error) {
      // True failure already handled above via _stale check
    } else if (data.total_sessions === 0) {
      qa_warnings.push('sessions=0 but script succeeded - possible auth/scope issue');
    }
    if ((data.pages || []).length === 0 && data.total_sessions > 0) {
      qa_warnings.push('sessions reported but no pages - check API dimensions');
    }
    if (!data.insights || !data.insights.recommendations || data.insights.recommendations.length === 0) {
      qa_warnings.push('no insights/recommendations generated - GA4 data may be insufficient');
    }
    if (data.insights && data.insights.recommendations && data.insights.recommendations.length === 0 && data.total_sessions > 100) {
      qa_warnings.push('high sessions but no recommendations - low engagement pages may be missing');
    }
  }

  // 9. Source mode detection — how fresh is this data really?
  let source_mode = 'LIVE';
  if (file === 'youtube-trends.json') {
    if (data._synthetic === true || data.data_source === 'synthetic_sa_market') {
      source_mode = 'SYNTHETIC';
    } else if (data.data_source && data.data_source !== 'rss_feeds' && data.data_source !== 'newsapi') {
      source_mode = 'SYNTHETIC'; // Known proxy source = not truly live
    }
  }
  
  return {
    file, label, critical,
    data_status: 'PASS',
    script_status: 'PASS',
    fallback_used: false,
    source_mode,
    age_hours: parseFloat(ageHours.toFixed(1)),
    reason: 'Fresh - ' + ageHours.toFixed(1) + 'h old' + (source_mode === 'SYNTHETIC' ? ' (synthetic source)' : ''),
    next_action: 'No action needed',
    qa_warnings,
  };
}

function validateDashboard() {
  const dashPath = path.join(__dirname, '..', 'dashboard.html');

  if (!fs.existsSync(dashPath)) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, data_status: 'FAIL', qa_warnings: [], source_mode: 'FAILED', script_status: 'FAIL', fallback_used: false, age_hours: null, reason: 'File missing', next_action: 'Run compile_dashboard.js' };
  }

  const stats = fs.statSync(dashPath);
  if (stats.size < 5000) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, data_status: 'FAIL', qa_warnings: [], source_mode: 'FAILED', script_status: 'FAIL', fallback_used: false, age_hours: null, reason: 'File too small', next_action: 'Recompile dashboard' };
  }

  const content = fs.readFileSync(dashPath, 'utf8');
  if (!content.includes('Swing Shack') || !content.includes('Marketing Intelligence')) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, data_status: 'FAIL', qa_warnings: [], source_mode: 'FAILED', script_status: 'FAIL', fallback_used: false, age_hours: null, reason: 'Missing expected content', next_action: 'Recompile dashboard' };
  }

  const matches = content.match(/Last Build[\s\S]*?(\d{4}\/\d{2}\/\d{2},?\s*\d{2}:\d{2}:\d{2})/);
  if (!matches) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, data_status: 'STALE', qa_warnings: [], script_status: 'N/A', fallback_used: false, age_hours: null, reason: 'No timestamp found', next_action: 'Recompile dashboard' };
  }

  const lastBuild = matches[1];
  const buildDate = new Date(lastBuild.replace(',', ''));
  if (isNaN(buildDate.getTime())) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, data_status: 'STALE', qa_warnings: [], script_status: 'N/A', fallback_used: false, age_hours: null, reason: 'Unparseable timestamp', next_action: 'Recompile dashboard' };
  }

  const ageHours = (Date.now() - buildDate.getTime()) / 3600000;
  if (ageHours > 26) {
    return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, data_status: 'STALE', qa_warnings: [], script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'Dashboard ' + ageHours.toFixed(1) + 'h old', next_action: 'Recompile and republish' };
  }

  return { file: 'dashboard.html', label: 'Dashboard HTML', critical: true, data_status: 'PASS', script_status: 'PASS', fallback_used: false, age_hours: parseFloat(ageHours.toFixed(1)), reason: 'Last build ' + lastBuild, next_action: 'No action needed', last_build: lastBuild };
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

  const failures = checks.filter(c => c.data_status === 'FAIL');
  const stales = checks.filter(c => c.data_status === 'STALE');
  const passes = checks.filter(c => c.data_status === 'PASS');
  const scriptFailures = checks.filter(c => c.script_status === 'FAIL');
  const fallbacksUsed = checks.filter(c => c.fallback_used === true);
  const syntheticFiles = checks.filter(c => c.source_mode === 'SYNTHETIC').length;

  const criticalFailures = failures.filter(c => c.critical);
  const nonCriticalFails = failures.filter(c => !c.critical);
  
  // FAIL only if critical files failed; PARTIAL if any non-critical failures, stale, synthetic, or script failures
  const overall = criticalFailures.length > 0 ? 'FAIL'
    : (nonCriticalFails.length > 0 || stales.length > 0 || syntheticFiles > 0 || scriptFailures.length > 0) ? 'PARTIAL'
    : 'PASS';

  const liveFresh = checks.filter(c => c.data_status === 'PASS' && c.source_mode === 'LIVE').length;
  const staleFiles = checks.filter(c => c.data_status === 'STALE').length;
  const failedFiles = checks.filter(c => c.data_status === 'FAIL').length;
  
  const report = {
    timestamp: new Date().toISOString(),
    overall_status: overall,
    summary: {
      pass: passes.length,
      stale: stales.length,
      fail: failures.length,
      script_failures: scriptFailures.length,
      fallbacks_used: fallbacksUsed.length,
      live_fresh: liveFresh,
      synthetic: syntheticFiles,
      stale: staleFiles,
      failed: failedFiles,
      total: checks.length,
    },
    critical_failure: criticalFailures.length > 0,
    should_stop: criticalFailures.length > 0,
    checks,
  };

  if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
  fs.writeFileSync(REPORT_FILE, JSON.stringify(report, null, 2));

  // Console output
  console.log('VALIDATION REPORT');
  console.log('='.repeat(50));
  console.log('Pipeline Status: ' + overall);
  
  // Source integrity breakdown
  console.log('');
  
  console.log('SOURCE INTEGRITY:');
  for (const c of checks) {
    const mode = c.source_mode || 'LIVE';
    const sym = mode === 'LIVE' ? 'LIVE' : mode === "SYNTHETIC" ? "SYNTHETIC" : mode === 'STALE_FALLBACK' ? 'STALE_FALLBACK' : mode === 'FAILED' ? 'FAIL' : mode === 'STALE' ? 'STALE' : 'LIVE';
    console.log('  ' + c.label + ': ' + sym);
  }
  console.log('');
  console.log('SOURCE COUNTS:');
  console.log('  Live fresh: ' + liveFresh + '/' + checks.length);
  if (syntheticFiles > 0) console.log('  Synthetic: ' + syntheticFiles + '/' + checks.length);
  if (staleFiles > 0) console.log('  Stale: ' + staleFiles + '/' + checks.length);
  if (failedFiles > 0) console.log('  Failed: ' + failedFiles + '/' + checks.length);
  if (scriptFailures.length > 0) console.log('  Failed scripts: ' + scriptFailures.length);
  console.log('');
  console.log('CRITICAL FILES:');
  for (const c of checks.filter(c => c.critical)) {
    const icon = c.data_status === 'PASS' ? 'PASS' : c.data_status === 'STALE' ? 'STALE' : 'FAIL';
    const script = c.script_status === 'FAIL' ? ' [SCRIPT FAILED]' : '';
    console.log('  ' + icon + ': ' + c.label + script + ' - ' + c.reason);
    if (c.next_action !== 'No action needed') {
      console.log('     -> ' + c.next_action);
    }
  }
  console.log('');
  console.log('NON-CRITICAL FILES:');
  for (const c of checks.filter(c => !c.critical)) {
    const icon = c.data_status === 'PASS' ? 'PASS' : c.data_status === 'STALE' ? 'STALE' : 'FAIL';
    const fallback = c.fallback_used ? ' [fallback]' : '';
    const script = c.script_status === 'FAIL' ? ' [SCRIPT FAILED]' : '';
    const mode = c.source_mode === "SYNTHETIC" ? " [SYNTHETIC]"' : c.source_mode === 'STALE_FALLBACK' ? ' [STALE_FALLBACK]' : '';
    console.log('  ' + icon + ': ' + c.label + fallback + script + mode + ' - ' + c.reason);
  }
  console.log('');
  
  // Script failures detail
  if (scriptFailures.length > 0) {
    console.log('SCRIPT FAILURES:');
    for (const c of checks.filter(c => c.script_status === 'FAIL')) {
      const isCritical = c.critical ? ' (critical)' : ' (non-critical)' ;
      console.log('  - ' + c.file + isCritical + ': ' + (c.next_action || c.reason));
    }
    console.log('');
  }

  const qa_warnings = [];
  const allChecks = checks.filter(c => c.qa_warnings && c.qa_warnings.length > 0);
  if (allChecks.length > 0) {
    console.log('QA WARNINGS:');
    for (const c of allChecks) {
      for (const w of c.qa_warnings) {
        console.log('  ⚠️  ' + c.label + ': ' + w);
      }
    }
    console.log('');
  }
  
  if (overall === 'FAIL') {
    console.log('STOPPING PIPELINE - Critical failure');
  } else if (overall === 'PARTIAL') {
    console.log('CONTINUING - Some sources stale');
  } else {
    console.log('ALL CLEAR - All sources fresh and valid');
  }

  return report;
}

module.exports = { run, validateFile, validateDashboard };

if (require.main === module) run();