#!/usr/bin/env node
/**
 * fetch_postiz_analytics.js
 * Pull IG analytics from Postiz API and normalise to hook-level data
 */
const fs = require('fs');
const path = require('path');
const { loadPostizApiKey } = require('./_lib/postiz-credentials');

const DATA_FILE = path.join(__dirname, '..', 'data', 'ig-analytics.json');

// Postiz credential loaded via shared helper. Never stored as literal.
let API_KEY;
try {
  const c = loadPostizApiKey();
  API_KEY = c.apiKey;
  console.log(`[fetch_postiz_analytics] Postiz credential loaded: source=${c.source}, length=${c.length}`);
} catch (e) {
  console.error(`[fetch_postiz_analytics] ${e.message}`);
  process.exit(2);
}
const INSTAGRAM_ID = 'cmnfoum2703e6ql0yiajgcg21';

async function fetchMedia() {
  const { execSync } = require('child_process');
  
  // Get all posts from Postiz
  const cmd = `curl -s -X POST "https://api.postiz.com/public/v1/post/list" \
    -H "Authorization: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"integrationId":"${INSTAGRAM_ID}","limit":50}' 2>/dev/null`;
  
  try {
    const raw = execSync(cmd, { encoding: 'utf8', timeout: 20000 });
    const data = JSON.parse(raw);
    return data.posts || [];
  } catch (e) {
    // Fallback: try alternative endpoint
    const alt = `curl -s "https://api.postiz.com/public/v1/post?integrationId=${INSTAGRAM_ID}&limit=50" -H "Authorization: ${API_KEY}" 2>/dev/null`;
    try {
      const raw2 = execSync(alt, { encoding: 'utf8', timeout: 20000 });
      return JSON.parse(raw2).posts || [];
    } catch (e2) {
      console.log('Postiz API unavailable:', e2.message.slice(-100));
      return [];
    }
  }
}

function extractHook(caption) {
  if (!caption) return 'unknown';
  // First line or first sentence as hook
  const firstLine = caption.split('\n')[0].trim();
  return firstLine.length > 8 ? firstLine.substring(0, 80) : firstLine;
}

function deriveMetrics(post) {
  const reach = parseInt(post.reach || post.impressions || 0);
  const likes = parseInt(post.likes || post.likeCount || post.like_count || 0);
  const comments = parseInt(post.comments || post.commentsCount || post.comments_count || 0);
  const saves = parseInt(post.saves || post.saved || 0);
  const shares = parseInt(post.shares || post.shared || 0);
  const follows = parseInt(post.follows || post.followsGained || 0);
  
  const engagementRate = reach > 0 ? ((likes + comments) / reach * 100).toFixed(2) : '0.00';
  const saveRate = reach > 0 ? (saves / reach * 100).toFixed(2) : '0.00';
  const shareRate = reach > 0 ? (shares / reach * 100).toFixed(2) : '0.00';
  const followConversion = reach > 0 ? (follows / reach * 100).toFixed(3) : '0.000';
  
  return { engagementRate, saveRate, shareRate, followConversion };
}

async function run() {
  const rawPosts = await fetchMedia();
  
  const posts = rawPosts.map(p => {
    const caption = p.caption || p.content || '';
    const hook = extractHook(caption);
    const metrics = deriveMetrics(p);
    
    // Determine format type
    const format = caption.match(/carousel|slide|#\d/i) ? 'carousel' :
                   caption.match(/reel|video|watch/i) ? 'reel' :
                   caption.match(/story|stories/i) ? 'story' : 'static';
    
    // Topic cluster
    const topic = caption.match(/fitting|clubs|driver|irons|wedges/i) ? 'equipment' :
                  caption.match(/slice|hook|swing|technique|fix/i) ? 'technique' :
                  caption.match(/coach|lesson|learn|training/i) ? 'coaching' :
                  caption.match(/trackman|data|stats|numbers/i) ? 'trackman' :
                  caption.match(/membership|price|deal|offer/i) ? 'promotion' : 'general';
    
    return {
      id: p.id || p._id || 'unknown',
      postId: p.postId || p.externalId || p.id,
      timestamp: p.date || p.publishedAt || p.createdAt || new Date().toISOString(),
      // Permalink: Postiz returns releaseURL/releaseId; fall back to shortcode-based URL when missing.
      // Without this, the Insights tab renders the post as a non-clickable row (live UX bug).
      permalink: p.permalink || p.url || p.postUrl || p.releaseURL || null,
      permalink_shortcode: p.shortcode || p.code || null,
      captionPreview: caption.substring(0, 80),
      hook_text: hook,
      hook_id: hook.toLowerCase().replace(/[^a-z0-9]/g, '-').substring(0, 50),
      format_type: format,
      topic_cluster: topic,
      reach: parseInt(p.reach || p.impressions || 0),
      likes: parseInt(p.likes || p.likeCount || 0),
      comments: parseInt(p.comments || p.commentsCount || 0),
      saves: parseInt(p.saves || 0),
      shares: parseInt(p.shares || 0),
      profile_visits: parseInt(p.profile_visits || 0),
      follows_gained: parseInt(p.follows || 0),
      ...metrics,
    };
  }).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  
  const result = {
    updated: new Date().toISOString(),
    source: 'Postiz API',
    total_posts: posts.length,
    posts,
  };
  
  fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
  console.log(`✅ IG Analytics: ${posts.length} posts synced`);
  return result;
}

run().catch(e => {
  console.log('Error:', e.message);
  process.exit(1);
});