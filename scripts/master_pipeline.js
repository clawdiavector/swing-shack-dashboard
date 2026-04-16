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

function computeStageStatus(stage, stepResults) {
  // If any critical step failed, stage is FAIL
  const criticalFailed = stepResults.filter(r => r.status === 'FAIL' && r.critical);
  if (criticalFailed.length > 0) {
    return 'FAIL';
  }
  
  // If any step failed (critical or not), it's PARTIAL
  const anyFailed = stepResults.filter(r => r.status === 'FAIL');
  if (anyFailed.length > 0) {
    return 'PARTIAL';
  }
  
  // All steps passed
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
  
  const staleChecks = (validatorReport?.checks || []).filter(c => c.status === 'STALE');
  const failedChecks = (validatorReport?.checks || []).filter(c => c.status === 'FAIL');
  
  // Determine overall pipeline status
  const overall = validatorReport?.overall_status || 'UNKNOWN';
  
  // Get top idea
  const topIdea = ideas.post_today?.[0] || ideas.ideas?.[0] || null;
  
  const summary = {
    pipeline_status: overall,
    timestamp: new Date().toISOString(),
    stage_results: stageResults.map(s => ({
      stage: s.stage,
      status: s.status,
      steps: s.results.map(r => ({ name: r.name, status: r.status })),
    })),
    stale_sources: staleChecks.map(c => c.label),
    failed_sources: failedChecks.map(c => c.label),
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
    weakest_sources: failedChecks.length > 0 
      ? failedChecks.map(c => c.label) 
      : staleChecks.map(c => c.label),
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
  console.log(`Timestamp: ${saTime}`);
  console.log('');
  
  console.log('STAGE RESULTS:');
  for (const s of summary.stage_results) {
    const icon = s.status === 'PASS' ? '✅' : s.status === 'PARTIAL' ? '⚠️' : '❌';
    console.log(`  ${icon} ${s.stage}: ${s.status}`);
    for (const step of s.steps) {
      const stepIcon = step.status === 'PASS' ? '  ✅' : step.status === 'FAIL' ? '  ❌' : '  ⚠️';
      console.log(`    ${stepIcon} ${step.name}`);
    }
  }
  console.log('');
  
  console.log('DATA SUMMARY:');
  console.log(`  IG Posts: ${summary.data_summary.ig_posts}`);
  console.log(`  Ideas: ${summary.data_summary.ideas_generated}`);
  console.log(`  Hooks: ${summary.data_summary.hooks_tracked}`);
  console.log('');
  
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
    
    const stageStatus = computeStageStatus(stage, results);
    stageResults.push({ stage: stage.name, status: stageStatus, results });
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