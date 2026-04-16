#!/usr/bin/env node
/**
 * fetch_ga4.js
 * Pulls website performance from Google Analytics 4 Data API
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DATA_FILE = path.join(__dirname, '..', 'data', 'ga4-metrics.json');
const CREDS_FILE = '/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/google-service-account.json';
const PROPERTY_ID = '427380680';

function run() {
  try {
    // Try GA4 Data API via curl
    const today = new Date();
    const startDate = new Date(today);
    startDate.setDate(startDate.getDate() - 7);
    const startStr = startStr || startDate.toISOString().split('T')[0];
    const endStr = today.toISOString().split('T')[0];
    
    const creds = JSON.parse(fs.readFileSync(CREDS_FILE, 'utf8'));
    const token = execSync(
      `node -e "const {OAuth2Client} = require('google-auth-library'); const creds = JSON.parse(require('fs').readFileSync('${CREDS_FILE}','utf8')); const client = new OAuth2Client(creds.client_id, creds.client_secret); client.getAccessToken().then(t => console.log(t.token)).catch(e => console.log('err',e.message))"`,
      { encoding: 'utf8', timeout: 15000 }
    ).trim();
    
    // GA4 Data API runReport
    const cmd = `curl -s -X POST "https://analyticsdata.googleapis.com/v1beta/properties/${PROPERTY_ID}:runReport" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d '{
        "dateRanges": [{"startDate": "${startStr}", "endDate": "${endStr}"}],
        "dimensions": [{"name": "pagePath"}, {"name": "sessionSource"}],
        "metrics": [{"name": "sessions"}, {"name": "engagementRate"}, {"name": "averageSessionDuration"}]
      }' 2>/dev/null`;
    
    const raw = execSync(cmd, { encoding: 'utf8', timeout: 20000 });
    const report = JSON.parse(raw);
    
    const rows = (report.rows || []).map(r => ({
      pagePath: r.dimensionValues?.[0]?.value || '',
      source: r.dimensionValues?.[1]?.value || '',
      sessions: parseInt(r.metricValues?.[0]?.value || 0),
      engagementRate: parseFloat(r.metricValues?.[1]?.value || 0),
      avgSessionDuration: parseFloat(r.metricValues?.[2]?.value || 0),
    })).sort((a, b) => b.sessions - a.sessions);
    
    // Top pages
    const topPages = rows.slice(0, 10).map(r => ({
      path: r.pagePath,
      sessions: r.sessions,
      engRate: (r.engagementRate * 100).toFixed(1) + '%',
    }));
    
    // Sessions by source
    const sources = {};
    rows.forEach(r => {
      const src = r.source || 'direct';
      sources[src] = (sources[src] || 0) + r.sessions;
    });
    
    const topSources = Object.entries(sources)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([source, sessions]) => ({ source, sessions }));
    
    // Compute insights
    const highTraffic = topPages.filter(p => p.sessions > 50);
    const weakPages = topPages.filter(p => p.engRate < 50);
    
    const insights = {
      recommendations: [],
    };
    
    if (weakPages.length > 0) {
      insights.recommendations.push({
        type: 'weak_cta',
        priority: 'high',
        message: `${weakPages.length} pages have high traffic but <50% engagement. Review CTA placement.`,
        pages: weakPages.map(p => p.path),
      });
    }
    
    const organic = topSources.filter(s => s.source.includes('google') || s.source.includes('organic'));
    if (organic.length > 0) {
      insights.recommendations.push({
        type: 'organic_opportunity',
        priority: 'medium',
        message: `${organic.reduce((s, x) => s + x.sessions, 0)} organic sessions. Ensure these pages have clear booking CTAs.`,
      });
    }
    
    const result = {
      updated: new Date().toISOString(),
      data_window: `${startStr} to ${endStr}`,
      total_sessions: rows.reduce((s, r) => s + r.sessions, 0),
      pages: topPages,
      sources: topSources,
      insights,
    };
    
    fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
    console.log(`✅ GA4: ${result.total_sessions} sessions, ${topPages.length} pages, ${insights.recommendations.length} insights`);
    return result;
  } catch (e) {
    console.log(`⚠️  GA4 fetch failed: ${e.message.slice(-100)}`);
    // Keep previous data
    return null;
  }
}

module.exports = { run };
if (require.main === module) run();