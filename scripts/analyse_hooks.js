#!/usr/bin/env node
/**
 * analyse_hooks.js
 * Reads IG analytics → generates hook bank with scores and formulas
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUT_FILE = path.join(DATA_DIR, 'hook-bank.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch(e) { return {}; }
}

function scoreHook(post) {
  const eng = parseFloat(post.engagementRate) || 0;
  const saves = parseFloat(post.saveRate) || 0;
  const shares = parseFloat(post.shareRate) || 0;
  const reach = parseInt(post.reach || 0);
  
  // Score: weighted combination, capped at 10
  const raw = (eng * 2) + (saves * 3) + (shares * 5) + Math.min(reach / 100, 3);
  return Math.min(10, Math.max(0, raw));
}

function extractFormula(hookText) {
  if (!hookText) return 'unknown';
  // Categorise by structure
  if (hookText.match(/YOUR|THIS IS|THE/i)) return 'stat-demand'; // "YOUR DRIVE: 199M"
  if (hookText.match(/\?|WHAT IF/i)) return 'question';
  if (hookText.match(/slice|hook|problem|fix|wrong/i)) return 'pain-point';
  if (hookText.match(/pros average|trackman shows/i)) return 'proof-led';
  if (hookText.match(/from r\d/i)) return 'price-led';
  return 'general';
}

function run() {
  const ig = readJson('ig-analytics.json');
  const ab = readJson('ab-tests.json');
  
  const posts = ig.posts || [];
  
  // Score every post's hook
  const scored = posts.map(p => ({
    hook_text: p.hook_text || p.captionPreview || 'unknown',
    hook_id: p.hook_id || (p.hook_text || '').toLowerCase().replace(/[^a-z0-9]/g, '-').substring(0, 50),
    score: scoreHook(p),
    engagementRate: p.engagementRate || '0',
    saveRate: p.saveRate || '0',
    shareRate: p.shareRate || '0',
    reach: p.reach || 0,
    topic_cluster: p.topic_cluster || 'general',
    format_type: p.format_type || 'static',
    formula_type: extractFormula(p.hook_text),
    post_id: p.postId || p.id,
  })).sort((a, b) => b.score - a.score);
  
  // Proven hooks (score >= 4)
  const proven = scored.filter(h => h.score >= 4);
  
  // Fresh to test (score 2-4)
  const fresh = scored.filter(h => h.score >= 2 && h.score < 4).slice(0, 8);
  
  // Hook formulas by category
  const formulaBuckets = {};
  scored.forEach(h => {
    const f = h.formula_type;
    if (!formulaBuckets[f]) formulaBuckets[f] = [];
    formulaBuckets[f].push(h);
  });
  
  const result = {
    updated: new Date().toISOString(),
    total_hooks: scored.length,
    proven_hooks: proven,
    fresh_hooks_to_test: fresh,
    weak_hooks: scored.filter(h => h.score < 2),
    hooks_by_goal: {
      reach: scored.sort((a, b) => b.reach - a.reach).slice(0, 5),
      saves: scored.sort((a, b) => parseFloat(b.saveRate) - parseFloat(a.saveRate)).slice(0, 5),
      engagement: proven.slice(0, 5),
      equipment: scored.filter(h => h.topic_cluster === 'equipment').slice(0, 5),
      coaching: scored.filter(h => h.topic_cluster === 'coaching').slice(0, 5),
      technique: scored.filter(h => h.topic_cluster === 'technique').slice(0, 5),
    },
    hook_formulas: Object.entries(formulaBuckets).map(([formula, hooks]) => ({
      formula,
      count: hooks.length,
      best_example: hooks[0]?.hook_text || '',
      avg_score: (hooks.reduce((s, h) => s + h.score, 0) / hooks.length).toFixed(1),
    })),
    ab_winners: (ab.tests || []).filter(t => t.winner).map(t => ({
      name: t.name,
      winner: t.winner,
      eng: t.engagement || t.engagementRate || '?',
      next_action: t.next_action || 'reuse formula',
    })),
  };
  
  fs.writeFileSync(OUT_FILE, JSON.stringify(result, null, 2));
  console.log(`✅ Hook bank: ${proven.length} proven, ${fresh.length} fresh, ${scored.length} total`);
  return result;
}

run();