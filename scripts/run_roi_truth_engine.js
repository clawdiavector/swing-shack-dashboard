const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

// ROI truth engine — classify confidence by source
// Rules:
// DIRECT: post → click → booking confirmed (requires GA4 → booking system integration)
// STRONG_PROXY: post → reach → booking page visit → session with UTM → recommendation (requires Postiz → GA4 UTM link)
// WEAK_PROXY: post → reach → engagement → indirect correlation
// UNMEASURABLE: no data path exists

const roi_sources=[
  {
    source:'low_risk_publish',name:'Low-Risk Publishing',
    path:'post → Postiz → IG → reach → UTM → GA4 session → booking page → service',
    can_measure:'STRONG_PROXY',
    current_state:'indirect_only',
    gap:'GA4 sessions linked to UTM params, but not to actual bookings. No booking system → GA4 integration.',
    needs:'GA4 event on booking confirmation page + UTM source → booking_value mapping',
    priority:2,
  },
  {
    source:'gmb_posting',name:'GMB Posts',
    path:'GMB post → profile visit → direction click → website → booking',
    can_measure:'STRONG_PROXY',
    current_state:'manual_correlation',
    gap:'GMB insights are visible in dashboard. Direction clicks trackable via GA4.',
    needs:'GMB API read access + GA4 goal on /contact/booking page',
    priority:3,
  },
  {
    source:'review_thank_you',name:'Review Thank-Yous',
    path:'5★ thank-you → review rating improves → trust → organic discovery → booking',
    can_measure:'WEAK_PROXY',
    current_state:'not_measured',
    gap:'Review rating visible publicly. No causal link to bookings. Long-term brand effect.',
    needs:'Google Business Profile API for review analytics + GA4 referral tracking',
    priority:3,
  },
  {
    source:'evergreen_repost',name:'Evergreen Reposts',
    path:'Approved post → scheduled repost → reach → UTM → GA4 → booking',
    can_measure:'STRONG_PROXY',
    current_state:'same_as_publish',
    gap:'Uses same UTM chain as low_risk_publish. Cannot distinguish repost from new post without Postiz analytics.',
    needs:'Postiz post-level analytics distinguishing repost vs new',
    priority:3,
  },
  {
    source:'fallback_swap',name:'Fallback Swaps',
    path:'A/B winner hook used → swap applied → same measurement as low_risk_publish',
    can_measure:'WEAK_PROXY',
    current_state:'weak',
    gap:'Fallback swaps are infrequent. A/B winner is confirmed but swap effect is isolated.',
    needs:'Hook-level analytics in Postiz — which hook drove which session',
    priority:2,
  },
  {
    source:'lead_routing',name:'Lead Routing',
    path:'WhatsApp message → lead response → booking → revenue',
    can_measure:'UNMEASURABLE',
    current_state:'not_connected',
    gap:'WhatsApp API not connected. lead_router_live is 100% simulated.',
    needs:'WhatsApp Business API + CRM → booking system integration',
    priority:1,
  },
  {
    source:'tiny_ad_shift',name:'Budget Shifts',
    path:'Meta Ads spend → reach → click → GA4 → booking',
    can_measure:'UNMEASURABLE',
    current_state:'not_connected',
    gap:'Meta Ads API not connected. Budget shifts are placeholder.',
    needs:'Meta Ads API + GA4 goal tracking + ROAS calculation',
    priority:1,
  },
  {
    source:'approval_auto_promote',name:'Auto-Promote Approved',
    path:'Approved → scheduled → published → same as low_risk_publish',
    can_measure:'DIRECT',
    current_state:'indirect',
    gap:'Time from approval to publish is measurable. Publishing quality is same as low_risk_publish.',
    needs:'Approval timestamp in Postiz → publish timestamp tracking',
    priority:3,
  },
];

const direct=roi_sources.filter(s=>s.can_measure==='DIRECT');
const strong=roi_sources.filter(s=>s.can_measure==='STRONG_PROXY');
const weak=roi_sources.filter(s=>s.can_measure==='WEAK_PROXY');
const unmeas=roi_sources.filter(s=>s.can_measure==='UNMEASURABLE');

const blockers={};
roi_sources.forEach(s=>{
  if(s.can_measure==='UNMEASURABLE'||s.can_measure==='WEAK_PROXY'){
    blockers[s.source]=s.needs;
  }
});

const recommendations=[];
unmeas.forEach(s=>{
  recommendations.push({priority:1,source:s.source,name:s.name,action:s.needs,why:'Cannot prove ROI without this integration'});
});
weak.forEach(s=>{
  recommendations.push({priority:2,source:s.source,name:s.name,action:s.needs,why:'Current proxy is weak — improve confidence'});
});
strong.forEach(s=>{
  recommendations.push({priority:3,source:s.source,name:s.name,action:'Connect GA4 booking confirmation event',why:'Would upgrade STRONG_PROXY to DIRECT'});
});

const out={
  schema:'https://clawdia.io/agents/roi-truth-engine/v1',
  generated:now.toISOString(),
  sources:roi_sources,
  summary:{
    total:roi_sources.length,
    direct:direct.length,
    strong_proxy:strong.length,
    weak_proxy:weak.length,
    unmeasurable:unmeas.length,
    verdict:'Publishing ROI is STRONG_PROXY. Lead and ad ROI is UNMEASURABLE. Only DIRECT comes when GA4 → booking system integrates.',
  },
  blockers,
  recommendations:recommendations.sort((a,b)=>a.priority-b.priority),
};
fs.writeFileSync(path.join(DATA,'roi-truth.json'),JSON.stringify(out,null,2));
console.log('✅ roi_truth_engine: '+roi_sources.length+' sources classified');
console.log('   DIRECT: '+direct.length+' | STRONG_PROXY: '+strong.length+' | WEAK_PROXY: '+weak.length+' | UNMEASURABLE: '+unmeas.length);
strong.forEach(s=>console.log('   STRONG: '+s.name));
weak.forEach(s=>console.log('   WEAK: '+s.name));
unmeas.forEach(s=>console.log('   NONE: '+s.name));
console.log('   Verdict: '+out.summary.verdict);
