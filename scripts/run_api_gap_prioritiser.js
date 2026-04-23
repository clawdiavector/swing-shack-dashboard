const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const conn=r('api-connections.json')||{apis:[]};
const roi=r('roi-coverage.json')||{unmeasurable:[]};
const apis=conn.apis||[];
const unmeas=(roi.unmeasurable||[]);

// Rank APIs by: ROI unlock × feasibility × effort
const gaps=[
  {
    api_id:'whatsapp_business',api_name:'WhatsApp Business API',
    status:apis.find(a=>a.id==='whatsapp_business')?.connected?'partial':'disconnected',
    capabilities_blocked:['lead_routing'],
    roi_unlock:'HIGH',
    effort:'medium',
    feasibility:'medium',
    steps:['Get WhatsApp Business API access (Facebook Business app)','Configure webhook for incoming messages','Connect to Postiz or direct MCPorter','Test with one real hot lead'],
    blockers:['WhatsApp Business requires Facebook Business Verification','Premium tier needed for full API','Setup complexity: medium'],
    why_first:'lead_router_live is the highest-value paused capability. WhatsApp is how you close the loop from social → booking. No other integration unlocks this.'},
  {
    api_id:'meta_ads',api_name:'Meta Ads Manager',
    status:apis.find(a=>a.id==='meta_ads')?.connected?'partial':'disconnected',
    capabilities_blocked:['tiny_ad_shift'],
    roi_unlock:'MEDIUM',
    effort:'high',
    feasibility:'medium',
    steps:['Set up Meta OAuth server (long-lived token)','Replace Basic Display with proper Page Access Token','Connect to Postiz or direct Meta API','Enable server-side refresh cron'],
    blockers:['Token expires same-day. Root cause: Basic Display tokens.','Needs OAuth server infrastructure.','Effort is HIGH — not a quick win.'],
    why_first:'High effort. Worth doing but not first.'},
  {
    api_id:'postiz',api_name:'Postiz Booking Attribution',
    status:apis.find(a=>a.id==='postiz')?.connected?'connected':'disconnected',
    capabilities_blocked:['low_risk_publish_roi'],
    roi_unlock:'HIGH',
    effort:'low',
    feasibility:'high',
    steps:['Enable Postiz analytics API (if available)','Add UTM builder to all Postiz posts','Set up GA4 → Postiz data link','Track: post → click → booking confirmation'],
    blockers:['Postiz may not expose booking attribution API','UTM pass-through to booking system needs server config','Swing Shack booking system integration needed'],
    why_first:'Already connected. Only adds data layer, not new integration.'},
  {
    api_id:'search_console',api_name:'Google Search Console',
    status:'disconnected',
    capabilities_blocked:['seo_performance_tracking'],
    roi_unlock:'MEDIUM',
    effort:'medium',
    feasibility:'medium',
    steps:['Verify site ownership in GSC','Set up service account access','Connect to GA4 dashboard','Enable: queries → clicks → conversions'],
    blockers:['No credentials in credentials/','GSC is read-only — low risk integration','SEO data helps blog content decisions'],
    why_first:'Medium value, medium effort. Good for content intelligence.'},
  {
    api_id:'youtube',api_name:'YouTube Data API',
    status:'disconnected',
    capabilities_blocked:['hook_smith_youtube_signals'],
    roi_unlock:'LOW',
    effort:'low',
    feasibility:'high',
    steps:['Get YouTube Data API v3 key from Google Cloud','Add to credentials/','hook_smith already uses scraper — API would improve signal'],
    blockers:['hook_smith works with scraper already. API would be enhancement not requirement.'],
    why_first:'Nice to have. hook_smith is functional without it.'},
  {
    api_id:'google_business',api_name:'Google Business Profile API',
    status:apis.find(a=>a.id==='google_business')?.connected?'connected':'disconnected',
    capabilities_blocked:['review_response_posting'],
    roi_unlock:'MEDIUM',
    effort:'medium',
    feasibility:'medium',
    steps:['Verify GMB API access in Google Cloud Console','Enable read-write scopes','Connect to reputation_responder for auto-posting'],
    blockers:['Google restricts GMB API — only允许 businesses with verified locations','reputation_responder already drafts well. Full posting needs extra setup.'],
    why_first:'Already connected for posting. Review posting needs verified access.'},
];

const ranked=gaps.sort((a,b)=>{
  const roiScore={HIGH:3,MEDIUM:2,LOW:1}[a.roi_unlock]||0;
  const effScore={high:0,medium:1,low:2}[a.feasibility]||0;
  const effortScore={high:0,medium:1,low:2}[a.effort]||0;
  return (roiScore+effScore+effortScore);
});

ranked.forEach((g,i)=>g.rank=i+1);

const out={
  schema:'https://clawdia.io/agents/api-gap-prioritiser/v1',
  generated:now.toISOString(),
  summary:{
    total_gaps:gaps.length,
    immediate_priority:ranked[0]?.api_name||'none',
    roi_impact:ranked.map(g=>g.roi_unlock).filter((v,i,a)=>a.indexOf(v)===i).join(', '),
    next_step:ranked[0]?'Connect '+ranked[0].api_name+' — '+ranked[0].steps[0]:'All APIs connected',
  },
  gaps:ranked,
  immediate_action:ranked[0]||null,
};
fs.writeFileSync(path.join(DATA,'api-gap-priority.json'),JSON.stringify(out,null,2));
console.log('✅ api_gap_prioritiser: '+gaps.length+' gaps ranked');
ranked.forEach(g=>console.log('   #'+g.rank+' '+g.api_name+' (ROI:'+g.roi_unlock+', effort:'+g.effort+')'));
console.log('   IMMEDIATE: '+out.summary.next_step);
