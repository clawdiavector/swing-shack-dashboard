const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

const lm=r('live-mode.json')||{};
const audit=r('live-action-audit.json')||{};
const rollback=r('rollback-log.json')||{};
const mode=lm.modes?.current||'OFF';
const trust=lm.modes?.trust_score||7.2;

// Capability-level freeze controls
// Individual capability can be paused without killing all autonomy
const capabilityStatus={
  discord_nudge:{status:'active',paused_by:null,failures:0,last_fail:null},
  fallback_swap:{status:'active',paused_by:null,failures:0,last_fail:null},
  story_scheduling:{status:'active',paused_by:null,failures:0,last_fail:null},
  evergreen_repost:{status:'active',paused_by:null,failures:0,last_fail:null},
  approval_auto_promote:{status:'active',paused_by:null,failures:0,last_fail:null},
  low_risk_publish:{status:'active',paused_by:null,failures:0,last_fail:null},
  lead_routing:{status:'active',paused_by:null,failures:0,last_fail:null},
  tiny_ad_shift:{status:'paused',paused_by:'guardian',reason:'Meta Ads API not connected',last_fail:null},
};

// Check audit findings — any bad actions?
const badActions=(audit.bad_actions||[]).length;
const questionableActions=(audit.questionable_actions||[]).length;

// Check rollback incidents
const rollbacksToday=(rollback.summary?.rollbacks_today||0);
const anomaliesActive=(rollback.summary?.anomalies_active||0);

// Auto-freeze rules
const freezeActions=[];
// Bad action detected → freeze only that capability class
if(badActions>0){
  freezeActions.push({capability:'low_risk_publish',action:'freeze',reason:'Bad action in audit — requires review before re-enabling',until:'manual_review'});
}
if(questionableActions>3){
  freezeActions.push({capability:'approval_auto_promote',action:'probation',reason:'Too many questionable actions — probation until reviewed',until:'guardian_clear'});
}
if(rollbacksToday>=2){
  freezeActions.push({capability:'lead_routing',action:'freeze',reason:'Multiple rollbacks today — freeze lead routing',until:'guardian_clear'});
}
if(anomaliesActive>0){
  freezeActions.push({capability:'tiny_ad_shift',action:'freeze',reason:'Active anomaly — budget shifts frozen',until:'anomaly_clear'});
}

// Apply freeze actions
freezeActions.forEach(fa=>{
  if(capabilityStatus[fa.capability]){
    capabilityStatus[fa.capability].status=fa.action;
    capabilityStatus[fa.capability].paused_by=fa.until==='manual_review'?'manual':fa.until==='guardian_clear'?'guardian':'system';
    capabilityStatus[fa.capability].last_fail=now.toISOString();
  }
});

// Mode downgrade check
let modeAction=null;
if(trust<6&&mode!=='OFF')modeAction={action:'force_OFF',reason:'Trust <6',by:'guardian'};
else if(trust<7&&mode==='LIVE')modeAction={action:'demote_LIMITED',reason:'Trust <7',by:'guardian'};
else if(trust<8&&mode==='LIMITED')modeAction={action:'demote_MINIMAL',reason:'Trust <8',by:'guardian'};
else if(trust<9&&mode==='LIVE_PLUS')modeAction={action:'demote_LIVE',reason:'Trust <9',by:'guardian'};

// Streak recovery — how many clean days until re-enabling frozen capabilities?
const streakDays=(lm.modes?.streak_days)||0;
const recoveryEligible=streakDays>=7;

const out={
  schema:'https://clawdia.io/agents/mode-guardian/v1',
  generated:now.toISOString(),
  current_mode:mode,
  trust,
  mode_action:modeAction,
  capability_controls:capabilityStatus,
  active_capabilities:Object.values(capabilityStatus).filter(c=>c.status==='active').length,
  frozen_capabilities:Object.values(capabilityStatus).filter(c=>c.status!=='active').length,
  freeze_actions_this_run:freezeActions,
  recovery:{streak_days:streakDays,eligible:recoveryEligible,eligible_after_days:Math.max(0,7-streakDays)},
  summary:{
    mode_healthy:!modeAction,
    capabilities_healthy:freezeActions.length===0,
    verdict:modeAction?'DOWNGRADE_RECOMMENDED':freezeActions.length>0?'CAPABILITIES_FROZEN':'ALL_HEALTHY',
  },
};
fs.writeFileSync(path.join(DATA,'mode-guardian.json'),JSON.stringify(out,null,2));
console.log('✅ mode_guardian: mode='+mode+', trust='+trust);
console.log('   Active: '+out.active_capabilities+' | Frozen: '+out.frozen_capabilities);
console.log('   Freeze actions: '+freezeActions.length);
freezeActions.forEach(f=>console.log('   FREEZE: '+f.capability+' — '+f.reason.substring(0,50)));
if(modeAction)console.log('   '+modeAction.action+': '+modeAction.reason);
else console.log('   Mode healthy — no downgrade needed');
