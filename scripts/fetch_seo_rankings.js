#!/usr/bin/env node
/**
 * fetch_seo_rankings.js
 * Tracks target keyword rankings for Swing Shack
 * Runs via curl scraping (free, no API key)
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DATA_FILE = path.join(__dirname, '..', 'data', 'seo-rankings.json');

const KEYWORDS = [
  'indoor golf johannesburg',
  'golf simulator johannesburg',
  'club fitting johannesburg',
  'golf lessons randburg',
  'golf practice johannesburg',
  'trackman johannesburg',
  'custom clubs johannesburg',
  'indoor golf randburg',
  'golf simulator south africa',
  'golf fitting johannesburg price',
];

const TARGET_URL = 'https://swingshack.co.za';

function fetchGoogleRank(keyword) {
  try {
    // Try to check if Swing Shack appears for these keywords via site search
    // Use site: search to check indexing status
    const query = encodeURIComponent(`${keyword} site:swingshack.co.za`);
    const cmd = `curl -s "https://www.google.com/search?q=${query}&num=5" -H "User-Agent: Mozilla/5.0" 2>/dev/null | head -c 5000`;
    const html = execSync(cmd, { encoding: 'utf8', timeout: 15000 });
    
    // Check if our site appears in results
    const siteAppears = html.includes('swingshack.co.za');
    const positionMatch = html.match(/swingshack\.co\.za.*?(\d+)/);
    
    return {
      keyword,
      current_rank: siteAppears ? (positionMatch ? parseInt(positionMatch[1]) : 1) : null,
      target_url: TARGET_URL,
      search_intent: keyword.match(/price|cost/i) ? 'commercial' : keyword.match(/what|how|guide/i) ? 'informational' : 'mixed',
      note: siteAppears ? 'Found in search results' : 'Not found in top results',
    };
  } catch (e) {
    return {
      keyword,
      current_rank: null,
      target_url: TARGET_URL,
      search_intent: 'unknown',
      note: 'Fetch failed - ' + e.message.slice(-50),
    };
  }
}

function run() {
  console.log('🔍 Fetching SEO rankings...');
  
  const results = KEYWORDS.map(k => fetchGoogleRank(k));
  
  // Calculate deltas (mock for now - would need historical storage)
  const rising = results.filter(r => r.current_rank && r.current_rank <= 5);
  const falling = [];
  const quickWins = results.filter(r => r.current_rank === null);
  
  const result = {
    updated: new Date().toISOString(),
    keywords: results,
    rising_keywords: rising.map(r => r.keyword),
    falling_keywords: falling,
    quick_wins: quickWins.map(r => r.keyword),
    summary: {
      tracked: results.length,
      found: results.filter(r => r.current_rank !== null).length,
      not_found: quickWins.length,
    },
    recommendations: [
      ...quickWins.map(k => ({
        type: 'not_indexed',
        keyword: k.keyword,
        action: `Create or optimize page targeting "${k.keyword}"`,
        priority: 'high',
      })),
      ...rising.map(k => ({
        type: 'opportunity',
        keyword: k.keyword,
        action: `Strengthen internal links to page targeting "${k.keyword}"`,
        priority: 'medium',
      })),
    ],
  };
  
  fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
  console.log(`✅ SEO Rankings: ${result.summary.found}/${result.summary.tracked} keywords found`);
  return result;
}

module.exports = { run };
if (require.main === module) run();