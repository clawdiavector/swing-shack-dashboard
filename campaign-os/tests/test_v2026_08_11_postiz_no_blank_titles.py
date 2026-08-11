"""v2026-08-11 — Postiz surface must render real queue + refs data, not blanks.

The pre-pick sweep on 2026-08-11 (scripts/sweep_campaign_os_live.py + a
focused walk) caught TWO broken renderers inside renderPostiz():

  1. Queue rows (#postiz-queue) — all 20 visible rows rendered with an
     EMPTY title + just "instagram · queued · " in the meta line.
     Root cause: the live data (data/publish-queue.json) carries the
     caption text under `caption_preview` (NOT `caption` or `name`),
     the status under `status` (NOT `publishStatus`), and the schedule
     timestamp under `scheduled_date` (NOT `publishDate`). The renderer
     read `it.caption || it.name`, so every row fell through to ''.

  2. Refs rows (#postiz-refs) — the single canonical reference rendered
     as a "—" title with a trailing-empty meta line.
     Root cause: data/publishing-references.json carries the upstream
     postiz id under `postizPostId` (NOT `postizId`) and the lifecycle
     status under `currentStatus` (NOT `publishStatus`). The renderer
     read the legacy key names, so the row rendered as em-dash fallback.

This is the same lying-affordance pattern that bit renderFAQs() and the
Reddit replies renderer before it. Fix at campaign-os.html:9764-9795.

Fix contract:
  - Queue title = first non-empty string among `caption_preview`,
    `caption`, `name`, `linked_hook_id` (mirrors publish page's pickTitle).
    NEVER the empty string.
  - Queue meta = `platform · status · scheduled_date` (date optional).
  - Refs title = `postizPostId` first (canonical upstream id), fall back
    to `postizId` / `id` / `publishingId`. NEVER the em-dash.
  - Refs meta = `platform · campaignId · assetId · currentStatus`.
  - The empty-state strings ("Queue empty", "No canonical references
    yet") remain as the honest fallbacks when the data really is empty.
"""
from __future__ import annotations

import json
import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(REPO_ROOT, "campaign-os", "campaign-os.html")
QUEUE_DATA = os.path.join(REPO_ROOT, "data", "publish-queue.json")
REFS_DATA = os.path.join(REPO_ROOT, "data", "publishing-references.json")
LIVE_URL = "https://swing-shack-dashboard-production.up.railway.app"


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ─── 1. STATIC — the renderer must read the canonical field names ─────
class TestPostizRendererReadsCanonicalFields(unittest.TestCase):
    def setUp(self):
        self.html = _read(HTML_PATH)
        # Scope to renderPostiz() so other generic renderers (which might
        # also read .caption) don't trip these checks.
        m = re.search(r"async function renderPostiz\(\)\{(.*?)\n\}\n", self.html, re.DOTALL)
        self.assertIsNotNone(m, "renderPostiz() function not found in HTML")
        self.body = m.group(1)

    def test_queue_renderer_reads_caption_preview(self):
        # The queue title must read `caption_preview` as the primary field.
        # Without this, all 20 rows render blank.
        self.assertIn(
            "caption_preview", self.body,
            "renderPostiz() queue branch does not read `caption_preview` — "
            "every queued item will render with an empty title.",
        )

    def test_queue_renderer_does_not_drop_to_empty_on_real_data(self):
        # Sanity: the title-extractor must NOT be the simple
        # `it.caption || it.name` chain that was the bug. We require the
        # chain to start with `caption_preview` so the bug is structurally
        # prevented.
        # Match the entire $("#postiz-queue").innerHTML = ... assignment,
        # which can span multiple lines.
        block = self._extract_renderer_block("postiz-queue")
        # The block must reference caption_preview BEFORE any other
        # caption-ish fallback. Use a simple substring check.
        first_fallback_idx = block.find("caption_preview")
        self.assertGreater(first_fallback_idx, 0, "#postiz-queue block never references caption_preview")
        # Confirm the legacy fallback chain didn't get re-introduced
        # without caption_preview coming first.
        legacy_first = block.find("(it.caption||it.name||")
        self.assertEqual(
            legacy_first, -1,
            "renderPostiz() queue branch still uses the legacy "
            "`it.caption || it.name` chain as the title source. Replace "
            "with `caption_preview || caption || name || linked_hook_id`.",
        )

    def _extract_renderer_block(self, sel):
        # Pull the entire assignment to $('#{sel}').innerHTML = ... up to
        # the first top-level .join('') or .join('')). The block ends at
        # the .join('') closing.
        idx = self.html.find(f"$('#{sel}').innerHTML")
        if idx < 0:
            return ""
        # Find the next .join closing pattern. The renderer ends with
        # .join('') || '<div...>' so just walk up to that .join('') call.
        # Use a regex from the match point.
        snippet = self.html[idx:idx + 4000]
        m = re.search(r"\$\(.{1,3}#" + re.escape(sel) + r".{1,3}\)\.innerHTML\s*=\s*(.*?\.join\([^)]*\))", snippet, re.DOTALL)
        if not m:
            return ""
        return m.group(1)

    def test_refs_renderer_reads_postiz_post_id(self):
        # The refs title must read `postizPostId` (the upstream id).
        self.assertIn(
            "postizPostId", self.body,
            "renderPostiz() refs branch does not read `postizPostId` — "
            "the canonical reference row will render as '—' instead of "
            "the upstream postiz id.",
        )

    def test_refs_renderer_reads_current_status(self):
        self.assertIn(
            "currentStatus", self.body,
            "renderPostiz() refs branch does not read `currentStatus` — "
            "the lifecycle status pill will be blank for every canonical ref.",
        )

    def test_no_lying_affordance_legacy_fields_only(self):
        # The refs title chain must include the legacy `postizId` and `id`
        # as fallbacks (so a future schema change that goes back to the
        # legacy key still renders something). It must NOT be ONLY those
        # legacy fields, which was the bug.
        block = self._extract_renderer_block("postiz-refs")
        self.assertTrue(
            block,
            "could not find #postiz-refs renderer block via regex",
        )
        # Should mention both postizPostId AND either postizId or id (fallback)
        self.assertIn("postizPostId", block)
        has_legacy = ("postizId" in block and "postizPostId" in block and
                      block.find("postizId") > block.find("postizPostId"))
        self.assertTrue(
            has_legacy or "publishingId" in block,
            "#postiz-refs block must read `postizPostId` as primary with a "
            "legacy or `publishingId` fallback.",
        )

    def test_no_em_dashes_in_new_code(self):
        # Standing rule: no em-dashes in newly authored strings or
        # comments. Em-dashes in the UI fallback string ('—' rendered
        # when ALL fields are missing) are pre-existing intentional
        # placeholder copy, not new authoring.
        diff_block = self.body
        # Look for em-dashes NOT inside a single-quoted string used as
        # a fallback value (those are the intentional '—' placeholders).
        em_dashes = [m.start() for m in re.finditer(r"—", diff_block)]
        for pos in em_dashes:
            ctx = diff_block[max(0, pos - 30):pos + 30]
            # OK contexts: inside single-quoted fallback string OR
            # the existing user-facing meta bullets that already used '· '
            # separator style (not em-dash, but defensive)
            if "'—'" in ctx or '"—"' in ctx:
                continue
            self.fail(
                f"renderPostiz() contains em-dash in non-fallback context: "
                f"...{ctx}..."
            )


