# Let Campaign OS save Yoast titles and descriptions on pages

Status: written 2026-10-23, **not installed**. Needs someone with WordPress admin on swingshack.co.za.

## Why
Yoast makes its title, description and focus keyphrase writable over WordPress's REST API for **posts only**. On **pages** (Membership, Club Fitting, the homepage) a save is accepted and silently dropped, so Campaign OS cannot set them. Found by a supervised live test on 2026-10-23; see the wiki page `research/yoast-page-meta-not-writable-2026-10-23`.

Until this is installed, Campaign OS shows the suggested text for pages with a Copy button, and you paste it into the Yoast box by hand. Blog posts already work.

## The snippet
```php
add_action('init', function () {
    foreach (['_yoast_wpseo_title', '_yoast_wpseo_metadesc', '_yoast_wpseo_focuskw'] as $key) {
        register_post_meta('page', $key, [
            'type'          => 'string',
            'single'        => true,
            'show_in_rest'  => true,
            'auth_callback' => function () {
                return current_user_can('edit_pages');
            },
        ]);
    }
});
```
It registers the same three fields Yoast already exposes for posts, for pages too. Only a logged-in user who can edit pages (the Application Password user) can save them.

## Where to put it
Any one of these:
- **Code Snippets plugin**, if it is installed: add a new PHP snippet, run everywhere, activate.
- **A must-use plugin file:** `wp-content/mu-plugins/yoast-pages-rest.php`, starting with `<?php`.
- **The child theme's `functions.php`** (lost if the theme is replaced, so the first two are better).

## Check it worked
1. Reload Campaign OS > Results > SEO. The Membership "Fix" box should now show **Apply** instead of the copy notice.
2. Or ask Claude to re-run the page check: `OPTIONS /wp-json/wp/v2/pages` lists the three `_yoast_wpseo_*` keys under `meta`.
3. Then do one supervised write (Membership), with Undo ready, before turning anything else on.

## Undo
Delete the snippet. Nothing else changes. Any description already saved stays in Yoast.

## Risks
- Low. It adds three fields to the page REST schema and changes nothing on the site's front end.
- If Yoast later registers these fields for pages itself, WordPress keeps the first registration; remove this snippet then.
- Try it on a staging copy first if there is one.
