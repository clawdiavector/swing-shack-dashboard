#!/bin/bash
# Start the Blueprint API server for CampaignOS cockpit
#
# IMPORTANT: This server binds to 0.0.0.0:3456 and is accessible from
# any device on the local network at http://192.168.0.3:3456
#
# Auth: admin / swing-shack-bp-2026
#
# Before using Accept/Regenerate in the cockpit:
# 1. Keep this running
# 2. Open cockpit at: http://192.168.0.3/cockpit-operational.html
#    (NOT the GitHub Pages version for this feature)
# 3. Scroll to Blueprint Versions panel at the bottom of any campaign
# 4. Click Accept or Regenerate
#
cd "$(dirname "$0")"

# Get GitHub token for git push auth (used by API server for commits)
export GH_TOKEN
GH_TOKEN=$(gh auth token 2>/dev/null)

node server.js 3456 admin swing-shack-bp-2026
