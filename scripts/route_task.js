#!/usr/bin/env node
/**
 * route_task.js — Task Router v1
 * Deterministic task routing using keyword + capability rules.
 * NOT AI routing — routes based on declared agent capabilities.
 *
 * Usage: node route_task.js "your task description"
 * Output: data/route-log.json
 */
const fs = require('fs');
const path = require('path');

const BASE   = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA   = path.join(BASE, 'data');
const OUTPUT = path.join(DATA, 'route-log.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, name), 'utf8')); }
  catch { return null; }
}

function uid() { return 'rtl_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 4); }

// ── Keyword → Agent capability map ────────────────────────────
const ROUTING_RULES = [
  {
    agent_id:  'data_harvester',
    keywords:  ['pull', 'fetch', 'sync', 'collect', 'harvest', 'refresh data', 'update analytics', 'scrape'],
    examples:  ['pull latest IG analytics', 'sync GA4 data', 'fetch Reddit trends'],
    weight:    'primary',
  },
  {
    agent_id:  'hook_smith',
    keywords:  ['hook', 'caption', 'angle', 'headline', 'copy', 'write post', 'create hook'],
    examples:  ['generate new hooks', 'write caption for post', 'what hooks work best'],
    weight:    'primary',
  },
  {
    agent_id:  'insight_analyst',
    keywords:  ['insight', 'analyse', 'analyze', 'pattern', 'trend', 'missed', 'opportunity', 'anomaly', 'leak', 'funnel', 'attribution'],
    examples:  ['what anomalies this week', 'missed opportunities', 'funnel leak analysis'],
    weight:    'primary',
  },
  {
    agent_id:  'taskmaster',
    keywords:  ['plan', 'task', 'schedule', 'post', 'queue', 'deadline', 'blocker', 'approve', 'approval', 'capacity', 'workload', 'experiment'],
    examples:  ['what should post today', 'schedule this post', 'approve caption', 'who is overloaded'],
    weight:    'primary',
  },
  {
    agent_id:  'nudge_bot',
    keywords:  ['nudge', 'remind', 'follow up', 'follow-up', 'chase', 'reminder', 'send message', 'discord'],
    examples:  ['nudge Coach Cat', 'send reminder', 'chase for asset'],
    weight:    'primary',
  },
  {
    agent_id:  'idea_generator',
    keywords:  ['idea', 'content', 'topic', 'what to post', 'content plan', 'youtube'],
    examples:  ['give me content ideas', 'what should we post this week'],
    weight:    'primary',
  },
  {
    agent_id:  'cta_analyst',
    keywords:  ['cta', 'call to action', 'conversion', 'click', 'button'],
    examples:  ['which CTA performs best', 'optimise CTAs'],
    weight:    'primary',
  },
  {
    agent_id:  'pulse_keeper',
    keywords:  ['health', 'status', 'pipeline', 'dashboard', 'uptime', 'broken', 'failed', 'error', 'system'],
    examples:  ['is the dashboard healthy', 'check pipeline status', 'what failed'],
    weight:    'primary',
  },
  {
    agent_id:  'memory_keeper',
    keywords:  ['remember', 'memory', 'what did we', 'history', 'past', 'previously', 'campaign', 'bug'],
    examples:  ['remember what hooks worked', 'what was the bug last week'],
    weight:    'primary',
  },
  {
    agent_id:  'content_architect',
    keywords:  ['format', 'render', 'image', 'asset', 'video', 'reel', 'carousel', 'story'],
    examples:  ['turn this hook into a reel', 'create the image for this post'],
    weight:    'fallback',
  },
];

// ── Score a task against a rule ────────────────────────────────
function scoreTask(taskText, rule) {
  const text = taskText.toLowerCase();
  let score = 0;
  const matched = [];
  for (const kw of rule.keywords) {
    if (text.includes(kw)) {
      score += kw.length; // longer keyword match = stronger
      matched.push(kw);
    }
  }
  return { score, matched };
}

// ── Route a task ───────────────────────────────────────────────
function routeTask(taskText) {
  const results = [];

  for (const rule of ROUTING_RULES) {
    const { score, matched } = scoreTask(taskText, rule);
    if (score > 0) {
      results.push({
        agent_id: rule.agent_id,
        score,
        matched_keywords: matched,
        weight: rule.weight,
        examples: rule.examples,
      });
    }
  }

  // Sort by score descending, then primary before fallback
  results.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.weight === 'primary' ? -1 : 1;
  });

  const primary   = results.find(r => r.weight === 'primary');
  const secondary = results.find(r => r.weight === 'fallback');

  return {
    task:        taskText,
    routed_to:   primary ? primary.agent_id : (secondary ? secondary.agent_id : 'unknown'),
    confidence:  primary ? Math.min(10, Math.round((primary.score / 20) * 10)) : 3,
    alternatives: results.slice(1, 4),
    routed_at:   new Date().toISOString(),
    routing_type: 'deterministic_keyword_v1',
  };
}

