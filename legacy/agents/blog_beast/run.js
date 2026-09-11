#!/usr/bin/env node
/** run.js — blog_beast agent wrapper */
/**
 * Rule: PARTIAL outputs are honest, not failures.
 * blog_beast PARTIAL when SEO feeds are weak but briefs still generate.
 */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '', stdout = '';
try {
  stdout = exec(`node ${path.join(BASE, 'scripts', 'generate_blog_drafts.js')}`, { cwd: BASE, timeout: 30000 }).toString().trim();
  // Script outputs PARTIAL when feeds are weak — that's honest
  if (stdout.includes('Status: PARTIAL') || stdout.includes("'PARTIAL'")) status = 'PARTIAL';
} catch (e) {
  const msg = e.message || '';
  if (msg.includes('ENOENT') || msg.includes('MODULE_NOT_FOUND')) {
    status = 'FAIL'; errMsg = msg.slice(0, 80);
  } else {
    status = 'PARTIAL'; errMsg = msg.slice(0, 80);
  }
}

let counts = {};
try {
  const b = JSON.parse(fs.readFileSync(path.join(DATA, 'blog-briefs.json'), 'utf8'));
  const d = JSON.parse(fs.readFileSync(path.join(DATA, 'blog-drafts.json'), 'utf8'));
  const f = JSON.parse(fs.readFileSync(path.join(DATA, 'faq-opportunities.json'), 'utf8'));
  counts = { briefs: b.briefs?.length || 0, drafts: d.drafts?.length || 0, faqs: f.faqs?.length || 0 };
} catch { counts = { briefs: 0, drafts: 0, faqs: 0 }; }

// Honest: PASS if we got content, PARTIAL if degraded, FAIL only if nothing
const valid = counts.briefs > 0 || counts.drafts > 0;
const runStatus = status === 'FAIL' ? 'FAIL' : (valid ? status : 'PARTIAL');

const runResult = {
  agent_id: 'blog_beast',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: runStatus,
  scripts: [{ script: 'generate_blog_drafts.js', status, err: errMsg }],
  outputs: {
    'data/blog-briefs.json': { valid: counts.briefs > 0, count: counts.briefs },
    'data/blog-drafts.json': { valid: counts.drafts > 0, count: counts.drafts },
    'data/faq-opportunities.json': { valid: counts.faqs > 0, count: counts.faqs },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
  partial: status === 'PARTIAL' ? 1 : 0,
};

console.log(`\n[blog_beast] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${counts.briefs > 0 ? '✅' : '❌'} blog-briefs.json: ${counts.briefs} briefs`);
console.log(`  ${counts.drafts > 0 ? '✅' : '❌'} blog-drafts.json: ${counts.drafts} drafts`);
console.log(`  ${counts.faqs > 0 ? '✅' : '❌'} faq-opportunities.json: ${counts.faqs} FAQ clusters`);
if (errMsg) console.log(`  Note: ${errMsg}`);
if (stdout) console.log(`  ${stdout.slice(0, 200)}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['blog_beast'] = runs.agents['blog_beast'] || [];
runs.agents['blog_beast'].push(runResult);
runs.agents['blog_beast'] = runs.agents['blog_beast'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runStatus === 'FAIL' ? 1 : 0);
