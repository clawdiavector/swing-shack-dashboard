#!/usr/bin/env node
/**
 * Social Media Auto-Poster
 * 
 * Posts approved content to social media platforms via Postiz
 * 
 * Usage:
 *   node scripts/post-to-social.js post <queue-index>
 *   node scripts/post-to-social.js post-all
 *   node scripts/post-to-social.js status
 */

const fs = require('fs');
const path = require('path');

const QUEUE_FILE = path.join(__dirname, '../clients/swing-shack/data/approval-queue.json');
const CREDS_FILE = path.join(__dirname, '../clients/swing-shack/credentials.json');

// Load credentials
function loadCreds() {
    const creds = JSON.parse(fs.readFileSync(CREDS_FILE, 'utf8'));
    return {
        secretCode: creds.postiz.secretCode,
        integrations: creds.postiz.integrations
    };
}

// Load queue
function loadQueue() {
    try {
        return JSON.parse(fs.readFileSync(QUEUE_FILE, 'utf8'));
    } catch {
        return { pending: [], approved: [], rejected: [], posted: [] };
    }
}

// Save queue
function saveQueue(queue) {
    fs.writeFileSync(QUEUE_FILE, JSON.stringify(queue, null, 2));
}

// Platform mapping
const PLATFORM_INTEGRATION_MAP = {
    'instagram': null,  // will fill from creds
    'tiktok': null,
    'facebook': null,
    'youtube': null,
    'google-business': null,
    'gmb': null
};

// Initialize platform IDs
function initPlatforms(integrations) {
    PLATFORM_INTEGRATION_MAP['instagram'] = integrations.instagram;
    PLATFORM_INTEGRATION_MAP['tiktok'] = integrations.tiktok;
    PLATFORM_INTEGRATION_MAP['facebook'] = integrations.facebook;
    PLATFORM_INTEGRATION_MAP['youtube'] = integrations.youtube;
    PLATFORM_INTEGRATION_MAP['google-business'] = integrations.gmb;
    PLATFORM_INTEGRATION_MAP['gmb'] = integrations.gmb;
}

// Post to a single platform
async function postToPlatform(integrationId, content, mediaUrl = null) {
    const POSTIZ_KEY = loadCreds().secretCode;
    
    const payload = {
        type: 'now',
        date: new Date().toISOString(),
        shortLink: false,
        tags: ['SwingShack', 'Golf'],
        posts: [{
            integration: { id: integrationId },
            settings: {
                message: content
            }
        }]
    };
    
    // Add media if provided
    if (mediaUrl) {
        payload.posts[0].settings.media = {
            images: [{ url: mediaUrl }]
        };
    }
    
    // Add call to action for Google Business
    if (integrationId === PLATFORM_INTEGRATION_MAP['gmb']) {
        payload.posts[0].settings.callToActionType = 'CALL';
    }
    
    try {
        const response = await fetch('https://api.postiz.com/public/v1/posts', {
            method: 'POST',
            headers: {
                'Authorization': POSTIZ_KEY,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        return { success: true, data };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

// Post approved item to all its platforms
async function postApprovedItem(index) {
    const queue = loadQueue();
    const creds = loadCreds();
    initPlatforms(creds.integrations);
    
    const item = queue.approved[index];
    if (!item) {
        console.log('❌ Item not found at index', index);
        return;
    }
    
    console.log(`\n📤 Posting: ${item.caption.substring(0, 50)}...`);
    console.log(`   Platforms: ${item.platforms.join(', ')}`);
    
    const results = [];
    
    for (const platform of item.platforms) {
        const integrationId = PLATFORM_INTEGRATION_MAP[platform];
        
        if (!integrationId) {
            console.log(`   ⚠️ ${platform}: No integration ID found`);
            results.push({ platform, success: false, error: 'No integration ID' });
            continue;
        }
        
        console.log(`   📱 Posting to ${platform}...`);
        const result = await postToPlatform(integrationId, item.caption, item.mediaUrl || item.image);
        
        if (result.success) {
            console.log(`   ✅ ${platform}: Posted successfully`);
            results.push({ platform, success: true });
        } else {
            console.log(`   ❌ ${platform}: ${result.error}`);
            results.push({ platform, success: false, error: result.error });
        }
    }
    
    // Move to posted
    const allSuccess = results.every(r => r.success);
    if (allSuccess || results.some(r => r.success)) {
        queue.approved.splice(index, 1);
        item.postedAt = new Date().toISOString();
        item.postResults = results;
        queue.posted.push(item);
        saveQueue(queue);
        console.log(`\n✅ Marked as posted!`);
    } else {
        console.log(`\n❌ All posts failed, keeping in approved`);
    }
    
    return results;
}

// Post all approved items
async function postAllApproved() {
    const queue = loadQueue();
    
    if (queue.approved.length === 0) {
        console.log('No approved items to post');
        return;
    }
    
    console.log(`Found ${queue.approved.length} approved items`);
    
    // Post in reverse order (newest first)
    for (let i = queue.approved.length - 1; i >= 0; i--) {
        await postApprovedItem(i);
    }
}

// Show status
function showStatus() {
    const queue = loadQueue();
    const creds = loadCreds();
    
    console.log('\n📊 Approval Queue Status');
    console.log('========================');
    console.log(`Pending:  ${queue.pending.length}`);
    console.log(`Approved: ${queue.approved.length}`);
    console.log(`Rejected: ${queue.rejected.length}`);
    console.log(`Posted:   ${queue.posted.length}`);
    
    console.log('\n🔗 Connected Platforms:');
    for (const [platform, id] of Object.entries(creds.integrations)) {
        console.log(`   ${platform}: ${id}`);
    }
}

// CLI
const args = process.argv.slice(2);
const command = args[0];

if (command === 'post') {
    const index = parseInt(args[1]);
    postApprovedItem(index);
} else if (command === 'post-all') {
    postAllApproved();
} else if (command === 'status') {
    showStatus();
} else {
    console.log(`
Social Media Auto-Poster

Usage:
  node post-to-social.js status       # Show queue status
  node post-to-social.js post <id>   # Post approved item by index
  node post-to-social.js post-all    # Post all approved items

Example:
  node post-to-social.js post 0      # Post first approved item
    `);
}