#!/usr/bin/env node
/**
 * fetch_ga4.js
 * Pulls website performance from Google Analytics 4 Data API
 * Uses GoogleAuth with service account for reliable token refresh
 * Falls back to stale data if auth fails (non-critical file)
 */
const fs = require('fs');
const path = require('path');
const { GoogleAuth } = require('google-auth-library');

const DATA_FILE = path.join(__dirname, '..', 'data', 'ga4-metrics.json');
const CREDS_FILE = '/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/google-service-account.json';
const PROPERTY_ID = '427380680';

async function fetchGA4Data(authClient) {
  const today = new Date();
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - 7);
  const startStr = startDate.toISOString().split('T')[0];
  const endStr = today.toISOString().split('T')[0];
  
  const { execSync } = require('child_process');
  const client = await authClient.getClient();
  const accessTokenResult = await client.getAccessToken();
  const accessToken = accessTokenResult.token;
  
  const requestBody = JSON.stringify({
    dateRanges: [{ startDate: startStr, endDate: endStr }],
    dimensions: [{ name: 'pagePath' }, { name: 'sessionSource' }],
    metrics: [{ name: 'sessions' }, { name: 'engagementRate' }, { name: 'averageSessionDuration' }],
    limit: 200,
  });
  
  // Write body to temp file to avoid shell escaping issues
  const tmpFile = '/tmp/ga4_request_body.json';
  fs.writeFileSync(tmpFile, requestBody);
  
  const cmd = `curl -s -X POST "https://analyticsdata.googleapis.com/v1beta/properties/${PROPERTY_ID}:runReport" \
    -H "Authorization: Bearer ${accessToken}" \
    -H "Content-Type: application/json" \
    -d @${tmpFile}`;
  
  const raw = execSync(cmd, { encoding: 'utf8', timeout: 20000 });
  fs.unlinkSync(tmpFile);
  
  const report = JSON.parse(raw);
  
  if (report.error) {
    throw new Error('GA4 API error: ' + JSON.stringify(report.error).slice(0, 100));
  }
  
  const rows = (report.rows || []).map(r => ({
    pagePath: r.dimensionValues?.[0]?.value || '',
    source: r.dimensionValues?.[1]?.value || '',
    sessions: parseInt(r.metricValues?.[0]?.value || 0),
    engagementRate: parseFloat(r.metricValues?.[1]?.value || 0),
    avgSessionDuration: parseFloat(r.metricValues?.[2]?.value || 0),
  })).sort((a, b) => b.sessions - a.sessions);
  
  const topPages = rows.slice(0, 10).map(r => ({
    path: r.pagePath,
    sessions: r.sessions,
    engRate: (r.engagementRate * 100).toFixed(1) + '%',
  }));
  
  const sources = {};
  rows.forEach(r => {
    const src = r.source || 'direct';
    sources[src] = (sources[src] || 0) + r.sessions;
  });
  const topSources = Object.entries(sources).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([source, sessions]) => ({ source, sessions }));
  
  const weakPages = topPages.filter(p => parseFloat(p.engRate) < 50);
  const recommendations = [];
  if (weakPages.length > 0) {
    recommendations.push({ type: 'weak_cta', priority: 'high', message: `${weakPages.length} pages with high traffic but <50% engagement. Review CTA placement.`, pages: weakPages.map(p => p.path) });
  }
  
  const organic = topSources.filter(s => s.source.includes('google') || s.source.includes('organic'));
  if (organic.length > 0) {
    recommendations.push({ type: 'organic_opportunity', priority: 'medium', message: `${organic.reduce((s, x) => s + x.sessions, 0)} organic sessions. Ensure these pages have clear booking CTAs.` });
  }
  
  return {
    updated: new Date().toISOString(),
    fetched_at: new Date().toISOString(),
    property_id: PROPERTY_ID,
    data_window: `${startStr} to ${endStr}`,
    total_sessions: rows.reduce((s, r) => s + r.sessions, 0),
    pages: topPages,
    sources: topSources,
    insights: { recommendations },
    top_pages_count: topPages.length,
    insights_count: recommendations.length,
    _stale: false,
    _auth_worked: true,
  };
}

async function runAsync() {
  // Check if previous valid data exists (for fallback)
  let hadFallback = false;
  let existingData = null;
  if (fs.existsSync(DATA_FILE)) {
    try {
      existingData = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
      if (existingData.total_sessions && existingData.total_sessions > 0) {
        hadFallback = true;
      }
    } catch (e) { hadFallback = false; }
  }
  
  try {
    const creds = JSON.parse(fs.readFileSync(CREDS_FILE, 'utf8'));
    const auth = new GoogleAuth({
      credentials: creds,
      scopes: 'https://www.googleapis.com/auth/analytics.readonly',
    });
    
    const result = await fetchGA4Data(auth);
    fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
    console.log(`✅ GA4: ${result.total_sessions} sessions, ${result.pages.length} pages, ${result.insights.recommendations.length} insights`);
    return result;
  } catch (e) {
    const errMsg = e.message.slice(-100);
    
    if (hadFallback && existingData) {
      // Keep previous valid data, mark it stale
      existingData.updated = new Date().toISOString();
      existingData._stale = true;
      existingData._stale_reason = errMsg;
      existingData._fallback_used = true;
      fs.writeFileSync(DATA_FILE, JSON.stringify(existingData, null, 2));
      console.log(`⚠️  GA4: stale fallback used (${errMsg})`);
      return existingData;
    } else {
      // No fallback — this is a real failure
      const empty = {
        updated: new Date().toISOString(),
        error: errMsg,
        total_sessions: 0,
        pages: [],
        insights: { recommendations: [] },
        _stale: true,
        _fallback_used: false,
        _no_previous_data: true,
      };
      fs.writeFileSync(DATA_FILE, JSON.stringify(empty, null, 2));
      console.log(`❌ GA4: no data and no fallback - ${errMsg}`);
      process.exit(1); // Script failure — no fallback available
    }
  }
}

function run() {
  runAsync().catch(e => {
    console.log(`❌ GA4 async error: ${e.message.slice(-80)}`);
    process.exit(1);
  });
}

module.exports = { run };
if (require.main === module) run();