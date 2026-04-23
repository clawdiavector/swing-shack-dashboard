const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

// Audit every autonomous action taken in LIVE mode
const pubLog=r('live-publish-log.json')||{};
const budgetAct=r('budget-actions.json')||{};
const leadLog=r('lead-routing-log.json')||{};
const reviewAct=r('review-actions.json')||{};
const lm=r('live-mode.json')||{};
const mode=lm.modes?.current||'OFF';

// Build action log from all live agents
const allActions=[];
const sources=[
  {actions:(pubLog||{}).actions||[],source:'publisher'},
  {actions:(budgetAct||{}).actions||[],source:'budget'},
  {actions:(leadLog||{}).actions||[],source:'lead'},
  {actions:(reviewAct||{}).actions||[],source:'review'},
];
sources.forEach(src=>{
  (src.actions||[]).forEach(a=>{
    const confidence=a.confidence||0.70;
    const wasAllowed=a.status==='sent'||a.status==='posted'||a.status==='queued'||a.status==='recommended';
    // Confidence check
    let confidenceHonest=true;
    if(a.type&&a.type.includes('publish')&&confidence<0.80)confidenceHonest=false;
    if(a.type==='review_thank_you'&&confidence<0.85)confidenceHonest=false;
    // Rollback needed?
    let rollbackNeeded=false;
    if(a.status==='posted'&&a.reversible===false)rollbackNeeded=true;
    if(a.status==='sent'&&a.reversible===false)rollbackNeeded=true;
    // Rule-based = presumed allowed
    const matchedRule=!!a.rule;
    // Honest verdict
    let should_allowed='pending';
    if(a.status==='queued'||a.status==='recommended'||a.status==='draft'||a.status==='drafted')should_allowed='yes';
    else if(wasAllowed&&confidence>=0.75&&matchedRule)should_allowed='yes';
    else if(wasAllowed&&confidence>=0.60)should_allowed='questionable';
    else if(wasAllowed)should_allowed='no';
    else should_allowed='pending';

    allActions.push({...a,confidence,confidence_honest:confidenceHonest,rollback_needed:rollbackNeeded,matched_rule:matchedRule,should_allowed,source:src.source});
  });
});

// Score
let good=0,questionable=0,bad=0,pending=0;
allActions.forEach(a=>{
  if(a.should_allowed==='yes'&&a.confidence_honest&&!a.rollback_needed)good++;
  else if(a.should_allowed==='questionable')questionable++;
  else if(a.should_allowed==='no')bad++;
  else pending++;
});

// By type
const byType={};
allActions.forEach(a=>{
  const t=a.type||'unknown';
  if(!byType[t])byType[t]={total:0,good:0,questionable:0,bad:0,pending:0};
  byType[t].total++;
  if(a.should_allowed==='yes')byType[t].good++;
  else if(a.should_allowed==='questionable')byType[t].questionable++;
  else if(a.should_allowed==='no')byType[t].bad++;
  else byType[t].pending++;
});

const questionableActions=allActions.filter(a=>a.should_allowed==='questionable');
const badActions=allActions.filter(a=>a.should_allowed==='no');
const rollbackNeeded=allActions.filter(a=>a.rollback_needed);

const recommendations=[];
if(badActions.length>0)recommendations.push({priority:1,action:'Review '+badActions.length+' bad actions — consider rollback',why:'Actions that should not have been allowed need review'});
if(questionableActions.length>3)recommendations.push({priority:2,action:'Review '+questionableActions.length+' questionable actions — confidence calibration needed',why:'Confidence inflation needs tightening'});
if(allActions.length===0)recommendations.push({priority:3,action:'No LIVE actions yet — audit is clean (no data to fail)',why:'Empty audit = nothing bad happened yet'});

const out={
  schema:'https://clawdia.io/agents/live-action-auditor/v1',
  generated:now.toISOString(),
  mode,
  summary:{
    total_actions:allActions.length,
    good,questionable,bad,pending,
    rollback_needed:rollbackNeeded.length,
    verdict:bad>0?'REVIEW_REQUIRED':questionable>2?'WATCH':'CLEAN',
  },
  actions:allActions.slice(0,20),
  by_type:byType,
  questionable_actions:questionableActions.slice(0,5).map(a=>({type:a.type,status:a.status,confidence:a.confidence,reason:a.should_allowed})),
  bad_actions:badActions.slice(0,5).map(a=>({type:a.type,status:a.status,confidence:a.confidence,reason:a.should_allowed})),
  recommendations,
};
fs.writeFileSync(path.join(DATA,'live-action-audit.json'),JSON.stringify(out,null,2));
console.log('✅ live_action_auditor: '+allActions.length+' actions audited');
console.log('   Good: '+good+' | Questionable: '+questionable+' | Bad: '+bad+' | Pending: '+pending);
console.log('   Verdict: '+out.summary.verdict);
badActions.slice(0,3).forEach(a=>console.log('   BAD: '+a.type+' (confidence='+a.confidence+')'));
if(recommendations.length>0)recommendations.forEach(r=>console.log('   P'+r.priority+': '+r.action.substring(0,60)));
