#!/usr/bin/env node
/**
 * fetch_golf_news.js
 * Fetches SA + world golf news from free RSS/HTML sources
 */
const fs = require('fs');
const path = require('path');

const DATA_FILE = path.join(__dirname, '..', 'data', 'golf-news.json');
const LOG_FILE = path.join(__dirname, '..', 'logs', 'daily-run.log');

const SOURCES = [
  { name: 'GolfRSA', url: 'https://www.golfrsa.co.za/news/' },
  { name: 'Sunshine Tour', url: 'https://sunshinetour.com/news/' },
  { name: 'News24 Golf', url: 'https://www.news24.com/Sport/Golf' },
];

async function scrapePage(url) {
  try {
    const { execSync } = require('child_process');
    const cmd = `curl -s -L -A "Mozilla/5.0" --max-time 15 "${url}" 2>/dev/null | head -c 50000`;
    const html = execSync(cmd, { encoding: 'utf8', timeout: 20000 });
    
    // Very basic extraction - find article titles
    const titleMatches = html.match(/<h[23][^>]*>([^<]{10,80})<\/h[23]>/gi) || [];
    const linkMatches = html.match(/href="(\/[^"]*(?:news|article|golf)[^"]*)"/gi) || [];
    
    const articles = [];
    for (let i = 0; i < Math.min(titleMatches.length, 8); i++) {
      const title = titleMatches[i].replace(/<[^>]+>/g, '');
      let url = '';
      if (linkMatches[i]) {
        url = linkMatches[i].replace('href="', '').replace('"', '');
        if (url.startsWith('/')) {
          const base = new URL(url).origin || 'https://www.news24.com';
          // extract base from original URL
          const parsedUrl = new URL(url);
          url = url.startsWith('http') ? url : parsedUrl.protocol + '//' + parsedUrl.host + url;
        }
      }
      if (title && title.length > 15) {
        articles.push({
          title: title.trim(),
          source: url.includes('news24') ? 'News24' : url.includes('golfrsa') ? 'GolfRSA' : url.includes('sunshine') ? 'Sunshine Tour' : 'Golf',
          url: url,
          date: new Date().toISOString().split('T')[0],
          local_relevance_score: title.match(/south africa|johannesburg|sa|ernest|oudtshoorn|cape town|durban/i) ? 8 : 5,
          content_angle_score: title.match(/golf|swingshack|indoor|trackman|fitting|lesson| simulator/i) ? 8 : 5,
          topic_cluster: title.match(/fitting|clubs|equipment/i) ? 'equipment' :
                        title.match(/lesson|coach|teaching|swing/i) ? 'coaching' :
                        title.match(/tournament|winner|score/i) ? 'tournament' : 'general',
        });
      }
    }
    return articles;
  } catch (e) {
    return [];
  }
}

async function fetchAll() {
  const allNews = [];
  
  // Try RSS feeds first (more reliable)
  const RSS_FEEDS = [
    { name: 'News24 Golf RSS', url: 'https://www.news24.com/Sport/Golf/rss' },
  ];
  
  for (const feed of RSS_FEEDS) {
    try {
      const { execSync } = require('child_process');
      const cmd = `curl -s -L --max-time 10 "${feed.url}" 2>/dev/null | head -c 30000`;
      const rss = execSync(cmd, { encoding: 'utf8', timeout: 15000 });
      
      const items = rss.match(/<item>(.*?)<\/item>/gis) || [];
      for (const item of items.slice(0, 8)) {
        const title = (item.match(/<title[^>]*>([^<]+)<\/title>/i) || [])[1] || '';
        const link = (item.match(/<link[^>]*>([^<]+)<\/link>/i) || [])[1] || '';
        const pubDate = (item.match(/<pubDate[^>]*>([^<]+)<\/pubDate>/i) || [])[1] || '';
        const description = (item.match(/<description[^>]*>([^<]+)<\/description>/i) || [])[1] || '';
        
        if (title && title.length > 10) {
          allNews.push({
            title: title.replace(/<!\[CDATA\[|\]\]>/g, '').trim(),
            source: 'News24 Golf',
            url: link,
            published_date: pubDate ? new Date(pubDate).toISOString().split('T')[0] : new Date().toISOString().split('T')[0],
            local_relevance_score: title.match(/south africa|johannesburg|sa golf/i) ? 9 : 6,
            content_angle_score: 7,
            topic_cluster: title.match(/fitting|equipment|clubs/i) ? 'equipment' :
                          title.match(/lesson|coach|teaching/i) ? 'coaching' :
                          title.match(/liv|pga|tour|tournament/i) ? 'tournament' : 'general',
            summary: description.replace(/<[^>]+>/g, '').substring(0, 150),
          });
        }
      }
    } catch (e) {
      // RSS failed, continue
    }
  }
  
  // Deduplicate by title
  const seen = new Set();
  const unique = allNews.filter(n => {
    const key = n.title.substring(0, 50);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  
  const result = {
    updated: new Date().toISOString(),
    source: 'News24 RSS + web scraping',
    news: unique.slice(0, 12),
    post_ideas: unique
      .filter(n => n.content_angle_score >= 7)
      .slice(0, 3)
      .map(n => ({
        headline: n.title,
        format: n.title.match(/video|watch|highlight/i) ? 'reel' : 'static',
        source: 'golf-news',
        reason: `Breaking: ${n.title.substring(0, 50)}`,
      })),
    story_today: unique.filter(n => n.local_relevance_score >= 8).slice(0, 2),
    reel_today: unique.filter(n => n.topic_cluster === 'tournament').slice(0, 2),
  };
  
  fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
  
  const log = fs.readFileSync(LOG_FILE, 'utf8').split('\n').slice(-50).join('\n');
  fs.writeFileSync(LOG_FILE, log + `\n[${new Date().toISOString()}] fetch_golf_news: ${unique.length} articles collected`);
  
  console.log(`✅ Golf news: ${unique.length} articles`);
  return result;
}

fetchAll().catch(e => {
  fs.writeFileSync(LOG_FILE, `\n[${new Date().toISOString()}] ERROR fetch_golf_news: ${e.message}`);
  process.exit(1);
});