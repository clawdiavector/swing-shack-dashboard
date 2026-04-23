const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const lm=r('live-mode.json')||{};
const mode=lm.modes.current||'OFF';
const allowed=(lm.permissions_by_mode||{})[mode]||[];

const actions=[];
const uid=()=>'pub-'+Date.now().toString(36)+Math.random().toString(36).substring(2,6);

// Safe actions available in LIMITED/LIVE
const safeTypes=['evergreen_repost','story_scheduling','approval_auto_promote','low_risk_publish'];
const ig=r('ig-analytics.json');
const posts=(ig&&ig.posts)||[];
const recentApproved=posts.filter(p=>p.approved&&!p.live_published).slice(0,3);

recentApproved.forEach(p=>{
  const actionId=uid();
  const safeType=p.hook_type==='static'?'low_risk_publish':'evergreen_repost';
  if(!allowed.includes(safeType))return;
  actions.push({
    action_id:actionId,
    type:safeType,
    post_id:p.id||actionId,
    hook:p.hook||'',
    caption:p.caption?'[caption exists]':'',
    why:'Approved post ready to go. '+safeType+' is low risk.',
    confidence:0.92,
    rule:'approved_post_ready',
    reversible:true,
    rollback:'delete_from_queue',
    status:'queued',
    scheduled:null,
    mode,
  });
});

// Fallback swaps — swap hooks if A/B winner known
const ab=r('ab-winners.json');
if(ab&&ab.winner&&allowed.includes('fallback_swap')){
  const winner=ab.winner;
  actions.push({
    action_id:uid(),
    type:'fallback_swap',
    what:'Use hook: '+winner,
    why:'A/B winner confirmed. Swap to winner across queued posts.',
    confidence:0.88,
    rule:'ab_winner_confirmed',
    reversible:true,
    rollback:'revert_to_control',
    status:'queued',
    mode,
  });
}

// Discord nudges
if(allowed.includes('discord_nudge')){
  actions.push({
    action_id:uid(),
    type:'discord_nudge',
    target:'research_agent',
    why:'Trending topic window open. Nudge research for relevant hook.',
    confidence:0.75,
    rule:'trending_window',
    reversible:false,
    rollback:null,
    status:'sent',
    mode,
  });
}

const out={
  schema:'https://clawdia.io/agents/autonomous-publisher-live/v1',
  generated:now.toISOString(),
  mode,
  allowed_actions:allowed,
  blocked_reason:!allowed.includes('low_risk_publish')&&!allowed.includes('evergreen_repost')&&!allowed.includes('discord_nudge')?'Mode too restrictive — no safe actions available':null,
  actions_taken:actions.length,
  actions,
  summary:{
    queued:actions.filter(a=>a.status==='queued').length,
    sent:actions.filter(a=>a.status==='sent').length,
    blocked:actions.filter(a=>a.status==='blocked').length,
  },
};
fs.writeFileSync(path.join(DATA,'live-publish-log.json'),JSON.stringify(out,null,2));
console.log('✅ autonomous_publisher_live: mode='+mode+', '+actions.length+' actions');
actions.filter(a=>a.status==='queued').slice(0,2).forEach(a=>console.log('   QUEUED: '+a.type+' — '+a.why.substring(0,50)));
