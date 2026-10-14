"""Guards for tests that read the old hand-written campaign-os.html.

On 2026-09-30 (917f2228) campaign-os.html became the inlined Vite build of
web/, and app.py redirects away from the old page. Tests that parse code out of
the old page cannot find it, and errored on every CI run since. They skip
while their own marker is missing, and run again if it ever comes back.
Whether web/ re-implements what each one guarded is not checked here.
"""
from __future__ import annotations

import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "campaign-os.html"
REASON = ("old hand-written campaign-os.html replaced by the web/ Vite build "
          "(917f2228, 2026-09-30); marker {!r} not in page")


def has(marker: str) -> bool:
    return marker in PAGE.read_text(encoding="utf-8")


def skip_module_unless(marker: str) -> None:
    if not has(marker):
        raise unittest.SkipTest(REASON.format(marker))


def skip_unless(marker: str):
    return unittest.skipUnless(has(marker), REASON.format(marker))


# Present 43 times in the old page and never in the Vite build: one static
# <section> per sidebar page. Used where a test has no narrower marker.
OLD_PAGE = '<section class="section" id="sec-'
on_old_page_only = skip_unless(OLD_PAGE)
