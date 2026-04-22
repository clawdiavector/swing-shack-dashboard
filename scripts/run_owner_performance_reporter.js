#!/usr/bin/env node
/**
 * run_owner_performance_reporter.js
 * Reads: agent-runs.json, published-posts.json, approval-actions.json, daily-task-cards.json
 * Produces: owner-performance.json
 *
 * Schema: https://clawdia.io/agents/owner-performance-reporter/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const weekAgo = new Date(now - 7 * 86400000);

  const agentRu = readJson('agent-runs.json') || {};
  const pubPost = readJson('published-posts.json') || {};
  const apprAc  = readJson('approval-actions.json') || {};
  const tasks   = readJson('daily-task-cards.json') || {};
  const recOut  = readJson('recommendation-outcomes.json') || {};

  const published = (pubPost.published || []).filter(p => !p.published_at || new Date(p.published_at) >= weekAgo);
  const agents   = agentRu.agents || {};

  // ── Build owner map from published posts ─────────────────────────
  const ownerMap = {};
  published.forEach(p => {
    const o = p.owner || 'unassigned';
    ownerMap[o] = ownerMap[o] || { published: 0, failed: 0, wins: [], hook_ids: [], cta_types: [] };
    ownerMap[o].published++;
    if (p.hook_id) ownerMap[o].hook_ids.push(p.hook_id);
    if (p.cta_type) ownerMap[o].cta_types.push(p.cta_type);
    if (p.status === 'failed') ownerMap[o].failed++;
  });

  // ── Agent run counts ─────────────────────────────────────────────
  const agentCounts = {};
  Object.entries(agents).forEach(([agentId, runs]) => {
    const recent = (runs || []).filter(r => new Date(r.run_at) >= weekAgo);
    const passed = recent.filter(r => r.status === 'PASS').length;
    const failed = recent.filter(r => r.status !== 'PASS').length;
    agentCounts[agentId] = { total: recent.length, passed, failed, pass_rate: recent.length > 0 ? Math.round((passed/recent.length)*100)+'%' : '0%' };
  });

  // ── Approval delays ───────────────────────────────────────────────
  const apprDelayCount = ((apprAc.actions || []).filter(a => a.action === 'reset_approval')).length;
  const promotedCount  = ((apprAc.actions || []).filter(a => a.action === 'promote_to_publish')).length;

  // ── Overload detection ───────────────────────────────────────────
  const overloadThreshold = 5;
  const overloaded = Object.entries(ownerMap).filter(([,o]) => o.published > overloadThreshold).map(([k]) => k);

  // ── Wins attached to owner ────────────────────────────────────────
  const outcomeRecs = recOut.outcomes || [];
  const ownerWins = {};
  outcomeRecs.filter(o => o.outcome_timestamp && new Date(o.outcome_timestamp) >= weekAgo).forEach(o => {
    if (!o.owner) return;
    ownerWins[o.owner] = ownerWins[o.owner] || { published: 0, attributed: [] };
    ownerWins[o.owner].published++;
    if (o.recommendation_id) ownerWins[o.owner].attributed.push(o.recommendation_id);
  });

  // ── Blocked by assets/approval ───────────────────────────────────
  const blockedTasks = (tasks.blocked || tasks.items || []).filter(t => t.status === 'blocked' || t.status === 'waiting_assets').length;

  const ownerPerf = {
    schema: 'https://clawdia.io/agents/owner-performance-reporter/v1',
    generated: now.toISOString(),
    period_from: weekAgo.toISOString().split('T')[0],
    period_to: now.toISOString().split('T')[0],
    summary: {
      total_owners: Object.keys(ownerMap).length,
      total_published: published.length,
      total_failed: published.filter(p => p.status === 'failed').length,
      approval_delays: apprDelayCount,
      promote_count: promotedCount,
      blocked_tasks: blockedTasks,
      overloaded_owners: overloaded,
      owner_list: Object.keys(ownerMap),
    },
    by_owner: Object.entries(ownerMap).map(([owner, o]) => ({
      owner,
      published: o.published,
      failed: o.failed,
      wins: ownerWins[owner]?.attributed?.length || 0,
      hook_count: [...new Set(o.hook_ids)].length,
      cta_count: [...new Set(o.cta_types)].length,
      is_overload: overloaded.includes(owner),
    })),
    agent_runs: agentCounts,
    risk_flags: [
      ...overloaded.map(o => ({ type: 'overload', owner: o, message: `Owner ${o} has ${ownerMap[o]?.published || 0} publishes — above threshold of ${overloadThreshold}` })),
      ...(apprDelayCount > 3 ? [{ type: 'approval_delays', message: `${apprDelayCount} approval resets this week — investigate` }] : []),
    ],
  };

  fs.writeFileSync(path.join(DATA, 'owner-performance.json'), JSON.stringify(ownerPerf, null, 2));
  console.log(`✅ Owner performance: ${Object.keys(ownerMap).length} owners | ${published.length} published | ${overloaded.length} overloaded`);
  console.log(`   Approval delays: ${apprDelayCount} | Promote: ${promotedCount} | Blocked tasks: ${blockedTasks}`);
  if (overloaded.length > 0) console.log(`   ⚠️  Overloaded: ${overloaded.join(', ')}`);
}

module.exports = { run };
if (require.main === module) run();