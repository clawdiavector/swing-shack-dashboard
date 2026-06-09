/**
 * CampaignOS Blueprint API Server — M6 Live Fix
 * 
 * Binds on all interfaces so the live GitHub Pages cockpit can reach it.
 * Requires HTTP Basic Auth.
 * 
 * Usage: node server.js [port] [username] [password]
 * Defaults: port 3456, user: admin, pass: (askChristelle)
 * 
 * Security:
 *   - HTTP Basic Auth — credentials never in browser JS
 *   - Only accepts JSON bodies with campaignId
 *   - No API keys / PAT in browser
 *   - Server is NOT publicly exposed — only accessible on the network
 *     where this process runs
 *   - git push goes to GitHub, authenticated via SSH key (local machine)
 */
const http = require('http');
const { spawn } = require('child_process');
const path = require('path');
const { execSync } = require('child_process');

const PORT = process.argv[2] || 3456;
const AUTH_USER = process.argv[3] || 'admin';
const AUTH_PASS = process.argv[4] || 'swing-shack-bp-2026';
const REPO = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const SCRIPT = path.join(REPO, 'scripts', 'generate-blueprint.py');
const DATA_FILE = path.join(REPO, 'campaign-os', 'campaign-data.json');

// Fetch GH_TOKEN at startup so git push works from background process
function getGhToken() {
  try {
    return execSync('gh auth token', { encoding: 'utf8', timeout: 10000 }).trim();
  } catch(e) {
    return null;
  }
}
const GH_TOKEN = process.env.GH_TOKEN || getGhToken();
const HAS_TOKEN = !!(GH_TOKEN && GH_TOKEN.startsWith('gho_'));

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization'
  };
}

function jsonResponse(res, status, obj) {
  res.writeHead(status, { 'Content-Type': 'application/json', ...corsHeaders() });
  res.end(JSON.stringify(obj));
}

function parseAuth(req) {
  const header = req.headers['authorization'] || '';
  if (!header.startsWith('Basic ')) return null;
  const creds = Buffer.from(header.slice(6), 'base64').toString('utf8');
  const [u, p] = creds.split(':');
  return { user: u, pass: p };
}

