#!/usr/bin/env node
/**
 * fetch_youtube_trends.js
 * Scrapes YouTube golf trending content and Shorts data
 * Uses curl + basic HTML parsing (no API key needed)
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DATA_FILE = path.join(__dirname, '..', 'data', 'youtube-trends.json');

const SEARCHES = [
  { q: 'golf swing tips 2026', label: 'Golf Swing Tips' },
  { q: 'indoor golf simulator', label: 'Indoor Golf' },
  { q: 'golfTrackMan analysis', label: 'TrackMan/Data' },
  { q: 'golf practice drills', label: 'Practice Drills' },
  { q: 'golf lesson improvement', label: 'Golf Lessons' },
];

function curl(url, maxAge = 86400) {
  const cacheFile = `/tmp/yt_${Buffer.from(url).toString('base64').slice(0, 30)}.json`;
  try {
    if (fs.existsSync(cacheFile)) {
      const age = (Date.now() - fs.statSync(cacheFile).mtimeMs) / 1000;
      if (age < maxAge) return JSON.parse(fs.readFileSync(cacheFile, 'utf8'));
    }
  } catch(e) {}
  
  try {
    const cmd = `curl -s -L -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1" --max-time 10 "${url.replace(/"/g, '\\"')}" 2>/dev/null | head -c 30000`;
    const raw = execSync(cmd, { encoding: 'utf8', timeout: 15000 });
    
    // Extract video data from YouTube HTML
    const results = [];
    // Match YouTube video structured data or standard links
    const videoIdMatches = raw.match(/\/watch\?v=([a-zA-Z0-9_-]{11})/g) || [];
    const seen = new Set();
    videoIdMatches.slice(0, 10).forEach(m => {
      const id = m.match(/v=([a-zA-Z0-9_-]{11})/)?.[1];
      if (id && !seen.has(id)) { seen.add(id); results.push({ videoId: id, url: `https://www.youtube.com/watch?v=${id}` }); }
    });
    
    const titleMatches = raw.match(/"title":"([^"]{10,100})"/g) || [];
    titleMatches.slice(0, results.length).forEach((m, i) => {
      if (results[i]) results[i].title = JSON.parse('{"' + m + '}').title;
    });
    
    const viewMatches = raw.match(/"viewCount":"([^"]{1,20})"/g) || [];
    viewMatches.slice(0, results.length).forEach((m, i) => {
      if (results[i]) results[i].views = JSON.parse('{"' + m + '}').viewCount;
    });
    
    try { fs.writeFileSync(cacheFile, JSON.stringify(results)); } catch(e) {}
    return results;
  } catch(e) {
    return [];
  }
}

function parseViews(s) {
  if (!s) return 0;
  const num = parseFloat(s.replace(/[^0-9.]/g, ''));
  if (s.includes('K')) return num * 1000;
  if (s.includes('M')) return num * 1000000;
  if (s.includes('B')) return num * 1000000000;
  return num;
}

function run() {
  const allVideos = [];
  const trends = [];
  let updated = new Date().toISOString();
  
  for (const search of SEARCHES) {
    const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(search.q)}&sp=CAISAgAIhA%3D%3D`;
    const videos = curl(url);
    
    const golfVideos = videos.filter(v => {
      const t = (v.title || '').toLowerCase();
      return t.includes('golf') || t.includes('swing') || t.includes('driver') || t.includes('putting') || t.includes('iron') || t.includes('chip') || t.includes('trackman') || t.includes('simulator') || t.includes('indoor');
    }).slice(0, 5);
    
    golfVideos.forEach(v => {
      allVideos.push({
        ...v,
        search_query: search.q,
        search_label: search.label,
        fetched_at: updated,
      });
    });
  }
  
  // Sort by views to find top performers
  const topByViews = [...allVideos]
    .filter(v => v.views)
    .sort((a, b) => parseViews(b.views) - parseViews(a.views))
    .slice(0, 10)
    .map(v => ({
      videoId: v.videoId,
      title: v.title || 'Untitled',
      views: v.views,
      views_num: parseViews(v.views),
      search_label: v.search_label,
      url: v.url,
    }));
  
  // Extract common themes from titles
  const allTitles = topByViews.map(v => v.title.toLowerCase());
  const themes = {
    swing_speed: allTitles.some(t => t.includes('speed') || t.includes('mph') || t.includes('driver')),
    short_game: allTitles.some(t => t.includes('chip') || t.includes('pitch') || t.includes('putt')),
    trackman_data: allTitles.some(t => t.includes('trackman') || t.includes('data') || t.includes('launch')),
    practice: allTitles.some(t => t.includes('practice') || t.includes('drill') || t.includes('training')),
    lessons: allTitles.some(t => t.includes('lesson') || t.includes('coach') || t.includes('pro')),
    simulator: allTitles.some(t => t.includes('simulator') || t.includes('indoor') || t.includes('launch monitor')),
  };
  
  // Trending hooks from titles
  const hooks = topByViews.slice(0, 5).map((v, i) => {
    const title = v.title;
    // Extract the hook pattern
    const hook = title.length > 60 ? title.slice(0, 57) + '...' : title;
    return {
      idea_id: `yt-hook-${Date.now()}-${i}`,
      source: 'youtube_trending',
      hook_text: hook,
      views: v.views,
      topic: v.search_label,
      url: v.url,
      freshness_score: 8,
    };
  });
  
  trends.push({
    updated,
    query_count: SEARCHES.length,
    videos_found: allVideos.length,
    top_videos: topByViews,
    trending_themes: themes,
    hooks,
    summary: {
      top_theme: Object.entries(themes).filter(([,v]) => v).map(([k]) => k.replace(/_/g, ' ')).join(', ') || 'general golf',
      total_views: topByViews.reduce((s, v) => s + (v.views_num || 0), 0),
    },
  });
  
  fs.writeFileSync(DATA_FILE, JSON.stringify(trends[0], null, 2));
  console.log(`✅ YouTube Trends: ${allVideos.length} videos, ${hooks.length} hooks, top theme: ${trends[0].summary.top_theme}`);
  return trends[0];
}

module.exports = { run };
if (require.main === module) run();