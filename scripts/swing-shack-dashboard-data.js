/**
 * Swing Shack Dashboard Data Updater
 * Fetches GA4 data, IG analytics, and A/B test results
 * Outputs to clients/swing-shack/data/dashboard-live.json
 * Run via cron: 6am, 12pm, 6pm (or whenever)
 */

const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');

const CREDENTIALS_PATH = path.join(__dirname, '../clients/swing-shack/credentials/google-service-account.json');
const IG_ANALYTICS_PATH = path.join(__dirname, '../clients/swing-shack/analytics/instagram-analytics.json');
const OUTPUT_PATH = path.join(__dirname, '../clients/swing-shack/data/dashboard-live.json');
const GA4_PROPERTY_ID = '427380680';

async function fetchGA4(auth) {
  const analyticsdata = google.analyticsdata({ version: 'v1beta', auth });
  
  const [overview, topPages, sources, devices] = await Promise.all([
    // Main overview metrics
    analyticsdata.properties.runReport({
      property: `properties/${GA4_PROPERTY_ID}`,
      requestBody: {
        dateRanges: [{ startDate: '7daysAgo', endDate: 'today' }],
        metrics: [
          { name: 'activeUsers' },
          { name: 'sessions' },
          { name: 'screenPageViews' },
          { name: 'averageSessionDuration' },
          { name: 'bounceRate' }
        ]
      }
    }),
    // Top pages
    analyticsdata.properties.runReport({
      property: `properties/${GA4_PROPERTY_ID}`,
      requestBody: {
        dateRanges: [{ startDate: '7daysAgo', endDate: 'today' }],
        dimensions: [{ name: 'pagePath' }],
        metrics: [{ name: 'screenPageViews' }],
        orderBys: [{ metric: { metricName: 'screenPageViews' }, desc: true }],
        limit: 10
      }
    }),
    // Traffic sources
    analyticsdata.properties.runReport({
      property: `properties/${GA4_PROPERTY_ID}`,
      requestBody: {
        dateRanges: [{ startDate: '7daysAgo', endDate: 'today' }],
        dimensions: [{ name: 'sessionSource' }],
        metrics: [{ name: 'sessions' }],
        orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
        limit: 10
      }
    }),
    // Devices
    analyticsdata.properties.runReport({
      property: `properties/${GA4_PROPERTY_ID}`,
      requestBody: {
        dateRanges: [{ startDate: '7daysAgo', endDate: 'today' }],
        dimensions: [{ name: 'deviceCategory' }],
        metrics: [{ name: 'sessions' }],
        orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
        limit: 5
      }
    })
  ]);

  const ov = overview.data;
  const metrics = ov.rows[0].metricValues;
  
  return {
    activeUsers: parseInt(metrics[0].value),
    sessions: parseInt(metrics[1].value),
    pageViews: parseInt(metrics[2].value),
    avgSessionSeconds: parseFloat(metrics[3].value),
    bounceRate: parseFloat(metrics[4].value),
    topPages: topPages.data.rows.map(r => ({
      path: r.dimensionValues[0].value,
      views: parseInt(r.metricValues[0].value)
    })),
    topSources: sources.data.rows.map(r => ({
      source: r.dimensionValues[0].value,
      sessions: parseInt(r.metricValues[0].value)
    })),
    devices: devices.data.rows.map(r => ({
      device: r.dimensionValues[0].value,
      sessions: parseInt(r.metricValues[0].value)
    }))
  };
}

async function fetchSearchConsole(auth) {
  const webmasters = google.webmasters({ version: 'v3', auth });
  
  try {
    const today = new Date();
    const d28 = new Date(today); d28.setDate(d28.getDate() - 28);
    const fmt = D => D.toISOString().split('T')[0];
    const result = await webmasters.searchanalytics.query({
      siteUrl: 'https://swingshack.co.za/',
      requestBody: {
        startDate: fmt(d28),
        endDate: fmt(today),
        dimensions: ['query'],
        rowLimit: 10
      }
    });
    
    return result.data.rows.map(r => ({
      query: r.keys[0],
      clicks: r.clicks,
      impressions: r.impressions,
      position: parseFloat(r.position).toFixed(1)
    }));
  } catch (e) {
    console.error('Search Console error:', e.message);
    return null;
  }
}

