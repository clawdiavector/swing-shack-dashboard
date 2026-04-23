const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const conn=r('api-connections.json')||{apis:[]};
const health=r('integration-health.json')||{health:[]};
const apis=conn.apis||[];
const healthById={};
(health.health||[]).forEach(h=>{healthById[h.id]=h;});

const lm=r('live-mode.json')||{};
const scorecard=r('live-mode-scorecard.json')||{};
const mode=lm.modes?.current||'OFF';
const trust=lm.modes?.trust_score||7.2;

// Map autonomy capabilities → required APIs → current status
const capabilityMap=[
  {
    id:'discord_nudge',name:'Discord Nudges',
    required_apis:['discord'],
    required_connections:[],
    current_status:'live',
    api_status:'connected',
    measurement:'discord_nudge_sent_log',
    reason:'Discord bot connected via OpenClaw. No external API needed.',
  },
  {
    id:'fallback_swap',name:'Fallback Swaps',
    required_apis:['postiz'],
    required_connections:['postiz'],
    current_status: apis.find(a=>a.id==='postiz')?.connected?'live':'paused',
    api_status: apis.find(a=>a.id==='postiz')?.connected?'connected':'not_connected',
    measurement:'ab_winner_confirmed + hook_swap_log',
    reason:'Uses existing IG analytics data. No additional API needed.',
  },
  {
    id:'story_scheduling',name:'Story Scheduling',
    required_apis:['postiz'],
    required_connections:['postiz'],
    current_status: apis.find(a=>a.id==='postiz')?.connected?'live':'paused',
    api_status: apis.find(a=>a.id==='postiz')?.connected?'connected':'not_connected',
    measurement:'story_views + story_completions',
    reason:'Postiz handles story scheduling. IG Business API needed for insights.',
  },
  {
    id:'evergreen_repost',name:'Evergreen Reposts',
    required_apis:['postiz'],
    required_connections:['postiz'],
    current_status: apis.find(a=>a.id==='postiz')?.connected?'live':'paused',
    api_status: apis.find(a=>a.id==='postiz')?.connected?'connected':'not_connected',
    measurement:'post_engagement_on_reposts',
    reason:'Same as story scheduling. Reusing approved content.',
  },
  {
    id:'approval_auto_promote',name:'Auto-Promote Approved',
    required_apis:['postiz'],
    required_connections:['postiz'],
    current_status: apis.find(a=>a.id==='postiz')?.connected?'live':'paused',
    api_status: apis.find(a=>a.id==='postiz')?.connected?'connected':'not_connected',
    measurement:'approved_to_published_time',
    reason:'Postiz handles promotion. Already wired in.',
  },
  {
    id:'low_risk_publish',name:'Low-Risk Publishing',
    required_apis:['postiz','instagram_content'],
    required_connections:['postiz'],
    current_status: apis.find(a=>a.id==='postiz')?.connected?'live':'paused',
    api_status: apis.find(a=>a.id==='postiz')?.connected?'connected':'not_connected',
    measurement:'post_reach + engagement_rate + booking_conversions_via_utms',
    reason:'Postiz publishes. IG analytics shows reach. UTMs track conversions.',
  },
  {
    id:'lead_routing',name:'Lead Routing',
    required_apis:['whatsapp_business'],
    required_connections:['whatsapp_business'],
    current_status: apis.find(a=>a.id==='whatsapp_business')?.connected?'live':'paused',
    api_status: apis.find(a=>a.id==='whatsapp_business')?.connected?'connected':'not_connected',
    measurement:'lead_response_time + conversion_rate + sla_met_pct',
    reason:'WhatsApp Business API required. Current: simulated only.',
  },
  {
    id:'tiny_ad_shift',name:'Budget Shifts',
    required_apis:['meta_ads'],
    required_connections:['meta_ads'],
    current_status: (healthById['meta_ads']?.status==='connected'||healthById['meta_ads']?.auth_status==='active')?'live':'paused',
    api_status: healthById['meta_ads']?.status||'not_connected',
    measurement:'roas_change + cost_per_booking',
    reason:'Meta Ads API required. Token unstable — needs server-side OAuth.',
  },
  {
    id:'review_thank_you',name:'Review Thank-Yous',
    required_apis:['google_business'],
    required_connections:['google_business'],
    current_status: apis.find(a=>a.id==='google_business')?.connected?'live':'paused',
    api_status: apis.find(a=>a.id==='google_business')?.connected?'connected':'not_connected',
    measurement:'review_rating_delta + review_response_rate',
    reason:'Google Business Profile API required. GMB is connected via Postiz.',
  },
  {
    id:'gmb_posting',name:'GMB Posts',
    required_apis:['google_business'],
    required_connections:['google_business'],
    current_status: apis.find(a=>a.id==='google_business')?.connected?'live':'paused',
    api_status: apis.find(a=>a.id==='google_business')?.connected?'connected':'not_connected',
    measurement:'gmb_post_impressions + profile_visits',
    reason:'GMB automation running weekly. Postiz handles scheduling.',
  },
];

const live=capabilityMap.filter(c=>c.current_status==='live');
const paused=capabilityMap.filter(c=>c.current_status==='paused');
const locked=capabilityMap.filter(c=>c.current_status==='locked');

const recommendations=[];
paused.forEach(c=>{
  const missingApis=c.required_connections.filter(apiId=>{
    const a=apis.find(a=>a.id===apiId);
    return !a||!a.connected;
  });
  if(missingApis.length>0){
    recommendations.push({capability:c.id,name:c.name,missing_apis:missingApis,priority:c.id==='lead_routing'?1:c.id==='tiny_ad_shift'?2:3});
  }
});

const out={
  schema:'https://clawdia.io/agents/capability-unlock-engine/v1',
  generated:now.toISOString(),
  mode,trust,
  summary:{total:capabilityMap.length,live:live.length,paused:paused.length,locked:locked.length},
  capabilities:capabilityMap,
  live,
  paused,
  recommendations:recommendations.sort((a,b)=>a.priority-b.priority),
};
fs.writeFileSync(path.join(DATA,'capability-unlocks.json'),JSON.stringify(out,null,2));
console.log('✅ capability_unlock_engine: '+live.length+' live, '+paused.length+' paused');
live.forEach(c=>console.log('   LIVE: '+c.name+' ('+c.measurement+')'));
paused.forEach(c=>console.log('   PAUSED: '+c.name+' — needs: '+c.required_connections.join(', ')));
