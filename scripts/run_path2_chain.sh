#!/bin/bash
# Path 2 chain - fires only the scripts that have working upstream feeds.
# Captures exit status per step, logs to file. NEVER fails the wrap.
set +e

BASE="/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard"
LOG="/Users/fivefriday/.openclaw-instance2/workspace/logs/path2-chain.log"
ERR="/Users/fivefriday/.openclaw-instance2/workspace/logs/path2-chain.err.log"
mkdir -p "$(dirname "$LOG")"

ts() { date '+%Y-%m-%d %H:%M:%S %Z'; }

echo "============================================================" | tee -a "$LOG"
echo "[$(ts)] PATH 2 CHAIN START" | tee -a "$LOG"
echo "============================================================" | tee -a "$LOG"

run() {
  local name="$1"
  shift
  echo ""
  echo "--- [$(ts)] STEP: $name ---" | tee -a "$LOG"
  "$@" >> "$LOG" 2>> "$ERR"
  local rc=$?
  if [ $rc -eq 0 ]; then
    echo "[$(ts)] OK $name (rc=0)" | tee -a "$LOG"
  else
    echo "[$(ts)] FAIL $name (rc=$rc)" | tee -a "$ERR"
  fi
  return 0  # never propagate failure; we want the rest to run
}

# Stage 1: fetch (have working feeds)
cd "$BASE"
run "fetch_youtube_trends" node scripts/fetch_youtube_trends.js
run "fetch_ga4"            node scripts/fetch_ga4.js
run "sync_ig_analytics"    node scripts/sync_ig_analytics.js

# Stage 2: analysis chain
run "analyse_hooks"              node scripts/analyse_hooks.js
run "generate_content_ideas"     node scripts/generate_content_ideas.js
run "generate_content_blueprints" node scripts/generate_content_blueprints.js

# Stage 3: production
run "generate_visual_briefs"   node scripts/generate_visual_briefs.js
run "generate_reddit_ghost"    node scripts/generate_reddit_ghost.js
run "landing_page_optimizer"   node scripts/run_landing_page_optimizer.js

# Stage 4: conversion attribution chain (CMO-brain layer)
# Was previously missing from this chain - caused the entire
# attribution layer to be 113 days stale. Now wired in.
run "run_booking_event_mapper"        node scripts/run_booking_event_mapper.js
run "run_roi_truth_engine"            node scripts/run_roi_truth_engine.js
run "run_conversion_truth_engine"     node scripts/run_conversion_truth_engine.js
run "generate_conversion_attribution" node scripts/generate_conversion_attribution.js
run "run_postiz_attribution_layer"    node scripts/run_postiz_attribution_layer.js

echo ""
echo "[$(ts)] PATH 2 CHAIN END" | tee -a "$LOG"
