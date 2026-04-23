const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const conn=r('api-connections.json')||{apis:[]};
const unlocks=r('capability-unlocks.json')||{capabilities:[]};
const apis=conn.apis||[];
const caps=(unlocks.capabilities||[]);

// What can we measure RIGHT NOW vs what's blocked
const roiMap=[
  {
    action:'low_risk_publish',name:'Low-Risk Publishing',
    can_measure:true,
    how:'Postiz publishes → IG analytics (via mcporter) shows reach/likes/engagement → GA4 tracks website sessions via UTM → booking confirmations from Swing Shack website',
    current_data:['ig-analytics.json (reach, likes, engagement rate)','website-insights.json (sessions from IG UTM)','booking_flow data (manual correlation)'],
    gap:'Cannot automatically link IG post → specific booking. Needs: Postiz booking attribution API or UTM pass-through to booking system.',
    roi_signal:'indirect',
    priority:1,
  },
  {
    action:'gmb_posting',name:'GMB Posts',
    can_measure:true,
    how:'Weekly GMB posts via Postiz → Google Business Profile shows post views → profile visits → direction calls',
    current_data:['website-insights.json (sessions from google/organic)','gmb-automation posts history'],
    gap:'No live GMB insights API. Post views and profile visits are visible in GMB dashboard manually.',
    roi_signal:'indirect',
    priority:2,
  },
  {
    action:'review_thank_you',name:'Review Thank-Yous',
    can_measure:true,
    how:'5-star thank-yous posted to Google → review rating trend → review count trend',
    current_data:['manual review of Google Business Profile'],
    gap:'No live Google Reviews API. Review response is manual. Only reviews visible publicly.',
    roi_signal:'indirect_long_term',
    priority:3,
  },
  {
    action:'lead_routing',name:'Lead Routing',
    can_measure:false,
    how:null,
    current_data:[],
    gap:'WhatsApp Business API not connected. lead_router_live is 100% simulated. No real leads routed.',
    roi_signal:'unmeasurable',
    priority:1,
  },
  {
    action:'tiny_ad_shift',name:'Budget Shifts',
    can_measure:false,
    how:null,
    current_data:[],
    gap:'Meta Ads API not connected. Budget shifts are placeholder. Cannot measure ROAS.',
    roi_signal:'unmeasurable',
    priority:1,
  },
  {
    action:'evergreen_repost',name:'Evergreen Reposts',
    can_measure:true,
    how:'Same as low_risk_publish — IG analytics shows engagement on reposted content',
    current_data:['ig-analytics.json (engagement on all posts)'],
    gap:'Cannot distinguish evergreen repost from new post without Postiz post-level analytics.',
    roi_signal:'indirect',
    priority:3,
  },
  {
    action:'fallback_swap',name:'Fallback Swaps',
    can_measure:true,
    how:'A/B winner confirmed → winner hook used in next posts → IG analytics shows if winner continues to outperform',
    current_data:['ab-winners.json','ig-analytics.json'],
    gap:'Fallback swaps are infrequent. Cannot isolate swap effect from content quality.',
    roi_signal:'weak_indirect',
    priority:2,
  },
  {
    action:'approval_auto_promote',name:'Auto-Promote Approved',
    can_measure:true,
    how:'Time from approval to publish tracked in Postiz → faster publishing = more content consistency',
    current_data:['approval-log.json (manual)','postiz post queue (manual check)'],
    gap:'No automated approval-to-publish time tracking. Manual correlation needed.',
    roi_signal:'weak_indirect',
    priority:3,
  },
];

const measurable=roiMap.filter(m=>m.can_measure);
const unmeasurable=roiMap.filter(m=>!m.can_measure);

const recommendations=[];
if(unmeasurable.find(m=>m.action==='lead_routing')){
  recommendations.push({action:'Connect WhatsApp Business API',roi:'HIGH — real leads can be tracked from WhatsApp → booking',effort:'medium',blocking:'lead_router_live is simulated'});
}
if(unmeasurable.find(m=>m.action==='tiny_ad_shift')){
  recommendations.push({action:'Fix Meta Ads API + add server-side OAuth',roi:'MEDIUM — ROAS tracking enables data-driven budget moves',effort:'high',blocking:'Token expires same day. Needs OAuth server.'});
}
const measureableWithGaps=measurable.filter(m=>m.gap.includes('Cannot')||m.gap.includes('no live'));
recommendations.push({action:'Connect Postiz booking attribution API',roi:'HIGH — closes measurement loop from post → booking',effort:'medium',blocking:'Current: indirect only'});

const out={
  schema:'https://clawdia.io/agents/roi-measurement-connector/v1',
  generated:now.toISOString(),
  summary:{
    total:roiMap.length,
    measurable:measurable.length,
    unmeasurable:unmeasurable.length,
    measurable_with_gaps:measureableWithGaps.length,
    honest_verdict:'Publishing ROI is indirect and manual. Lead and ad ROI is unmeasurable until APIs connect.',
  },
  roi_map:roiMap,
  measurable,
  unmeasurable,
  recommendations,
};
fs.writeFileSync(path.join(DATA,'roi-coverage.json'),JSON.stringify(out,null,2));
console.log('✅ roi_measurement_connector: '+measurable.length+' measurable, '+unmeasurable.length+' unmeasurable');
measurable.forEach(m=>console.log('   MEASURABLE: '+m.name+' (signal: '+m.roi_signal+')'));
unmeasurable.forEach(m=>console.log('   UNMEASURABLE: '+m.name));
console.log('   Honest: '+out.summary.honest_verdict);
