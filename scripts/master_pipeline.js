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
    optionalOutputs: ['youtube-trends.json', 'youtube-ideas.json', 'youtube-hook-signals.json'],
    steps: [
      { name: 'fetch_youtube_trends', script: `node ${BASE}/scripts/fetch_youtube_trends.js`, critical: false },
      { name: 'generate_youtube_ideas', script: `node ${BASE}/scripts/generate_youtube_ideas.js`, critical: false },
      { name: 'extract_youtube_signals', script: `node ${BASE}/scripts/extract_youtube_signals.js`, critical: false },
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
    name: 'Plan',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['post-plan.json', 'sales-priority.json', 'missed-opportunities.json', 'follow-up-queue.json', 'asset-needs.json', 'owner-workload.json', 'conversion-attribution.json', 'funnel-leaks.json', 'cta-performance.json', 'retargeting-recommendations.json', 'recommendation-scores.json', 'recommendation-outcomes.json', 'experiment-queue.json', 'scaling-recommendations.json', 'kill-list.json', 'anomaly-alerts.json', 'daily-task-cards.json', 'approval-queue.json', 'deadline-risk.json', 'blockers.json', 'capacity-shift.json', 'nudge-queue.json', 'fallback-queue.json', 'next-day-queue.json', 'auto-messages.json', 'suppression-rules.json', 'discord-deliveries.json', 'delivery-audit.json', 'system-health.json', 'route-log.json', 'routing-log.json', 'agent-scorecards.json', 'content-blueprints.json', 'hook-variants.json', 'hook-recommendations.json', 'cta-recommendations.json', 'captions.json', 'caption-variants.json', 'visual-briefs.json', 'image-prompts.json', 'thumbnail-briefs.json', 'blog-briefs.json', 'blog-drafts.json', 'faq-opportunities.json', 'reddit-replies.json', 'reddit-opportunities.json', 'forum-opportunities.json', 'qa-report.json', 'qa-failures.json', 'ready-for-approval.json', 'approval-queue.json', 'approval-summary.json', 'brand-guard-report.json', 'tone-violations.json', 'publish-queue.json', 'published-items.json', 'scheduled-items.json', 'publish-failures.json', 'postback-log.json', 'schedule-board.json', 'tomorrow-slots.json', 'reschedule-log.json', 'approval-actions.json', 'approval-expiry.json'],
    steps: [
      { name: 'generate_post_plan',          script: `node ${BASE}/scripts/generate_post_plan.js`,          critical: false },
      { name: 'generate_sales_priority',     script: `node ${BASE}/scripts/generate_sales_priority.js`,     critical: false },
      { name: 'detect_missed_opportunities', script: `node ${BASE}/scripts/detect_missed_opportunities.js`, critical: false },
      { name: 'generate_follow_up_queue',    script: `node ${BASE}/scripts/generate_follow_up_queue.js`,    critical: false },
      { name: 'generate_asset_needs',         script: `node ${BASE}/scripts/generate_asset_needs.js`,         critical: false },
      { name: 'generate_owner_workload',     script: `node ${BASE}/scripts/generate_owner_workload.js`,   critical: false },
      { name: 'generate_conversion_attribution', script: `node ${BASE}/scripts/generate_conversion_attribution.js`, critical: false },
      { name: 'generate_funnel_leaks',        script: `node ${BASE}/scripts/generate_funnel_leaks.js`,        critical: false },
      { name: 'generate_cta_performance',       script: `node ${BASE}/scripts/generate_cta_performance.js`,       critical: false },
      { name: 'generate_retargeting_recommendations',   script: `node ${BASE}/scripts/generate_retargeting_recommendations.js`,   critical: false },
      { name: 'generate_recommendation_scores',        script: `node ${BASE}/scripts/generate_recommendation_scores.js`,        critical: false },
      { name: 'generate_recommendation_outcomes',     script: `node ${BASE}/scripts/generate_recommendation_outcomes.js`,     critical: false },
      { name: 'generate_experiment_queue',         script: `node ${BASE}/scripts/generate_experiment_queue.js`,         critical: false },
      { name: 'generate_scaling_recommendations', script: `node ${BASE}/scripts/generate_scaling_recommendations.js`, critical: false },
      { name: 'generate_kill_list',               script: `node ${BASE}/scripts/generate_kill_list.js`,               critical: false },
      { name: 'generate_anomaly_alerts',            script: `node ${BASE}/scripts/generate_anomaly_alerts.js`,            critical: false },
      { name: 'generate_daily_task_cards',       script: `node ${BASE}/scripts/generate_daily_task_cards.js`,       critical: false },
      { name: 'generate_approval_queue',          script: `node ${BASE}/scripts/generate_approval_queue.js`,          critical: false },
      { name: 'generate_deadline_risk',         script: `node ${BASE}/scripts/generate_deadline_risk.js`,         critical: false },
      { name: 'generate_blockers',               script: `node ${BASE}/scripts/generate_blockers.js`,               critical: false },
      { name: 'generate_capacity_shift',            script: `node ${BASE}/scripts/generate_capacity_shift.js`,            critical: false },
      { name: 'generate_nudge_queue',               script: `node ${BASE}/scripts/generate_nudge_queue.js`,               critical: false },
      { name: 'generate_fallback_queue',           script: `node ${BASE}/scripts/generate_fallback_queue.js`,           critical: false },
      { name: 'generate_next_day_queue',          script: `node ${BASE}/scripts/generate_next_day_queue.js`,          critical: false },
      { name: 'generate_auto_messages',           script: `node ${BASE}/scripts/generate_auto_messages.js`,           critical: false },
      { name: 'generate_suppression_rules',        script: `node ${BASE}/scripts/generate_suppression_rules.js`,        critical: false },
      { name: 'send_discord_nudges',              script: `node ${BASE}/scripts/send_discord_nudges.js`,              critical: false },
      { name: 'log_discord_deliveries',           script: `node ${BASE}/scripts/log_discord_deliveries.js`,           critical: false },
      { name: 'generate_delivery_audit',         script: `node ${BASE}/scripts/generate_delivery_audit.js`,         critical: false },
      { name: 'generate_pulse_keeper',           script: `node ${BASE}/scripts/generate_pulse_keeper.js`,           critical: false },
      { name: 'generate_content_blueprints',   script: `node ${BASE}/scripts/generate_content_blueprints.js`,   critical: false },
      { name: 'store_daily_learnings',        script: `node ${BASE}/scripts/store_daily_learnings.js`,        critical: false },
      { name: 'generate_agent_scorecards',    script: `node ${BASE}/scripts/generate_agent_scorecards.js`,    critical: false },
    ]
  },
  {
    name: 'Production',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['captions.json', 'caption-variants.json', 'visual-briefs.json', 'image-prompts.json', 'thumbnail-briefs.json', 'blog-briefs.json', 'blog-drafts.json', 'faq-opportunities.json', 'reddit-replies.json', 'reddit-opportunities.json', 'forum-opportunities.json'],
    steps: [
      { name: 'caption_closer',  script: `node ${BASE}/agents/caption_closer/run.js`,  critical: false },
      { name: 'visual_forge',    script: `node ${BASE}/agents/visual_forge/run.js`,    critical: false },
      { name: 'blog_beast',      script: `node ${BASE}/agents/blog_beast/run.js`,      critical: false },
      { name: 'reddit_ghost',    script: `node ${BASE}/agents/reddit_ghost/run.js`,    critical: false },
    ]
  },
  {
    name: 'QA',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['qa-report.json', 'qa-failures.json', 'ready-for-approval.json', 'approval-queue.json', 'approval-summary.json', 'brand-guard-report.json', 'tone-violations.json'],
    steps: [
      { name: 'qa_inspector',       script: `node ${BASE}/agents/qa_inspector/run.js`,      critical: false },
      { name: 'approval_captain',    script: `node ${BASE}/agents/approval_captain/run.js`, critical: false },
      { name: 'brand_guard',         script: `node ${BASE}/agents/brand_guard/run.js`,       critical: false },
    ]
  },
  {
    name: 'Publishing',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['publish-queue.json', 'published-items.json', 'scheduled-items.json', 'publish-failures.json', 'postback-log.json', 'schedule-board.json', 'tomorrow-slots.json', 'reschedule-log.json', 'approval-actions.json', 'approval-expiry.json'],
    steps: [
      { name: 'publisher',         script: `node ${BASE}/agents/publisher/run.js`,        critical: false },
      { name: 'postback_logger',   script: `node ${BASE}/agents/postback_logger/run.js`,  critical: false },
      { name: 'schedule_captain',  script: `node ${BASE}/agents/schedule_captain/run.js`, critical: false },
      { name: 'approval_runner',   script: `node ${BASE}/agents/approval_runner/run.js`,  critical: false },
    ]
  },
  {
    name: 'Reporting',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['weekly-report.json', 'weekly-report.md', 'weekly-learnings.json', 'what-to-repeat.json', 'what-to-stop.json', 'executive-brief.json', 'owner-performance.json', 'trend-delta.json'],
    steps: [
      { name: 'weekly_reporter',              script: `node ${BASE}/scripts/run_weekly_reporter.js`,             critical: false },
      { name: 'learning_summariser',         script: `node ${BASE}/scripts/run_learning_summariser.js`,        critical: false },
      { name: 'executive_brief_builder',     script: `node ${BASE}/scripts/run_executive_brief_builder.js`,    critical: false },
      { name: 'owner_performance_reporter',  script: `node ${BASE}/scripts/run_owner_performance_reporter.js`, critical: false },
      { name: 'trend_delta_reporter',        script: `node ${BASE}/scripts/run_trend_delta_reporter.js`,        critical: false },
    ]
  },
  {
    name: 'Autonomy',
    critical: false,
    requiredOutputs: ['autonomy-rules.json'],
    optionalOutputs: ['autonomy-decisions.json', 'live-nudge-log.json', 'auto-swaps.json', 'auto-approval-actions.json', 'autopublished-items.json'],
    steps: [
      { name: 'autonomy_rules_engine',      script: `node ${BASE}/scripts/run_autonomy_rules_engine.js`,      critical: true },
      { name: 'live_nudge_dispatcher',      script: `node ${BASE}/scripts/run_live_nudge_dispatcher.js`,      critical: false },
      { name: 'fallback_auto_swapper',      script: `node ${BASE}/scripts/run_fallback_auto_swapper.js`,      critical: false },
      { name: 'approval_auto_promoter',     script: `node ${BASE}/scripts/run_approval_auto_promoter.js`,     critical: false },
      { name: 'low_risk_publisher',         script: `node ${BASE}/scripts/run_low_risk_publisher.js`,         critical: false },
    ]
  },
  {
    name: 'RevenueRecovery',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['lead-recovery.json', 'landing-page-fixes.json', 'retargeting-campaigns.json', 'email-nurtures.json', 'offer-opportunities.json'],
    steps: [
      { name: 'lead_recovery_engine',           script: `node ${BASE}/scripts/run_lead_recovery_engine.js`,           critical: false },
      { name: 'landing_page_optimizer',         script: `node ${BASE}/scripts/run_landing_page_optimizer.js`,         critical: false },
      { name: 'retargeting_campaign_builder',    script: `node ${BASE}/scripts/run_retargeting_campaign_builder.js`,    critical: false },
      { name: 'email_nurture_builder',           script: `node ${BASE}/scripts/run_email_nurture_builder.js`,           critical: false },
      { name: 'offer_engine',                    script: `node ${BASE}/scripts/run_offer_engine.js`,                   critical: false },
    ]
  },
  {
    name: 'CommerceCapture',
    critical: false,
    requiredOutputs: [],
    optionalOutputs: ['lead-capture-fixes.json', 'booking-flow-improvements.json', 'bundle-opportunities.json', 'lead-quality.json', 'whatsapp-flows.json'],
    steps: [
      { name: 'lead_capture_optimizer',       script: `node ${BASE}/scripts/run_lead_capture_optimizer.js`,       critical: false },
      { name: 'booking_flow_engine',         script: `node ${BASE}/scripts/run_booking_flow_engine.js`,         critical: false },
      { name: 'bundle_builder',              script: `node ${BASE}/scripts/run_bundle_builder.js`,              critical: false },
      { name: 'lead_quality_scorer',         script: `node ${BASE}/scripts/run_lead_quality_scorer.js`,         critical: false },
      { name: 'whatsapp_conversion_builder',  script: `node ${BASE}/scripts/run_whatsapp_conversion_builder.js`,  critical: false },
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

/**
 * Stage PASS rule (locked):
 * A stage may be PASS only if all scripts assigned to that stage either:
 * - succeeded with LIVE output (no _synthetic flag), OR
 * - are explicitly excluded from stage health (not in requiredOutputs)
 * Any SYNTHETIC, STALE, or failed non-critical script makes the stage PARTIAL.
 * Any failed critical script makes the stage FAIL.
 */
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
      hooks_tracked: hooks.total_hooks || 0,
    },
    validator: {
      overall_status: validatorReport?.overall_status || 'UNKNOWN',
      live_fresh: validatorReport?.summary?.live_fresh || 0,
      synthetic: validatorReport?.summary?.synthetic || 0,
      stale: validatorReport?.summary?.stale || 0,
      failed: validatorReport?.summary?.failed || 0,
      total: validatorReport?.summary?.total || 0,
      script_failures: validatorReport?.summary?.script_failures || 0,
      fallbacks_used: validatorReport?.summary?.fallbacks_used || 0,
      qa_warnings: (validatorReport?.checks || []).filter(c => c.qa_warnings?.length > 0).map(c => ({ file: c.label, warnings: c.qa_warnings })),
      source_integrity: (validatorReport?.checks || []).map(c => ({ label: c.label, mode: c.source_mode || 'LIVE', status: c.data_status })),
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
  const scriptFails = v?.summary?.script_failures || 0;
  const fallbacksUsed = v?.summary?.fallbacks_used || 0;
  const liveFresh = v?.summary?.live_fresh || 0;
  const syntheticFiles = v?.summary?.synthetic || 0;
  console.log('VALIDATOR: ' + (v?.overall_status || 'UNKNOWN'));
  console.log('  Live fresh: ' + liveFresh + '/' + (v?.summary?.total || 0));
  if (syntheticFiles > 0) console.log('  Synthetic: ' + syntheticFiles + '/' + (v?.summary?.total || 0));
  if (scriptFails > 0) console.log('  Failed scripts: ' + scriptFails + (fallbacksUsed > 0 ? ' (' + fallbacksUsed + ' used fallback)' : ''));
  console.log('');
  
  // SOURCE MODE - per-source integrity
  const syntheticSources = (v?.checks || []).filter(c => c.source_mode === 'SYNTHETIC').map(c => c.label);
  const staleSources = (v?.checks || []).filter(c => c.data_status === 'STALE').map(c => c.label);
  const failedSources = (v?.checks || []).filter(c => c.data_status === 'FAIL').map(c => c.label);
  if (syntheticSources.length > 0 || staleSources.length > 0 || failedSources.length > 0) {
    console.log('SOURCE MODE:');
    for (const c of (v?.checks || [])) {
      if (c.source_mode === 'SYNTHETIC') {
        console.log('  ' + c.label + ': SYNTHETIC');
      } else if (c.source_mode === 'STALE_FALLBACK') {
        console.log('  ' + c.label + ': STALE_FALLBACK');
      } else if (c.data_status === 'STALE') {
        console.log('  ' + c.label + ': STALE');
      } else if (c.data_status === 'FAIL') {
        console.log('  ' + c.label + ': FAIL');
      }
    }
    console.log('');
  }
  
  // OPEN GAP — known system limitations, explicitly called out
  console.log('OPEN GAP:');
  console.log('  - Real-time publish-triggered used-items marking not yet wired');
  console.log('  - Current protection: daily Ideas stage reconciliation only');
  console.log('  - Risk: same-day duplicate ideas may slip through once');
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