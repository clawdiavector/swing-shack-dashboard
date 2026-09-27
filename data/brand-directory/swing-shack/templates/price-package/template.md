# ss-price-package — monthly hero price card

Single package name, qualifier, centred price + optional billing period on a dimmed full-bleed venue photo with white frame, logo, divider rules, CTA and URL.

## Platforms

- Instagram post (1080×1350) and story (1080×1920, block centred — no story overrides)
- Facebook uses `ig_post` (4:5)

## Copy fields

| Field | Role |
|---|---|
| `caption_hook` | Package name |
| `qualifier` | What's included (≤2 lines) |
| `price` | Formatted amount (required) |
| `price_period` | e.g. Per month (optional) |
| `cta` | Footer CTA |
| `accent` | Optional — else derived from headline |

Tag calendar records `post_type: price_package` (or pin `template_id: ss-price-package`).

## Assets

Logo reused from `templates/did-you-know/assets/logo-white.png`. Background photos are did-you-know stand-ins until raw venue shots are added.
