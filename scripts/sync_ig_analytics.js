#!/usr/bin/env node
/**
 * sync_ig_analytics.js
 * Reads from the existing instagram-analytics.json and syncs to the dashboard data format
 */
const fs = require('fs');
const path = require('path');

const SOURCE = '/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/analytics/instagram-analytics.json';
const DEST = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data/ig-analytics.json';

function run() {
  try {
    const data = JSON.parse(fs.readFileSync(SOURCE, 'utf8'));
    const posts = (data.posts || []).map(p => {
      const caption = p.caption || '';
      const hook = caption.split('\n')[0] || caption.substring(0, 80) || 'unknown';
      return {
        id: p.id || 'unknown',
        postId: p.id || 'unknown',
        timestamp: p.timestamp || new Date().toISOString(),
        captionPreview: caption.substring(0, 80),
        hook_text: hook.substring(0, 80),
        hook_id: hook.toLowerCase().replace(/[^a-z0-9]/g, '-').substring(0, 50),
        format_type: caption.match(/carousel/i) ? 'carousel' : caption.match(/reel|video/i) ? 'reel' : 'static',
        topic_cluster: caption.match(/fitting|clubs|equipment/i) ? 'equipment' :
                       caption.match(/slice|hook|swing|technique/i) ? 'technique' :
                       caption.match(/coach|lesson/i) ? 'coaching' :
                       caption.match(/trackman|data|stats/i) ? 'trackman' : 'general',
        reach: parseInt(p.reach || 0),
        likes: parseInt(p.likeCount || 0),
        comments: parseInt(p.commentsCount || 0),
        saves: parseInt(p.saves || 0),
        shares: parseInt(p.shares || 0),
        profile_visits: parseInt(p.profile_visits || 0),
        follows_gained: parseInt(p.follows || 0),
        engagementRate: p.engagementRate || '0.00',
        saveRate: p.saves && p.reach ? (p.saves / p.reach * 100).toFixed(2) : '0.00',
        shareRate: p.shares && p.reach ? (p.shares / p.reach * 100).toFixed(2) : '0.00',
        followConversion: p.follows && p.reach ? (p.follows / p.reach * 100).toFixed(3) : '0.000',
      };
    });
    
    const result = {
      updated: data.lastUpdated || data.updated || new Date().toISOString(),
      source: 'instagram-analytics.json (daily tracker)',
      total_posts: posts.length,
      posts,
    };
    
    fs.writeFileSync(DEST, JSON.stringify(result, null, 2));
    console.log(`✅ Synced ${posts.length} IG posts to dashboard data`);
  } catch (e) {
    console.log('Error syncing IG analytics:', e.message);
  }
}

run();