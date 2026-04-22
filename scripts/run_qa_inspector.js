#!/usr/bin/env node
/**
 * run_qa_inspector.js — qa_inspector agent core script
 * Reads: captions, visual briefs, blog drafts, reddit replies, post plan, hook bank, used items
 * Produces: qa-report.json, qa-failures.json, ready-for-approval.json
 *
 * Per item verdict: pass | fix | reject
 * Schema: https://clawdia.io/agents/qa-inspector/v1
 */
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');

function readJson(n) {
  try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); }
  catch { return null; }
}

function uid() {
  return Math.random().toString(36).substring(2, 10);
}

function run() {
  const captions     = readJson('captions.json') || {};
  const capVariants  = readJson('caption-variants.json') || {};
  const vbBriefs     = readJson('visual-briefs.json') || {};
  const imgPrompts   = readJson('image-prompts.json') || {};
  const blogDrafts   = readJson('blog-drafts.json') || {};
  const redditRepl   = readJson('reddit-replies.json') || {};
  const postPlan     = readJson('post-plan.json') || {};
  const hookBank     = readJson('hook-bank.json') || {};
  const usedItems    = readJson('used-items.json') || { suppressed_ideas: [], suppressed_hooks: [] };

  // ── QA rule sets ─────────────────────────────────────────────────
  const FORBIDDEN_PHRASES = [
    'we are', 'our team is', 'here at', 'passionate about',
    'cutting edge', 'world class', 'best in class', 'revolutionary',
    'game changer', 'game-changing', 'best-in-class', 'next level',
  ];

  const WEAK_CTAS = [
    'click the link', 'click here', 'check out our', 'visit us at',
    'come and see', 'stop by', 'get in touch', 'reach out to us',
  ];

  const OVERUSED_LINES = [
    'your golf numbers', 'numbers don\'t lie', 'trackman shows',
    'book your session', 'link in bio',
  ];

  const SLICE_WORDS = ['slice', 'hook', 'offline', 'shank', 'topped', 'skulled'];
  const PROOF_WORDS = ['trackman', 'data', 'number', 'stat', 'speed', 'distance', 'meters', 'mph'];

  // ── Check functions ────────────────────────────────────────────────
  function checkCaption(c) {
    const issues = [];
    const text = ((c.short_caption || '') + ' ' + (c.medium_caption || '')).toLowerCase();

    // CTA presence
    if (!text.match(/book|link in bio|dm|swipe|drop|comment/i)) {
      issues.push({ type: 'missing_cta', severity: 'high', msg: 'No clear CTA found' });
    }

    // Broken hashtags (too many)
    const hashtags = (text.match(/#\w+/g) || []);
    if (hashtags.length > 15) {
      issues.push({ type: 'too_many_hashtags', severity: 'medium', msg: `${hashtags.length} hashtags — IG may suppress` });
    }

    // Generic AI-sounding
    const hasGeneric = FORBIDDEN_PHRASES.some(p => text.includes(p));
    if (hasGeneric) {
      issues.push({ type: 'generic_ai_tone', severity: 'medium', msg: 'Contains generic marketing phrasing' });
    }

    // Weak CTA
    const hasWeak = WEAK_CTAS.some(p => text.includes(p));
    if (hasWeak) {
      issues.push({ type: 'weak_cta', severity: 'low', msg: 'Weak CTA language detected' });
    }

    // Check hook not suppressed
    const suppressed = usedItems.suppressed_hooks || [];
    const hookUsed = suppressed.some(s => (c.hook_text || '').toLowerCase().includes(s.toLowerCase()));
    if (hookUsed) {
      issues.push({ type: 'hook_suppressed', severity: 'high', msg: 'Hook was previously used and suppressed' });
    }

    const severity = issues.some(i => i.severity === 'high') ? 'high'
      : issues.some(i => i.severity === 'medium') ? 'medium' : 'low';

    return {
      item_id: c.caption_id,
      item_type: 'caption',
      linked_blueprint_id: c.linked_blueprint_id,
      verdict: severity === 'high' ? 'reject' : severity === 'medium' ? 'fix' : 'pass',
      issues,
      passed_checks: 4 - issues.length,
      total_checks: 4,
    };
  }

  function checkBlogDraft(d) {
    const issues = [];
    const text = ((d.headline || '') + ' ' + (d.sections || '')).toLowerCase();

    // Length check
    const wordCount = (d.sections || '').split(/\s+/).length;
    if (wordCount < 300) {
      issues.push({ type: 'too_short', severity: 'high', msg: `Only ${wordCount} words — informational posts need 800+` });
    }

    // CTA presence
    if (!text.includes('book') && !text.includes('swingshack.co.za') && !text.includes('link in bio')) {
      issues.push({ type: 'missing_cta', severity: 'high', msg: 'No booking CTA found' });
    }

    // Factual check — mention TrackMan
    if (!text.includes('trackman') && !text.includes('launch monitor')) {
      issues.push({ type: 'missing_proof', severity: 'medium', msg: 'No TrackMan/launch monitor mention — key differentiator missing' });
    }

    // Pricing reference (if claiming affordability)
    if (text.includes('from r') && !text.match(/from r\d+/)) {
      issues.push({ type: 'vague_pricing', severity: 'low', msg: 'Mentions pricing without specific number' });
    }

    // Brand tone
    const hasGeneric = FORBIDDEN_PHRASES.some(p => text.includes(p));
    if (hasGeneric) {
      issues.push({ type: 'generic_ai_tone', severity: 'medium', msg: 'Generic marketing language detected' });
    }

    const severity = issues.some(i => i.severity === 'high') ? 'high'
      : issues.some(i => i.severity === 'medium') ? 'medium' : 'low';

    return {
      item_id: d.draft_id,
      item_type: 'blog_draft',
      linked_brief_id: d.linked_brief_id,
      verdict: severity === 'high' ? 'reject' : severity === 'medium' ? 'fix' : 'pass',
      issues,
      passed_checks: 5 - issues.length,
      total_checks: 5,
    };
  }

  function checkRedditReply(r) {
    const issues = [];
    const text = ((r.reply_draft || '') + ' ' + (r.soft_brand_mention || '')).toLowerCase();

    // No direct links
    if (text.match(/swingshack\.co\.za|www\.|http/i)) {
      issues.push({ type: 'direct_link', severity: 'high', msg: 'Reddit reply has direct link — rejected, no links allowed' });
    }

    // No salesy language
    const salesy = ['amazing', 'incredible', 'best', 'guaranteed', 'proven to', 'will change'];
    const hasSalesy = salesy.some(p => text.includes(p));
    if (hasSalesy) {
      issues.push({ type: 'salesy_language', severity: 'medium', msg: 'Salesy language detected — native tone broken' });
    }

    // Too short
    if ((r.reply_draft || '').length < 100) {
      issues.push({ type: 'too_short', severity: 'medium', msg: 'Reply too short to provide value — needs more substance' });
    }

    // Soft brand mention present
    if (!r.soft_brand_mention) {
      issues.push({ type: 'missing_brand', severity: 'low', msg: 'No soft brand mention — opportunity missed' });
    }

    const severity = issues.some(i => i.severity === 'high') ? 'reject'
      : issues.some(i => i.severity === 'medium') ? 'fix' : 'pass';

    return {
      item_id: r.reply_id,
      item_type: 'reddit_reply',
      sentiment: r.sentiment,
      verdict: severity,
      issues,
      passed_checks: 4 - issues.length,
      total_checks: 4,
    };
  }

  function checkImagePrompt(p) {
    const issues = [];
    const text = (p.prompt_text || '').toLowerCase();

    // No people if service is data/tech
    if (text.includes('data card') && text.includes('person')) {
      issues.push({ type: 'style_conflict', severity: 'low', msg: 'Data card brief includes person — may conflict with aesthetic' });
    }

    // Aspect ratio check
    if (!text.includes('9:16') && !text.includes('1:1') && !text.includes('16:9') && !text.includes('square') && !text.includes('vertical')) {
      issues.push({ type: 'missing_aspect', severity: 'medium', msg: 'No aspect ratio specified — may produce wrong format' });
    }

    // Hook present in prompt
    if (p.hook_text && typeof p.hook_text === 'string' && !text.includes(p.hook_text.substring(0, 10))) {
      issues.push({ type: 'hook_mismatch', severity: 'low', msg: 'Hook text not clearly referenced in prompt' });
    }

    const severity = issues.some(i => i.severity === 'high') ? 'reject'
      : issues.some(i => i.severity === 'medium') ? 'fix' : 'pass';

    return {
      item_id: p.prompt_id,
      item_type: 'image_prompt',
      linked_blueprint_id: p.linked_blueprint_id,
      verdict: severity,
      issues,
      passed_checks: 3 - issues.length,
      total_checks: 3,
    };
  }

  function checkVisualBrief(b) {
    const issues = [];
    const brief = b.brief || {};

    if (!brief.layout) {
      issues.push({ type: 'missing_layout', severity: 'high', msg: 'No layout specified in visual brief' });
    }
    if (!brief.mood) {
      issues.push({ type: 'missing_mood', severity: 'low', msg: 'No mood/style guidance in brief' });
    }

    const severity = issues.some(i => i.severity === 'high') ? 'reject'
      : issues.some(i => i.severity === 'medium') ? 'fix' : 'pass';

    return {
      item_id: b.brief_id,
      item_type: 'visual_brief',
      linked_blueprint_id: b.linked_blueprint_id,
      verdict: severity,
      issues,
      passed_checks: 2 - issues.length,
      total_checks: 2,
    };
  }

  // ── Run all checks ─────────────────────────────────────────────────
  const allReports = [];

  (captions.captions || []).forEach(c => allReports.push(checkCaption(c)));
  (capVariants.variants || []).forEach(v => {
    const caption = captions.captions?.find(c => c.caption_id === v.linked_caption_id);
    const issues = [];
    if (v.strong_cta && !v.strong_cta.match(/book|link in bio|dm/i)) {
      issues.push({ type: 'weak_strong_cta', severity: 'medium', msg: 'Strong CTA missing clear action' });
    }
    if (!v.soft_cta || v.soft_cta.length < 10) {
      issues.push({ type: 'missing_soft_cta', severity: 'low', msg: 'Soft CTA missing' });
    }
    const severity = issues.some(i => i.severity === 'high') ? 'reject'
      : issues.some(i => i.severity === 'medium') ? 'fix' : 'low';
    allReports.push({
      item_id: v.variant_id,
      item_type: 'caption_variant',
      linked_caption_id: v.linked_caption_id,
      verdict: caption?.verdict === 'reject' ? 'reject' : severity === 'low' ? 'pass' : severity,
      issues,
      passed_checks: 3 - issues.length,
      total_checks: 3,
    });
  });
  (blogDrafts.drafts || []).forEach(d => allReports.push(checkBlogDraft(d)));
  (redditRepl.replies || []).forEach(r => allReports.push(checkRedditReply(r)));
  (imgPrompts.prompts || []).forEach(p => allReports.push(checkImagePrompt(p)));
  (vbBriefs.briefs || []).forEach(b => allReports.push(checkVisualBrief(b)));

  // ── Categorise ────────────────────────────────────────────────────
  const passList = allReports.filter(r => r.verdict === 'pass');
  const fixList  = allReports.filter(r => r.verdict === 'fix');
  const rejectList = allReports.filter(r => r.verdict === 'reject');

  const qaReport = {
    schema: 'https://clawdia.io/agents/qa-inspector/v1',
    generated: new Date().toISOString(),
    total_items: allReports.length,
    pass: passList.length,
    fix: fixList.length,
    reject: rejectList.length,
    pass_rate: allReports.length > 0 ? Math.round((passList.length / allReports.length) * 100) : 0,
    by_type: {
      caption: allReports.filter(r => r.item_type === 'caption').length,
      caption_variant: allReports.filter(r => r.item_type === 'caption_variant').length,
      blog_draft: allReports.filter(r => r.item_type === 'blog_draft').length,
      reddit_reply: allReports.filter(r => r.item_type === 'reddit_reply').length,
      image_prompt: allReports.filter(r => r.item_type === 'image_prompt').length,
      visual_brief: allReports.filter(r => r.item_type === 'visual_brief').length,
    },
    reports: allReports,
  };

  const qaFailures = {
    schema: 'https://clawdia.io/agents/qa-inspector/v1',
    generated: new Date().toISOString(),
    failures: [...fixList, ...rejectList],
    fix_count: fixList.length,
    reject_count: rejectList.length,
    critical_issues: rejectList.flatMap(r => r.issues.filter(i => i.severity === 'high')).length,
  };

  const readyForApproval = {
    schema: 'https://clawdia.io/agents/qa-inspector/v1',
    generated: new Date().toISOString(),
    count: passList.length,
    items: passList,
    top_issues_fixed: fixList.flatMap(r => r.issues).slice(0, 5),
    blocked_rejects: rejectList.length,
  };

  fs.writeFileSync(path.join(DATA, 'qa-report.json'), JSON.stringify(qaReport, null, 2));
  fs.writeFileSync(path.join(DATA, 'qa-failures.json'), JSON.stringify(qaFailures, null, 2));
  fs.writeFileSync(path.join(DATA, 'ready-for-approval.json'), JSON.stringify(readyForApproval, null, 2));

  console.log(`✅ QA complete: ${allReports.length} items`);
  console.log(`   PASS: ${passList.length} | FIX: ${fixList.length} | REJECT: ${rejectList.length}`);
  console.log(`   Pass rate: ${qaReport.pass_rate}%`);
  if (rejectList.length > 0) console.log(`   ⚠️  ${rejectList.length} REJECTED — see qa-failures.json`);
  if (fixList.length > 0) console.log(`   🔧 ${fixList.length} need fixes before publishing`);
}

module.exports = { run };
if (require.main === module) run();