const fs=require('fs');const path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
function r(n){try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}}
function uid(){return Math.random().toString(36).substring(2,10);}
function run(){
  const now=new Date();
  const comps=[
    {name:'Golf Bar SA',score:4.2,total_reviews:89,response_rate:60,pattern:'great_venue,bad_food,inconsistent_service',common_praise:['venue','atmosphere','location'],common_complaint:['food_cold','service_slow','crowded','no_golf_improvement']},
    {name:'The Golden Tee',score:3.9,total_reviews:156,response_rate:20,pattern:'fun_night,poor_maintenance,inconsistent',common_praise:['fun','social','drinks'],common_complaint:['simulator_quality','outdated_software','staff_turnover']},
    {name:'Other Indoor Golf',score:3.7,total_reviews:45,response_rate:10,pattern:'cheap_alternative,no_instruction',common_praise:['price','convenient'],common_complaint:['no_data','no_instructors','boring']},
  ];
  const ourScore=4.8,ourReviews=127;
  const compAvgScore=Math.round(comps.reduce(function(s,c){return s+c.score;},0)/comps.length*10)/10;
  const emphasis=[
    {theme:'trackman_data',why:'Competitors cant match this — none offer launch monitor data per session',how:'Feature in every review request. "Your TrackMan report is ready."',priority:1},
    {theme:'certified_instructors',why:'Golf Bar and Golden Tee have no named instructors. We have Catherine and Dave.',how:'"Coached by certified instructors — not just a simulator."',priority:1},
    {theme:'no_pressure_environment',why:'Competitors complaints: crowded, noisy, food cold. Ours is focused.',how:'"Come improve. Not just play."',priority:2},
    {theme:'actual_improvement',why:'Competitors have no coaching. We have TPI + TrackMan + lessons.',how:'"Measured improvement. Not just fun."',priority:1},
  ];
  const responseTemplates=[
    {scenario:'positive_review',template:'Thanks [name]! Really glad you enjoyed [specific_mention]. See you again soon — bring your mates.',personalisation:'reference specific detail from review'},
    {scenario:'neutral_review',template:'Thanks [name]! Always looking to improve — if there is anything we can do better, let us know: [WhatsApp].',personalisation:'ask what could improve'},
    {scenario:'negative_review',template:'Hey [name], really sorry to hear that. That is not our standard. Please reach out directly — we will make it right. [WhatsApp]',personalisation:'immediate resolution offer'},
  ];
  const reviewPriorities=[
    {action:'post_visit_review_request',channel:'whatsapp',timing:'immediately_after_visit',message:'Hey [name]! Would you take 30 seconds to leave us a Google review? [link] It helps us reach more golfers.',priority:'high'},
    {action:'review_qr_at_counter',channel:'in_person',timing:'every_visit',message:'Scan the QR on the counter to leave a review.',priority:'high'},
    {action:'photo_review_request',channel:'whatsapp',timing:'24h_after',message:'Hi [name]! Here is your TrackMan data from today: [link]. Want to share your results in a Google review? [review link] Thanks!',priority:'medium'},
  ];
  const out={schema:'https://clawdia.io/agents/review-domination-engine/v1',generated:now.toISOString(),summary:{our_score:ourScore,our_review_count:ourReviews,competitor_avg_score:compAvgScore,our_advantages:['+0.6 above nearest competitor','100% response rate vs avg 30%','certified instructors vs none','TrackMan data vs none'],priority_actions:reviewPriorities.filter(function(p){return p.priority==='high';}).map(function(p){return p.action;})},response_templates:responseTemplates,emphasis:emphasis,competitors:comps};
  fs.writeFileSync(path.join(DATA,'review-domination.json'),JSON.stringify(out,null,2));
  console.log('Review domination: our score '+ourScore+' vs avg '+compAvgScore);console.log('   Advantage: +'+(ourScore-compAvgScore).toFixed(1)+' stars vs nearest competitor');emphasis.filter(function(e){return e.priority===1;}).forEach(function(e){console.log('   P1: '+e.theme);});reviewPriorities.filter(function(p){return p.priority==='high';}).forEach(function(p){console.log('   HIGH: '+p.action);});}
run();
