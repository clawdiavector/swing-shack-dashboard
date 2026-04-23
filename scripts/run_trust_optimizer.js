const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const now=new Date();

const lm=r('live-mode.json')||{};
const runs=r('agent-runs.json')||{agents:{}};
const ab=r('ab-winners.json')||{};

// Analyse what's dragging trust score
const currentTrust=lm.trust_score||7.2;
const agents=r('agent-runs.json')?Object.values(runs.agents||{}).flat():[];
const recentAgents=agents.slice(-50);
const fails=recentAgents.filter(a=>a.status!=='PASS');
const passRate=recentAgents.length>0?recentAgents.filter(a=>a.status==='PASS').length/recentAgents.length:1;
const failRate=1-passRate;

// Stale data impact
const ga4=r('ga4-metrics.json');
const ig=r('ig-analytics.json');
const reddit=r('reddit-trends.json');
const lastGA4=ga4?new Date(ga4.updated||0):null;
const lastIG=ig?new Date(ig.updated||0):null;
const lastReddit=reddit?new Date(reddit.updated||0):null;
const staleDaysGA4=lastGA4?Math.floor((now-lastGA4)/(86400000)):999;
const staleDaysIG=lastIG?Math.floor((now-lastIG)/(86400000)):999;
const staleDaysReddit=lastReddit?Math.floor((now-lastReddit)/(86400000)):999;

// Calculate trust gaps
const gaps=[];
let trustDrag=0;

if(staleDaysGA4>3){const d=Math.min(0.5,(staleDaysGA4-3)*0.1);gaps.push({issue:'GA4 data stale',days:staleDaysGA4,impact:-d,fix:'Run instagram-analytics-tracker or fix GA4 cron',priority:1});trustDrag+=d;}
if(staleDaysReddit>7){const d=Math.min(0.3,(staleDaysReddit-7)*0.05);gaps.push({issue:'Reddit trends stale',days:staleDaysReddit,impact:-d,fix:'Check Reddit scraper cron is running',priority:2});trustDrag+=d;}
if(fails.length>0){const d=Math.min(0.4,fails.length*0.1);gaps.push({issue:fails.length+' failed agent runs',count:fails.length,impact:-d,fix:'Fix or disable failing agents',priority:1});trustDrag+=d;}
if(!lm.kill_switches||Object.values(lm.kill_switches).filter(Boolean).length>2){const d=0.2;gaps.push({issue:'Too many kill switches active',impact:-d,fix:'Resolve root causes to restore autonomy',priority:2});trustDrag+=d;}
if(passRate<0.9){const d=(0.9-passRate);gaps.push({issue:'Low run success rate',rate:Math.round(passRate*100)+'%',impact:-d,fix:'Fix flaky agents — stability_engine will identify',priority:1});trustDrag+=d;}

// Quick wins
const quickWins=[];
if(staleDaysGA4<=3&&staleDaysReddit<=7&&fails.length<=2)quickWins.push({action:'Fix '+fails.length+' failing agents',gain:'+0.1 to +0.3',time:'today'});
if(passRate>=0.9)quickWins.push({action:'Maintain clean runs',gain:'+0.05/day',time:'ongoing'});
if(staleDaysGA4>3)quickWins.push({action:'Run GA4 tracker now',gain:'+0.1 to +0.3',time:'today'});
if(staleDaysReddit>7)quickWins.push({action:'Fix Reddit scraper',gain:'+0.05',time:'today'});

// Path to LIMITED (8.0) and LIVE (9.0)
const trustToLimited=Math.max(0,8-currentTrust);
const trustToLive=Math.max(0,9-currentTrust);
const daysToLimited=trustToLimited<=0?0:Math.ceil(trustToLimited/0.1);
const daysToLive=trustToLive<=0?0:Math.ceil(trustToLive/0.1);

const out={
  schema:'https://clawdia.io/agents/trust-optimizer/v1',
  generated:now.toISOString(),
  current_trust:currentTrust,
  summary:{trust_drag:Math.round(trustDrag*100)/100,gap_to_limited:Math.round(trustToLimited*10)/10,gap_to_live:Math.round(trustToLive*10)/10,days_to_limited:daysToLimited,days_to_live:daysToLive,quick_wins:quickWins.length},
  gaps:gaps.sort((a,b)=>b.impact-a.impact),
  quick_wins:quickWins,
  data_freshness:{ga4_days_stale:staleDaysGA4,reddit_days_stale:staleDaysReddit,ig_days_stale:staleDaysIG},
};
fs.writeFileSync(path.join(DATA,'trust-gaps.json'),JSON.stringify(out,null,2));
console.log('✅ trust_optimizer: current='+currentTrust+', drag='+Math.round(trustDrag*100)/100);
gaps.slice(0,3).forEach(g=>console.log('   '+g.issue+': '+g.impact.toFixed(2)));
console.log('   Days to LIMITED (8): '+daysToLimited+' | to LIVE (9): '+daysToLive);
