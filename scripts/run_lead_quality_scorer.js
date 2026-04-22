#!/usr/bin/env node
const fs=require('fs');const path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function r(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}}
function uid(){return Math.random().toString(36).substring(2,10);}
function run(){
  const now=new Date();
  const conv=r('conversion-attribution.json')||{};
  const lead=r('lead-recovery.json')||{};
  const web=r('website-insights.json')||{};
  const ga4=r('ga4-metrics.json')||{};
  const rec=r('recommendation-scores.json')||{};
  const topService=rec.summary?.top_service||'Practice';
  const scoringRules=[
    {signal:'service_selected=club_fitting',score:+30,label:'hot',reason:'High-intent signal — fitting decision involves money and commitment'},
    {signal:'service_selected=coaching',score:+25,label:'hot',reason:'Coaching intent — serious about improvement'},
    {signal:'page_depth>3',score:+20,label:'warm',reason:'Deep browsing = active research'},
    {signal:'repeat_visit',score:+20,label:'warm',reason:'Return visitor — pre-qualified interest'},
    {signal:'cta_clicked=book_now',score:+25,label:'hot',reason:'Direct booking intent click'},
    {signal:'cta_clicked=pricing',score:+15,label:'warm',reason:'Pricing research — decision stage'},
    {signal:'cta_clicked=whatsapp',score:+20,label:'warm',reason:'Prefers direct communication — SA market fit'},
    {signal:'source=whatsapp_share',score:+15,label:'warm',reason:'Social proof via WhatsApp — warm referral'},
    {signal:'source=instagram',score:+10,label:'warm',reason:'Social discovery — mid-funnel'},
    {signal:'source=google',score:+15,label:'warm',reason:'Active search intent'},
    {signal:'mobile_booking_form_start',score:+10,label:'warm',reason:'Started booking — strong intent'},
    {signal:'service_selected=social_play',score:+5,label:'cold',reason:'Social/play intent — low commitment signal'},
    {signal:'single_page_visit',score:-10,label:'cold',reason:'Bounced — low engagement'},
    {signal:'no_cta_click',score:-5,label:'cold',reason:'No clear intent action taken'},
    {signal:'long_session_no_action',score:+5,label:'warm',reason:'Long browsing but no action — research mode, not cold'},
  ];
  // Example lead profiles
  const profiles=[
    {profile_id:'hot-fitting',label:'hot',score:80,name:'High-Intent Fitting Lead',signals:['service_selected=club_fitting','cta_clicked=book_now','repeat_visit'],next_action:'Direct WhatsApp response within 1h. Offer Fitting Starter Pack. Confirm slot availability.', SLA_hours:1,example:'WhatsApp: "Hi [name], I saw you\'re interested in our fitting assessment. We have R900 Driver Fitting available [tomorrow/today]. Want me to hold a spot?"'},
    {profile_id:'warm-coaching',label:'warm',score:55,name:'Researching Coaching Lead',signals:['service_selected=coaching','page_depth>3','source=google'],next_action:'WhatsApp follow-up in 4h. Share TPI assessment value + coach credentials. Offer introductory session.',SLA_hours:4,example:'WhatsApp: "Hi [name], great to see you checking out our coaching. Our TPI assessment gives you a complete blueprint of your game. Want the summary?"'},
    {profile_id:'warm-practice',label:'warm',score:40,name:'Practice Interest Lead',signals:['service_selected=practice','repeat_visit','cta_clicked=pricing'],next_action:'WhatsApp in 8h. Practice Pack offer. No pressure — value-first.',SLA_hours:8,example:'WhatsApp: "Hi [name], if you\'re looking to get more from your practice sessions — our TrackMan setup tracks every shot. From R250. Happy to answer any questions."'},
    {profile_id:'cold-social',label:'cold',score:15,name:'Social Play Browser',signals:['service_selected=social_play','single_page_visit','no_cta_click'],next_action:'WhatsApp in 24h. Low-pressure. Share social experience vibe + group offer.',SLA_hours:24,example:'WhatsApp: "Hi [name], Swing Shack is great for groups — food, drinks, TrackMan screens. Let me know if you want to come try it out."'},
  ];
  const out={schema:'https://clawdia.io/agents/lead-quality-scorer/v1',generated:now.toISOString(),summary:{total_profiles:profiles.length,hot:profiles.filter(p=>p.label==='hot').length,warm:profiles.filter(p=>p.label==='warm').length,cold:profiles.filter(p=>p.label==='cold').length},scoring_rules:scoringRules,profiles};
  fs.writeFileSync(path.join(DATA,'lead-quality.json'),JSON.stringify(out,null,2));
  console.log('✅ Lead quality scorer: '+profiles.length+' profiles');profiles.forEach(p=>console.log('   '+p.label.toUpperCase()+' ('+p.score+'pts): '+p.name+' — SLA:'+p.SLA_hours+'h'));}
run();