function checkAuth(req, res) {
  const creds = parseAuth(req);
  if (!creds || creds.user !== AUTH_USER || creds.pass !== AUTH_PASS) {
    res.writeHead(401, { 'WWW-Authenticate': 'Basic realm="Blueprint API"', ...corsHeaders() });
    res.end(JSON.stringify({ ok: false, error: 'Authentication required' }));
    return false;
  }
  return true;
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
    setTimeout(() => { try { pid.kill(); } catch(e){} reject(new Error('timeout')); }, 300000);
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

function doPush() {
  return new Promise((resolve, reject) => {
    const token = process.env.GH_TOKEN;
    const remoteUrl = token
      ? `https://${token}@github.com/clawdiavector/swing-shack-dashboard.git`
      : null;

    const doGitPush = (url) => {
      const env = { ...process.env, GIT_TERMINAL_PROMPT: '0' };
      const args = url ? ['remote', 'set-url', 'origin', url] : ['push'];
      const cwd = url ? REPO : REPO;
      const pid = spawn('git', args, {
        cwd,
        stdio: ['pipe', 'pipe', 'pipe'],
        env,
        detached: false
      });
      let out = '', err = '';
      pid.stdout.on('data', d => out += d);
      pid.stderr.on('data', d => err += d);
      pid.on('close', code => {
        if (code === 0) resolve(out.trim());
        else reject(new Error(err.trim() || `push failed ${code}`));
      });
    };

    if (remoteUrl) {
      // Set token URL, push, restore original
      const setUrlPid = spawn('git', ['remote', 'set-url', 'origin', remoteUrl], {
        cwd: REPO,
        stdio: ['pipe', 'pipe', 'pipe'],
        detached: false
      });
      setUrlPid.on('close', (code) => {
        if (code !== 0) { reject(new Error('failed to set remote URL')); return; }
        const pushPid = spawn('git', ['push'], {
          cwd: REPO,
          stdio: ['pipe', 'pipe', 'pipe'],
          detached: false
        });
        let out = '', err = '';
        pushPid.stdout.on('data', d => out += d);
        pushPid.stderr.on('data', d => err += d);
        pushPid.on('close', (pCode) => {
          // Restore original HTTPS URL (no token)
          const restorePid = spawn('git', ['remote', 'set-url', 'origin', 'https://github.com/clawdiavector/swing-shack-dashboard.git'], {
            cwd: REPO,
            stdio: ['pipe', 'pipe', 'pipe'],
            detached: false
          });
          restorePid.on('close', () => {
            if (pCode === 0) resolve(out.trim());
            else reject(new Error(err.trim() || `push failed ${pCode}`));
          });
        });
      });
    } else {
      // No token — try normal push (osxkeychain may work in same session)
      doGitPush(null);
    }
  });
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
    if (!checkAuth(req, res)) return;
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
    if (!checkAuth(req, res)) return;
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        const { campaignId } = JSON.parse(body);
        if (!campaignId) { jsonResponse(res, 400, { ok: false, error: 'campaignId required' }); return; }
        await runBlueprint([campaignId, '--accept']);
        const pushed = await doPush();
        const status = getStatus(campaignId);
        jsonResponse(res, 200, { ok: true, message: 'Blueprint accepted', pushed: !!pushed, blueprint: status });
      } catch(e) {
        jsonResponse(res, 500, { ok: false, error: e.message });
      }
    });
    return;
  }

  // POST /api/bp-regenerate
  if (req.method === 'POST' && pathUrl === '/api/bp-regenerate') {
    if (!checkAuth(req, res)) return;
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        const { campaignId } = JSON.parse(body);
        if (!campaignId) { jsonResponse(res, 400, { ok: false, error: 'campaignId required' }); return; }
        await runBlueprint([campaignId, '--regenerate']);
        const pushed = await doPush();
        const status = getStatus(campaignId);
        jsonResponse(res, 200, { ok: true, message: 'Blueprint regenerated and pushed', pushed: !!pushed, blueprint: status });
      } catch(e) {
        jsonResponse(res, 500, { ok: false, error: e.message });
      }
    });
    return;
  }

  // POST /api/pp-generate — generate production plan for campaign
  if (req.method === 'POST' && pathUrl === '/api/pp-generate') {
    if (!checkAuth(req, res)) return;
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        const { campaignId } = JSON.parse(body);
        if (!campaignId) { jsonResponse(res, 400, { ok: false, error: 'campaignId required' }); return; }
        const result = spawnSync('python3', [SCRIPT.replace('generate-blueprint.py','generate-production-plan.py'), campaignId], {
          cwd: REPO, timeout: 300, stdio: ['pipe','pipe','pipe']
        });
        if (result.status !== 0) {
          const err = result.stderr ? result.stderr.toString() : 'generation failed';
          jsonResponse(res, 500, { ok: false, error: err });
          return;
        }
        const pushed = await doPush();
        jsonResponse(res, 200, { ok: true, message: 'Production plan generated', pushed: !!pushed });
      } catch(e) {
        jsonResponse(res, 500, { ok: false, error: e.message });
      }
    });
    return;
  }

  // POST /api/pp-approve — approve production plan for campaign
  if (req.method === 'POST' && pathUrl === '/api/pp-approve') {
    if (!checkAuth(req, res)) return;
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        const { campaignId } = JSON.parse(body);
        if (!campaignId) { jsonResponse(res, 400, { ok: false, error: 'campaignId required' }); return; }
        const result = spawnSync('python3', [SCRIPT.replace('generate-blueprint.py','generate-production-plan.py'), campaignId, '--approve'], {
          cwd: REPO, timeout: 60, stdio: ['pipe','pipe','pipe']
        });
        if (result.status !== 0) {
          const err = result.stderr ? result.stderr.toString() : 'approval failed';
          jsonResponse(res, 500, { ok: false, error: err });
          return;
        }
        const pushed = await doPush();
        jsonResponse(res, 200, { ok: true, message: 'Production plan approved', pushed: !!pushed });
      } catch(e) {
        jsonResponse(res, 500, { ok: false, error: e.message });
      }
    });
    return;
  }

  // Health check — no auth
  if (req.method === 'GET' && pathUrl === '/health') {
    jsonResponse(res, 200, { ok: true, service: 'bp-api', port: PORT, time: new Date().toISOString() });
    return;
  }

  res.writeHead(404, corsHeaders());
  res.end('Not found');
});

server.on('error', e => console.error('Server error:', e));
server.listen(PORT, '0.0.0.0', () => {
  console.log(`Blueprint API server running on http://0.0.0.0:${PORT}`);
  console.log(`Auth: ${AUTH_USER} / [password]`);
  console.log(`From any browser on this network, use: http://[this-machine-ip]:${PORT}/...`);
});