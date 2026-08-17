"""Regression test: Agents > Integrations renderer surfaces blockers + capabilities.

Background
----------
/api/intel/agents returns integration_health.health[] with rich fields
per row: status, connected, auth_status, last_success, hours_ago, days_ago,
scope_level, api_key_prefix, evidence, blockers[], capabilities_at_risk[],
capabilities_unlocked[].

The pre-fix renderAgents() called the generic itemHtml() on these rows,
which only knows `name` (title) + `status` pill + `id` pill — and buried
the rest of the payload inside the JSON.stringify fallback. Christelle
saw `Meta Ads Manager | DEGRADED | meta_ads` with no way to know WHY Meta
is degraded or WHAT blocks WhatsApp.

The fix adds integrationHealthHtml() that:
  - Renders a KV grid (Status / Connected / Auth / Last seen / Last
    success / Scope / Key prefix) with colour-mapped pills
  - Renders evidence, note, blockers (as a bullet list), capabilities at
    risk (red pills), capabilities unlocked (green pills) as expandable
    detail rows
  - Surfaces days_ago/hours_ago as readable age ("just now" / "3h ago" /
    "5d ago" / "never") instead of a raw 999 sentinel
  - Never falls through to JSON.stringify(it)

Tests
-----
1. integrationHealthHtml() is defined in the SPA bundle.
2. renderAgents() wires the new renderer for #agents-int, NOT itemHtml.
3. The renderer reads every meaningful field from the payload (status,
   connected, auth_status, evidence, blockers, capabilities_at_risk,
   capabilities_unlocked, last_success, scope_level, days_ago, hours_ago).
4. No em-dash in the renderer body (standing rule).
5. No JSON.stringify(it) fallback inside the renderer.
6. The renderer translates the days_ago=999 sentinel to "never".
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"
HTML = HTML_PATH.read_text(encoding="utf-8")


def _integration_health_block() -> str:
    """Return the body of the `function integrationHealthHtml(...)` function."""
    m = re.search(r"function\s+integrationHealthHtml\([^)]*\)\{(.*?)\n\}\n", HTML, re.DOTALL)
    assert m, "integrationHealthHtml() not found in SPA bundle"
    return m.group(0)


def _agents_int_render_call() -> str:
    """Return the #agents-int render call wiring."""
    # The bundle is minified: everything sits on one line. The actual call
    # chain is .map(integrationHealthHtml).filter(Boolean).join('') and
    # the only `||` fallback is the trailing '<div class="empty">…'. We
    # anchor on `#agents-int'` and read until the `.join('')` immediately
    # followed by the empty-state OR clause so the regex cannot span past
    # the expression we care about.
    pattern = (
        r"\$"
        r"\("
        r"'#agents-int'"
        r"\)"
        r"\.innerHTML"
        r"\s*=.*?"
        r"\.join\(''\)"
        r"\s*\|\|\s*'<div class=\"empty\">"
    )
    m = re.search(pattern, HTML)
    assert m, "Could not find #agents-int render call wiring"
    return m.group(0)


class IntegrationHealthRendererTests(unittest.TestCase):
    """Agents > Integrations must surface blockers + capabilities, not just (name + status + id)."""

    def test_01_function_defined(self):
        """integrationHealthHtml() must be defined on the SPA."""
        self.assertRegex(HTML, r"function\s+integrationHealthHtml\(",
                         "integrationHealthHtml() must be defined on the SPA")

    def test_02_render_agents_wires_new_renderer(self):
        """#agents-int must use integrationHealthHtml, NOT itemHtml."""
        call = _agents_int_render_call()
        self.assertIn("integrationHealthHtml", call,
                      f"#agents-int must call integrationHealthHtml, found: {call!r}")
        self.assertNotIn(".map(itemHtml)", call,
                         "Must not fall back to the generic itemHtml()")

    def test_03_renderer_reads_meaningful_fields(self):
        """The renderer must read every actionable field from the payload."""
        body = _integration_health_block()
        required = [
            "h.status",
            "h.connected",
            "h.auth_status",
            "h.evidence",
            "h.blockers",
            "h.capabilities_at_risk",
            "h.capabilities_unlocked",
            "h.last_success",
            "h.scope_level",
            "h.days_ago",
            "h.hours_ago",
        ]
        missing = [f for f in required if f not in body]
        self.assertEqual(missing, [],
                         f"integrationHealthHtml() must read these fields: {missing}")

    def test_04_no_em_dash_in_renderer(self):
        """Standing rule: no em-dash in published copy."""
        body = _integration_health_block()
        self.assertNotIn("\u2014", body,
                         "integrationHealthHtml() must not use em-dash (standing rule)")
        self.assertNotIn("\u2013", body,
                         "integrationHealthHtml() must not use en-dash (standing rule)")

    def test_05_no_json_stringify_fallback(self):
        """The renderer must never fall through to JSON.stringify(it) wall-of-braces."""
        body = _integration_health_block()
        self.assertNotIn("JSON.stringify(it)", body,
                         "Renderer still has JSON.stringify(it) fallback - must be removed so raw JSON never bleeds into the title")

    def test_06_age_label_handles_999_sentinel(self):
        """days_ago: 999 means 'never / unknown' - the renderer must translate it."""
        body = _integration_health_block()
        # The 999 sentinel is what the integration_health service emits for
        # 'no successful connection recorded'. Show that as 'never' rather
        # than '999d ago' which is misleading.
        self.assertRegex(body, r"999",
                         "Renderer should explicitly handle the 999 sentinel value")
        self.assertIn("never", body,
                      "Renderer must render the 999 sentinel as 'never'")


if __name__ == "__main__":
    unittest.main()