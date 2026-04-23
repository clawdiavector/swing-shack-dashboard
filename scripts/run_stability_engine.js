const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

const runs=r('agent-runs.json')||{agents:{}};
const allAgents=Object.entries(runs.agents||{});

// 7-day reliability analysis
const sevenDaysAgo=new Date(Date.now()-7*86400000);
const threeDaysAgo=new Date(Date.now()-3*86400000);
const oneDayAgo=new Date(Date.now()-86400000);

const perAgent=[];
let totalRuns=0,totalPass=0;

Object.entries(runs.agents||{}).forEach(([name,agentRuns])=>{
  const recent=agentRuns.filter(a=>new Date(a.run_at)>sevenDaysAgo);
  const last48h=agentRuns.filter(a=>new Date(a.run_at)>threeDaysAgo);
  const last24h=agentRuns.filter(a=>new Date(a.run_at)>oneDayAgo);
  const pass=recent.filter(a=>a.status==='PASS').length;
  const partial=recent.filter(a=>a.status==='PARTIAL').length;
  const total=recent.length;
  const ok=pass+partial; // PARTIAL = honest degraded, not failure
  const passRate=total>0?ok/total:1;
  const streak=calculateStreak(agentRuns.slice(-20).reverse());
  const flaky=passRate<0.8&&total>=3&&pass<total*0.8; // real FAIL rate >20%
  perAgent.push({name,passes:pass,partial,fail_rate:Math.round((1-passRate)*100),streak_days:streak,last_48h:last48h.length,last_24h:last24h.length,flaky,status:flaky?'flaky':'stable'});
  totalRuns+=total;
  totalPass+=ok;
});

// Calculate overall streak
const allRecent=Object.values(runs.agents||{}).flat().filter(a=>new Date(a.run_at)>sevenDaysAgo).sort((a,b)=>new Date(b.run_at)-new Date(a.run_at));
const overallStreak=calculateStreak(allRecent);
const overallPassRate=totalRuns>0?totalPass/totalRuns:1;

// 7-day streak milestones
const milestones={};
if(overallStreak>=7)milestones.seven_day_clean='&#10004; 7-day clean streak achieved';
if(overallPassRate>=0.95)milestones['95%_pass_rate_7d']='&#10004; 95%+ pass rate (7 days)';
if(Object.values(perAgent).every(a=>a.status==='stable'))milestones.all_agents_stable='&#10004; All agents stable';
if(totalRuns>=50)milestones.volume='&#10004; 50+ runs logged';

const recommendations=[];
if(flaky=perAgent.filter(a=>a.flaky),flaky.length>0){recommendations.push({priority:1,action:'Fix flaky agents: '+flaky.map(a=>a.name).join(', '),why:'Trust drag from intermittent failures'});}
if(overallPassRate<0.9){recommendations.push({priority:1,action:'Improve overall pass rate below 90%',why:'Critical for mode promotion'});}
if(overallStreak<7){recommendations.push({priority:2,action:'Maintain '+Math.max(0,7-overallStreak)+' more clean days for 7-day streak',why:'Required for LIMITED promotion'});}
if(Object.keys(milestones).length<2){recommendations.push({priority:3,action:'Build milestone history',why:'Required for LIVE promotion'});}

function calculateStreak(sortedRuns){
  let streak=0;
  const days=new Set();
  sortedRuns.forEach(run=>{if(run.status==='PASS')days.add(new Date(run.run_at).toDateString());});
  const uniqueDays=Array.from(days).sort().reverse();
  const today=new Date().toDateString();
  if(uniqueDays[0]!==today&&uniqueDays[0]!==new Date(Date.now()-86400000).toDateString())return 0;
  for(let i=0;i<uniqueDays.length;i++){
    const expected=new Date(Date.now()-(i)*86400000).toDateString();
    if(uniqueDays[i]===expected)streak++;else break;
  }
  return streak;
}

const out={
  schema:'https://clawdia.io/agents/stability-engine/v1',
  generated:now.toISOString(),
  summary:{total_runs:totalRuns,pass_rate_7d:Math.round(overallPassRate*100)+'%',streak_days:overallStreak,flaky_agents:perAgent.filter(a=>a.flaky).length,stable_agents:perAgent.filter(a=>a.status==='stable').length},
  milestones,
  recommendations,
  per_agent:perAgent.sort((a,b)=>a.fail_rate-b.fail_rate),
};
fs.writeFileSync(path.join(DATA,'stability-report.json'),JSON.stringify(out,null,2));
console.log('✅ stability_engine: '+overallPassRate*100+'% pass rate, streak='+overallStreak+' days');
perAgent.filter(a=>a.flaky).slice(0,3).forEach(a=>console.log('   FLAKY: '+a.name+' ('+a.fail_rate+'% fail, '+a.total+' runs)'));
recommendations.filter(r=>r.priority===1).forEach(r=>console.log('   P1: '+r.action));