function loadIGData() {
  try {
    const data = JSON.parse(fs.readFileSync(IG_ANALYTICS_PATH, 'utf8'));
    const posts = data.posts || [];
    const topPerformers = data.topPerformers || [];
    
    // Recent posts (last 7 days)
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const recentPosts = posts
      .filter(p => new Date(p.timestamp) > sevenDaysAgo)
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, 20);
    
    // Top performers (best engagement)
    const topPosts = [...posts]
      .filter(p => parseFloat(p.engagementRate) > 0)
      .sort((a, b) => parseFloat(b.engagementRate) - parseFloat(a.engagementRate))
      .slice(0, 5);
    
    // Avg engagement (last 30 days)
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    const recentEngagement = posts
      .filter(p => new Date(p.timestamp) > thirtyDaysAgo)
      .map(p => parseFloat(p.engagementRate) || 0);
    const avgEngagement = recentEngagement.length > 0
      ? (recentEngagement.reduce((a, b) => a + b, 0) / recentEngagement.length).toFixed(2)
      : '0.00';
    
    return {
      followers: data.instagram?.followers || 0,
      posts: posts.length,
      avgEngagement,
      recentPosts,
      topPosts,
      lastUpdated: data.lastUpdated
    };
  } catch (e) {
    console.error('IG data error:', e.message);
    return null;
  }
}

async function main() {
  console.log('Fetching dashboard data...');
  
  // GA4 data
  let ga4Data = null;
  try {
    const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, 'utf8'));
    const auth = new google.auth.GoogleAuth({
      credentials: creds,
      scopes: ['https://www.googleapis.com/auth/analytics.readonly']
    });
    ga4Data = await fetchGA4(auth);
    console.log('GA4: OK -', ga4Data.activeUsers, 'users,', ga4Data.sessions, 'sessions');
  } catch (e) {
    console.error('GA4 Error:', e.message);
  }
  
  // Search Console
  let scData = null;
  try {
    const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, 'utf8'));
    const auth = new google.auth.GoogleAuth({
      credentials: creds,
      scopes: ['https://www.googleapis.com/auth/webmasters.readonly']
    });
    scData = await fetchSearchConsole(auth);
    if (scData) console.log('Search Console: OK -', scData.length, 'queries');
  } catch (e) {
    console.error('Search Console Error:', e.message);
  }
  
  // IG data
  const igData = loadIGData();
  if (igData) {
    // Use known follower count as fallback (fetched from Meta API when token is fresh)
    if (!igData.followers) igData.followers = 2230;
    console.log('IG: OK -', igData.followers, 'followers,', igData.posts, 'posts');
  }
  
  // Build output
  const output = {
    lastUpdated: new Date().toISOString(),
    source: 'automated',
    website: ga4Data || { activeUsers: 0, sessions: 0, pageViews: 0 },
    searchConsole: scData,
    instagram: igData || {}
  };
  
  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
  console.log('Dashboard data saved to', OUTPUT_PATH);
  console.log('Timestamp:', output.lastUpdated);

  // Push updated data + dashboard to GitHub Pages
  // PATCH 2026-06-30 @forge_v2: repointed from /tmp/swing-shack-dashboard (phantom dir,
  // never cloned by any prior step) to the actual repo location. Dropped the gen-dashboard.py
  // step — that file doesn't exist on disk; HTML templates read dashboard-live.json via JS at
  // runtime and are updated by hand, not regenerated.
  try {
    const { execSync } = require('child_process');
    const repoDir = path.join(__dirname, '../swing-shack-dashboard');
    const dataSrc = OUTPUT_PATH;
    const dataDir = path.join(repoDir, 'data');

    // Defensive: ensure target dir exists (handles fresh clones / first-run)
    fs.mkdirSync(dataDir, { recursive: true });

    // Copy data file into the repo
    fs.copyFileSync(dataSrc, path.join(dataDir, 'dashboard-live.json'));

    // PATCH 2026-07-30 @heidi: replaced inline git push with git-safe-push.sh.
    // The previous command (`git add && git commit && git push origin main`)
    // had no fetch/rebase step. If a human pushed visualizer/meme-lab work to
    // remote main between cron runs, this cron would silently force-push and
    // drop those commits — that's how Railway deploys got broken twice this week.
    // The safe-push wrapper fetches, fast-forwards if behind, refuses on
    // divergence, and uses --force-with-lease to catch races.
    execSync(`bash ${path.join(__dirname, 'git-safe-push.sh')} "${repoDir}" main`, {
      stdio: 'pipe',
      cwd: repoDir,
      timeout: 60000
    });
    console.log('GitHub Pages updated successfully');
  } catch (e) {
    console.error('GitHub push failed:', e.stderr ? e.stderr.toString() : e.message);
  }
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
