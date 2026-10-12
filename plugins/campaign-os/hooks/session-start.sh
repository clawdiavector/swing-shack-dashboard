#!/usr/bin/env bash
# SessionStart: make sure the Campaign OS wiki is cloned and current, then print a short brief (becomes context).
[[ "${CAMPAIGNOS_KB_HOOKS:-on}" == "off" ]] && exit 0
source "${CLAUDE_PLUGIN_ROOT}/skills/campaign-os-wiki/scripts/wiki-lib.sh"
if ! wiki_sync >/dev/null 2>&1; then
  if [[ -f "$WIKI_ROOT/kb.config.yaml" ]]; then STALE=" (sync FAILED: content may be stale, say so if you rely on it)"
  else echo "## Campaign OS wiki unavailable"; echo "Could not clone $WIKI_URL (no access?). Ask Kyle for a collaborator invite and run: gh auth login. Do not invent wiki content."; exit 0; fi
fi
cd "$WIKI_ROOT"
echo "## Campaign OS wiki${STALE:-}"
echo "Clone: $WIKI_ROOT (shared by Kyle and Christelle; pushes go straight to the main branch)."
echo "Before Campaign OS research or changes: read CampaignOS/index.md and the matching page (research/, modules/, decisions/, runbooks/). After research, an audit or a decision: file it with the campaign-os-wiki skill (/campaign-os:wiki-write). Never put secrets in the wiki."
echo "Recent:"; grep '^- ' CampaignOS/log.md | tail -n 6 | sed 's/^/  /'
echo "Sections:"
for d in research modules decisions runbooks; do n=$(find "CampaignOS/$d" -name '*.md' ! -name 'index.md' ! -name '_*' 2>/dev/null | wc -l); echo "  $d: $n pages"; done
exit 0
