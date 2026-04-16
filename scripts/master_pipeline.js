#!/usr/bin/env node
/**
 * master_pipeline.js
 * Orchestrator - runs all 6 stages in order, validates, stops on critical failure
 * Produces honest daily run summary with PASS/PARTIAL/FAIL per stage
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const LOG_DIR = path.join(__dirname, '..', 'logs');
const LOG_FILE = path.join(LOG_DIR, 'daily-run.log');
const SUMMARY_FILE = path.join(DATA_DIR, 'dashboard-summary.json');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';

const STAGES = [
  {
    name: 'Research',
    critical: false,
    requiredOutputs: ['ig-analytics.json', 'golf-news.json', 'reddit-trends.json'],
    optionalOutputs: ['ga4-metrics.json', 'seo-rankings.json'],
    steps: [
      { name: 'sync_ig_analytics', script: `node ${BASE}/scripts/sync_ig_analytics.js`, critical: true },
      { name: 'fetch_golf_news', script: `node ${BASE}/scripts/fetch_golf_news.js`, critical: false },
      { name: 'fetch_reddit_trends', script: `node ${BASE}/scripts/fetch_reddit_trends.js`, critical: false },
      { name: 'fetch_seo_rankings', script: `node ${BASE}/scripts/fetch_seo_rankings.js`, critical: false },
      { name: 'fetch_ga4', script: `node ${BASE}/scripts/fetch_ga4.js`, critical: false },
    ]
  },
  {
    name: 'Analysis',
    critical: true,
    requiredOutputs: ['hook-bank.json'],
    optionalOutputs: [],
    steps: [
      { name: 'analyse_hooks', script: `node ${BASE}/scripts/analyse_hooks.js`, critical: true },
    ]
  },
  {
    name: 'Ideas',
    critical: true,
    requiredOutputs: ['content-ideas.json'],
    optionalOutputs: ['used-items.json'],
    steps: [
      { name: 'generate_content_ideas', script: `node ${BASE}/scripts/generate_content_ideas.js`, critical: true },
      { name: 'update_used_items', script: `node ${BASE}/scripts/update_used_items.js`, critical: false },
    ]
  },
  {
    name: 'YouTube',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['youtube-trends.json', 'youtube-ideas.json'],
    steps: [
      { name: 'fetch_youtube_trends', script: `node ${BASE}/scripts/fetch_youtube_trends.js`, critical: false },
      { name: 'generate_youtube_ideas', script: `node ${BASE}/scripts/generate_youtube_ideas.js`, critical: false },
    ]
  },
  {
    name: 'Audit',
    critical: false,
    requiredOutputs: ['seo-audit.json', 'geo-audit.json'],
    optionalOutputs: [],
    steps: [
      { name: 'run_seo_audit', script: `node ${BASE}/scripts/run_seo_audit.js`, critical: false },
      { name: 'run_geo_audit', script: `node ${BASE}/scripts/run_geo_audit.js`, critical: false },
    ]
  },
  {
    name: 'Insights',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['website-insights.json'],
    steps: [
      { name: 'fetch_website_insights', script: `node ${BASE}/scripts/fetch_website_insights.js`, critical: false },
    ]
  },
  {
    name: 'Compile',
    critical: true,
    requiredOutputs: ['dashboard-summary.json'],
    optionalOutputs: [],
    steps: [
      { name: 'compile_dashboard', script: `node ${BASE}/scripts/compile_dashboard.js`, critical: true },
    ]
  },
  {
    name: 'Publish',
    critical: true,
    requiredOutputs: [],
    optionalOutputs: [],
    steps: [
      { name: 'publish_github', script: `node ${BASE}/scripts/publish_github.js`, critical: true },
    ]
  },
];

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
    const existing = fs.existsSync(LOG_FILE) ? fs.readFileSync(LOG_FILE, 'utf8').split('\n').slice(-300).join('\n') : '';
    fs.writeFileSync(LOG_FILE, existing + '\n' + line);
  } catch(e) {}
}

function runStep(step) {
  try {
    const out = execSync(step.script, { encoding: 'utf8', timeout: 60000 });
    return { name: step.name, status: 'PASS', output: out };
  } catch(e) {
    const err = e.status === 1 ? e.message.slice(-200) : `exit ${e.status}`;
    return { name: step.name, status: 'FAIL', error: err, critical: step.critical };
  }
}

function computeStageStatus(stage, stepResults, staleOutputs) {
  // If any critical step failed, stage is FAIL
  const criticalFailed = stepResults.filter(r => r.status === 'FAIL' && r.critical);
  if (criticalFailed.length > 0) {
    return 'FAIL';
  }
  
  // Check for any failed outputs in this stage
  const requiredStale = (stage.requiredOutputs || []).filter(f => staleOutputs.includes(f));
  if (requiredStale.length > 0) {
    return 'PARTIAL';
  }
  
  // If any step failed (non-critical), it's PARTIAL
  const anyFailed = stepResults.filter(r => r.status === 'FAIL');
  if (anyFailed.length > 0) {
    return 'PARTIAL';
  }
  
  // If any optional output is stale, it's PARTIAL
  const optionalStale = (stage.optionalOutputs || []).filter(f => staleOutputs.includes(f));
  if (optionalStale.length > 0) {
    return 'PARTIAL';
  }
  
  return 'PASS';
}

function loadValidationReport() {
  const REPORT_FILE = path.join(LOG_DIR, 'validation-report.json');
  try {
    return JSON.parse(fs.readFileSync(REPORT_FILE, 'utf8'));
  } catch (e) {
    return null;
  }
}

function compileSummary(stageResults, validatorReport) {
  const ig = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'ig-analytics.json'), 'utf8'));
  const ideas = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'content-ideas.json'), 'utf8'));
  const hooks = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'hook-bank.json'), 'utf8'));
  const checks = validatorReport?.checks || [];
  
  const staleChecks = checks.filter(c => c.data_status === 'STALE');
  const failedChecks = checks.filter(c => c.data_status === 'FAIL');
  const scriptFails = checks.filter(c => c.script_status === 'FAIL');
  const fallbacks = checks.filter(c => c.fallback_used === true);
  const syntheticChecks = checks.filter(c => c.source_mode === 'SYNTHETIC');
  
  // Trust Score - machine derived from validator checks
  // -2 per failed file, -1 per stale file, -1 per synthetic non-critical
  let trustScore = 10;
  const trustDeductions = [];
  
  // Stale non-critical = -1 each
  for (const c of staleChecks) {
    trustScore -= 1;
    trustDeductions.push(c.label + ' stale (-1)');
  }
  // Failed = -2 each (more severe than stale)
  for (const c of failedChecks) {
    if (!staleChecks.find(s => s.file === c.file)) { // don't double count
      trustScore -= 2;
      trustDeductions.push(c.label + ' failed (-2)');
    }
  }
  // Synthetic = -1 each (not real data)
  for (const c of syntheticChecks) {
    if (!staleChecks.find(s => s.file === c.file) && !failedChecks.find(s => s.file === c.file)) {
      trustScore -= 1;
      trustDeductions.push(c.label + ' synthetic (-1)');
    }
  }
  trustScore = Math.max(0, trustScore);
  
  // FAIL only if CRITICAL files failed; PARTIAL if non-critical failed, stale, or synthetic
  const criticalFailed = failedChecks.filter(c => c.critical);
  const nonCriticalFailed = failedChecks.filter(c => !c.critical);
  const overall = criticalFailed.length > 0 ? 'FAIL' : (nonCriticalFailed.length > 0 || staleChecks.length > 0 || syntheticChecks.length > 0) ? 'PARTIAL' : 'PASS';
  
  const topIdea = ideas.post_today?.[0] || ideas.ideas?.[0] || null;
  
  const summary = {
    pipeline_status: overall,
    timestamp: new Date().toISOString(),
    trust_score: trustScore,
    trust_deductions: trustDeductions,
    stage_results: stageResults.map(s => ({
      stage: s.stage,
      status: s.status,
      steps: s.results.map(r => ({ name: r.name, status: r.status })),
    })),
    stale_sources: staleChecks.map(c => c.label),
    failed_sources: failedChecks.map(c => c.label),
    synthetic_sources: syntheticChecks.map(c => ({ label: c.label, reason: c.reason || 'synthetic fallback' })),
    script_failures: scriptFails.map(c => c.label),
    fallbacks_used: fallbacks.map(c => c.label),
    top_action_today: topIdea ? {
      idea: topIdea.title || topIdea.hook || 'N/A',
      format: topIdea.format || 'static',
      reason: topIdea.source_reason || '',
      cta: topIdea.best_cta || 'link in bio',
      freshness_score: topIdea.freshness_score || 0,
    } : null,
    data_summary: {
      ig_posts: (ig.posts || []).length,
      ideas_generated: (ideas.ideas || []).length,
      hooks_tracked: (hooks.proven_hooks || []).length + (hooks.fresh_hooks_to_test || []).length,
    },
    validator: {
      overall_status: validatorReport?.overall_status || 'UNKNOWN',
      fresh_files: validatorReport?.summary?.pass || 0,
      total_files: (validatorReport?.checks || []).length || 0,
      script_failures: validatorReport?.summary?.script_failures || 0,
      fallbacks_used: validatorReport?.summary?.fallbacks_used || 0,
      qa_warnings: (validatorReport?.checks || []).filter(c => c.qa_warnings?.length > 0).map(c => ({ file: c.label, warnings: c.qa_warnings })),
    },
    weakest_sources: failedChecks.length > 0 
      ? failedChecks.map(c => c.label) 
      : staleChecks.length > 0
        ? staleChecks.map(c => c.label)
        : syntheticChecks.map(c => c.label),
  };
  
  fs.writeFileSync(SUMMARY_FILE, JSON.stringify(summary, null, 2));
  return summary;
}

function printFinalSummary(summary, validatorReport) {
  const saTime = new Date().toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg' });
  
  console.log('\n');
  console.log('═'.repeat(60));
  console.log('📊 DAILY RUN SUMMARY');
  console.log('═'.repeat(60));
  console.log(`Pipeline Status: ${summary.pipeline_status}`);
  console.log(`Trust Score: ${summary.trust_score}/10`);
  if (summary.trust_deductions.length > 0) {
    console.log(`  ${summary.trust_deductions.join(' | ')}`);
  }
  console.log(`Timestamp: ${saTime}`);
  console.log('');
  
  console.log('STAGE RESULTS:');
  for (const s of summary.stage_results) {
    const icon = s.status === 'PASS' ? '✅' : s.status === 'PARTIAL' ? '⚠️' : '❌';
    console.log(`  ${icon} ${s.stage}: ${s.status}`);
    for (const step of s.steps) {
      const stepIcon = step.status === 'PASS' ? '  ✅' : step.status === 'FAIL' ? '  ❌' : '  ⚠️';
      const scriptDetail = step.script_status === 'FAIL' ? ' [SCRIPT FAILED]' : '';
      const fallbackDetail = step.fallback_used ? ' [fallback used]' : '';
      console.log(`    ${stepIcon} ${step.name}${scriptDetail}${fallbackDetail}`);
    }
  }
  console.log('');
  
  if (summary.script_failures.length > 0) {
    console.log('🔴 SCRIPT FAILURES:');
    for (const s of summary.script_failures) {
      console.log(`  - ${s}`);
    }
    console.log('');
  }
  
  console.log('DATA SUMMARY:');
  console.log(`  IG Posts: ${summary.data_summary.ig_posts}`);
  console.log(`  Ideas: ${summary.data_summary.ideas_generated}`);
  console.log(`  Hooks: ${summary.data_summary.hooks_tracked}`);
  console.log('');
  
  // Validator confirmation line
  const v = validatorReport;
  const passCount = v?.summary?.pass || 0;
  const totalCount = (v?.checks || []).length || 0;
  const scriptFails = v?.summary?.script_failures || 0;
  const fallbacksUsed = v?.summary?.fallbacks_used || 0;
  console.log('VALIDATOR: ' + (v?.overall_status || 'UNKNOWN'));
  console.log('  Fresh files: ' + passCount + '/' + totalCount + ' checked');
  if (scriptFails > 0) console.log('  Script failures: ' + scriptFails + (fallbacksUsed > 0 ? ' (' + fallbacksUsed + ' used fallback)' : ''));
  console.log('');
  
  // SOURCE MODE - which sources are live vs synthetic
  const syntheticSources = (v?.checks || []).filter(c => c.source_mode === 'SYNTHETIC').map(c => c.label);
  const staleSources = (v?.checks || []).filter(c => c.data_status === 'STALE').map(c => c.label);
  if (syntheticSources.length > 0 || staleSources.length > 0) {
    console.log('SOURCE MODE:');
    for (const c of (v?.checks || [])) {
      if (c.source_mode === 'SYNTHETIC') {
        console.log('  ⚠️  ' + c.label + ': SYNTHETIC fallback (no live external source)');
      } else if (c.source_mode === 'STALE_FALLBACK') {
        console.log('  ⚠️  ' + c.label + ': STALE_FALLBACK (fresh fetch failed, previous data used)');
      }
    }
    console.log('');
  }
  
  if (summary.stale_sources.length > 0) {
    console.log('⚠️  STALE SOURCES:');
    for (const s of summary.stale_sources) {
      console.log(`  - ${s}`);
    }
    console.log('');
  }
  
  if (summary.failed_sources.length > 0) {
    console.log('❌ FAILED SOURCES:');
    for (const s of summary.failed_sources) {
      console.log(`  - ${s}`);
    }
    console.log('');
  }
  
  if (summary.top_action_today) {
    console.log('🎯 TOP ACTION TODAY:');
    console.log(`  "${summary.top_action_today.idea}"`);
    console.log(`  Format: ${summary.top_action_today.format} | Freshness: ${summary.top_action_today.freshness_score}/10`);
    console.log(`  CTA: ${summary.top_action_today.cta}`);
    console.log('');
  }
  
  if (summary.weakest_sources.length > 0) {
    console.log('🔥 MOST IMPORTANT WEAKNESS:');
    console.log(`  ${summary.weakest_sources[0]}`);
    if (summary.weakest_sources.length > 1) {
      console.log(`  Also stale: ${summary.weakest_sources.slice(1).join(', ')}`);
    }
    console.log('');
  }
  
  console.log('═'.repeat(60));
  
  if (summary.pipeline_status === 'PASS') {
    console.log('✅ PIPELINE COMPLETE - All sources fresh');
  } else if (summary.pipeline_status === 'PARTIAL') {
    console.log('⚠️  PIPELINE COMPLETE - Some sources stale');
  } else if (summary.pipeline_status === 'FAIL') {
    console.log('🚫 PIPELINE FAILED - Critical stage broken');
  } else {
    console.log('❓ PIPELINE STATUS UNKNOWN');
  }
  console.log('═'.repeat(60));
}

async function main() {
  log('═══════════════════════════════════════════════');
  log('MASTER PIPELINE STARTED');
  log('═══════════════════════════════════════════════');
  
  const stageResults = [];
  
  for (const stage of STAGES) {
    log(`\n📦 STAGE: ${stage.name}`);
    
    const results = [];
    for (const step of stage.steps) {
      log(`  → Running: ${step.name}`);
      const result = runStep(step);
      results.push(result);
      
      if (result.status === 'FAIL') {
        if (step.critical) {
          log(`  ❌ ${step.name} FAILED (CRITICAL) - STOPPING`);
          stageResults.push({ stage: stage.name, status: 'FAIL', critical: true, results });
          log(`\n🚫 CRITICAL STAGE FAILED: ${stage.name} - stopping pipeline`);
          
          // Run validator to get final state
          log('\n🔍 Running validation...');
          execSync(`node ${BASE}/scripts/validator.js`, { encoding: 'utf8', timeout: 15000 });
          const validatorReport = loadValidationReport();
          const summary = compileSummary(stageResults, validatorReport);
          printFinalSummary(summary, validatorReport);
          return;
        } else {
          log(`  ⚠️  ${step.name} FAILED (non-critical) - continuing`);
        }
      } else {
        log(`  ✅ ${step.name}`);
      }
    }
    
    // Check for any stale outputs in this stage (required or optional)
    // Use comprehensive stale check that mirrors validator logic
    const allOutputs = [...(stage.requiredOutputs || []), ...(stage.optionalOutputs || [])];
    const staleOutputs = allOutputs.filter(f => {
      const fpath = path.join(DATA_DIR, f);
      if (!fs.existsSync(fpath)) return true; // missing = stale
      try {
        const data = JSON.parse(fs.readFileSync(fpath, 'utf8'));
        if (!data.updated || data.updated === 'never') return true;
        if (data._stale === true) return true; // script marked it stale
        const age = (Date.now() - new Date(data.updated).getTime()) / 3600000;
        if (age > 26) return true;
        // Special cases: non-empty expected
        if (f === 'ig-analytics.json' && (!data.posts || data.posts.length === 0)) return true;
        if (f === 'content-ideas.json' && (!data.ideas || data.ideas.length === 0)) return true;
        if (f === 'hook-bank.json' && (!data.proven_hooks && !data.hooks && !data.hooks_by_goal)) return true;
        if (f === 'youtube-trends.json' && (!data.videos_found || data.videos_found === 0)) return true;
        if (f === 'youtube-trends.json' && data._synthetic === true) return true; // synthetic = partial
        if (f === 'youtube-ideas.json' && (!data.ideas || data.ideas.length === 0)) return true;
        return false;
      } catch { return true; }
    });
    
    // Now compute stage status based on script results + stale outputs
  const stageStatus = computeStageStatus(stage, results, staleOutputs);
    stageResults.push({ stage: stage.name, status: stageStatus, results, staleOutputs });
  }
  
  // Run validator
  log('\n🔍 Running validation...');
  execSync(`node ${BASE}/scripts/validator.js`, { encoding: 'utf8', timeout: 15000 });
  const validatorReport = loadValidationReport();
  
  // Compile summary
  const summary = compileSummary(stageResults, validatorReport);
  
  // Print final summary
  printFinalSummary(summary, validatorReport);
  
  log('\n✅ Master pipeline complete');
  return summary;
}

main().catch(e => {
  log(`\n💥 PIPELINE ERROR: ${e.message}`);
  console.log('\n🚫 PIPELINE FAILED');
  process.exit(1);
});