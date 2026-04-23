#!/usr/bin/env node
const{execSync}=require("child_process");const fs=require("fs");const path=require("path");
const BASE="/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard";const DATA=path.join(BASE,"data");const A="auto_budget_shifter";const start=Date.now();
let status="PASS",errMsg="";try{execSync("node "+path.join(BASE,"scripts","run_"+A+".js"),{cwd:BASE,timeout:30000});}catch(e){status="FAIL";errMsg=e.message.slice(0,80);}
const r={agent_id:A,run_at:new Date().toISOString(),duration_ms:Date.now()-start,status:status==="PASS"?"PASS":"PARTIAL",scripts:[{script:"run_"+A+".js",status,err:errMsg}],passed:status==="PASS"?1:0,failed:status==="FAIL"?1:0};
console.log("\\n["+A+"] "+r.status+" ("+r.duration_ms+"ms)");
if(errMsg)console.log("   ERROR: "+errMsg);
const RF=path.join(DATA,"agent-runs.json");let runs={agents:{}};try{runs=JSON.parse(fs.readFileSync(RF,"utf8"));}catch{}
runs.agents[A]=runs.agents[A]||[];runs.agents[A].push(r);runs.agents[A]=runs.agents[A].slice(-50);runs.updated=new Date().toISOString();
fs.writeFileSync(RF,JSON.stringify(runs,null,2));process.exit(r.status==="PASS"?0:1);
