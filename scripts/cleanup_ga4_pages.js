#!/usr/bin/env node
/**
 * cleanup_ga4_pages.js — one-shot normaliser for cached data/ga4-metrics.json.
 *
 * The fetcher (fetch_ga4.js) historically emitted topPages by taking the first
 * 10 RAW rows from a (pagePath, sessionSource) GA4 query — so the homepage
 * appeared 5+ times with different engagement rates. This script re-runs the
 * same aggregation logic against the cached file so the fix is visible
 * immediately (no need to wait for the next cron).
 *
 * Idempotent: running twice on an already-aggregated file is a no-op.
 */
const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, '..', 'data', 'ga4-metrics.json');
const d = JSON.parse(fs.readFileSync(FILE, 'utf8'));
const oldPages = d.pages || [];

// Detect whether already aggregated (all unique paths).
const uniquePaths = new Set(oldPages.map(p => p.path));
if (uniquePaths.size === oldPages.length) {
  console.log(`ga4-metrics.json: ${oldPages.length} unique pages already — nothing to do`);
  process.exit(0);
}

console.log(`ga4-metrics.json: ${oldPages.length} pages with ${oldPages.length - uniquePaths.size} duplicates — normalising`);

// We don't have per-source rows in the cached file, so we can only dedupe
// sessions-and-rates in the naive "sum sessions, average engagement rate as
// arithmetic mean of the displayed strings" way. This is a stopgap until the
// next cron re-runs fetch_ga4.js (which now does session-weighted aggregation
// from the real GA4 rows). Document the limitation in the output.
const parseEr = s => {
  if (s == null) return 0;
  const v = parseFloat(String(s).replace('%',''));
  return isNaN(v) ? 0 : v;
};

const byPath = {};
oldPages.forEach(p => {
  const cur = byPath[p.path] || { sessions: 0, erSum: 0, n: 0 };
  cur.sessions += (p.sessions || 0);
  cur.erSum += parseEr(p.engRate);
  cur.n += 1;
  byPath[p.path] = cur;
});

const aggregated = Object.entries(byPath)
  .map(([p, v]) => ({
    path: p,
    sessions: v.sessions,
    engRate: (v.erSum / v.n).toFixed(1) + '%',
  }))
  .sort((a, b) => b.sessions - a.sessions);

d.pages = aggregated.slice(0, 10);

// Also normalise the weak_cta recommendation if it references duplicate paths.
if (Array.isArray(d.insights?.recommendations)) {
  d.insights.recommendations.forEach(r => {
    if (r.type === 'weak_cta' && Array.isArray(r.pages)) {
      r.pages = [...new Set(r.pages)];
    }
  });
}

fs.writeFileSync(FILE, JSON.stringify(d, null, 2));
console.log(`ga4-metrics.json: now ${aggregated.length} unique paths`);
aggregated.forEach(p => console.log(`  ${String(p.sessions).padStart(4)} sessions · ${p.engRate.padStart(6)} · ${p.path}`));
