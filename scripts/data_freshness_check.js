#!/usr/bin/env node
// data_freshness_check.js — sweep data/*.json for stale entries.
//
// Walks every JSON file under the workspace's data/ directory, inspects any
// timestamp-like fields we know about (generated / lastUpdated / last_run /
// ts / date / saved_at / published_at / posted_at / polled / fetched_at),
// and writes data/freshness.json: a per-file + per-kind summary that surfaces
// where the OS depends on something that hasn't been refreshed lately.
//
// Heuristic: a file is "stale" if its newest timestamp field is older than
// STALE_DAYS (default 14). A file with no timestamp fields is treated as
// "static config" (always considered fresh).
//
// Cron: daily 07:30 SAST (after all data crons).

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(ROOT, 'data');
const OUT = path.join(DATA_DIR, 'freshness.json');
const STALE_DAYS = parseInt(process.env.STALE_DAYS || '14', 10);
const TS_KEYS = new Set([
  'generated', 'lastUpdated', 'last_run', 'last_run_at', 'last_check',
  'ts', 'date', 'saved_at', 'published_at', 'posted_at', 'polled',
  'fetched_at', 'updated_at', 'created_at', 'scanned_at', 'synced_at',
  'checked_at', 'detected_at', 'analyzed_at', 'snapshot_at',
]);
// Conventional filenames whose absence of TS doesn't mean stale — they get
// rewritten in place by the writers.
const LIVE_FILES = new Set(['freshness.json', 'meta-auth-health.json']);

function walkJSON(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    let st;
    try { st = fs.statSync(p); } catch { continue; }
    if (st.isDirectory()) { walkJSON(p, out); continue; }
    if (!st.isFile()) continue;
    if (name.endsWith('.json')) out.push(p);
  }
  return out;
}

// Find any timestamp-ish string/number in the object, by DFS.
function findTimestamps(node, hits = []) {
  if (hits.length > 50) return hits;
  if (Array.isArray(node)) {
    for (const v of node) findTimestamps(v, hits);
  } else if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node)) {
      if (TS_KEYS.has(k) && (typeof v === 'string' || typeof v === 'number')) {
        hits.push({ key: k, value: v, path: k });
      }
      if (v && (typeof v === 'object')) findTimestamps(v, hits);
    }
  }
  return hits;
}

// Sanity range: any timestamp outside this window is treated as junk and
// skipped, not classified. Date.parse() happily accepts strings like
// "Apr 22" and returns 2001-04-21, which then produces age_days=9238
// and a spurious "🚨 N files > 42 days" banner on Home. Cap the window
// generously (2010 → current_year+1) so we still capture real cron data
// from 2010+ projects while filtering content-only date labels.
function _inSaneRange(dt) {
  if (!dt || Number.isNaN(dt.getTime())) return false;
  const yr = dt.getUTCFullYear();
  return yr >= 2010 && yr <= new Date().getUTCFullYear() + 1;
}

function parseTs(v) {
  if (typeof v === 'number') {
    // Seconds vs ms — phone home by magnitude
    const ms = v > 1e11 ? v : (v > 1e9 ? v * 1000 : null);
    const dt = ms ? new Date(ms) : null;
    return _inSaneRange(dt) ? dt : null;
  }
  if (typeof v !== 'string') return null;
  const s = v.trim();
  // yyyy-mm-dd only — already includes year, so always sane after 2010
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const dt = new Date(s + 'T00:00:00Z');
    return _inSaneRange(dt) ? dt : null;
  }
  // ISO 8601 with explicit year — Date.parse is fine here
  if (/^\d{4}-/.test(s)) {
    const iso = Date.parse(s);
    const dt = Number.isNaN(iso) ? null : new Date(iso);
    return _inSaneRange(dt) ? dt : null;
  }
  // English dates with explicit year like "Apr 22, 2026" — Date.parse
  // handles these and returns the right year, then sanity-check catches
  // bad ones. Bare strings like "Apr 22" without any year fall through
  // and return null (they parse to 2001 in JS — junk).
  const iso = Date.parse(s);
  const dt = Number.isNaN(iso) ? null : new Date(iso);
  return _inSaneRange(dt) ? dt : null;
}

