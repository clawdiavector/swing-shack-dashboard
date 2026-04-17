#!/usr/bin/env node
/**
 * generate_owner_workload.js
 * Aggregates workload by owner from post-plan + follow-up-queue + missed-opportunities
 * Outputs: data/owner-workload.json
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUTPUT   = path.join(DATA_DIR, 'owner-workload.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch { return null; }
}

const postPlan  = readJson('post-plan.json')        || {};
const followUpQ = readJson('follow-up-queue.json')  || {};
const missed    = readJson('missed-opportunities.json') || {};

function urgencyRank(u) {
  return u === 'today' ? 0 : u === 'this_week' ? 1 : 2;
}

// ── Build per-owner item list ────────────────────────────────────
const ownerItems = {};

function addItem(owner, item) {
  if (!owner || owner === 'undefined') return;
  if (!ownerItems[owner]) {
    ownerItems[owner] = {
      owner,
      items: [],
      by_urgency: { today: 0, this_week: 0, flexible: 0 },
      by_source:   { post_plan: 0, follow_up_queue: 0, missed_opportunity: 0 },
      total: 0,
    };
  }
  ownerItems[owner].items.push(item);
  ownerItems[owner].total++;
  if (item.urgency === 'today')     ownerItems[owner].by_urgency.today++;
  if (item.urgency === 'this_week') ownerItems[owner].by_urgency.this_week++;
  if (item.urgency === 'flexible')  ownerItems[owner].by_urgency.flexible++;
  ownerItems[owner].by_source[item.source] = (ownerItems[owner].by_source[item.source] || 0) + 1;
}

// From post plan
(postPlan.plan || []).forEach(p => {
  if (!p.owner || !p.hook) return;
  addItem(p.owner, {
    source:      'post_plan',
    urgency:    p.urgency,
    hook:       p.hook ? p.hook.substring(0, 60) : null,
    cta:        p.cta,
    day:        `${p.day} ${p.date}`,
    objective:  p.objective,
    format:     p.format,
    topics:     p.topics,
  });
});

// From follow-up queue
(followUpQ.queue || []).forEach(q => {
  if (!q.owner) return;
  addItem(q.owner, {
    source:      'follow_up_queue',
    urgency:    q.urgency,
    hook:       q.suggested_hook ? q.suggested_hook.substring(0, 60) : null,
    original_hook: q.original_hook ? q.original_hook.substring(0, 60) : null,
    cta:        q.suggested_cta,
    topic:      q.topic,
    angle:      q.angle,
    reason_blocked: q.reason_blocked,
    already_planned: q.already_planned,
  });
});

// From missed opportunities (high severity only)
(missed.opportunities || [])
  .filter(o => o.severity === 'high' && o.owner && o.owner !== 'Swing Shack page')
  .forEach(o => {
    addItem(o.owner, {
      source:       'missed_opportunity',
      urgency:      o.severity === 'high' ? 'this_week' : 'flexible',
      topic:        o.topic || o.keyword || null,
      hook:         o.hook ? o.hook.substring(0, 60) : null,
      suggested_fix: o.suggested_fix,
      category:     o.category,
    });
  });

// ── Sort items within each owner by urgency ────────────────────
Object.values(ownerItems).forEach(ow => {
  ow.items.sort((a, b) => urgencyRank(a.urgency) - urgencyRank(b.urgency));
});

// Sort owners: most items first, then by today count
const sorted = Object.values(ownerItems).sort((a, b) => {
  if (b.by_urgency.today !== a.by_urgency.today) return b.by_urgency.today - a.by_urgency.today;
  return b.total - a.total;
});

// ── Summary ──────────────────────────────────────────────────────
const summary = {
  total_owners:   sorted.length,
  total_items:    sorted.reduce((s, o) => s + o.total, 0),
  today_total:     sorted.reduce((s, o) => s + o.by_urgency.today, 0),
  this_week_total: sorted.reduce((s, o) => s + o.by_urgency.this_week, 0),
  most_loaded:     sorted[0]?.owner || 'n/a',
  most_loaded_count: sorted[0]?.total || 0,
};

// ── Write output ─────────────────────────────────────────────────
const output = {
  updated:   new Date().toISOString(),
  generated: 'generate_owner_workload.js',
  ...summary,
  owners: sorted,
};

fs.writeFileSync(OUTPUT, JSON.stringify(output, null, 2));
console.log(`✅ Owner workload generated: ${OUTPUT}`);
console.log(`   Owners: ${sorted.length} | Total items: ${summary.total_items} | Today: ${summary.today_total} | This week: ${summary.this_week_total}`);
console.log(`   Most loaded: ${summary.most_loaded} (${summary.most_loaded_count} items)`);
sorted.forEach(ow => {
  const today = ow.by_urgency.today;
  const thisW = ow.by_urgency.this_week;
  console.log(`   ${ow.owner}: ${ow.total} items (today:${today} this_week:${thisW} flexible:${ow.by_urgency.flexible})`);
  ow.items.slice(0, 2).forEach(item => {
    console.log(`     → [${item.urgency}] ${item.hook?.substring(0, 50) || item.topic || '—'}`);
  });
});
