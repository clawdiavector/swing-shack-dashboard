# Post type → compose archetype (Swing Shack + Stick)

Selection is **last matching rule wins** in each brand's `visual-spec/archetypes.json`
(`selection.rules`), then `selection.default`. Pinned `template_id` on the calendar
record always overrides rules.

## Swing Shack service templates

| post_type | Archetype | Notes |
|---|---|---|
| `price_package` | `ss-price-package` | Single hero price + qualifier |
| `price_list`, `package_list`, `rate_card` | `ss-price-list` | Multi-row rate card; needs sidecar price fields |
| `tip`, `did_you_know`, `myth` | `ss-did-you-know` | Question headline tile |

See each pack's `template.md` for copy budgets and sidecar keys.