function classify(filePath, parsed) {
  const stat = fs.statSync(filePath);
  const mt = new Date(stat.mtimeMs);
  if (!parsed || typeof parsed !== 'object') {
    return { newest_ts: null, mtime: mt.toISOString(), staleness: 'unknown' };
  }
  const hits = findTimestamps(parsed);
  if (hits.length === 0) {
    return { newest_ts: null, mtime: mt.toISOString(), staleness: 'static' };
  }
  let newest = null;
  let newestRaw = null;
  for (const h of hits) {
    const dt = parseTs(h.value);
    if (dt && (!newest || dt > newest)) {
      newest = dt;
      newestRaw = h.value;
    }
  }
  if (!newest) {
    return { newest_ts: null, mtime: mt.toISOString(), staleness: 'unknown' };
  }
  const ageDays = (Date.now() - newest.getTime()) / 86400000;
  let staleness = 'fresh';
  if (ageDays > STALE_DAYS * 3) staleness = 'rotten';
  else if (ageDays > STALE_DAYS) staleness = 'stale';
  return { newest_ts: newest.toISOString(), newest_raw: newestRaw, age_days: Math.round(ageDays * 10) / 10, staleness, mtime: mt.toISOString() };
}

function main() {
  if (!fs.existsSync(DATA_DIR)) { console.error('No data dir at', DATA_DIR); process.exit(1); }
  const files = walkJSON(DATA_DIR);
  const summary = {
    generated: new Date().toISOString(),
    stale_days_threshold: STALE_DAYS,
    total_files: files.length,
    by_staleness: { fresh: 0, stale: 0, rotten: 0, unknown: 0, static: 0 },
    files: [],
    stale_files: [],
    rotten_files: [],
  };
  for (const fp of files) {
    const rel = path.relative(ROOT, fp);
    const base = path.basename(fp);
    if (base === 'freshness.json') continue; // skip self
    let parsed = null;
    try { parsed = JSON.parse(fs.readFileSync(fp, 'utf8')); }
    catch { /* leave null */ }
    const c = classify(fp, parsed);
    summary.files.push({ path: rel, ...c });
    summary.by_staleness[c.staleness] = (summary.by_staleness[c.staleness] || 0) + 1;
    if (c.staleness === 'stale') summary.stale_files.push({ path: rel, age_days: c.age_days, newest_ts: c.newest_ts });
    if (c.staleness === 'rotten') summary.rotten_files.push({ path: rel, age_days: c.age_days, newest_ts: c.newest_ts });
  }
  // Sort lists newest→oldest for readability
  summary.stale_files.sort((a, b) => b.age_days - a.age_days);
  summary.rotten_files.sort((a, b) => b.age_days - a.age_days);
  // Alphabetise by path for stable diff
  summary.files.sort((a, b) => a.path.localeCompare(b.path));

  fs.writeFileSync(OUT, JSON.stringify({
    // Summary (small — what the OS UI shows on Home)
    generated: new Date().toISOString(),
    stale_days_threshold: STALE_DAYS,
    total_files: files.length,
    by_staleness: summary.by_staleness,
    stale_files: summary.stale_files,
    rotten_files: summary.rotten_files,
    // Full per-file list lives in data/freshness-detail.json (intentionally
    // not gitignored: it's small once rotten/stale are removed, and lets
    // `git log -p` show what changed overnight).
  }, null, 2));

  // Also dump per-file breakdown (used by ad-hoc debugging, not the OS UI).
  const DETAIL = path.join(DATA_DIR, 'freshness-detail.json');
  fs.writeFileSync(DETAIL, JSON.stringify({ generated: new Date().toISOString(), files: summary.files }, null, 2));
  console.log(`✅ freshness: scanned ${files.length} files`);
  console.log(`   fresh=${summary.by_staleness.fresh || 0} stale=${summary.by_staleness.stale || 0} rotten=${summary.by_staleness.rotten || 0} static=${summary.by_staleness.static || 0} unknown=${summary.by_staleness.unknown || 0}`);
  if (summary.rotten_files.length > 0) {
    console.log('   TOP ROTTEN:');
    summary.rotten_files.slice(0, 8).forEach(f => console.log('     -', f.path, `(${f.age_days}d)`));
  }
}

main();
