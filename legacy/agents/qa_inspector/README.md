# qa_inspector

Quality gate — grammar, tone, CTA presence, broken links, duplicates, brand safety.

## Role
Phase 3A layer. First checkpoint before anything moves to approval. Runs automated checks on all Phase 2C production output.

## Schema
`https://clawdia.io/agents/qa-inspector/v1`

## Checks owned
- Grammar and spelling (pattern-based)
- CTA presence on all captions
- Broken hashtags (too many, wrong format)
- Duplicate hook detection (vs used-items suppress list)
- Image prompt sanity (aspect ratio, hook alignment)
- Blog factual checks (length, proof, pricing reference)
- Reddit anti-spam (no direct links, native tone)

## Inputs consumed
- `data/captions.json`, `data/caption-variants.json`
- `data/visual-briefs.json`, `data/image-prompts.json`
- `data/blog-drafts.json`, `data/reddit-replies.json`
- `data/post-plan.json`, `data/hook-bank.json`, `data/used-items.json`

## Outputs produced
| File | Contents |
|---|---|
| `data/qa-report.json` | Full per-item QA report with issues |
| `data/qa-failures.json` | Failed items with fix instructions |
| `data/ready-for-approval.json` | Items that passed all checks |

## Verdict rule
Every item gets: `pass` | `fix` | `reject`
- `high` severity issue → reject
- `medium` severity issue → fix
- `low`/no issues → pass

## How to run
```bash
node agents/qa_inspector/run.js
node scripts/run_agent.js qa_inspector
```