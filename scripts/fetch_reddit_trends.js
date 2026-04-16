#!/usr/bin/env node
/**
 * fetch_reddit_trends.js
 * Pulls trending posts from r/golf and r/golftips
 */
const fs = require('fs');
const path = require('path');

const DATA_FILE = path.join(__dirname, '..', 'data', 'reddit-trends.json');

function run() {
  try {
    const { execSync } = require('child_process');
    
    const subreddits = ['golf', 'golftips'];
    const allTrends = [];
    
    for (const sub of subreddits) {
      try {
        const cmd = `curl -s -H "User-Agent: Mozilla/5.0" "https://www.reddit.com/r/${sub}/hot.json?limit=20" 2>/dev/null`;
        const raw = execSync(cmd, { encoding: 'utf8', timeout: 15000 });
        const data = JSON.parse(raw);
        
        const posts = data.data?.children || [];
        for (const post of posts) {
          const d = post.data;
          if (d.over_18) continue; // skip NSFW
          
          // Classify intent
          const title = (d.title || '').toLowerCase();
          const intent = [];
          if (title.match(/slice|hook|swing.?problem|fix|help/i)) intent.push('fix_intent');
          if (title.match(/beginner|start|first.?time|new.?to/i)) intent.push('beginner_help');
          if (title.match(/buy|which|should.?i|recommend|best/i)) intent.push('buying_intent');
          if (title.match(/fitting|club.?fit|driver|irons|wedges/i)) intent.push('fitting_intent');
          if (title.match(/simulator|indoor|launch.?monitor|trackman/i)) intent.push('simulator_interest');
          if (title.match(/distance|yard|driver|speed/i)) intent.push('distance_problem');
          if (title.match(/humor|funny|laugh|i.?don't|cart.?girl/i)) intent.push('humor');
          if (title.match(/couple|friends|group|social|party/i)) intent.push('social_golf');
          if (!intent.length) intent.push('general');
          
          // Check for trend repetition
          const words = title.split(' ').filter(w => w.length > 5);
          const keyTerms = words.slice(0, 5).join(' ');
          
          allTrends.push({
            subreddit: sub,
            title: d.title,
            score: d.score || 0,
            comments_count: d.num_comments || 0,
            url: d.url || '',
            permalink: `https://reddit.com${d.permalink}`,
            created_utc: new Date((d.created_utc || 0) * 1000).toISOString(),
            intent,
            key_terms: keyTerms,
            is_self: d.is_self || false,
            selftext_snippet: (d.selftext || '').substring(0, 200),
          });
        }
      } catch (e) {
        // Subreddit failed, continue
      }
    }
    
    // Sort by score descending
    allTrends.sort((a, b) => b.score - a.score);
    
    // Build trend clusters (repeated topics)
    const clusters = {};
    allTrends.forEach(t => {
      t.key_terms.split(' ').forEach(term => {
        if (term.length > 5) {
          clusters[term] = (clusters[term] || 0) + t.score;
        }
      });
    });
    const topClusters = Object.entries(clusters)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20)
      .map(([term, score]) => ({ term, score }));
    
    // Identify hot pain points
    const painPoints = allTrends.filter(t => 
      t.score > 100 && 
      (t.intent.includes('fix_intent') || t.intent.includes('distance_problem'))
    ).slice(0, 5).map(t => t.title);
    
    const result = {
      updated: new Date().toISOString(),
      total_trends: allTrends.length,
      trends: allTrends.slice(0, 30),
      trend_clusters: topClusters,
      hot_pain_points: painPoints,
      top_posts: allTrends.slice(0, 5),
    };
    
    fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
    console.log(`✅ Reddit: ${allTrends.length} trends, ${painPoints.length} hot pain points`);
    return result;
  } catch (e) {
    console.log(`⚠️  Reddit fetch failed: ${e.message.slice(-100)}`);
    return null;
  }
}

module.exports = { run };
if (require.main === module) run();