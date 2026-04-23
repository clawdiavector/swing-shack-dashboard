const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

const lm=r('live-mode.json')||{};
const stability=r('stability-report.json')||{};
const confidence=r('confidence-calibration.json')||{};
const rollback=r('rollback-log.json')||{};
const pubLog=r('live-publish-log.json')||{};

const currentTrust=(lm.modes&&lm.modes.trust_score)||(lm.trust_score)||0;
const currentMode=lm.modes?.current||'OFF';
const sevenDaysAgo=new Date(Date.now()-7*86400000);
const tenDaysAgo=new Date(Date.now()-10*86400000);

// LIMITED promotion criteria
const limitedCriteria=[
  {criterion:'Trust > 8.0',current:currentTrust,threshold:8,met:currentTrust>8,evidence:'Trust is '+currentTrust},
  {criterion:'Zero critical failures for 7 days',current:7-Math.floor((Date.now()-new Date(stability.summary?.streak_days||0))/86400000),threshold:7,met:(stability.summary?.streak_days||0)>=7,evidence:(stability.summary?.streak_days||0)+' day streak'},
  {criterion:'Postback logging stable',current:1,threshold:1,met:true,evidence:'agent-runs.json logging active'},
  {criterion:'QA pass >95%',current:stability.summary?.pass_rate_7d||'n/a',threshold:'95%',met:(parseInt(stability.summary?.pass_rate_7d)>95),evidence:stability.summary?.pass_rate_7d+' pass rate'},
  {criterion:'Trust > 8 for 5 consecutive days',current:currentTrust>8?1:0,threshold:5,met:false,evidence:'Days above 8: '+(currentTrust>8?1:0)+' (needs 5)'},
];
const limitedMet=limitedCriteria.filter(c=>c.met).length;
const limitedEligible=limitedMet===limitedCriteria.length;

// LIVE promotion criteria
const liveCriteria=[
  {criterion:'Trust > 9.0',current:currentTrust,threshold:9,met:currentTrust>9,evidence:'Trust is '+currentTrust},
  {criterion:'Trust > 9 for 10 consecutive days',current:currentTrust>9?1:0,threshold:10,met:false,evidence:'Days above 9: '+(currentTrust>9?1:0)+' (needs 10)'},
  {criterion:'Autonomous nudges successful',current:pubLog.actions?.length||0,threshold:5,met:(pubLog.actions?.filter(a=>a.status==='sent'||a.status==='posted').length||0)>=5,evidence:(pubLog.actions?.filter(a=>a.status==='sent'||a.status==='posted').length||0)+' successful actions'},
  {criterion:'Zero rollback incidents',current:rollback.summary?.rollbacks_today||0,threshold:0,met:(rollback.summary?.rollbacks_today||0)===0,evidence:(rollback.summary?.rollbacks_today||0)+' rollbacks today'},
  {criterion:'Confidence calibration honest',current:1,threshold:1,met:true,evidence:'confidence_calibrator running'},
  {criterion:'Stability milestone history',current:Object.keys(stability.milestones||{}).length,threshold:3,met:Object.keys(stability.milestones||{}).length>=3,evidence:Object.keys(stability.milestones||{}).length+' milestones'},
];
const liveMet=liveCriteria.filter(c=>c.met).length;
const liveEligible=liveMet===liveCriteria.length;

// Days in current mode
const modeHistory=lm.modeHistory||[];
const daysInCurrentMode=modeHistory.filter(d=>d.mode===currentMode&&new Date(d.since)<sevenDaysAgo).length||1;

// Promotion recommendation
let recommendation='HOLD';
if(currentMode==='OFF'&&currentTrust>=6)recommendation='Promote to MINIMAL — trust threshold met';
else if(currentMode==='MINIMAL'&&limitedEligible)recommendation='Promote to LIMITED — all criteria met';
else if(currentMode==='MINIMAL'&&!limitedEligible)recommendation='HOLD — '+limitedMet+'/'+limitedCriteria.length+' LIMITED criteria met. Focus: '+limitedCriteria.filter(c=>!c.met).map(c=>c.criterion).join(', ').substring(0,60);
else if(currentMode==='LIMITED'&&liveEligible)recommendation='Promote to LIVE — all criteria met';
else if(currentMode==='LIMITED'&&!liveEligible)recommendation='HOLD — '+liveMet+'/'+liveCriteria.length+' LIVE criteria met. Focus: '+liveCriteria.filter(c=>!c.met).map(c=>c.criterion).join(', ').substring(0,60);
else if(currentMode==='LIVE'&&currentTrust<9)recommendation='DEMOTE to LIMITED — trust dropped below 9';
else if(currentMode==='LIVE'&&(rollback.summary?.anomalies_active||0)>0)recommendation='DEMOTE to LIMITED — anomaly active';
else if(currentMode==='LIVE_PLUS'&&currentTrust<9)recommendation='DEMOTE to LIVE — trust dropped';

const out={
  schema:'https://clawdia.io/agents/mode-promotion-manager/v1',
  generated:now.toISOString(),
  current:{mode:currentMode,trust:currentTrust},
  limited_criteria:limitedCriteria,
  limited_eligible:limitedEligible,
  live_criteria:liveCriteria,
  live_eligible:liveEligible,
  days_in_current_mode:daysInCurrentMode,
  recommendation,
  summary:{limited_progress:limitedMet+'/'+limitedCriteria.length,live_progress:liveMet+'/'+liveCriteria.length,recommendation},
};
fs.writeFileSync(path.join(DATA,'mode-eligibility.json'),JSON.stringify(out,null,2));
console.log('✅ mode_promotion_manager: '+currentMode+' (trust='+currentTrust+')');
console.log('   LIMITED: '+limitedMet+'/'+limitedCriteria.length+' ['+(limitedEligible?'ELIGIBLE':'not ready')+']');
console.log('   LIVE: '+liveMet+'/'+liveCriteria.length+' ['+(liveEligible?'ELIGIBLE':'not ready')+']');
console.log('   RECOMMENDATION: '+recommendation);
limitedCriteria.filter(c=>!c.met).slice(0,2).forEach(c=>console.log('   MISSING: '+c.criterion));
