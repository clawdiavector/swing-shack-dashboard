#!/usr/bin/env node
/**
 * retrieve_memory.js
 * Memory Castle — deterministic retrieval by keyword/tag/date/type.
 * No semantic genius — just useful filtering and sorting.
 *
 * Usage:
 *   node retrieve_memory.js --all                   # show all
 *   node retrieve_memory.js --recent 10             # 10 most recent
 *   node retrieve_memory.js --type win              # wins only
 *   node retrieve_memory.js --tag hook              # by tag
 *   node retrieve_memory.js --keyword slice          # in summary
 *   node retrieve_memory.js --agent insight_analyst
 *   node retrieve_memory.js --date 2026-04-17       # specific date
 *   node retrieve_memory.js --importance 8          # min importance
 *   node retrieve_memory.js --limit 5
 */
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const MEM  = path.join(BASE, 'memory');

function readMem(name) {
  try { return JSON.parse(fs.readFileSync(path.join(MEM, name), 'utf8')); }
  catch { return null; }
}

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(BASE, 'data', name), 'utf8')); }
  catch { return null; }
}

// ── Collect all memory entries ─────────────────────────────────
function collectAll() {
  const entries = [];
  const subdirs = ['daily', 'wins', 'losses', 'bugs', 'campaigns', 'hooks', 'tasks', 'learnings'];
  for (const sub of subdirs) {
    const dir = path.join(MEM, sub);
    if (!fs.existsSync(dir)) continue;
    for (const file of fs.readdirSync(dir)) {
      if (!file.endsWith('.json')) continue;
      const entry = readMem(path.join(sub, file));
      if (entry) entries.push(entry);
    }
  }
  return entries;
}

function scoreRelevance(entry, keyword) {
  if (!keyword) return 1;
  const k = keyword.toLowerCase();
  let score = 0;
  if (entry.summary?.toLowerCase().includes(k)) score += 3;
  if (entry.content?.hook?.toLowerCase().includes(k)) score += 2;
  if (entry.tags?.some(t => t.toLowerCase().includes(k))) score += 2;
  if (entry.type?.toLowerCase().includes(k)) score += 1;
  if (entry.source_agent?.toLowerCase().includes(k)) score += 1;
  return score;
}

// ── Main filter ────────────────────────────────────────────────
function retrieve(opts = {}) {
  let entries = collectAll();

  if (opts.type) {
    entries = entries.filter(e => e.type === opts.type);
  }
  if (opts.tag) {
    const t = opts.tag.toLowerCase();
    entries = entries.filter(e => e.tags?.some(g => g.toLowerCase().includes(t)));
  }
  if (opts.keyword) {
    entries = entries.filter(e => scoreRelevance(e, opts.keyword) > 0);
    entries.forEach(e => { e._relevance = scoreRelevance(e, opts.keyword); });
  }
  if (opts.agent) {
    entries = entries.filter(e => e.source_agent === opts.agent);
  }
  if (opts.date) {
    entries = entries.filter(e => e.date === opts.date);
  }
  if (opts.minImportance != null) {
    entries = entries.filter(e => (e.importance || 0) >= opts.minImportance);
  }
  if (opts.days) {
    const cutoff = new Date(Date.now() - opts.days * 86400000).toISOString().split('T')[0];
    entries = entries.filter(e => e.date >= cutoff);
  }

  // Sort: relevance first (if keyword), then importance desc, then date desc
  entries.sort((a, b) => {
    if (opts.keyword) {
      if ((b._relevance || 0) !== (a._relevance || 0)) return (b._relevance || 0) - (a._relevance || 0);
    }
    if ((b.importance || 0) !== (a.importance || 0)) return (b.importance || 0) - (a.importance || 0);
    return (b.date || '').localeCompare(a.date || '');
  });

  if (opts.limit) entries = entries.slice(0, opts.limit);

  return entries;
}

