#!/bin/bash
# Start the Blueprint API server for CampaignOS cockpit
# Run this before using Accept/Regenerate in the cockpit UI
cd "$(dirname "$0")"
node server.js