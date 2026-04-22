#!/usr/bin/env node
const fs=require('fs');const path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function r(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}}
function uid(){return Math.random().toString(36).substring(2,10);}
function run(){
  const now=new Date();
  const lead=r('lead-recovery.json')||{};
  const conv=r('conversion-attribution.json')||{};
  const rec=r('recommendation-scores.json')||{};
  const topService=rec.summary?.top_service||'Practice';
  const improvements=[
    {id:'bf-1',type:'service_first_routing',name:'Service-first landing routing',problem:'Users clicking "Book" go to generic /book. No service pre-selection.',fix:'Route ?service=fitting to /book?service=club-fitting pre-filled. Create: /book?service=coaching and /book?service=practice variants.',impact:'high',evidence:'service_path_confusion',priority:1},
    {id:'bf-2',type:'abandoned_booking_recovery',name:'Abandoned booking WhatsApp nudge',problem:'Form started but not submitted — zero recovery.',fix:'If user reaches /book and leaves without submitting: capture session, retarget via WhatsApp within 2h with "Still interested? Your session is waiting — R250 to confirm."',impact:'high',evidence:'booking_drop_off',priority:1},
    {id:'bf-3',type:'prefilled_booking',name:'Pre-filled booking with WhatsApp',problem:'Returning visitors re-enter same data.',fix:'Auto-populate name/email from first visit cookie. Show "Welcome back, [name] — book in 30 seconds."',impact:'medium',evidence:'returning_visitor_no_conversion',priority:2},
    {id:'bf-4',type:'fitting_intent_flow',name:'"Coming for fitting?" direct flow',problem:'Fitting visitors get same booking flow as coaching. Fitting = higher intent, faster decision.',fix:'On /club-fitting page, primary CTA goes directly to fitting-specific booking: "Book Fitting Assessment — R900". No "general inquiry" step.',impact:'high',evidence:'fitting_page_high_intent',priority:1},
    {id:'bf-5',type:'reminder_sequence',name:'Booking reminder sequence',problem:'No-shows from forgetfulness.',fix:'At booking confirmation: "See you [date] — we\'ll send a WhatsApp reminder 24h before." Then auto-send reminder via WhatsApp.',impact:'medium',evidence:'no_show_pattern',priority:2},
    {id:'bf-6',type:'membership_upsell',name:'Post-lesson membership upsell',problem:'Coaching clients don\'t naturally move to membership.',fix:'After first coaching lesson confirmation: "Want unlimited practice between lessons? R1,800/month — add it now." One-click upsell inline.',impact:'medium',evidence:'coaching_to_membership_gap',priority:2},
    {id:'bf-7',type:'mobile_booking_priority',name:'Mobile booking-first redesign',problem:'Mobile traffic high, desktop conversion higher — mobile booking is friction-heavy.',fix:'Mobile: single-page booking with large touch targets, WhatsApp option prominent, progress bar, minimal fields.',impact:'high',evidence:'mobile_low_conversion',priority:1},
  ];
  improvements.sort((a,b)=>a.priority-b.priority);
  const out={schema:'https://clawdia.io/agents/booking-flow-engine/v1',generated:now.toISOString(),summary:{total:improvements.length,high_impact:improvements.filter(i=>i.impact==='high').length,top_improvement:improvements[0].name},improvements};
  fs.writeFileSync(path.join(DATA,'booking-flow-improvements.json'),JSON.stringify(out,null,2));
  console.log('✅ Booking flow engine: '+improvements.length+' improvements');improvements.filter(i=>i.priority===1).forEach(i=>console.log('   P1: '+i.name));}
run();