// ── CLI ────────────────────────────────────────────────────────
const args = process.argv.slice(2);
if (args.length === 0 || args[0] === '--help') {
  console.log(`\nMemory Castle Retrieval`);
  console.log(`Usage:`);
  console.log(`  node retrieve_memory.js --all`);
  console.log(`  node retrieve_memory.js --recent 10`);
  console.log(`  node retrieve_memory.js --type win`);
  console.log(`  node retrieve_memory.js --tag hook`);
  console.log(`  node retrieve_memory.js --keyword slice`);
  console.log(`  node retrieve_memory.js --agent insight_analyst`);
  console.log(`  node retrieve_memory.js --days 7`);
  console.log(`  node retrieve_memory.js --importance 8`);
  console.log(`  node retrieve_memory.js --limit 5\n`);
  process.exit(0);
}

const opts = {
  type:         args.includes('--type')         ? args[args.indexOf('--type') + 1]         : null,
  tag:          args.includes('--tag')          ? args[args.indexOf('--tag') + 1]          : null,
  keyword:      args.includes('--keyword')      ? args[args.indexOf('--keyword') + 1]       : null,
  agent:        args.includes('--agent')        ? args[args.indexOf('--agent') + 1]         : null,
  date:         args.includes('--date')         ? args[args.indexOf('--date') + 1]          : null,
  days:         args.includes('--days')         ? parseInt(args[args.indexOf('--days') + 1]) : null,
  minImportance: args.includes('--importance') ? parseInt(args[args.indexOf('--importance') + 1]) : null,
  limit:        args.includes('--limit')        ? parseInt(args[args.indexOf('--limit') + 1])  : null,
  recent:       args.includes('--recent')       ? parseInt(args[args.indexOf('--recent') + 1]) : null,
  all:          args.includes('--all'),
};

if (opts.recent) { opts.limit = opts.recent; opts.days = opts.days || 30; }

// Default: last 7 days, top 10
if (opts.all || Object.keys(opts).filter(k => opts[k] && k !== 'limit').length === 0) {
  opts.days = 7; opts.limit = 10;
}

const results = retrieve(opts);

console.log(`\n🧠 Memory Castle — ${results.length} result${results.length !== 1 ? 's' : ''}`);
if (opts.keyword)   console.log(`   Keyword: "${opts.keyword}"`);
if (opts.type)      console.log(`   Type: ${opts.type}`);
if (opts.tag)       console.log(`   Tag: ${opts.tag}`);
if (opts.agent)     console.log(`   Agent: ${opts.agent}`);
if (opts.days)      console.log(`   Period: last ${opts.days} days`);
console.log('');

results.forEach((e, i) => {
  console.log(`${i + 1}. [${e.type?.toUpperCase()}] ${e.date} | imp:${e.importance} | ${e.source_agent}`);
  console.log(`   ${e.summary?.substring(0, 80)}${e.summary?.length > 80 ? '...' : ''}`);
  if (e.content?.hook)      console.log(`   Hook: ${e.content.hook.substring(0, 60)}`);
  if (e.content?.what_to_repeat?.length) console.log(`   Repeat: ${e.content.what_to_repeat[0].substring(0, 60)}`);
  if (e.content?.what_to_stop?.length)    console.log(`   Stop: ${e.content.what_to_stop[0].substring(0, 60)}`);
  if (e.next_use) console.log(`   → ${e.next_use}`);
  console.log('');
});

// Also update routing log if keyword was provided
if (opts.keyword && results.length > 0) {
  const routeLog = readJson('route-log.json') || { queries: [] };
  routeLog.queries.push({
    query: opts.keyword,
    results_count: results.length,
    top_result: results[0].summary?.substring(0, 80),
    retrieved_at: new Date().toISOString(),
  });
  fs.writeFileSync(path.join(BASE, 'data', 'route-log.json'), JSON.stringify(routeLog, null, 2));
}
