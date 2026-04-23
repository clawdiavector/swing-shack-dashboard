const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

// Trust score starts at OFF for safety
const lastRun=r('agent-runs.json');
const runCount=lastRun?Object.values(lastRun.agents||{}).reduce((s,a)=>s+a.length,0):0;
const failRate=lastRun?(Object.values(lastRun.agents||{}).flat().filter(a=>a.status!=='PASS').length/Math.max(Object.values(lastRun.agents||{}).flat().length,1)):0;
const trustScore=Math.max(0,Math.min(10,10-(failRate*10)-0.5));

const modes=['OFF','MINIMAL','LIMITED','LIVE','LIVE_PLUS'];
const currentMode=(trustScore>=9?'LIVE':trustScore>=8?'LIMITED':trustScore>=7?'MINIMAL':'OFF');

const kills={
  pricing:false,legal:false,sensitive:false,budget_over_r100:false,negative_reviews:false,
};
const overrides={manual_override:false,kill_switch_triggered:false};

const agentRuns=lastRun?Object.values(lastRun.agents||{}).flat().slice(-20):[];
const recentFails=agentRuns.filter(a=>a.status!=='PASS').length;
const recentPass=agentRuns.filter(a=>a.status==='PASS').length;
const runSuccess=recentPass+recentFails>0?recentPass/(recentPass+recentFails):1;

const out={
  schema:'https://clawdia.io/agents/live-mode-controller/v1',
  generated:now.toISOString(),
  modes:{available:modes,current:currentMode,trust_score:Math.round(trustScore*10)/10},
  kill_switches:kills,
  overrides,
  permissions_by_mode:{
    OFF:['reporting','dashboard','alerts'],
    MINIMAL:['reporting','dashboard','alerts','discord_nudge','fallback_swap'],
    LIMITED:['reporting','dashboard','alerts','discord_nudge','fallback_swap','story_scheduling','evergreen_repost','approval_auto_promote'],
    LIVE:['reporting','dashboard','alerts','discord_nudge','fallback_swap','story_scheduling','evergreen_repost','approval_auto_promote','low_risk_publish','lead_routing','tiny_ad_shift'],
    LIVE_PLUS:['reporting','dashboard','alerts','discord_nudge','fallback_swap','story_scheduling','evergreen_repost','approval_auto_promote','low_risk_publish','lead_routing','tiny_ad_shift','review_thank_you','experiment'],
  },
  trust_rules:{9:'LIVE allowed',8:'LIMITED max',7:'MINIMAL max',6:'OFF forced'},
  summary:{
    mode:currentMode,trust_score:Math.round(trustScore*10)/10,
    off_switches:Object.values(kills).filter(Boolean).length,
    run_success_rate:Math.round(runSuccess*100)+'%',
    total_runs:runCount,
  },
};
fs.writeFileSync(path.join(DATA,'live-mode.json'),JSON.stringify(out,null,2));
console.log('✅ live_mode_controller: '+currentMode+' (trust: '+Math.round(trustScore*10)/10+')');
console.log('   OFF triggers: '+Object.entries(kills).filter(([,v])=>v).map(([k])=>k).join(', ')||'none');
console.log('   Allowed: '+out.permissions_by_mode[currentMode].join(', '));
