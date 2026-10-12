#!/usr/bin/env bash
# Clone (first run) or update the Campaign OS wiki. Prints SYNC_OK <root> or fails.
set -euo pipefail
source "$(dirname "$0")/wiki-lib.sh"
wiki_sync || { echo "SYNC_FAIL cannot reach $WIKI_URL (no access? ask Kyle for an invite, then run: gh auth login)" >&2; exit 1; }
echo "SYNC_OK $WIKI_ROOT"
