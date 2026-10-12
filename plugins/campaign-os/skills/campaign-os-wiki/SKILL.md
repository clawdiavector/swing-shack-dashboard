---
name: campaign-os-wiki
description: Read and write the shared Campaign OS wiki (research, audits, decisions, runbooks, how-it-works pages) that Kyle and Christelle both use. Load when a task touches Campaign OS, Swing Shack, Stick or Bag Drop and you need background; before starting research (check what is already known); and after research, an audit or a decision (file it so the other person's Claude finds it).
---

# Campaign OS wiki

A separate private git repo, **clawdiavector/campaign-os-wiki** (branch `main`), cloned to `~/CampaignOSKnowledgeBase` (override with `CAMPAIGNOS_KB_URL` / `CAMPAIGNOS_KB_ROOT`). This plugin carries the tooling; the wiki carries the knowledge. It is not product code: the app is the working-directory repo.

The SessionStart hook clones and syncs it automatically. By hand: `bash ${CLAUDE_SKILL_DIR}/scripts/wiki-sync.sh` (prints `SYNC_OK <path>`). If sync fails, say the wiki may be stale; if it cannot be cloned, the person needs a GitHub invite to the wiki repo.

## Read (`/campaign-os:wiki-read <topic>`)

1. Sync (above).
2. Read `CampaignOS/index.md`, then the matching page. Grep under `CampaignOS/` for the topic.
3. Answer with path citations. Pages seeded from older snapshots say so in `source:`; re-verify against prod/code before relying on "done" claims. Warn on `status: deprecated`.
4. Never commit while reading.

## Write (`/campaign-os:wiki-write <what>`)

When: research or an audit finished, an investigation answered a question, a decision was made, a procedure was learned. One topic per page. Ticket or no ticket does not matter; anyone's findings belong here.

1. Sync. Stop on conflict and report; never overwrite remote with stale local.
2. Folder: `research/` (what we learned, with evidence), `decisions/` (what we chose and why), `runbooks/` (how to do X), `modules/` (how a part of the system works).
3. New page: copy `CampaignOS/research/_template.md`. Required frontmatter: `title, module, type, status, updated`; add `tags` (3-6 lowercase keywords; the prompt hook matches on them).
4. Research pages state: the question, the answer in 3 lines, evidence (file:line, URLs, command output), confidence, open questions, and the repo commit SHA it was based on.
5. Update the nearest `index.md`, bump `updated:` on edited pages, append one line to `CampaignOS/log.md` (`- YYYY-MM-DD — who — what`).
6. Commit and push from the wiki clone:

```bash
git add CampaignOS/ meta/
git commit -m "kb(<module>): <short description>"
git pull --rebase origin main
git push origin HEAD:main
```

Retry once on push failure, then stop and report. Never `--force`.

## Test (`/campaign-os:wiki-test`)

`bash ${CLAUDE_SKILL_DIR}/scripts/wiki-selftest.sh`. Expect `=== wiki-selftest PASSED ===`. It pushes one stamp file to the wiki; skip it where pushing is not wanted.

## Rules

- Write only under `CampaignOS/` and `meta/` of the wiki clone.
- No secrets, tokens or personal data. Name an env var (`COS_JOB_TOKEN`), never its value.
- The wiki holds knowledge, not publishable post copy.

## Hooks (installed with the plugin)

| Hook | Effect |
|---|---|
| SessionStart | clones/syncs the wiki and injects a short brief |
| UserPromptSubmit | names wiki pages whose title/tags match the prompt (no LLM) |
| Stop | once per session, after substantial Campaign OS research with nothing filed, asks Claude to file it |

Turn off with `CAMPAIGNOS_KB_HOOKS=off`.
