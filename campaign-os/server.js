/**
 * CampaignOS Blueprint API Server
 * Handles Accept/Regenerate actions for the cockpit UI.
 * 
 * Usage: node server.js
 * Runs on http://localhost:3456
 */
const http = require('http');
const { spawn } = require('child_process');
const path = require('path');

const PORT = 3456;
const REPO = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const SCRIPT = path.join(REPO, 'scripts', 'generate-blueprint.py');
const DATA_FILE = path.join(REPO, 'campaign-os', 'campaign-data.json');

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
  };
}

function jsonResponse(res, status, obj) {
  res.writeHead(status, { 'Content-Type': 'application/json', ...corsHeaders() });
  res.end(JSON.stringify(obj));
}

function runBlueprint(scriptArgs) {
  return new Promise((resolve, reject) => {
    const pid = spawn('python3', [SCRIPT, ...scriptArgs], {
      cwd: REPO,
      stdio: ['ignore', 'pipe', 'pipe']
    });
    let stdout = '';
    let stderr = '';
    pid.stdout.on('data', d => { stdout += d.toString(); });
    pid.stderr.on('data', d => { stderr += d.toString(); });
    pid.on('error', e => reject(e));
    pid.on('close', code => {
      if (code === 0) resolve(stdout.trim());
      else reject(new Error(stderr.trim() || `exit code ${code}`));
    });
    // Timeout after 120 seconds
    setTimeout(() => { try { pid.kill(); } catch(e){} reject(new Error('timeout')); }, 120000);
  });
}

function getStatus(campaignId) {
  const data = JSON.parse(require('fs').readFileSync(DATA_FILE, 'utf8'));
  const c = data.campaigns && data.campaigns[campaignId];
  if (!c) return { found: false };
  const bp = c.blueprint || {};
  const history = (c.memory && c.memory.blueprintHistory) || [];
  return {
    found: true,
    campaignId,
    currentVersion: bp.blueprintVersion || null,
    status: bp.status || null,
    generatedAt: bp.generatedAt || null,
    modelUsed: bp.modelUsed || null,
    diffSummary: bp.diffSummary || null,
    historyLength: history.length,
    history: history.map(h => ({
      version: h.blueprintVersion,
      generatedAt: h.generatedAt,
      status: h.status,
      diffSummary: h.diffSummary
    }))
  };
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, corsHeaders());
    res.end();
    return;
  }

  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathUrl = url.pathname;

  // GET /api/bp-status/:campaignId
  if (req.method === 'GET' && pathUrl.match(/^\/api\/bp-status\/(.+)$/)) {
    const campaignId = pathUrl.replace('/api/bp-status/', '');
    try {
      const status = getStatus(campaignId);
      jsonResponse(res, 200, { ok: true, ...status });
    } catch(e) {
      jsonResponse(res, 500, { ok: false, error: e.message });
    }
    return;
  }

  // POST /api/bp-accept
  if (req.method === 'POST' && pathUrl === '/api/bp-accept') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        const { campaignId } = JSON.parse(body);
        if (!campaignId) { jsonResponse(res, 400, { ok: false, error: 'campaignId required' }); return; }
        const out = await runBlueprint([campaignId, '--accept']);
        const status = getStatus(campaignId);
        jsonResponse(res, 200, { ok: true, message: 'Blueprint accepted', blueprint: status });
      } catch(e) {
        jsonResponse(res, 500, { ok: false, error: e.message });
      }
    });
    return;
  }

  // POST /api/bp-regenerate
  if (req.method === 'POST' && pathUrl === '/api/bp-regenerate') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        const { campaignId } = JSON.parse(body);
        if (!campaignId) { jsonResponse(res, 400, { ok: false, error: 'campaignId required' }); return; }
        const out = await runBlueprint([campaignId, '--regenerate']);
        const status = getStatus(campaignId);
        jsonResponse(res, 200, { ok: true, message: 'Blueprint regenerated', blueprint: status });
      } catch(e) {
        jsonResponse(res, 500, { ok: false, error: e.message });
      }
    });
    return;
  }

  res.writeHead(404, corsHeaders());
  res.end('Not found');
});

server.on('error', e => console.error('Server error:', e));
server.listen(PORT, () => {
  console.log(`Blueprint API server running on http://localhost:${PORT}`);
});
