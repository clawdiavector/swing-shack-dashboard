#!/usr/bin/env node
/**
 * master_pipeline.js
 * Orchestrator - runs all 6 stages in order, validates, stops on critical failure
 * Produces daily run summary
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
    steps: [
      { name: 'analyse_hooks', script: `node ${BASE}/scripts/analyse_hooks.js`, critical: true },
    ]
  },
  {
    name: 'Ideas',
    critical: true,
    steps: [
      { name: 'generate_content_ideas', script: `node ${BASE}/scripts/generate_content_ideas.js`, critical: true },
      { name: 'update_used_items', script: `node ${BASE}/scripts/update_used_items.js`, critical: false },
    ]
  },
  {
    name: 'Audit',
    critical: false,
    steps: [
      { name: 'run_seo_audit', script: `node ${BASE}/scripts/run_seo_audit.js`, critical: false },
      { name: 'run_geo_audit', script: `node ${BASE}/scripts/run_geo_audit.js`, critical: false },
      { name: 'fetch_website_insights', script: 'node scripts/fetch_website_insights.js', critical: false },
    ]
  },
  {
    name: 'Compile',
    critical: true,
    steps: [
      { name: 'compile_dashboard', script: `node ${BASE}/scripts/compile_dashboard.js`, critical: true },
    ]
  },
  {
    name: 'Publish',
    critical: true,
    steps: [
      { name: 'publish_github', script: `node ${BASE}/scripts/publish_github.js`, critical: true },
    ]
  },
];

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  try {
    const existing = fs.existsSync(LOG_FILE) ? fs.readFileSync(LOG_FILE, 'utf8').split('\n').slice(-300).join('\n') : '';
    fs.writeFileSync(LOG_FILE, existing + '\n' + line);
  } catch(e) {}
}

function runStep(step) {
  return new Promise((resolve) => {
    log(`  → Running: ${step.name}`);
    try {
      const out = execSync(step.script, { encoding: 'utf8', timeout: 60000 });
      resolve({ name: step.name, status: 'PASS', output: out });
    } catch(e) {
      const err = e.status === 1 ? e.message.slice(-200) : `exit ${e.status}`;
      resolve({ name: step.name, status: 'FAIL', error: err, critical: step.critical });
    }
  });
}

async function runStage(stage) {
  log(`\n📦 STAGE: ${stage.name}`);
  const results = [];
  
  for (const step of stage.steps) {
    const result = await runStep(step);
    results.push(result);
    
    if (result.status === 'FAIL') {
      if (step.critical) {
        log(`  ❌ ${step.name} FAILED (CRITICAL) - STOPPING`);
        return { stage: stage.name, status: 'FAIL', critical: true, results };
      } else {
        log(`  ⚠️  ${step.name} FAILED (non-critical) - marking stale, continuing`);
      }
    } else {
      log(`  ✅ ${step.name}`);
    }
  }
  
  return { stage: stage.name, status: 'PASS', results };
}

async function runValidator() {
  try {
    const { run } = require('./validator.js');
    return run();
  } catch(e) {
    return null;
  }
}

async function compileSummary(stageResults, validatorReport) {
  const ig = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'ig-analytics.json'), 'utf8'));
  const ideas = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'content-ideas.json'), 'utf8'));
  const hooks = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'hook-bank.json'), 'utf8'));
  
  const staleSources = (validatorReport?.results || [])
    .filter(r => r.status === 'STALE')
    .map(r => r.file.replace('.json', ''));
  
  const topIdea = ideas.post_today?.[0] || ideas.ideas?.[0] || null;
  
  const summary = {
    pipeline_status: validatorReport?.pipeline_status || 'UNKNOWN',
    timestamp: new Date().toISOString(),
    stage_results: stageResults.map(s => ({ stage: s.stage, status: s.status })),
    stale_sources: staleSources,
    top_action_today: topIdea ? {
      idea: topIdea.title || topIdea.hook || 'N/A',
      format: topIdea.format || 'static',
      reason: topIdea.source_reason || '',
      cta: topIdea.best_cta || 'link in bio',
    } : null,
    data_summary: {
      ig_posts: (ig.posts || []).length,
      ideas_generated: (ideas.ideas || []).length,
      hooks_tracked: (hooks.proven_hooks || []).length + (hooks.fresh_hooks_to_test || []).length,
    }
  };
  
  fs.writeFileSync(SUMMARY_FILE, JSON.stringify(summary, null, 2));
  return summary;
}

function printFinalSummary(summary, validatorReport) {
  console.log('\n');
  console.log('═'.repeat(60));
  console.log('📊 DAILY RUN SUMMARY');
  console.log('═'.repeat(60));
  console.log(`Pipeline Status: ${summary.pipeline_status}`);
  console.log(`Timestamp: ${new Date().toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg' })}`);
  console.log('');
  
  console.log('STAGE RESULTS:');
  for (const s of summary.stage_results) {
    const icon = s.status === 'PASS' ? '✅' : '❌';
    console.log(`  ${icon} ${s.stage}: ${s.status}`);
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
  
  if (summary.top_action_today) {
    console.log('🎯 TOP ACTION TODAY:');
    console.log(`  "${summary.top_action_today.idea}"`);
    console.log(`  Format: ${summary.top_action_today.format}`);
    console.log(`  CTA: ${summary.top_action_today.cta}`);
    console.log('');
  }
  
  const failedStages = summary.stage_results.filter(s => s.status === 'FAIL');
  if (failedStages.length > 0) {
    console.log('❌ FAILED STAGES:');
    for (const s of failedStages) {
      console.log(`  - ${s.stage}`);
    }
    console.log('');
  }
  
  console.log('═'.repeat(60));
  console.log(summary.pipeline_status === 'PASS' ? '✅ PIPELINE COMPLETE' : summary.pipeline_status === 'PARTIAL' ? '⚠️  PIPELINE COMPLETE - STALE DATA' : '🚫 PIPELINE FAILED');
  console.log('═'.repeat(60));
}

async function main() {
  log('═══════════════════════════════════════════════');
  log('MASTER PIPELINE STARTED');
  log('═══════════════════════════════════════════════');
  
  const stageResults = [];
  
  for (const stage of STAGES) {
    const result = await runStage(stage);
    stageResults.push(result);
    
    // Stop if critical stage failed
    if (result.status === 'FAIL' && result.critical) {
      log(`\n🚫 CRITICAL STAGE FAILED: ${stage.name} - stopping pipeline`);
      break;
    }
  }
  
  // Validate outputs
  log('\n🔍 Running validation...');
  const validatorReport = await runValidator();
  
  // Compile summary
  const summary = await compileSummary(stageResults, validatorReport);
  
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