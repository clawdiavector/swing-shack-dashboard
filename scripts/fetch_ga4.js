#!/usr/bin/env node
/**
 * fetch_ga4.js
 * Pulls website performance from Google Analytics 4 Data API
 * Uses stale fallback if auth fails — never silently returns empty
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DATA_FILE = path.join(__dirname, '..', 'data', 'ga4-metrics.json');
const CREDS_FILE = '/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/google-service-account.json';
const PROPERTY_ID = '427380680';

function fetchGA4Data(token) {
  const today = new Date();
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - 7);
  const startStr = startDate.toISOString().split('T')[0];
  const endStr = today.toISOString().split('T')[0];
  
  const cmd = `curl -s -X POST "https://analyticsdata.googleapis.com/v1beta/properties/${PROPERTY_ID}:runReport" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    -d '{"dateRanges":[{"startDate":"' + startStr + '","endDate":"' + endStr + '"}],"dimensions":[{"name":"pagePath"},{"name":"sessionSource"}],"metrics":[{"name":"sessions"},{"name":"engagementRate"},{"name":"averageSessionDuration"}],"limit":200}' 2>/dev/null`;
  
  const raw = execSync(cmd, { encoding: 'utf8', timeout: 20000 });
  const report = JSON.parse(raw);
  
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
    data_window: `${startStr} to ${endStr}`,
    total_sessions: rows.reduce((s, r) => s + r.sessions, 0),
    pages: topPages,
    sources: topSources,
    insights: { recommendations },
    _stale: false,
    _auth_worked: true,
  };
}

function run() {
  // Check if previous valid data exists and its age
  let hadFallback = false;
  if (fs.existsSync(DATA_FILE)) {
    try {
      const existing = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
      if (existing.total_sessions && existing.total_sessions > 0) {
        hadFallback = true;
      }
    } catch (e) { hadFallback = false; }
  }
  
  try {
    // Try to get access token
    const tokenResult = execSync(
      `node -e "const {OAuth2Client} = require('google-auth-library'); const c = JSON.parse(require('fs').readFileSync('${CREDS_FILE}','utf8')); const cl = new OAuth2Client(c.client_id, c.client_secret); cl.getAccessToken().then(t => console.log(t.token)).catch(e => console.log('ERR:'+e.message))"`,
      { encoding: 'utf8', timeout: 15000 }
    ).trim();
    
    if (!tokenResult || tokenResult.startsWith('ERR:')) {
      throw new Error('Token fetch failed: ' + tokenResult);
    }
    
    const result = fetchGA4Data(tokenResult);
    fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
    console.log(`✅ GA4: ${result.total_sessions} sessions, ${result.pages.length} pages, ${result.insights.recommendations.length} insights`);
    return result;
  } catch (e) {
    const errMsg = e.message.slice(-80);
    
    if (hadFallback) {
      // Keep previous data, mark it stale but don't fail the script
      const existing = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
      existing.updated = new Date().toISOString();
      existing._stale = true;
      existing._stale_reason = errMsg;
      existing._fallback_used = true;
      fs.writeFileSync(DATA_FILE, JSON.stringify(existing, null, 2));
      console.log(`⚠️  GA4: stale fallback used (${errMsg})`);
      return existing;
    } else {
      // No fallback - this is a real failure, exit non-zero
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
      process.exit(1); // Fail the script - no fallback available
    }
  }
}

module.exports = { run };
if (require.main === module) run();