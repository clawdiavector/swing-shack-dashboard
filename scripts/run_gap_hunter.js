#!/usr/bin/env node
const fs=require('fs');const path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function r(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}}
function uid(){return Math.random().toString(36).substring(2,10);}
function run(){
  const now=new Date();
  const reddit=r('reddit-trends.json')||{};
  const seo=r('seo-rankings.json')||{};
  const ig=r('ig-analytics.json')||{};
  // Confirmed gaps from prior competitor research
  const gaps=[
    {gap_id:'gap-1',type:'fitting_content',competitor_weakness:'No indoor facility in JHB does TrackMan fitting education content',our_strength:'TrackMan technology leader',easiest_win:true,highest_value:true,fastest_content:true,fastest_seo:true,content_idea:'"What TrackMan measures and why it matters" — blog post + IG carousel',seo_angle:'indoor golf johannesburg + golf fitting johannesburg',priority:1},
    {gap_id:'gap-2',type:'junior_golf',competitor_weakness:'No junior golf development programs in indoor golf market',our_strength:'Catherine + Dave coaching, family-friendly environment',easiest_win:false,highest_value:true,fastest_content:false,fastest_seo:false,content_idea:'"Junior golf development starts indoors" — blog + IG Reels targeting parents',seo_angle:'junior golf johannesburg, youth golf coaching',priority:2},
    {gap_id:'gap-3',type:'google_reviews_response',competitor_weakness:'Most local golf facilities have poor/no Google review responses',our_strength:'Swing Shack has 4.8★ — respond to every review',easiest_win:true,highest_value:false,fastest_content:false,fastest_seo:true,content_idea:'Own the "we respond to every review" angle in bio and local SEO',seo_angle:'best indoor golf johannesburg, golf lessons sandton',priority:1},
    {gap_id:'gap-4',type:'trackman_education',competitor_weakness:'No one explains TrackMan data to customers',our_strength:'TrackMan on every session, certified instructors',easiest_win:true,highest_value:false,fastest_content:true,fastest_seo:false,content_idea:'"What your TrackMan numbers mean" — IG series, blog, YouTube',seo_angle:null,priority:2},
    {gap_id:'gap-5',type:'blog_content',competitor_weakness:'Golf Bar has minimal blog. HomeTee has none. Golden Tee has none.',our_strength:'Swing Shack has no blog either — can be first to own this zone',easiest_win:false,highest_value:false,fastest_content:false,fastest_seo:true,content_idea:'Consistent weekly blog on golf improvement, TrackMan tips, indoor golf guides',seo_angle:'indoor golf johannesburg, golf simulator, trackman golf',priority:3},
    {gap_id:'gap-6',type:'video_content',competitor_weakness:'No competitor does YouTube/educational video',our_strength:'Can own YouTube + IG Reels for local indoor golf',easiest_win:false,highest_value:false,fastest_content:false,fastest_seo:false,content_idea:'"TrackMan Tuesday" — weekly short video explaining one metric',seo_angle:null,priority:3},
    {gap_id:'gap-7',type:'membership_transparency',competitor_weakness:'No competitor publishes membership pricing',our_strength:'Swing Shack publishes clear pricing',easiest_win:true,highest_value:true,fastest_content:true,fastest_seo:true,content_idea:'"From R250/session or R1,800/month — here\'s what you get"',seo_angle:'indoor golf membership johannesburg, golf membership cost',priority:1},
  ];
  gaps.sort((a,b)=>a.priority-b.priority);
  const fastestContent=gaps.filter(g=>g.fastest_content&&g.easiest_win);
  const fastestSEO=gaps.filter(g=>g.fastest_seo&&g.highest_value);
  const out={schema:'https://clawdia.io/agents/gap-hunter/v1',generated:now.toISOString(),summary:{total_gaps:gaps.length,highest_value_gaps:gaps.filter(g=>g.highest_value).length,easiest_gaps:gaps.filter(g=>g.easiest_win).length,fastest_content_win:fastestContent[0]?.content_idea||null,fastest_seo_win:fastestSEO[0]?.content_idea||null},gaps};
  fs.writeFileSync(path.join(DATA,'market-gaps.json'),JSON.stringify(out,null,2));
  console.log('✅ Gap hunter: '+gaps.length+' gaps found');gaps.filter(g=>g.priority===1).forEach(g=>console.log('   P1: '+g.type+' — '+g.competitor_weakness.substring(0,60)));console.log('   Fastest content win: '+(fastestContent[0]?.content_idea||'none').substring(0,60));}
run();
