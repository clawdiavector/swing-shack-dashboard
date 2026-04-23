const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

const runs=r('agent-runs.json')||{agents:{}};
const allRuns=Object.values(runs.agents||{}).flat().slice(-50).sort((a,b)=>new Date(b.run_at)-new Date(a.run_at));

// Time-of-day patterns
const hourBuckets={};
allRuns.forEach(run=>{
  const h=new Date(run.run_at).getHours();
  const bucket=h<6?'night':h<12?'morning':h<18?'afternoon':'evening';
  hourBuckets[bucket]=(hourBuckets[bucket]||{total:0,fails:0,partials:0});
  hourBuckets[bucket].total++;
  if(run.status==='FAIL')hourBuckets[bucket].fails++;
  if(run.status==='PARTIAL')hourBuckets[bucket].partials++;
});

// Repeated failure source
const failByAgent={};
const partialByAgent={};
allRuns.forEach(run=>{
  const a=run.agent_id||'unknown';
  if(run.status==='FAIL')failByAgent[a]=(failByAgent[a]||0)+1;
  if(run.status==='PARTIAL')partialByAgent[a]=(partialByAgent[a]||0)+1;
});

// Dependency patterns — which agents run before others
const sequences={};
for(let i=0;i<allRuns.length-1;i++){
  const curr=allRuns[i].agent_id||'?';
  const prev=allRuns[i+1].agent_id||'?';
  const key=curr+' → '+prev;
  sequences[key]=(sequences[key]||{count:0,fails:0});
  sequences[key].count++;
  if(allRuns[i].status==='FAIL')sequences[key].fails++;
}

// File collision patterns — look for ENOENT/MODULE_NOT_FOUND errors
const errorTypes={};
allRuns.forEach(run=>{
  const err=(run.scripts||[])[0]?.err||'';
  if(err.includes('ENOENT'))errorTypes.enoent=(errorTypes.enoent||0)+1;
  else if(err.includes('MODULE_NOT_FOUND'))errorTypes.module_not_found=(errorTypes.module_not_found||0)+1;
  else if(err.includes('timeout'))errorTypes.timeout=(errorTypes.timeout||0)+1;
  else if(err.includes('ECONNREFUSED'))errorTypes.connection=(errorTypes.connection||0)+1;
  else if(run.status==='PARTIAL')errorTypes.partial=(errorTypes.partial||0)+1;
  else if(run.status==='FAIL'&&!err)errorTypes.unknown=(errorTypes.unknown||0)+1;
});

// Most common failure window
const worstWindow=Object.entries(hourBuckets).sort((a,b)=>(b[1].fails/b[1].total)-(a[1].fails/a[1].total))[0];

// Repeat failure: same agent fails 2+ times in 48h
const repeatFails=Object.entries(failByAgent).filter(([,c])=>c>=2).map(([a])=>a);
const repeatPartial=Object.entries(partialByAgent).filter(([,c])=>c>=3).map(([a])=>a);

// Recommendations
const recs=[];
if(repeatFails.length>0)recs.push({priority:1,action:'Fix '+repeatFails.join(', ')+' — repeat failures in 48h',why:'Same agent failing repeatedly is a pattern, not noise'});
if(worstWindow&&worstWindow[1].fails>0)recs.push({priority:2,action:'Investigate '+worstWindow[0]+' window — highest failure rate',why:'Time-of-day pattern suggests resource contention or API limits'});
if(errorTypes.module_not_found>0)recs.push({priority:1,action:'Fix missing module/script references — ENOENT errors',why:'Script not found = immediate FAIL, easy fix'});
if(errorTypes.partial>3)recs.push({priority:2,action:'Improve data source freshness — '+errorTypes.partial+' PARTIAL from stale feeds',why:'Stale feeds cause honest PARTIAL, not FAIL'});

const out={
  schema:'https://clawdia.io/agents/failure-pattern-detector/v1',
  generated:now.toISOString(),
  summary:{
    total_runs:allRuns.length,
    fails:allRuns.filter(r=>r.status==='FAIL').length,
    partials:allRuns.filter(r=>r.status==='PARTIAL').length,
    repeat_fail_agents:repeatFails,
    worst_time_window:worstWindow?{window:worstWindow[0],fail_rate:Math.round(worstWindow[1].fails/worstWindow[1].total*100)+'%'}:null,
  },
  patterns:{
    by_time:hourBuckets,
    by_agent_fail:failByAgent,
    by_agent_partial:partialByAgent,
    error_types:errorTypes,
    sequences,
  },
  recommendations:recs,
};
fs.writeFileSync(path.join(DATA,'failure-patterns.json'),JSON.stringify(out,null,2));
console.log('✅ failure_pattern_detector: '+allRuns.length+' runs analysed');
console.log('   Fails: '+out.summary.fails+' | Partial: '+out.summary.partials);
console.log('   Repeat fail agents: '+(repeatFails.join(', ')||'none'));
console.log('   Error types: '+Object.entries(errorTypes).map(([k,v])=>k+':'+v).join(', ')||'none');
recs.slice(0,3).forEach(r=>console.log('   P'+r.priority+': '+r.action.substring(0,60)));
