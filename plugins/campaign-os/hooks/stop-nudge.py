#!/usr/bin/env python3
"""Stop: once per session, after real research-style work that wrote nothing to the wiki, ask Claude to file it."""
import json, os, re, sys, tempfile, pathlib
if os.environ.get("CAMPAIGNOS_KB_HOOKS", "on") == "off": sys.exit(0)
try: ev = json.load(sys.stdin)
except Exception: sys.exit(0)
if ev.get("stop_hook_active"): sys.exit(0)
marker = pathlib.Path(tempfile.gettempdir()) / f"cos-wiki-nudged-{ev.get('session_id','x')}"
if marker.exists(): sys.exit(0)
tp = ev.get("transcript_path")
if not tp or not os.path.exists(tp): sys.exit(0)
# Only real conversation turns count: the SessionStart brief (hook output) mentions the wiki and would always match.
turns = []
for line in open(tp, errors="ignore"):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") in ("user", "assistant"): turns.append(line)
raw = "".join(turns)
if raw.count('"type":"tool_use"') + raw.count('"type": "tool_use"') < 12: sys.exit(0)   # trivial session
# already filed: a write into the wiki clone, or a kb(...) commit
if re.search(r'file_path\\?"\s*:\s*\\?"[^"]*CampaignOS/(research|decisions|runbooks|modules)/|git commit[^"]*kb\(', raw): sys.exit(0)
if not re.search(r"\b(research|scout|investigat\w+|audit|findings?|root cause|decision|decided|compar\w+|evaluat\w+)\b", raw, re.I): sys.exit(0)
if not re.search(r"campaign[- ]?os|swing[- ]?shack|bag drop|cos-", raw, re.I): sys.exit(0)   # not a Campaign OS session
marker.write_text("1")
print(json.dumps({"decision": "block", "reason":
  "Before stopping: this session looked like Campaign OS research/decision work and nothing was filed to the Campaign OS wiki. "
  "If there are durable findings (what was learned, evidence, decisions, open questions), use the campaign-os-wiki skill (/campaign-os:wiki-write) to write them "
  "(one page, update index + log, commit + push). If nothing is worth keeping, reply 'nothing to file' and stop."}))
