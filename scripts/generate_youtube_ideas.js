#!/usr/bin/env node
/**
 * generate_youtube_ideas.js
 * Reads YouTube trends + hook bank + golf news → generates Shorts/Reels ideas
 * Converts what's trending on YouTube into actionable content for Swing Shack
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUT_FILE = path.join(DATA_DIR, 'youtube-ideas.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch(e) { return {}; }
}

function run() {
  const yt = readJson('youtube-trends.json');
  const hooks = readJson('hook-bank.json');
  const used = readJson('used-items.json');
  const news = readJson('golf-news.json');
  
  const suppressedHooks = new Set((used.suppressed_hooks || []).map(h => h.id));
  const suppressedIdeas = new Set((used.suppressed_ideas || []).map(i => i.id));
  
  const ideas = [];
  let id = 1;
  const date = new Date().toISOString().split('T')[0];
  
  // 1. Trending YouTube hooks → Shorts ideas
  const ytHooks = yt.hooks || [];
  ytHooks.forEach(h => {
    if (suppressedHooks.has(h.idea_id)) return;
    
    ideas.push({
      idea_id: `yt-shorts-${date}-${id++}`,
      title: h.hook_text,
      hook: h.hook_text,
      format: 'shorts',
      source: 'youtube_trending',
      source_reason: `Trending on YouTube (${h.views} views) under ${h.topic}`,
      best_cta: 'Link in bio · Book your TrackMan session',
      freshness_score: h.freshness_score || 8,
      difficulty: 'easy',
      topic_cluster: 'trending',
      used: false,
      video_url: h.url,
      is_youtube_remix: true,
    });
  });
  
  // 2. Trending themes → local angle ideas
  const themes = yt.trending_themes || {};
  const themeIdeas = [
    {
      key: 'swing_speed',
      hook: 'How fast should your club head speed be?',
      caption: 'Club head speed is the easiest way to add distance. Here\'s what TrackMan benchmarking tells you about yours.',
      topic: 'Performance Data',
    },
    {
      key: 'short_game',
      hook: 'That chip that always comes up short? TrackMan knows why.',
      caption: 'Short game drills are great, but TrackMan shows you exactly what\'s causing the chunked chips.',
      topic: 'Short Game',
    },
    {
      key: 'trackman_data',
      hook: 'Your launch monitor data is telling you exactly what to fix.',
      caption: 'TrackMan doesn\'t lie. Here\'s how to read your numbers and make real improvement.',
      topic: 'TrackMan Analysis',
    },
    {
      key: 'simulator',
      hook: 'Rain season is here. Your game doesn\'t have to stop.',
      caption: 'Indoor golf in Johannesburg means 24/7 practice regardless of weather. Here\'s what that does for your handicap.',
      topic: 'Indoor Golf',
    },
  ];
  
  themeIdeas.forEach(ti => {
    if (!themes[ti.key]) return; // Only generate if that theme is trending
    if (suppressedIdeas.has(`yt-theme-${ti.key}`)) return;
    
    ideas.push({
      idea_id: `yt-theme-${date}-${id++}`,
      title: ti.hook,
      hook: ti.hook,
      caption: ti.caption,
      format: 'static',
      source: 'youtube_trending_theme',
      source_reason: `Theme trending on YouTube: ${ti.key.replace(/_/g, ' ')}`,
      best_cta: 'Link in bio · Book your session',
      freshness_score: 8,
      difficulty: 'easy',
      topic_cluster: 'trending',
      used: false,
      is_youtube_remix: false,
    });
  });
  
  // 3. Golf news → local Swing Shack angle
  const topNews = (news.articles || []).slice(0, 3);
  topNews.forEach(article => {
    if (suppressedIdeas.has(`yt-news-${article.link?.slice(-20)}`)) return;
    
    ideas.push({
      idea_id: `yt-news-${date}-${id++}`,
      title: `SA Golf: ${article.title?.slice(0, 60)}`,
      hook: `While SA golf was watching this...`,
      caption: `Local take: Swing Shack has the same tech the pros use. TrackMan analysis from R250.`,
      format: 'static',
      source: 'golf_news',
      source_reason: `News hook: ${article.title?.slice(0, 50)}`,
      best_cta: 'Book a TrackMan session',
      freshness_score: 7,
      difficulty: 'medium',
      topic_cluster: 'news_angle',
      used: false,
    });
  });
  
  // 4. Remix ideas — IG Hook Bank winners → Shorts
  const provenHooks = (hooks.proven_hooks || []).slice(0, 3);
  provenHooks.forEach(h => {
    if (suppressedHooks.has(h.hook_id)) return;
    
    ideas.push({
      idea_id: `yt-remix-${date}-${id++}`,
      title: `[SHORTS] ${h.hook_text?.slice(0, 55)}`,
      hook: h.hook_text,
      caption: `This hook worked on IG. Now try it as a Shorts. ${h.engagement_rate ? h.engagement_rate + '% eng rate.' : ''}`,
      format: 'shorts',
      source: 'ig_hook_remix',
      source_reason: `IG winning hook (${h.engagement_rate || 'no data'} eng rate) → Shorts format`,
      best_cta: 'Link in bio',
      freshness_score: h.freshness_score || 7,
      difficulty: 'easy',
      topic_cluster: 'hook_remix',
      used: false,
      is_ig_to_shorts: true,
    });
  });
  
  // 5. SA-specific angles from YouTube data
  const saAngles = [
    { hook: 'Joburg rain season = indoor golf season. Here\'s what to work on.', caption: 'Rain stops outdoor play but not your improvement. TrackMan indoor golf in Johannesburg.' },
    { hook: 'Your handicap won\'t improve by hoping. TrackMan tells you what\'s actually wrong.', caption: 'Stop guessing. A TrackMan session shows you exactly where strokes are being lost.' },
    { hook: 'That slice that comes and goes? It\'s not in your head. It\'s in your data.', caption: 'TrackMan found it in 3 swings. Imagine what a full session reveals.' },
  ];
  
  saAngles.forEach((a, i) => {
    if (suppressedIdeas.has(`yt-sa-${i}`)) return;
    ideas.push({
      idea_id: `yt-sa-${date}-${id++}`,
      title: a.hook,
      hook: a.hook,
      caption: a.caption,
      format: 'shorts',
      source: 'sa_local_angle',
      source_reason: 'SA market local angle from YouTube insights',
      best_cta: 'Book TrackMan session · Link in bio',
      freshness_score: 7,
      difficulty: 'easy',
      topic_cluster: 'sa_local',
      used: false,
    });
  });
  
  const result = {
    updated: new Date().toISOString(),
    ideas_generated: ideas.length,
    by_format: {
      shorts: ideas.filter(i => i.format === 'shorts').length,
      static: ideas.filter(i => i.format === 'static').length,
    },
    by_source: {
      youtube_trending: ideas.filter(i => i.source === 'youtube_trending').length,
      youtube_trending_theme: ideas.filter(i => i.source === 'youtube_trending_theme').length,
      golf_news: ideas.filter(i => i.source === 'golf_news').length,
      ig_hook_remix: ideas.filter(i => i.source === 'ig_hook_remix').length,
      sa_local_angle: ideas.filter(i => i.source === 'sa_local_angle').length,
    },
    ideas: ideas.slice(0, 20), // cap at 20
    top_ideas: ideas.slice(0, 5),
    trending_themes_summary: yt?.summary?.top_theme || 'general golf',
  };
  
  fs.writeFileSync(OUT_FILE, JSON.stringify(result, null, 2));
  console.log(`✅ YouTube Ideas: ${result.ideas_generated} ideas (${result.by_format.shorts} Shorts, ${result.by_format.static} static)`);
  console.log(`   Top source: ${Object.entries(result.by_source).sort((a,b) => b[1]-a[1])[0]?.[0]}`);
  return result;
}

module.exports = { run };
if (require.main === module) run();