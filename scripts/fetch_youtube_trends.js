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

// YouTube Data API v3 key - provided by Christelle Apr 16 2026
const YOUTUBE_API_KEY = (() => {
  try {
    const credPath = path.join(__dirname, '..', '..', 'clients', 'swing-shack', 'credentials', 'youtube-api.json');
    console.error('Loading YouTube API key from: ' + credPath);
    const cred = JSON.parse(fs.readFileSync(credPath, 'utf8'));
    console.error('YouTube API key loaded: ' + (cred.api_key ? 'YES (' + cred.api_key.slice(0, 10) + '...)' : 'NO'));
    return cred.api_key || null;
  } catch(e) {
    console.error('Failed to load YouTube API key: ' + e.message);
    return null;
  }
})();

function fetchUrl(url, timeout = 15000) {
  try {
    const cmd = `curl -s --max-time 12 -L -A "Mozilla/5.0" "${url.replace(/"/g, '\\"')}" 2>/dev/null | head -c 20000`;
    return execSync(cmd, { encoding: 'utf8', timeout });
  } catch(e) {
    return '';
  }
}

function tryYouTubeAPI() {
  if (!YOUTUBE_API_KEY) return null;
  try {
    const queries = ['golf swing tips', 'golf lesson tutorial', 'golf simulator indoor', 'golf practice drill'];
    const allVideos = [];
    
    for (const query of queries) {
      try {
        const encodedQuery = encodeURIComponent(query);
        const cmd = 'curl -s --max-time 15 "https://www.googleapis.com/youtube/v3/search?q=' + encodedQuery + '&part=snippet&regionCode=ZA&type=video&maxResults=5&key=' + YOUTUBE_API_KEY + '" 2>/dev/null';
        console.error('[DEBUG] Running: ' + cmd.slice(0, 80) + '...');
        const raw = execSync(cmd, { encoding: 'utf8', timeout: 20000 });
        console.error('[DEBUG] Response length: ' + raw.length);
        const data = JSON.parse(raw);
        if (data.error) {
          console.error('[DEBUG] YouTube API error: ' + JSON.stringify(data.error));
          continue;
        }
        if (data.items && data.items.length > 0) {
          for (const item of data.items) {
            if (item.id?.videoId) {
              allVideos.push({
                title: item.snippet?.title || '',
                description: item.snippet?.description || '',
                videoId: item.id.videoId,
                channelTitle: item.snippet?.channelTitle || '',
                publishedAt: item.snippet?.publishedAt,
                source: 'youtube_api_v3',
                query,
              });
            }
          }
        }
      } catch(e) {
        console.error('[DEBUG] Query "' + query + '" failed: ' + e.message.slice(-100));
      }
    }
    
    if (allVideos.length > 0) {
      const seen = new Set();
      const deduped = allVideos.filter(v => {
        if (seen.has(v.videoId)) return false;
        seen.add(v.videoId);
        return true;
      });
      return deduped;
    }
  } catch(e) {
    console.error('YouTube API error: ' + e.message.slice(-100));
  }
  return null;
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
  let articles = [];
  let dataSource = 'none';
  let youtubeVideos = [];
  
  // Priority 1: YouTube Data API v3 (LIVE trending golf content in ZA)
  const ytVideos = tryYouTubeAPI();
  if (ytVideos && ytVideos.length > 0) {
    youtubeVideos = ytVideos;
    articles = ytVideos.map(v => ({ title: v.title, description: v.description, source: v.channelTitle, publishedAt: v.publishedAt }));
    dataSource = 'youtube_api_v3';
    console.log('YouTube Trends: ' + ytVideos.length + ' trending videos from YouTube API');
  }
  
  // Priority 2: Google News API
  if (articles.length === 0) {
    const newsArticles = tryGoogleNews();
    if (newsArticles && newsArticles.length > 0) {
      articles = newsArticles;
      dataSource = 'newsapi';
      console.log('YouTube Trends: ' + newsArticles.length + ' articles from NewsAPI');
    }
  }
  
  // Priority 3: Golf RSS feeds
  if (articles.length === 0) {
    const rssArticles = tryGolfRSS();
    if (rssArticles && rssArticles.length > 0) {
      articles = rssArticles;
      dataSource = 'rss_feeds';
      console.log('YouTube Trends: ' + rssArticles.length + ' articles from RSS');
    }
  }
  
  // Fallback: synthesize from existing data
  if (articles.length === 0) {
    const existing = synthesizeFromExisting();
    articles = [...(existing.news || []), ...(existing.reddit || [])];
    dataSource = 'golf_news_reddit_fallback';
  }
  
  // Final fallback: SA-market synthesis (always works)
  if (articles.length === 0 || dataSource === 'golf_news_reddit_fallback') {
    const existingIdeas = (() => {
      try {
        const ci = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'content-ideas.json'), 'utf8'));
        return ci.ideas || [];
      } catch(e) { return []; }
    })();
    
    const themes = { swing_speed: true, short_game: true, trackman: true, slice_fix: true, indoor: true };
    
    const hooks = existingIdeas.slice(0, 8).map((idea, i) => ({
      idea_id: `yt-synth-${Date.now()}-${i}`,
      source: 'content_ideas_synthesis',
      hook_text: (idea.hook || idea.title || '').slice(0, 70),
      description: (idea.caption || idea.source_reason || '').slice(0, 120),
      freshness_score: idea.freshness_score || 7,
      theme_signal: idea.topic_cluster || 'general',
    }));
    
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
        notes: 'All external sources blocked - using SA-market synthesis. YouTube API key available but sources unavailable.',
      },
      _synthetic: true,
    };
    
    fs.writeFileSync(DATA_FILE, JSON.stringify(output, null, 2));
    console.log('YouTube Trends: all external sources blocked - ' + hooks.length + ' SA-market hooks synthesized');
    process.exit(1);
  }
  
  const themes = extractThemes(articles);
  
  const saHooks = [
    { hook: 'That slice costing you yards off the tee? TrackMan found it in 3 swings.', theme: 'slice_fix' },
    { hook: 'How fast should your club head speed actually be? Pros average 112 mph.', theme: 'swing_speed' },
    { hook: 'Your launch monitor data is telling you exactly what to fix.', theme: 'trackman' },
    { hook: 'Rain season. Your game doesn\'t have to stop. Indoor golf in Johannesburg.', theme: 'indoor' },
    { hook: 'Short game practice that actually transfers to the course.', theme: 'short_game' },
    { hook: 'When was the last time a golf pro watched your actual swing on a launch monitor?', theme: 'lessons' },
  ];
  const seen = new Set();
  const allHooks = [];
  
  articles.slice(0, 8).forEach((item, i) => {
    const text = item.title || item.description || '';
    if (text.length < 15) return;
    const hook = text.length > 65 ? text.slice(0, 62) + '...' : text;
    const key = hook.toLowerCase().slice(0, 35);
    if (seen.has(key)) return;
    seen.add(key);
    const isRecent = item.publishedAt || item.date || item.fetched_at;
    const daysOld = isRecent ? Math.floor((Date.now() - new Date(isRecent).getTime()) / 86400000) : 2;
    const freshness = Math.max(5, 10 - daysOld);
    allHooks.push({ idea_id: `yt-hook-${Date.now()}-${i}`, source: item.source || 'article', hook_text: hook, description: (item.description || '').slice(0, 120), freshness_score: freshness, theme_signal: Object.entries(themes).filter(([, v]) => v)[0]?.[0] || 'general' });
  });
  
  saHooks.forEach((sh, i) => {
    const key = sh.hook.toLowerCase().slice(0, 35);
    if (!seen.has(key)) {
      allHooks.push({ idea_id: `yt-sa-${Date.now()}-${i}`, source: 'sa_market_always', hook_text: sh.hook, description: 'SA-market hook - always included', freshness_score: 8, theme_signal: sh.theme });
      seen.add(key);
    }
  });
  
  const topThemeEntry = Object.entries(themes).filter(([, v]) => v)[0];
  const topTheme = topThemeEntry ? topThemeEntry[0].replace(/_/g, ' ') : 'general golf';
  
  const output = {
    updated,
    data_source: dataSource,
    videos_found: youtubeVideos.length,
    top_videos: youtubeVideos.slice(0, 10),
    articles_sourced: articles.slice(0, 10),
    trending_themes: themes,
    hooks: allHooks.slice(0, 15),
    summary: {
      top_theme: topTheme,
      source: dataSource,
      notes: dataSource === 'youtube_api_v3' ? 'Live YouTube trending data for ZA region' : 'Golf trends from ' + dataSource,
    },
  };
  
  fs.writeFileSync(DATA_FILE, JSON.stringify(output, null, 2));
  console.log('YouTube Trends: ' + articles.length + ' articles, ' + allHooks.length + ' hooks, top theme: ' + topTheme + ' (' + dataSource + ')');
  
  return output;
}

module.exports = { run };
if (require.main === module) run();