"""
Regression test for the first-run welcome tour null-safety fix.

Bug (caught by the 2026-08-09 pre-pick sweep):
When a code path destroys the .welcome-tour child div (e.g. an external
cleanup pass or another tab-cycling routine) BEFORE the welcome tour runs,
the boot path `maybeShowWelcome() -> setTimeout(openWelcome, 600) ->
openWelcome() -> renderTourStep(0)` throws
  TypeError: Cannot set properties of null (setting 'textContent')
on the first missing element. Production pageerror in the wild.

Fix: guard every `$('#welcome-*')` setter in renderTourStep, openWelcome,
and closeWelcome with `if (el) el.textContent = ...`. The tour should
no-op gracefully when its DOM scaffolding is missing.

This is a read-only regression test — it never imports flask, never hits a
running server. It loads campaign-os.html as text and asserts structural
markers.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML = REPO / "campaign-os" / "campaign-os.html"


def _read() -> str:
    assert HTML.exists(), f"campaign-os.html missing at {HTML}"
    return HTML.read_text(encoding="utf-8")


class WelcomeTourNullSafeTests(unittest.TestCase):
    """Guard tests for the welcome tour null-safety fix."""

    def _renderTourStep_body(self) -> str:
        src = _read()
        m = re.search(
            r"function renderTourStep\(idx\)\{.*?\n(function openWelcome|function closeWelcome)",
            src,
            re.DOTALL,
        )
        assert m, "Could not locate renderTourStep() body in campaign-os.html"
        return m.group(0)

    def _openWelcome_body(self) -> str:
        src = _read()
        m = re.search(
            r"function openWelcome\(\)\{[\s\S]*?\n(function closeWelcome|function maybeShowWelcome)",
            src,
        )
        assert m, "Could not locate openWelcome() body"
        return m.group(0)

    def _closeWelcome_body(self) -> str:
        src = _read()
        m = re.search(
            r"function closeWelcome\(\)\{[\s\S]{0,300}?localStorage\.setItem",
            src,
        )
        assert m, "Could not locate closeWelcome() body"
        return m.group(0)

    def test_renderTourStep_guards_every_setter(self):
        """Every `$('#welcome-*')` setter inside renderTourStep must be guarded
        by an `if(el)` null-check so the tour no-ops gracefully when the DOM
        scaffolding is missing (the original pageerror path)."""
        body = self._renderTourStep_body()
        # Find every welcome-* selector reference and ensure each is followed
        # by an `if (` guard within ~150 chars (covers line wrap).
        setters = re.findall(r"\$\(\s*['\"]?#welcome-([a-z-]+)['\"]?\s*\)", body)
        assert setters, "No $('#welcome-*') setters found in renderTourStep body"

        seen = set()
        missing_guard = []
        for sel_id in setters:
            if sel_id in seen:
                continue
            seen.add(sel_id)
            # Look for any occurrence of the selector followed within 200 chars
            # by an `if (` guard — this covers both inline `if(el)` and the
            # split `const xxx = $('#welcome-Y'); if(xxx)` pattern.
            guard_pattern = re.compile(
                rf"\$\(\s*['\"]?#welcome-{re.escape(sel_id)}['\"]?\s*\)[\s\S]{{0,200}}if\(",
                re.DOTALL,
            )
            if not guard_pattern.search(body):
                missing_guard.append(sel_id)

        assert not missing_guard, (
            "These welcome-* setters in renderTourStep() are not null-guarded: "
            + ", ".join(missing_guard)
            + " — without the guard the page throws 'Cannot set properties of null' "
            + "when any welcome-* child has been removed from the DOM before the tour runs."
        )

    def test_openWelcome_guards_welcome_bg_setter(self):
        """openWelcome() must guard $('#welcome-bg').classList.add('on') with
        an `if(bg)` check."""
        body = self._openWelcome_body()
        unguarded = re.search(
            r"^\s*\$\(\#welcome-bg\)\.classList\.add\('on'\)\s*;\s*$",
            body,
            re.MULTILINE,
        )
        assert not unguarded, (
            "openWelcome() still has an unguarded $('#welcome-bg').classList.add('on') "
            "— wrap it in `if(bg)` so the tour no-ops if the modal was wiped."
        )

    def test_closeWelcome_guards_welcome_bg_setter(self):
        """closeWelcome() must guard $('#welcome-bg').classList.remove('on')
        with an `if(bg)` check."""
        body = self._closeWelcome_body()
        unguarded = re.search(
            r"^\s*\$\(\#welcome-bg\)\.classList\.remove\('on'\)\s*;\s*$",
            body,
            re.MULTILINE,
        )
        assert not unguarded, (
            "closeWelcome() still has an unguarded $('#welcome-bg').classList.remove('on') "
            "— wrap it in `if(bg)` so dismissing the tour never throws if the modal was wiped."
        )

    def test_no_unconditional_welcome_setters_left(self):
        """Belt + braces: scan the whole file for any unguarded `welcome-*`
        setter pattern. The patched code should have ZERO matches for the
        unguarded form `$('#welcome-X').<mutator>` on a line by itself.
        """
        src = _read()
        bad = re.findall(
            r"^\s*\$\(\#welcome-[a-z-]+\)\.(textContent|innerHTML|classList)\.[a-zA-Z_]+\(",
            src,
            re.MULTILINE,
        )
        assert not bad, (
            "Found unguarded welcome-* setter line(s) in campaign-os.html: "
            + repr(bad)
            + " — every welcome-* mutation must be wrapped in `if(el)`."
        )

    def test_renderTourStep_returns_early_on_missing_step(self):
        """The patched function adds `if(!tour) return;` after the
        `const tour = TOUR_STEPS[idx]` line so an out-of-range index is safe."""
        body = self._renderTourStep_body()
        assert "if(!tour) return;" in body, (
            "renderTourStep() should return early when TOUR_STEPS[idx] is "
            "undefined — guards against out-of-range index calls."
        )

    def test_no_em_dash_in_patched_block(self):
        """Standing rule: no em-dash in shipped copy. The new comment block is
        a code comment but the rule still gets a regression test."""
        body = self._renderTourStep_body()
        assert "\u2014" not in body and "\u2013" not in body, (
            "renderTourStep() body contains an em/en-dash. Use `,` or `:` instead."
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)