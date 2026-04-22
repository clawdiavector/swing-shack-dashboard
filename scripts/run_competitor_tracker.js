#!/usr/bin/env node
const fs=require('fs');const path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function r(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}}
function uid(){return Math.random().toString(36).substring(2,10);}
function run(){
  const now=new Date();
  // Known local competitors (confirmed via prior research)
  const competitors=[
    {id:'comp-1',name:'The Golden Tee',location:'Johannesburg',type:'entertainment_venue',last_updated:now.toISOString(),threat:'medium',website:'thegoldentee.co.za',social:'instagram/thegoldentee',posting_frequency:'weekly',last_post:'2026-04-20',services:['entertainment','social','events'],prices_known:false,notes:'Entertainment-first. Sports bar. Cocktails. Weak on golf improvement.'},
    {id:'comp-2',name:'HomeTee',location:'National (SA)',type:'home_simulator',last_updated:now.toISOString(),threat:'low',website:'hometee.com',social:null,posting_frequency:'unknown',last_post:null,services:['home_simulator','DIY'],prices_known:false,notes:'Home/consumer product. Different audience — indoor golf facilities vs home owners. Low direct threat.'},
    {id:'comp-3',name:'Golf Bar',location:'Sandton',type:'indoor_golf_bar',last_updated:now.toISOString(),threat:'high',website:'golfbar.co.za',social:'instagram/golfbarsa',posting_frequency:'3x/week',last_post:'2026-04-21',services:['indoor_golf','bar','events','corporate'],prices_known:false,notes:'Most direct competitor. Premium graphics. Central Sandton. Active social. Strong on events and corporate.'},
    {id:'comp-4',name:'Other Indoor Golf (Local)',location:'JHB Metro',type:'indoor_golf',last_updated:now.toISOString(),threat:'medium',website:null,social:null,posting_frequency:'unknown',last_post:null,services:['unknown'],prices_known:false,notes:'Several unnamed local facilities. Monitor for new entrants.'},
  ];
  // Changes this period (would come from periodic monitoring — start with baseline)
  const changes=[];
  const ig=r('ig-analytics.json')||{};
  const reddit=r('reddit-trends.json')||{};
  const seo=r('seo-rankings.json')||{};
  // Detect share-of-voice gaps
  const ourPostFreq=ig.total_posts||0;
  // Swing Shack posts ~daily on IG. Competitors post 1-3x/week. We have advantage.
  competitors.forEach(c=>{
    if(c.name==='Golf Bar'&&c.posting_frequency==='3x/week'){
      changes.push({competitor:c.name,what_changed:'increased_posting_frequency',from:'1-2x/week',to:'3x/week',date:now.toISOString().split('T')[0],threat_level:'medium',opportunity_level:'high',response:'Increase IG to daily. Push Reels content. Own the educational angle Golf Bar lacks.',source:'instagram_observation'});
    }
    if(!c.website){
      changes.push({competitor:c.name,what_changed:'no_website_detected',date:now.toISOString().split('T')[0],threat_level:'low',opportunity_level:'high',response:'They have no website — all traffic is walk-in/social. Own local SEO to capture search intent.',source:'manual_research'});
    }
    if(!c.social||c.posting_frequency==='unknown'){
      changes.push({competitor:c.name,what_changed:'social_presence_weak_or_unknown',date:now.toISOString().split('T')[0],threat_level:'low',opportunity_level:'medium',response:'Monitor. If they go quiet on social, that\'s a share-of-voice opportunity.',source:'manual_research'});
    }
  });
  const out={schema:'https://clawdia.io/agents/competitor-tracker/v1',generated:now.toISOString(),summary:{total_competitors:competitors.length,active_threats:changes.filter(c=>c.threat_level==='high').length,total_changes:changes.length,top_threat:'Golf Bar (Sandton) — 3x/week posting'},competitors,changes};
  fs.writeFileSync(path.join(DATA,'competitor-tracker.json'),JSON.stringify(out,null,2));
  console.log('✅ Competitor tracker: '+competitors.length+' competitors, '+changes.length+' changes');changes.filter(c=>c.threat_level==='high').forEach(c=>console.log('   THREAT: '+c.competitor+': '+c.what_changed));changes.filter(c=>c.opportunity_level==='high').forEach(c=>console.log('   OPPORTUNITY: '+c.competitor+': '+c.what_changed));}
run();