// ── Load registry for agent details ────────────────────────────
function getAgentDetails(agentId) {
  const reg = JSON.parse(fs.readFileSync(path.join(BASE, 'agents/registry.json'), 'utf8'));
  const a = (reg.agents || []).find(a => a.agent_id === agentId);
  return a ? { name: a.name, role: a.role, owns: a.owns, scripts: a.scripts, discord_channel: a.discord_channel } : null;
}

// ── Main ───────────────────────────────────────────────────────
const args = process.argv.slice(2);
if (args.length === 0) {
  console.log('Usage: node route_task.js "your task description"');
  console.log('       node route_task.js --status   # show routing status');
  process.exit(0);
}

if (args[0] === '--status') {
  const reg = JSON.parse(fs.readFileSync(path.join(BASE, 'agents/registry.json'), 'utf8'));
  console.log('Task Router v1 — registered agents:\n');
  (reg.agents || []).forEach(a => {
    console.log(`  ${a.agent_id} (${a.layer}): ${a.role}`);
  });
  process.exit(0);
}

const taskText = args.join(' ');
const result = routeTask(taskText);
const agent   = getAgentDetails(result.routed_to);

const output = {
  schema:    'https://clawdia.io/agents/output-schema/v1',
  agent_id:  'route_task',
  generated: new Date().toISOString(),
  status:    'PASS',
  data_status: 'FRESH',
  confidence: result.confidence,
  priority:  result.confidence >= 8 ? 'HIGH' : result.confidence >= 5 ? 'MEDIUM' : 'LOW',
  owner:     result.routed_to,
  next_action: agent ? `Route to ${agent.name} — see agents/registry.json` : 'Manual routing required',
  notes:     [],
  qa_warnings: result.confidence < 5 ? ['Low confidence — verify routing manually'] : [],
  route_id:  uid(),
  ...result,
  assigned_agent: agent,
};

// Append to routing log
const routeLogFile = path.join(BASE, 'data', 'routing-log.json');
let routeLog = { updated: new Date().toISOString(), queries: [], routes: [] };
try { const existing = JSON.parse(fs.readFileSync(routeLogFile, 'utf8')); routeLog = existing; } catch {}
routeLog.routes.push({
  route_id: output.route_id,
  task: output.task,
  routed_to: output.routed_to,
  confidence: output.confidence,
  alternatives: output.alternatives.map(a => a.agent_id),
  routed_at: output.routed_at,
  success: null, // filled when outcome known
});
routeLog.updated = new Date().toISOString();
routeLog.queries_count = (routeLog.queries?.length || 0) + (routeLog.routes?.length || 0);
fs.writeFileSync(routeLogFile, JSON.stringify(routeLog, null, 2));
fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));

console.log(`\n🎯 Task Router v1 — deterministic routing`);
console.log(`   Task: "${taskText.substring(0, 60)}${taskText.length > 60 ? '...' : ''}"`);
console.log(`   Routed to: ${result.routed_to} (confidence: ${result.confidence}/10)`);
if (agent) console.log(`   Role: ${agent.role}`);
if (result.alternatives.length > 0) console.log(`   Also considered: ${result.alternatives.map(a => a.agent_id).join(', ')}`);
console.log(`   Routed at: ${result.routed_at}`);
console.log(`\n✅ Route logged: ${OUTPUT}`);
