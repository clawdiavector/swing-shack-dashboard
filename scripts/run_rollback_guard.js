const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

// Check all recent actions across all logs
const logs=['live-publish-log.json','budget-actions.json','lead-routing-log.json','review-actions.json'];
const recentActions=[];
logs.forEach(log=>{
  const d=r(log);
  if(d&&d.actions)d.actions.forEach(a=>recentActions.push({...a,source:log.replace('.json','')}));
});
recentActions.sort((a,b)=>new Date(b.generated||0)-new Date(a.generated||0));

// Anomaly detection — simple rules
const anomalies=[];
const uid=()=>'rb-'+Date.now().toString(36)+Math.random().toString(36).substring(2,6);

// Check trust score
const lm=r('live-mode.json')||{};
const trust=lm.trust_score||10;
if(trust<6)anomalies.push({id:uid(),type:'trust_score_critical',detail:'Trust='+trust+'. OFF mode forced.',action:'mode_force_off',status:'triggered',generated:now.toISOString()});
else if(trust<7)anomalies.push({id:uid(),type:'trust_score_low',detail:'Trust='+trust+'. MINIMAL mode only.',action:'downgrade_to_minimal',status:'triggered',generated:now.toISOString()});
else if(trust<8)anomalies.push({id:uid(),type:'trust_score_warning',detail:'Trust='+trust+'. LIMITED max.',action:'warn_limit_mode',status:'active',generated:now.toISOString()});

// Check for failed actions
const failedActions=recentActions.filter(a=>a.status==='failed'||a.status==='error');
if(failedActions.length>=3)anomalies.push({id:uid(),type:'action_failure_spike',detail:failedActions.length+' failures in recent actions.',action:'freeze_publishers',status:'triggered',generated:now.toISOString()});

// Recent rollback log
const rollbackLog=r('rollback-log.json')||{rollbacks:[]};
const recentRollbacks=rollbackLog.rollbacks.filter(rb=>new Date(rb.rolled_back_at)>new Date(Date.now()-86400000));

const safetyActions=[];
if(anomalies.some(a=>a.status==='triggered')){
  safetyActions.push({
    action_id:uid(),type:'freeze_autonomy',scope:'all',
    why:'Anomaly detected. Safety freeze active until cleared.',
    until:'manual_clear',status:'active',
  });
}

const out={
  schema:'https://clawdia.io/agents/rollback-guard/v1',
  generated:now.toISOString(),
  trust_score:trust,
  anomalies,
  safety_actions:safetyActions,
  recent_rollbacks:recentRollbacks.slice(0,5),
  rollback_capability:{
    can_undo:true,
    can_freeze:true,
    can_restore_config:true,
    reversible_actions:recentActions.filter(a=>a.reversible===true).length,
    irreversible_actions:recentActions.filter(a=>a.reversible===false).length,
  },
  summary:{
    anomalies_active:anomalies.filter(a=>a.status==='triggered').length,
    safety_freezes:safetyActions.length,
    rollbacks_today:recentRollbacks.length,
  },
};
fs.writeFileSync(path.join(DATA,'rollback-log.json'),JSON.stringify(out,null,2));
console.log('✅ rollback_guard: trust='+trust);
console.log('   Anomalies: '+anomalies.length+' ('+anomalies.filter(a=>a.status==='triggered').length+' triggered)');
console.log('   Safety freezes: '+safetyActions.length);
console.log('   Reversible actions: '+out.rollback_capability.reversible_actions);
