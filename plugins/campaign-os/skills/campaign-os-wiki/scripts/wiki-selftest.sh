#!/usr/bin/env bash
# Sync -> read -> write -> commit -> push -> verify against the real remote. Pushes one stamp file.
set -euo pipefail
source "$(dirname "$0")/wiki-lib.sh"
echo '=== wiki-selftest: sync ==='
wiki_sync || { echo 'SYNC_FAIL' >&2; exit 1; }
cd "$WIKI_ROOT"; B="$(wiki_branch)"; B="${B:-main}"
grep -q 'Campaign OS wiki' CampaignOS/index.md || { echo 'READ_FAIL index.md' >&2; exit 1; }
echo 'READ_OK CampaignOS/index.md'
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; T=CampaignOS/runbooks/kb-selftest-last-run.md
printf -- '---\ntitle: KB self-test last run\nmodule: wiki\ntype: runbook\nstatus: active\nupdated: %s\n---\n\n# KB self-test\n\nLast successful run (UTC): `%s`\n' "$(date -u +%Y-%m-%d)" "$STAMP" > "$T"
echo "WRITE_OK $T"
git add "$T"; git commit -q -m "kb(wiki): selftest run $STAMP"
git pull -q --rebase origin "$B"; git push -q origin "HEAD:$B"; echo PUSH_OK
git fetch -q origin "$B"; git show "origin/$B:$T" | grep -qF "$STAMP" || { echo VERIFY_FAIL >&2; exit 1; }
echo '=== wiki-selftest PASSED ==='
