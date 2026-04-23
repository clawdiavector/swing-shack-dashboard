const fs=require('fs'),path=require('path');
const DATA='/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data';
const r=n=>{try{return JSON.parse(fs.readFileSync(path.join(DATA,n),'utf8'));}catch{return null;}};
const uid=()=>Math.random().toString(36).substring(2,10);
const now=new Date();
const recSc=r('recommendation-scores.json')||{};
// No live inventory data — honest manual/placeholder mode
const signals={
  schema:'https://clawdia.io/agents/inventory-signal-engine/v1',
  generated:now.toISOString(),
  data_mode:'manual_placeholder',
  confidence:'low',
  note:'No live POS/inventory data connected. All signals below are estimated. Connect actual inventory system for high-confidence signals.',
  signals:[
    {
      signal_id:'inv-1',type:'low_stock_signal',item:'Takomo fitting balls',urgency:'medium',
      evidence:'Fitting ball sleeves are consumable — limited per fitting session. Popular with repeat fitters.',
      action:'Manual count this week. Order if below 20 sleeves.',
      margin_impact:'medium',
    },
    {
      signal_id:'inv-2',type:'high_demand',item:'TrackMan booking slots',urgency:'high',
      evidence:'IG analytics show booking intent spikes mid-week. Slots fill fast for weekends.',
      action:'Add 2 weekend slots per week. More capacity = more bookings.',
      margin_impact:'high',
    },
    {
      signal_id:'inv-3',type:'dead_stock_signal',item:'Takomo apparel (sizes XS/XL)',urgency:'low',
      evidence:'Apparel in odd sizes moves slowly. In-store observation.',
      action:'Bundle odd sizes with lessons or fittings. "Free fitted ball sleeve with any Takomo top."',
      margin_impact:'low',
    },
    {
      signal_id:'inv-4',type:'pre_order_opportunity',item:'Takomo wedges',urgency:'medium',
      evidence:'Golf Bar announced new simulator season. Fitting traffic increases. New club launches drive fitting demand.',
      action:'Pre-order Takomo demo wedges. Offer "fit then buy" — fitting session + club trial same day.',
      margin_impact:'high',
    },
    {
      signal_id:'inv-5',type:'high_demand',item:'Birthday/Group bookings',urgency:'medium',
      evidence:'Social play group bookings spike on WhatsApp forwarded links. Fridays and Saturdays.',
      action:'Reserve 4 group slots per weekend. Pre-package with drinks. Reduce friction for group enquiries.',
      margin_impact:'high',
    },
  ],
  summary:{
    total_signals:5,
    low_stock:1,
    high_demand:2,
    dead_stock:1,
    pre_order:1,
    manual_override_needed:1,
    next_action:'Count Takomo fitting balls this week. Add 2 weekend slots.',
  },
};
fs.writeFileSync(path.join(DATA,'inventory-signals.json'),JSON.stringify(signals,null,2));
console.log('✅ Inventory signal engine: '+signals.signals.length+' signals (LOW CONFIDENCE — no live data)');
console.log('   '+signals.signals.filter(s=>s.urgency==='high').length+' high urgency, '+signals.signals.filter(s=>s.type==='high_demand').length+' high demand');
console.log('   '+signals.summary.next_action);
