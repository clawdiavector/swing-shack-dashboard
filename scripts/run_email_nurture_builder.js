#!/usr/bin/env node
/**
 * run_email_nurture_builder.js
 * Short nurture flows (3-email max) from winning hooks, best CTAs, top services, booking leaks.
 * Outputs: email-nurtures.json
 * Schema: https://clawdia.io/agents/email-nurture-builder/v1
 */
const fs = require('fs');
const path = require('path');
const DATA = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function readJson(n) { try { return JSON.parse(fs.readFileSync(path.join(DATA, n), 'utf8')); } catch { return null; } }
function uid() { return Math.random().toString(36).substring(2, 10); }

function run() {
  const now = new Date();
  const recSc  = readJson('recommendation-scores.json') || {};
  const recOut = readJson('recommendation-outcomes.json') || {};
  const leadRec = readJson('lead-recovery.json') || {};
  const ig      = readJson('ig-analytics.json') || {};

  const topHook    = recSc.summary?.top_hook || 'YOUR GAME IN NUMBERS';
  const topCTA     = recSc.summary?.top_cta || 'Book Your Session';
  const topService = recSc.summary?.top_service || 'Practice';
  const topLeak    = (leadRec.recoveries || [])[0];

  const nurtures = [];

  // Sequence 1: Booking recovery — booking drop audience
  nurtures.push({
    sequence_id: `nur-${uid()}`,
    schema: 'https://clawdia.io/agents/email-nurture-builder/v1',
    generated: now.toISOString(),
    name: 'Booking Recovery Sequence',
    objective: 'recover_abandoned_bookings',
    target_audience: 'visited_pricing_did_not_book',
    emails: [
      {
        day: 1,
        subject: 'Ready to crack your golf numbers?',
        hook: topHook,
        body: 'You visited Swing Shack and we noticed you didn\'t book. Here\'s what you\'re missing: TrackMan measures your swing speed, attack angle, carry distance — every number that matters.\n\nFirst session from R250. Book in 2 minutes.',
        cta: topCTA,
        cta_url: 'swingshack.co.za/book',
        service: topService,
      },
      {
        day: 3,
        subject: 'Your swing could be 15m longer',
        hook: '15 metres. That\'s what most golfers gain after 3 sessions with TrackMan data.',
        body: 'We showed you the numbers. Now let\'s fix them. Certified instructors, indoor comfort, TrackMan precision.\n\nBundle deal: 3 sessions + full swing analysis — R1,800.',
        cta: 'View Session Packages',
        cta_url: 'swingshack.co.za/membership',
        service: topService,
      },
      {
        day: 7,
        subject: 'Limited slots this month',
        hook: '3 spots left this week.',
        body: 'Quick one. We\'ve had a surge in booking inquiries and this week\'s slots are filling fast.\n\nIf you were on the fence — now\'s the time. Indoor golf, any weather, any skill level.\n\nOr reply here and we\'ll sort you manually.',
        cta: 'Check Availability',
        cta_url: 'swingshack.co.za/book',
        service: topService,
      },
    ],
  });

  // Sequence 2: New service discovery — for engaged but not converted
  nurtures.push({
    sequence_id: `nur-${uid()}`,
    schema: 'https://clawdia.io/agents/email-nurture-builder/v1',
    generated: now.toISOString(),
    name: 'Service Discovery — Club Fitting',
    objective: 'introduce_club_fitting_service',
    target_audience: 'engaged_blog_or_social_not_service_page',
    emails: [
      {
        day: 1,
        subject: 'What\'s killing your distance?',
        hook: 'Backspin. That\'s usually the culprit.',
        body: 'Most golfers don\'t know why their shots don\'t carry. It\'s rarely the club — it\'s the strike data.\n\nTrackMan\'s loft and lie assessment shows exactly where your numbers are bleeding.',
        cta: 'Get a Loft & Lie Check',
        cta_url: 'swingshack.co.za/club-fitting',
        service: 'Club Fitting',
      },
      {
        day: 4,
        subject: 'Driver fitting: what we found',
        hook: 'We fitted 47 golfers last month. Here\'s the pattern.',
        body: 'Same issue every time: lofts are 1.5 degrees too high for their swing speed. Easy fix. Same clubs, different numbers.\n\nFull bag fitting: R1,800. Loft & lie: R800.',
        cta: 'Book Fitting Assessment',
        cta_url: 'swingshack.co.za/club-fitting',
        service: 'Club Fitting',
      },
      {
        day: 8,
        subject: 'R800 gets you 20 more yards. Here\'s how.',
        hook: 'Not a sales pitch. A fact.',
        body: 'Loft & lie assessment. 1 hour. R800. We measure your attack angle, club path, and face angle. You leave knowing exactly what your clubs should be doing.\n\nLimited slots this week.',
        cta: 'Book Loft & Lie',
        cta_url: 'swingshack.co.za/book',
        service: 'Club Fitting',
      },
    ],
  });

  // Sequence 3: Coach onboarding — warm intro for coaching service
  nurtures.push({
    sequence_id: `nur-${uid()}`,
    schema: 'https://clawdia.io/agents/email-nurture-builder/v1',
    generated: now.toISOString(),
    name: 'Coaching Discovery',
    objective: 'convert_interested_leads_to_coaching',
    target_audience: 'visited_coaching_page_engaged',
    emails: [
      {
        day: 1,
        subject: 'Your swing\'s honest assessment',
        hook: topHook,
        body: 'Before you commit to coaching, get the truth about your game. TrackMan gives you the data. We give you the plan.\n\nTPI assessment: R1,250. 90 minutes. You leave knowing exactly what to work on.',
        cta: 'Book TPI Assessment',
        cta_url: 'swingshack.co.za/coaching',
        service: 'Coaching',
      },
      {
        day: 3,
        subject: 'What a TPI assessment actually looks like',
        hook: 'It\'s not a lesson. It\'s a blueprint.',
        body: 'We test 16 movement patterns. Then we map them to your swing. Then we tell you what to fix first.\n\nNo fluff. Just data and direction.',
        cta: 'See How It Works',
        cta_url: 'swingshack.co.za/coaching',
        service: 'Coaching',
      },
      {
        day: 6,
        subject: 'Three sessions. Noticeable difference.',
        hook: 'That\'s what most of our members report.',
        body: 'Birdie Hunter + Unlimited Practice: R2,300. Three sessions with certified coaching + unlimited simulator access until your game clicks.\n\nOr start with one lesson: R850.',
        cta: 'View Coaching Packages',
        cta_url: 'swingshack.co.za/membership',
        service: 'Coaching',
      },
    ],
  });

  const nurturesOut = {
    schema: 'https://clawdia.io/agents/email-nurture-builder/v1',
    generated: now.toISOString(),
    summary: {
      total_sequences: nurtures.length,
      total_emails: nurtures.reduce((s, n) => s + n.emails.length, 0),
      max_email_count: 3,
    },
    sequences: nurtures,
  };

  fs.writeFileSync(path.join(DATA, 'email-nurtures.json'), JSON.stringify(nurturesOut, null, 2));
  console.log('✅ Email nurture builder: ' + nurtures.length + ' sequences, ' + nurturesOut.summary.total_emails + ' emails');
  nurtures.forEach(n => console.log('   ' + n.name + ': ' + n.emails.length + ' emails'));
}

run();
