const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

const lm=r('live-mode.json')||{};
const audit=r('live-action-audit.json')||{};
const perf=r('autonomy-performance.json')||{};
const guardian=r('mode-guardian.json')||{};
const mode=lm.modes?.current||'OFF';
const trust=lm.modes?.trust_score||7.2;

const capabilities=[
  {
    id:'discord_nudge',name:'Discord Nudges',allowed:true,
    reliability:lm.permissions_by_mode?.[mode]?.includes('discord_nudge')?8:0,
    value:3, // low risk but unmeasured
    risk:2,
    verdict:'keep',
    reason:'Low risk, low blast radius. Keeps research responsive.',
    evidence:'Allowed in '+mode+' mode',
  },
  {
    id:'fallback_swap',name:'Fallback Swaps',allowed:true,
    reliability:lm.permissions_by_mode?.[mode]?.includes('fallback_swap')?8:0,
    value:5,
    risk:3,
    verdict:'keep',
    reason:'A/B winners improve content quality automatically.',
    evidence:'Swap to winner hook when confirmed',
  },
  {
    id:'story_scheduling',name:'Story Scheduling',allowed:lm.permissions_by_mode?.[mode]?.includes('story_scheduling')||false,
    reliability:lm.permissions_by_mode?.[mode]?.includes('story_scheduling')?6:0,
    value:4,
    risk:4,
    verdict:'keep',
    reason:'Stories are ephemeral — low blast radius if wrong.',
    evidence:'Low risk if branded template used',
  },
  {
    id:'evergreen_repost',name:'Evergreen Reposts',allowed:lm.permissions_by_mode?.[mode]?.includes('evergreen_repost')||false,
    reliability:lm.permissions_by_mode?.[mode]?.includes('evergreen_repost')?7:0,
    value:4,
    risk:3,
    verdict:'keep',
    reason:'Reusing proven hooks is efficient and safe.',
    evidence:'Only approved hooks get reposted',
  },
  {
    id:'approval_auto_promote',name:'Auto-Promote Approved',allowed:lm.permissions_by_mode?.[mode]?.includes('approval_auto_promote')||false,
    reliability:lm.permissions_by_mode?.[mode]?.includes('approval_auto_promote')?7:0,
    value:5,
    risk:4,
    verdict:'keep_with_watch',
    reason:'Auto-promoting approved content speeds up workflow.',
    evidence:'Only Christelle-approved items promoted',
    watch:'Monitor for drift — if approval rate drops, pause',
  },
  {
    id:'low_risk_publish',name:'Low-Risk Publishing',allowed:lm.permissions_by_mode?.[mode]?.includes('low_risk_publish')||false,
    reliability:lm.permissions_by_mode?.[mode]?.includes('low_risk_publish')?7:0,
    value:7,
    risk:6,
    verdict:'keep_with_watch',
    reason:'Actual IG posting is highest-value autonomy capability.',
    evidence:'One wrong post can be deleted — reversible',
    watch:'Content filter must catch banned words. Test weekly.',
  },
  {
    id:'lead_routing',name:'Lead Routing',allowed:lm.permissions_by_mode?.[mode]?.includes('lead_routing')||false,
    reliability:lm.permissions_by_mode?.[mode]?.includes('lead_routing')?5:0,
    value:8,
    risk:8,
    verdict:'pause_until_proven',
    reason:'HIGH risk — non-reversible routing. WhatsApp message cant be recalled.',
    evidence:'No real lead data yet — WhatsApp API not connected',
    watch:'Never route without manual gate on hot leads',
  },
  {
    id:'tiny_ad_shift',name:'Budget Shifts',allowed:lm.permissions_by_mode?.[mode]?.includes('tiny_ad_shift')||false,
    reliability:lm.permissions_by_mode?.[mode]?.includes('tiny_ad_shift')?4:0,
    value:5,
    risk:7,
    verdict:'paused',
    reason:'Meta Ads API not connected — placeholder only.',
    evidence:'Budget shifts are blocked until API connected',
  },
];

// Apply guardian freeze overrides
capabilities.forEach(c=>{
  const gc=(guardian.capability_controls||{})[c.id];
  if(gc&&gc.status!=='active'){
    c.allowed=false;
    c.verdict='paused';
    c.paused_by=gc.paused_by||'guardian';
    c.pause_reason=gc.reason||'guardian decision';
  }
});

const keep=capabilities.filter(c=>c.verdict==='keep'||c.verdict==='keep_with_watch');
const pause=capabilities.filter(c=>c.verdict==='pause_until_proven'||c.verdict==='paused');
const expand=capabilities.filter(c=>c.verdict==='expand');

const out={
  schema:'https://clawdia.io/agents/live-mode-scorecard/v1',
  generated:now.toISOString(),
  mode,trust,
  summary:{
    total:capabilities.length,
    keep:keep.length,
    pause:pause.length,
    expand:expand.length,
    overall:'LIVE mode is justified for: '+keep.map(c=>c.name).join(', ')+'. '+pause.length+' capabilities are paused or need proof first.',
  },
  capabilities,
  keep,
  pause,
  recommendations:capabilities.map(c=>{
    if(c.verdict==='pause_until_proven')return{capability:c.id,verdict:c.verdict,action:'PAUSE '+c.name+' until '+c.evidence,priority:1};
    if(c.verdict==='keep_with_watch')return{capability:c.id,verdict:c.verdict,action:'KEEP '+c.name+' — '+c.watch,priority:2};
    return null;
  }).filter(Boolean),
};
fs.writeFileSync(path.join(DATA,'live-mode-scorecard.json'),JSON.stringify(out,null,2));
console.log('✅ live_mode_scorecard: '+mode+', trust='+trust);
console.log('   KEEP: '+keep.map(c=>c.name).join(', '));
console.log('   PAUSE: '+pause.map(c=>c.name).join(', '));
keep.filter(c=>c.verdict==='keep_with_watch').forEach(c=>console.log('   WATCH: '+c.name+' — '+c.watch));
pause.forEach(c=>console.log('   PAUSE: '+c.name+' — '+c.evidence));
