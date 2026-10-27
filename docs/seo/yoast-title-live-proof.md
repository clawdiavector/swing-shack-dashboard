# Yoast title write — supervised live proof (Swing Shack)

Campaign OS **Fix / Improve** buttons call `seo_meta_publish.write_field(..., field="title")`, then **read back** from WordPress. Automated proof uses a fake WordPress in CI (`test_yoast_title_roundtrip_20261026.py`) and:

```bash
python3 campaign-os/scripts/seo_yoast_title_roundtrip_probe.py
```

That dry-run exits `0` when write + verify succeeds. **Do not** point the probe at production with a write — there is no live-write mode in the script.

## Before you start

1. Confirm the [Yoast pages REST snippet](wordpress-yoast-pages-snippet.md) is installed (or Yoast registers `_yoast_wpseo_title` on pages).
2. Read-only check from a machine with `SWINGSHACK_WP_USER` / `SWINGSHACK_WP_APP_PASSWORD` set:

   ```bash
   python3 campaign-os/scripts/seo_yoast_title_roundtrip_probe.py --live-check --brand swing-shack
   ```

   Expect `page_field_writable_title: true` and a non-empty `membership_title_before`.

3. Set `SEO_AUTOPUBLISH` on Railway to `dry-run` first if you want a logged “would change” before a real write.

## Supervised write on Membership (one page)

Use a **non-homepage** page first (Membership is the usual canary).

1. Open Campaign OS → **Results → SEO** → **Fix with a click**. Find **short title** (or missing) on **Membership**.
2. Note the **current** title shown in the edit box (or open WordPress → Pages → Membership → Yoast snippet).
3. Edit the proposal to a test title you can recognise (30–60 characters), e.g. append ` · proof` temporarily.
4. Click **Apply** (confirm any claim warning if shown).
5. **Verify in Campaign OS:** the item moves to **Changes made** with status applied and `verified` true. If verify fails, stop — WordPress is still dropping page titles (snippet missing or wrong user).
6. **Verify in WordPress:** reload the Membership editor; Yoast SEO title matches what you applied.
7. **Verify in REST (optional):** from a trusted shell with app password, `GET /wp-json/wp/v2/pages?slug=membership&context=edit` and check `meta._yoast_wpseo_title` or `yoast_head_json.title`.
8. **Undo** from Campaign OS history (newest first) to restore the previous title; confirm WordPress shows the old title again.

## What failure looks like

- Apply succeeds in the UI but verify fails → Yoast did not persist (pages not REST-writable).
- Apply refused with 409 stale → someone changed the title in WordPress between draft and apply; refresh and retry.
- Homepage: same mechanics, but automatic runs never touch it; manual click is still allowed — use extra care.

## After proof

Record date and operator in your runbook. Leave `SEO_AUTOPUBLISH` at the tier Kyle chose (`dry-run` vs `on`).
