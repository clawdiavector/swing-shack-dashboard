# brand_guard

Tone compliance, forbidden phrases, AI-sounding language, off-brand wording, overclaims.

## Role
Phase 3A layer. Enforces Swing Shack voice — direct, South African, data-driven, no fluff. Flags generic AI-sounding copy, salesy language, Americanisms, weak CTAs, and unsubstantiated performance claims.

## Schema
`https://clawdia.io/agents/brand-guard/v1`

## Inputs consumed
- `data/captions.json` — caption tone check
- `data/caption-variants.json` — CTA variant tone
- `data/blog-drafts.json` — blog brand check
- `data/reddit-replies.json` — Reddit native tone check

## Outputs produced
| File | Contents |
|---|---|
| `data/brand-guard-report.json` | Per-item brand score and violations |
| `data/tone-violations.json` | All violations by type with fix suggestions |

## Violation types flagged
| Type | Severity | Description |
|---|---|---|
| `generic_ai` | high | "world-class", "cutting edge", "passionate about" |
| `salesy_sludge` | medium | "amazing", "incredible", "mind-blowing" |
| `too_american` | low | American slang in SA market |
| `weak_cta` | low | "click the link", "check out our" |
| `overclaim` | high | Unsubstantiated performance guarantees |
| `no_proof` | medium | Golf improvement claim without data |

## Brand voice standard
- **Tone:** direct, South African, data-driven, no fluff
- **Good:** "Your swing speed is 83 mph. PGA Tour avg: 112. Here's how to close the gap."
- **Bad:** "World-class golfing experience awaits at our stunning facility!"

## How to run
```bash
node agents/brand_guard/run.js
node scripts/run_agent.js brand_guard
```