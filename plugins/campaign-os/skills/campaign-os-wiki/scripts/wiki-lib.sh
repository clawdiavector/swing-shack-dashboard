# Shared by the wiki scripts and hooks. Source it; do not run it.
# Resolves the wiki clone (CAMPAIGNOS_KB_ROOT, else ~/CampaignOSKnowledgeBase) and clones it if missing.
WIKI_URL="${CAMPAIGNOS_KB_URL:-https://github.com/clawdiavector/campaign-os-wiki.git}"
WIKI_ROOT="${CAMPAIGNOS_KB_ROOT:-$HOME/CampaignOSKnowledgeBase}"
wiki_branch() { awk '/^  branch:/{print $2; exit}' "$WIKI_ROOT/kb.config.yaml" 2>/dev/null || true; }
wiki_ensure() {   # clone if absent; returns 1 when the wiki is unavailable
  [[ -f "$WIKI_ROOT/kb.config.yaml" ]] && return 0
  [[ -e "$WIKI_ROOT" ]] && { echo "WIKI_PATH_BUSY $WIKI_ROOT exists but is not the wiki" >&2; return 1; }
  GIT_TERMINAL_PROMPT=0 timeout 40 git clone -q "$WIKI_URL" "$WIKI_ROOT" 2>/dev/null || return 1
}
wiki_sync() {
  wiki_ensure || return 1
  local b; b="$(wiki_branch)"; b="${b:-main}"
  cd "$WIKI_ROOT"
  GIT_TERMINAL_PROMPT=0 git fetch -q origin "$b" || return 1
  if [[ "$(git rev-parse --abbrev-ref HEAD)" == "$b" ]]; then git pull -q --rebase --autostash origin "$b"; else git rebase -q "origin/$b"; fi
}
