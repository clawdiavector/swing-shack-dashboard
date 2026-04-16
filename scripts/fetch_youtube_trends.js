#!/usr/bin/env node
/**
 * fetch_youtube_trends.js
 * Fetches what golf content is trending, using Google Search as YouTube intent proxy.
 * Falls back to synthesizing trends from golf news + reddit when scraping is blocked.
 * 
 * Strategy:
 * 1. Try Google News API (free tier) for golf news as YouTube intent signal
 * 2. Try RSS feeds from golf publications
 * 3. Fall back: mine golf news + reddit for trending topics
 * 
 * YouTube without an API key is unreliable - this gives us SA golf trends anyway.
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DATA_FILE = path.join(__dirname, '..', 'data', 'youtube-trends.json');
const NEWS_FILE = path.join(__dirname, '..', 'data', 'golf-news.json');
const REDDIT_FILE = path.join(__dirname, '..', 'data', 'reddit-trends.json');

function fetchUrl(url, userAgent) {
  const ua = userAgent || 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
  try {
    const cmd = `curl -s --max-time 12 -L -A "${ua}" "${url}" 2>/dev/null | head -c 20000`;
    return execSync(cmd, { encoding: 'utf8', timeout: 15000 });
  } catch(e) {
    return '';
  }
}

function tryGoogleNews() {
  // Try NewsAPI.org free tier (newsapi.org provides free golf news)
  const apiKey = process.env.NEWS_API_KEY;
  if (!apiKey) return null;
  
  try {
    const url = `https://newsapi.org/v2/everything?q=golf+swing+OR+golf+lesson+OR+golf+training&language=en&sortBy=relevancy&pageSize=20&apiKey=${apiKey}`;
    const raw = execSync(`curl -s --max-time 10 "${url}" 2>/dev/null`, { encoding: 'utf8', timeout: 12000 });
    const data = JSON.parse(raw);
    if (data.articles) {
      return data.articles.map(a => ({
        title: a.title,
        description: a.description,
        source: a.source?.name,
        publishedAt: a.publishedAt,
      }));
    }
  } catch(e) {}
  return null;
}

function tryGolfRSS() {
  // Try RSS feeds from golf publications
  const feeds = [
    { name: 'GolfDigest', url: 'https://www.golfdigest.com/rss/news' },
    { name: 'Golfweek', url: 'https://golfweek.com/index.xml' },
    { name: 'GolfMagic', url: 'https://www.golfmagic.com/rss/news.xml' },
  ];
  
  const articles = [];
  for (const feed of feeds) {
    try {
      const xml = fetchUrl(feed.url);
      if (!xml || xml.length < 100) continue;
      
      const titles = xml.match(/<title[^>]*>([^<]+)<\/title>/gi) || [];
      const descs = xml.match(/<description[^>]*>([^<]{20,300})/gi) || [];
      const links = xml.match(/<link[^>]*>([^<]+)<\/link>/gi) || [];
      
      for (let i = 0; i < Math.min(titles.length, 3); i++) {
        const title = titles[i].replace(/<[^>]+>/g, '').trim();
        const desc = (descs[i] || '').replace(/<[^>]+>/g, '').replace(/&[^;]+;/g, ' ').trim().slice(0, 150);
        if (title.length > 10) {
          articles.push({ title, description: desc, source: feed.name });
        }
      }
    } catch(e) {}
  }
  return articles.length > 0 ? articles : null;
}

function synthesizeFromExisting() {
  // When external sources fail, synthesize from what we already have
  const newsData = fs.existsSync(NEWS_FILE) ? JSON.parse(fs.readFileSync(NEWS_FILE, 'utf8')) : {};
  const redditData = fs.existsSync(REDDIT_FILE) ? JSON.parse(fs.readFileSync(REDDIT_FILE, 'utf8')) : {};
  
  const redditPosts = ((redditData.trends || redditData.posts || redditData.hot_pain_points || [])).slice(0, 5).map(p => ({
    title: p.title || p.headline || p.topic || '',
    description: p.description || p.selftext || p.insight || '',
    source: 'reddit-golf',
    publishedAt: redditData.updated,
  }));
  
  return {
    news: (newsData.news || newsData.articles || []).slice(0, 5).map(a => ({
      title: a.title || '',
      description: a.description || '',
      source: a.source || newsData.source || 'golf-news',
      publishedAt: a.publishedAt || newsData.updated,
    })),
    reddit: redditPosts,
  };
}

function extractThemes(items) {
  const text = items.map(i => ((i.title || '') + ' ' + (i.description || '')).toLowerCase()).join(' ');
  
  const themes = {
    swing_speed: ['swing speed', 'club head speed', 'mph', 'driver distance', 'yards off tee'],
    short_game: ['chip', 'pitch', 'putt', 'around the green', 'bunker'],
    trackman: ['trackman', 'launch monitor', 'launch angle', 'backspin', 'spin rate', 'data driven'],
    slice_fix: ['slice', 'hook', 'ball flight', 'aim line', 'club path'],
    practice: ['practice', 'drill', 'training', 'range session', 'muscle memory'],
    indoor: ['indoor', 'simulator', 'launch monitor', 'bad weather', 'rain'],
    lessons: ['lesson', 'pro', 'coach', 'instruction', 'golf professional'],
    fitness: ['fitness', 'flexibility', 'mobility', 'core', 'strength'],
  };
  
  const found = {};
  for (const [theme, keywords] of Object.entries(themes)) {
    found[theme] = keywords.some(kw => text.includes(kw));
  }
  return found;
}

function buildHooks(items, themes) {
  const hooks = [];
  const seen = new Set();
  
  // From news headlines
  items.slice(0, 8).forEach((item, i) => {
    const text = item.title || item.description || '';
    if (text.length < 15) return;
    
    const hook = text.length > 65 ? text.slice(0, 62) + '...' : text;
    const key = hook.toLowerCase().slice(0, 35);
    if (seen.has(key)) return;
    seen.add(key);
    
    // Determine freshness based on source recency
    const isRecent = item.publishedAt || item.date || item.fetched_at;
    const daysOld = isRecent ? Math.floor((Date.now() - new Date(isRecent).getTime()) / 86400000) : 2;
    const freshness = Math.max(5, 10 - daysOld);
    
    hooks.push({
      idea_id: `yt-hook-${Date.now()}-${i}`,
      source: item.source || 'synthesized',
      hook_text: hook,
      description: (item.description || '').slice(0, 120),
      freshness_score: freshness,
      theme_signal: Object.entries(themes).filter(([, v]) => v).map(([k]) => k)[0] || 'general',
    });
  });
  
  // From top themes, generate curiosity hooks
  const themeHooks = [
    { theme: 'swing_speed', hook: 'How fast should your club head speed actually be?', caption: 'Most amateurs are leaving 20+ yards on the table. Here\'s what TrackMan benchmarking shows.' },
    { theme: 'slice_fix', hook: 'That slice won\'t fix itself with the same swing.', caption: 'TrackMan found the real cause in 3 swings. Here\'s what it showed.' },
    { theme: 'trackman', hook: 'Your launch monitor data is telling you exactly what to fix.', caption: 'Stop guessing. Stop watching YouTube. Let TrackMan show you the exact problem.' },
    { theme: 'indoor', hook: 'Rain season. Your game doesn\'t have to stop.', caption: 'Indoor golf in Johannesburg means consistent practice 365 days a year. Here\'s what that does for your handicap.' },
    { theme: 'short_game', hook: 'Short game practice that actually transfers to the course.', caption: 'Most short game drills are useless. Here\'s what TrackMan data says actually works.' },
    { theme: 'lessons', hook: 'When was the last time a golf pro watched your actual swing?', caption: 'Not a tip. A TrackMan session gives you data, not opinions.' },
  ];
  
  themeHooks.forEach((th, i) => {
    if (!themes[th.theme]) return;
    const key = th.hook.toLowerCase().slice(0, 35);
    if (seen.has(key)) return;
    seen.add(key);
    
    hooks.push({
      idea_id: `yt-theme-${Date.now()}-${i}`,
      source: 'theme_signal',
      hook_text: th.hook,
      caption: th.caption,
      freshness_score: 8,
      theme_signal: th.theme,
    });
  });
  
  return hooks.slice(0, 15);
}

function run() {
  const updated = new Date().toISOString();
  
  // Try external sources in order
  let articles = tryGoogleNews() || tryGolfRSS();
  let dataSource = articles ? (tryGoogleNews() ? 'newsapi' : 'rss_feeds') : 'synthesized';
  
  // Fallback: synthesize from existing data
  if (!articles || articles.length === 0) {
    const existing = synthesizeFromExisting();
    articles = [...(existing.news || []), ...(existing.reddit || [])];
    dataSource = 'golf_news_reddit_fallback';
  }
  
  if (articles.length === 0) {
    // All external sources blocked - generate honest synthetic trend data
    // This is better than empty data: it's labeled, structured, and still actionable
    const existingIdeas = (() => {
      try {
        const ci = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'content-ideas.json'), 'utf8'));
        return ci.ideas || [];
      } catch(e) { return []; }
    })();
    
    const themes = { swing_speed: true, short_game: true, trackman: true, slice_fix: true, indoor: true };
    
    // Derive hooks from existing content ideas
    const hooks = existingIdeas.slice(0, 8).map((idea, i) => ({
      idea_id: `yt-synth-${Date.now()}-${i}`,
      source: 'content_ideas_synthesis',
      hook_text: (idea.hook || idea.title || '').slice(0, 70),
      description: (idea.caption || idea.source_reason || '').slice(0, 120),
      freshness_score: idea.freshness_score || 7,
      theme_signal: idea.topic_cluster || 'general',
    }));
    
    // Add SA-market specific hooks as fallback
    const saHooks = [
      { hook: 'That slice costing you yards off the tee? TrackMan found it in 3 swings.', theme: 'slice_fix' },
      { hook: 'How fast should your club head speed actually be? Pros average 112 mph.', theme: 'swing_speed' },
      { hook: 'Your launch monitor data is telling you exactly what to fix.', theme: 'trackman' },
      { hook: 'Rain season. Your game doesn\'t have to stop. Indoor golf in Johannesburg.', theme: 'indoor' },
      { hook: 'Short game practice that actually transfers to the course.', theme: 'short_game' },
    ];
    saHooks.forEach((sh, i) => {
      hooks.push({
        idea_id: `yt-sa-${Date.now()}-${i}`,
        source: 'sa_market_synthesis',
        hook_text: sh.hook,
        description: 'SA-market specific hook synthesized from proven winning angles',
        freshness_score: 8,
        theme_signal: sh.theme,
      });
    });
    
    const output = {
      updated,
      data_source: 'synthetic_sa_market',
      videos_found: 0,
      top_videos: [],
      articles_sourced: [],
      trending_themes: themes,
      hooks: hooks.slice(0, 12),
      summary: {
        top_theme: 'swing_speed_data',
        source: 'synthetic',
        notes: 'All external sources blocked - using SA-market synthesis from proven angles. Trust but verify.',
      },
      _synthetic: true,
    };
    
    fs.writeFileSync(DATA_FILE, JSON.stringify(output, null, 2));
    console.log('YouTube Trends: external blocked - ' + hooks.length + ' SA-market hooks synthesized');
    console.log('NOTE: YouTube trends are synthetic - external scraping blocked by all sources');
    return output;
  }
  
  const themes = extractThemes(articles);
  const hooks = buildHooks(articles, themes);
  
  // Always supplement with SA-market hooks regardless of how much real data we got
  // This ensures YouTube Ideas always has something to work with
  const saHooks = [
    { hook: 'That slice costing you yards off the tee? TrackMan found it in 3 swings.', theme: 'slice_fix' },
    { hook: 'How fast should your club head speed actually be? Pros average 112 mph.', theme: 'swing_speed' },
    { hook: 'Your launch monitor data is telling you exactly what to fix.', theme: 'trackman' },
    { hook: 'Rain season. Your game doesn\'t have to stop. Indoor golf in Johannesburg.', theme: 'indoor' },
    { hook: 'Short game practice that actually transfers to the course.', theme: 'short_game' },
    { hook: 'When was the last time a golf pro watched your actual swing on a launch monitor?', theme: 'lessons' },
  ];
  const seen = new Set(hooks.map(h => h.hook_text.toLowerCase().slice(0, 35)));
  saHooks.forEach((sh, i) => {
    const key = sh.hook.toLowerCase().slice(0, 35);
    if (!seen.has(key)) {
      hooks.push({
        idea_id: `yt-sa-${Date.now()}-${i}`,
        source: 'sa_market_always',
        hook_text: sh.hook,
        description: 'SA-market hook - always included',
        freshness_score: 8,
        theme_signal: sh.theme,
      });
      seen.add(key);
    }
  });
  
  // Top theme
  const topThemeEntry = Object.entries(themes).filter(([, v]) => v)[0];
  const topTheme = topThemeEntry ? topThemeEntry[0].replace(/_/g, ' ') : 'general golf';
  
  // If we got very few external articles, mark as synthetic — not enough for real trends
  const isInsufficientExternal = articles.length > 0 && articles.length < 3;
  const effectiveSource = isInsufficientExternal ? 'synthetic_sa_market' : dataSource;
  const output = {
    updated,
    data_source: effectiveSource,
    videos_found: articles.length,
    top_videos: [], // No YouTube IDs without API
    articles_sourced: articles.slice(0, 10),
    trending_themes: themes,
    hooks,
    summary: {
      top_theme: topTheme,
      source: effectiveSource,
      notes: isInsufficientExternal ? 'Insufficient external articles (< 3) — supplemented with SA-market synthesis' : 'Golf RSS feeds',
    },
    _synthetic: isInsufficientExternal,
  };
  
  fs.writeFileSync(DATA_FILE, JSON.stringify(output, null, 2));
  console.log('YouTube Trends: ' + articles.length + ' articles, ' + hooks.length + ' hooks, top theme: ' + topTheme + ' (' + effectiveSource + ')');
  
  return output;
}

module.exports = { run };
if (require.main === module) run();