# ─── 2. DATA — the live fixture really has the new field names ────────
class TestPostizQueueDataShape(unittest.TestCase):
    def setUp(self):
        with open(QUEUE_DATA, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def test_queue_has_items(self):
        q = self.data.get("queued") or []
        self.assertIsInstance(q, list)
        self.assertGreater(len(q), 0, "publish-queue.json has no queued items")

    def test_every_queue_item_has_caption_preview(self):
        for i, it in enumerate(self.data.get("queued", [])):
            with self.subTest(i=i):
                cp = it.get("caption_preview")
                self.assertIsNotNone(
                    cp,
                    f"queued[{i}] is missing `caption_preview` — the "
                    "renderer will fall through to '(no caption)'.",
                )
                self.assertIsInstance(cp, str)
                self.assertGreater(
                    len(cp.strip()), 0,
                    f"queued[{i}].caption_preview is empty/whitespace.",
                )

    def test_every_queue_item_has_status(self):
        for i, it in enumerate(self.data.get("queued", [])):
            with self.subTest(i=i):
                self.assertIsNotNone(
                    it.get("status"),
                    f"queued[{i}] is missing `status` — the renderer "
                    "will show an empty status pill.",
                )


class TestPostizRefsDataShape(unittest.TestCase):
    def setUp(self):
        with open(REFS_DATA, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def test_refs_has_references(self):
        refs = self.data.get("references") or []
        self.assertIsInstance(refs, list)
        # Note: 0 is fine (the live dataset may legitimately be empty),
        # but we need at least 1 for the live test below to be meaningful.
        self.assertGreater(
            len(refs), 0,
            "publishing-references.json has no references — live test "
            "below will be a no-op. Skipping the live assertions in that "
            "case is intentional (empty-state is honest).",
        )

    def test_every_ref_has_postiz_post_id(self):
        for i, ref in enumerate(self.data.get("references", [])):
            with self.subTest(i=i):
                self.assertIsNotNone(
                    ref.get("postizPostId"),
                    f"references[{i}] is missing `postizPostId` — the "
                    "renderer will render '—' for the canonical id.",
                )

    def test_every_ref_has_current_status(self):
        for i, ref in enumerate(self.data.get("references", [])):
            with self.subTest(i=i):
                self.assertIsNotNone(
                    ref.get("currentStatus"),
                    f"references[{i}] is missing `currentStatus` — the "
                    "renderer will render an empty status pill.",
                )


# ─── 3. LIVE — the rendered DOM on the live URL must show real titles ──
class TestPostizLiveRendersTitles(unittest.TestCase):
    def setUp(self):
        # Skip if no refs in dataset (test_refs_has_references will catch it).
        with open(REFS_DATA, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not d.get("references"):
            self.skipTest("publishing-references.json has no references")

    def test_live_postiz_queue_has_real_titles(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed in this env")

        pw = (os.environ.get("CAMPAIGN_OS_PASSWORD")
              or os.environ.get("SHARED_PASSWORD")
              or "swing-shack-dev-2026")
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.add_init_script(
                "try { localStorage.setItem('campaign-os.tour.dismissed.v2','1'); } catch(e){}"
            )
            page.goto(LIVE_URL + "/login", wait_until="domcontentloaded")
            page.wait_for_selector("input[type=password]", timeout=15000)
            page.fill("input[type=password]", pw)
            page.press("input[type=password]", "Enter")
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
            page.goto(LIVE_URL + "/campaign-os.html", wait_until="domcontentloaded")
            page.wait_for_selector("#sec-brief", state="attached", timeout=15000)
            page.evaluate("""() => { try { localStorage.setItem('co_welcomed','1'); } catch(e){}; const tour = document.querySelector('.tour, .welcome-tour'); if(tour) tour.remove(); }""")
            # Click postiz nav
            page.evaluate("""() => { const n = document.querySelector('.nav[data-go=\"postiz\"]'); if(n) n.click(); }""")
            page.wait_for_timeout(3500)
            queue = page.locator("#postiz-queue")
            self.assertEqual(queue.count(), 1, "#postiz-queue not in DOM")
            rows = queue.locator(".li")
            self.assertGreater(
                rows.count(), 0,
                "#postiz-queue rendered 0 rows — should be at least 1",
            )
            # Sample the first 5 rows: every title must be non-empty AND
            # not just an em-dash placeholder.
            blank_count = 0
            emdash_count = 0
            for i in range(min(5, rows.count())):
                title = rows.nth(i).locator(".li-title").inner_text() or ""
                t = title.strip()
                if not t:
                    blank_count += 1
                if t == "—":
                    emdash_count += 1
            self.assertEqual(
                blank_count, 0,
                f"{blank_count}/5 first queue rows have empty titles — "
                "the renderer is still reading the wrong field.",
            )
            self.assertEqual(
                emdash_count, 0,
                f"{emdash_count}/5 first queue rows render the em-dash "
                "placeholder — the renderer fell through every fallback.",
            )
            b.close()

    def test_live_postiz_refs_show_postiz_id_and_status(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed in this env")

        with open(REFS_DATA, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not d.get("references"):
            self.skipTest("no references in fixture")
        expected_id = d["references"][0].get("postizPostId") or ""
        expected_status = d["references"][0].get("currentStatus") or ""

        pw = (os.environ.get("CAMPAIGN_OS_PASSWORD")
              or os.environ.get("SHARED_PASSWORD")
              or "swing-shack-dev-2026")
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.add_init_script(
                "try { localStorage.setItem('campaign-os.tour.dismissed.v2','1'); } catch(e){}"
            )
            page.goto(LIVE_URL + "/login", wait_until="domcontentloaded")
            page.wait_for_selector("input[type=password]", timeout=15000)
            page.fill("input[type=password]", pw)
            page.press("input[type=password]", "Enter")
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
            page.goto(LIVE_URL + "/campaign-os.html", wait_until="domcontentloaded")
            page.wait_for_selector("#sec-brief", state="attached", timeout=15000)
            page.evaluate("""() => { try { localStorage.setItem('co_welcomed','1'); } catch(e){}; const tour = document.querySelector('.tour, .welcome-tour'); if(tour) tour.remove(); }""")
            page.evaluate("""() => { const n = document.querySelector('.nav[data-go=\"postiz\"]'); if(n) n.click(); }""")
            page.wait_for_timeout(3500)
            refs_block = page.locator("#postiz-refs")
            self.assertEqual(refs_block.count(), 1, "#postiz-refs not in DOM")
            rows = refs_block.locator(".li")
            self.assertGreater(rows.count(), 0, "#postiz-refs rendered 0 rows")
            html = refs_block.inner_html() or ""
            self.assertNotIn(
                "<li class=\"li\"><div class=\"li-body\"><div class=\"li-title\">—</div>",
                html,
                "First refs row still renders the em-dash placeholder "
                "title — renderer is not reading `postizPostId`.",
            )
            # The upstream id must appear in the rendered HTML.
            if expected_id:
                self.assertIn(
                    expected_id, html,
                    f"Rendered #postiz-refs does not contain the canonical "
                    f"upstream id ({expected_id!r}). Renderer likely reading "
                    "the wrong field.",
                )
            # The current status must appear in the rendered HTML.
            if expected_status:
                self.assertIn(
                    expected_status, html,
                    f"Rendered #postiz-refs does not contain the lifecycle "
                    f"status ({expected_status!r}). Renderer likely reading "
                    "the wrong field (`publishStatus` instead of `currentStatus`).",
                )
            b.close()


if __name__ == "__main__":
    unittest.main()