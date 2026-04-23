const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();
const lm=r('live-mode.json')||{};
const mode=lm.modes.current||'OFF';
const allowed=(lm.permissions_by_mode||{})[mode]||[];

const MAX_DAILY=100; // R100/day hard limit
const MAX_PCT=0.10;   // 10% per campaign

// In real implementation this reads Meta/Google Ads API
// For now: placeholder structure with honest "no data yet"
const campaigns=[
  {id:'camp-1',name:'Booking Intent — IG',budget:500,spent:230,roas:3.2,status:'performing',shift:0},
  {id:'camp-2',name:'Brand Awareness',budget:300,spent:180,roas:1.4,status:'paused',shift:0},
  {id:'camp-3',name:'Retargeting — Visitors',budget:200,spent:90,roas:2.1,status:'learning',shift:0},
];

const actions=[];
const uid=()=>'bud-'+Date.now().toString(36)+Math.random().toString(36).substring(2,6);

// Only act if in LIVE mode with tiny_ad_shift permission
if(!allowed.includes('tiny_ad_shift')){
  actions.push({
    action_id:uid(),type:'blocked',detail:'tiny_ad_shift',
    why:'Mode='+mode+'. Need LIVE mode for ad budget shifts.',
    rule:'mode_restriction',status:'blocked',
  });
} else {
  // Pause obvious loser
  const loser=campaigns.find(c=>c.status==='paused'&&c.roas<1.5);
  if(loser){
    actions.push({
      action_id:uid(),type:'pause',campaign:loser.name,
      amount:loser.budget,from:loser.name,
      why:'ROAS '+loser.roas+' < 1.5 threshold. Pausing to save spend.',
      confidence:0.85,rule:'roas_threshold',reversible:true,
      rollback:'unpause_campaign',status:'recommended',
    });
  }
  // Small boost to winner — within R100 daily limit
  const winner=campaigns.find(c=>c.status==='performing'&&c.roas>2.5);
  if(winner){
    const boost=Math.min(50,winner.budget*0.05);
    if(boost<=MAX_DAILY){
      actions.push({
        action_id:uid(),type:'boost',campaign:winner.name,
        amount:boost,from:'unallocated',
        why:'ROAS '+winner.roas+' > 2.5. Small boost within R'+MAX_DAILY+' daily limit.',
        confidence:0.80,rule:'roas_winner',reversible:true,
        rollback:'reduce_budget',status:'recommended',
      });
    }
  }
}

const out={
  schema:'https://clawdia.io/agents/auto-budget-shifter/v1',
  generated:now.toISOString(),
  mode,
  rules:{max_daily_r:MAX_DAILY,max_pct_per_campaign:MAX_PCT},
  campaigns,
  actions,
  summary:{
    total_actions:actions.length,
    recommended:actions.filter(a=>a.status==='recommended').length,
    blocked:actions.filter(a=>a.status==='blocked').length,
    total_budget_r:campaigns.reduce((s,c)=>s+c.budget,0),
    shift_capacity_r:MAX_DAILY,
  },
  note:'No live Meta/Google Ads API connected. Placeholder — connects when Christelle enables ad accounts.',
};
fs.writeFileSync(path.join(DATA,'budget-actions.json'),JSON.stringify(out,null,2));
console.log('✅ auto_budget_shifter: mode='+mode);
actions.forEach(a=>console.log('   '+a.status.toUpperCase()+': '+a.type+(a.campaign?' '+a.campaign:'')+(a.amount?' R'+a.amount:'')));
console.log('   NOTE: '+out.note.substring(0,80));
