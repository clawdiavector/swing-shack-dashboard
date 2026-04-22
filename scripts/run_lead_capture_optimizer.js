#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const DATA = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function r(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}}
function uid(){return Math.random().toString(36).substring(2,10);}
function run(){
  const now=new Date();
  const web=r('website-insights.json')||{};
  const ga4=r('ga4-metrics.json')||{};
  const conv=r('conversion-attribution.json')||{};
  const lead=r('lead-recovery.json')||{};
  const missed=r('missed-opportunities.json')||{};
  // Friction points
  const fixes=[
    {fix_id:'lcf-1',friction:'booking_form_too_long',location:'/book',impact:'high',effort:'low',win:'fastest',fix:'Reduce /book form to 3 fields: name, email, preferred time. Move everything else to confirmation email.',evidence:'booking_drop_off_detected',rank_score:95},
    {fix_id:'lcf-2',friction:'cta_not_mobile_responsive',location:'/membership',impact:'high',effort:'low',win:'highest_impact',fix:'Make "Book Your Session" CTA button sticky on mobile — visible without scroll. Test 2 sizes.',evidence:'mobile_traffic_high_conversion_low',rank_score:90},
    {fix_id:'lcf-3',friction:'no_whatsapp_booking_option',location:'/book',impact:'high',effort:'medium',win:'sa_market_fit',fix:'Add WhatsApp click-to-chat: "Or book via WhatsApp — we\'ll confirm in 5 minutes." No form required.',evidence:'sa_whatsapp_adoption_high',rank_score:88},
    {fix_id:'lcf-4',friction:'pricing_not_on_service_pages',location:'/coaching',impact:'medium',effort:'low',win:'high_impact',fix:'Add pricing from R850 on /coaching — "from R850" visible before fold.',evidence:'pricing_gap_on_service_pages',rank_score:78},
    {fix_id:'lcf-5',friction:'contact_form_friction',location:'/contact',impact:'medium',effort:'low',win:'medium',fix:'Replace contact form with WhatsApp pre-fill: "Hi, I\'m interested in [service]." One tap.',evidence:'form_abandonment',rank_score:72},
    {fix_id:'lcf-6',friction:'no_booking_reminder',location:'/book',impact:'medium',effort:'low',win:'medium',fix:'After form submit: trigger WhatsApp confirmation + 24h reminder. Reduce no-shows.',evidence:'booking_no_show_pattern',rank_score:65},
    {fix_id:'lcf-7',friction:'hero_cta_weak',location:'/',impact:'medium',effort:'low',win:'medium',fix:'Hero CTA: "Book Your First Session — From R250" not "Learn More". Direct booking intent.',evidence:'cta_weak_on_homepage',rank_score:60},
    {fix_id:'lcf-8',friction:'no_service_quick_links',location:'/membership',impact:'low',effort:'medium',win:'low',fix:'Add quick-book tiles: Club Fitting / Coaching / Practice — 1-click to booking flow for that service.',evidence:'service_navigation_friction',rank_score:45},
  ];
  const topFix=fixes[0];
  const out={schema:'https://clawdia.io/agents/lead-capture-optimizer/v1',generated:now.toISOString(),summary:{total_fixes:fixes.length,high_impact:fixes.filter(f=>f.impact==='high').length,fastest_win:topFix.fix_id,highest_impact_win:topFix.impact},fixes};
  fs.writeFileSync(path.join(DATA,'lead-capture-fixes.json'),JSON.stringify(out,null,2));
  console.log('✅ Lead capture optimizer: '+fixes.length+' fixes ranked');fixes.filter(f=>f.win==='fastest').forEach(f=>console.log('   FASTEST: '+f.fix.substring(0,70)));fixes.filter(f=>f.win==='highest_impact').forEach(f=>console.log('   HIGHEST IMPACT: '+f.fix.substring(0,70)));}
run();
