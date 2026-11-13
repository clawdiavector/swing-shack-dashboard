"""Ops layer links must not point at /?page= Classic pages.

Since 30 Sep 2026 campaign-os.html is the new app's build, so a /?page= link
opens a blank screen. See wiki research/full-os-audit-2026-11-13.
"""
import os

LIB = os.path.join(os.path.dirname(__file__), '..', '_lib')


def test_ops_layers_has_no_classic_page_links():
    with open(os.path.join(LIB, 'ops_layers.py'), encoding='utf-8') as f:
        src = f.read()
    assert '/?page=' not in src
