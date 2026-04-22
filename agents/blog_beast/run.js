#!/usr/bin/env node
/** run.js — blog_beast agent wrapper */
const { execSync: exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BASE = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const DATA = path.join(BASE, 'data');

const start = Date.now();
let status = 'PASS', errMsg = '';
try {
  exec(`node ${path.join(BASE, 'scripts', 'generate_blog_drafts.js')}`, { cwd: BASE, timeout: 30000 });
} catch (e) { status = 'FAIL'; errMsg = e.message.slice(0, 80); }

let counts = {};
try {
  const b = JSON.parse(fs.readFileSync(path.join(DATA, 'blog-briefs.json'), 'utf8'));
  const d = JSON.parse(fs.readFileSync(path.join(DATA, 'blog-drafts.json'), 'utf8'));
  const f = JSON.parse(fs.readFileSync(path.join(DATA, 'faq-opportunities.json'), 'utf8'));
  counts = { briefs: b.briefs?.length || 0, drafts: d.drafts?.length || 0, faqs: f.faqs?.length || 0 };
} catch { counts = { briefs: 0, drafts: 0, faqs: 0 }; }

const valid = counts.briefs > 0;
const runResult = {
  agent_id: 'blog_beast',
  run_at: new Date().toISOString(),
  duration_ms: Date.now() - start,
  status: valid ? 'PASS' : 'PARTIAL',
  scripts: [{ script: 'generate_blog_drafts.js', status, err: errMsg }],
  outputs: {
    'data/blog-briefs.json': { valid: counts.briefs > 0, count: counts.briefs },
    'data/blog-drafts.json': { valid: counts.drafts > 0, count: counts.drafts },
    'data/faq-opportunities.json': { valid: counts.faqs > 0, count: counts.faqs },
  },
  passed: status === 'PASS' ? 1 : 0,
  failed: status === 'FAIL' ? 1 : 0,
};

console.log(`\n[blog_beast] ${runResult.status} (${runResult.duration_ms}ms)`);
console.log(`  ${counts.briefs > 0 ? '✅' : '❌'} blog-briefs.json: ${counts.briefs} briefs`);
console.log(`  ${counts.drafts > 0 ? '✅' : '❌'} blog-drafts.json: ${counts.drafts} drafts`);
console.log(`  ${counts.faqs > 0 ? '✅' : '❌'} faq-opportunities.json: ${counts.faqs} FAQ clusters`);
if (errMsg) console.log(`  ERROR: ${errMsg}`);

const RUN_FILE = path.join(DATA, 'agent-runs.json');
let runs = { agents: {} };
try { runs = JSON.parse(fs.readFileSync(RUN_FILE, 'utf8')); } catch {}
runs.agents['blog_beast'] = runs.agents['blog_beast'] || [];
runs.agents['blog_beast'].push(runResult);
runs.agents['blog_beast'] = runs.agents['blog_beast'].slice(-50);
runs.updated = new Date().toISOString();
fs.writeFileSync(RUN_FILE, JSON.stringify(runs, null, 2));

process.exit(runResult.status === 'PASS' ? 0 : 1);