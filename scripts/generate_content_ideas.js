#!/usr/bin/env node
/**
 * generate_content_ideas.js
 * Reads IG analytics + hook data + golf news → generates fresh content ideas
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUT_FILE = path.join(DATA_DIR, 'content-ideas.json');

function readJson(name) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA_DIR, name), 'utf8')); }
  catch(e) { return {}; }
}

function run() {
  const ig = readJson('ig-analytics.json');
  const news = readJson('golf-news.json');
  const hooks = readJson('hook-bank.json');
  const used = readJson('used-items.json');
  const ab = readJson('ab-tests.json');
  
  const suppressedHooks = new Set((used.suppressed_hooks || []).map(h => h.id));
  const suppressedIdeas = new Set((used.suppressed_ideas || []).map(i => i.id));
  
  const ideas = [];
  let id = 1;
  const date = new Date().toISOString().split('T')[0];
  
  // 1. Top hooks → content ideas
  const topPosts = (ig.posts || []).sort((a, b) => (parseFloat(b.engagementRate) || 0) - (parseFloat(a.engagementRate) || 0)).slice(0, 10);
  topPosts.forEach(p => {
    if (suppressedHooks.has(p.hook_id)) return;
    if ((parseFloat(p.engagementRate) || 0) < 2) return;
    
    const hook = p.hook_text || p.captionPreview || '';
    if (hook.length < 10) return;
    
    ideas.push({
      idea_id: `ig-hook-${date}-${id++}`,
      title: hook,
      hook: hook,
      format: p.format_type || 'static',
      source_reason: `Hook generated ${p.engagementRate}% eng, ${p.reach} reach`,
      best_cta: 'Link in bio · Book your session',
      freshness_score: p.engagementRate > 4 ? 9 : p.engagementRate > 3 ? 7 : 5,
      difficulty: 'easy',
      topic_cluster: p.topic_cluster || 'general',
      used: false,
      priority: p.engagementRate > 4 ? 'today' : 'this-week',
    });
  });
  
  // 2. Slice/data hooks (proven winner)
  const sliceHook = {
    idea_id: `slice-fix-${date}-a`,
    title: "THAT SLICE COSTING YOU YARDS?",
    hook: "That slice costing you yards off the tee? TrackMan found it in 3 swings.",
    format: 'static',
    source_reason: 'All-time winning hook formula - 5.77% engagement',
    best_cta: 'TrackMan your swing · Book from R250',
    freshness_score: 9,
    difficulty: 'easy',
    topic_cluster: 'technique',
    used: false,
    priority: 'today',
  };
  if (!suppressedIdeas.has(sliceHook.idea_id)) ideas.push(sliceHook);
  
  // 3. Coaching angle
  const coachingHook = {
    idea_id: `coaching-${date}-a`,
    title: "YOUR GOLF NEEDS A MENTOR",
    hook: "Your golf doesn't need more practice. It needs smarter practice.",
    format: 'static',
    source_reason: 'Coaching content hit 4.99% engagement - community/humor angle',
    best_cta: 'Coaching from R850 · TrackMan + certified instructors',
    freshness_score: 8,
    difficulty: 'easy',
    topic_cluster: 'coaching',
    used: false,
    priority: 'today',
  };
  if (!suppressedIdeas.has(coachingHook.idea_id)) ideas.push(coachingHook);
  
  // 4. Custom fitting
  const fittingHook = {
    idea_id: `fitting-${date}-a`,
    title: "YOUR CLUBS ARE HOLDING YOU BACK",
    hook: "Off-the-rack clubs are built for average swings. Your swing isn't average.",
    format: 'static',
    source_reason: 'Custom fitting consistently 4%+-engagement - high-intent buyers',
    best_cta: 'TrackMan Fitting · from R900',
    freshness_score: 7,
    difficulty: 'easy',
    topic_cluster: 'equipment',
    used: false,
    priority: 'this-week',
  };
  if (!suppressedIdeas.has(fittingHook.idea_id)) ideas.push(fittingHook);
  
  // 5. Golf news ideas
  (news.news || []).slice(0, 3).forEach(n => {
    if (n.content_angle_score < 7) return;
    ideas.push({
      idea_id: `news-${date}-${id++}`,
      title: n.title,
      hook: n.title,
      format: n.title.match(/video|highlight/i) ? 'reel' : 'static',
      source_reason: `Golf news: ${n.source}`,
      best_cta: 'Read more via link in bio',
      freshness_score: 8,
      difficulty: 'medium',
      topic_cluster: n.topic_cluster || 'general',
      used: false,
      priority: 'today',
    });
  });
  
  // 6. Reel ideas from top performing posts
  const reels = [
    { title: "Show TrackMan data overlay - before/after swing", format: 'reel', freshness_score: 7 },
    { title: "Coach Catherine explains a common swing flaw", format: 'reel', freshness_score: 8 },
    { title: "Time-lapse of a full fitting session", format: 'reel', freshness_score: 7 },
    { title: "POV: First time at Swing Shack", format: 'reel', freshness_score: 9 },
    { title: "Quick tip: How to read your launch monitor data", format: 'reel', freshness_score: 7 },
  ];
  reels.forEach(r => {
    ideas.push({
      idea_id: `reel-${date}-${id++}`,
      ...r,
      hook: r.title,
      source_reason: 'Reel format outperforms static for golf content',
      best_cta: 'Save this · Share with a golfer',
      difficulty: 'medium',
      topic_cluster: 'general',
      used: false,
      priority: 'this-week',
    });
  });
  
  // Sort by freshness_score descending, take top 12
  ideas.sort((a, b) => b.freshness_score - a.freshness_score);
  const result = {
    updated: new Date().toISOString(),
    total: ideas.length,
    ideas: ideas.slice(0, 15),
    post_today: ideas.filter(i => i.priority === 'today').slice(0, 5),
    this_week: ideas.filter(i => i.priority === 'this-week').slice(0, 8),
    reels: ideas.filter(i => i.format === 'reel'),
    statics: ideas.filter(i => i.format === 'static'),
    suppressed_count: suppressedIdeas.size + suppressedHooks.size,
  };
  
  fs.writeFileSync(OUT_FILE, JSON.stringify(result, null, 2));
  console.log(`✅ Content ideas: ${ideas.length} generated (${result.suppressed_count} suppressed)`);
  return result;
}

run();