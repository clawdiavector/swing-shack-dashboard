"""No brand's CTA rules may name another brand.

creative_package._build_stub_core puts knowledge.json cta_rules.default_cta on
posters. Until 2026-10-15 Bag Drop's was "Drop your bag with us ->
swingshack.co.za". Only cta_rules is checked: other knowledge.json fields hold
cross-brand facts (sister-brand ownership, a dont_say entry naming the other
brands) that are legitimately there.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_DATA = Path(__file__).resolve().parents[2] / "data"

BRAND_NAMES = {
    "swing-shack": re.compile(r"swing\s*shack", re.I),
    "stick": re.compile(r"\bStick\b|stickgolf|stick\.paarl"),
    "bag-drop": re.compile(r"bag\s*drop", re.I),
}


def _strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("source", "source_class", "authority_level"):
                yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)
    elif isinstance(obj, str):
        yield obj


@pytest.mark.parametrize("brand", list(BRAND_NAMES))
def test_cta_rules_name_no_other_brand(brand):
    k = json.loads((REPO_DATA / "brand-directory" / brand / "knowledge.json").read_text(encoding="utf-8"))
    leaks = [
        (s, [b for b, pat in BRAND_NAMES.items() if b != brand and pat.search(s)])
        for s in _strings(k.get("cta_rules") or {})
    ]
    assert [l for l in leaks if l[1]] == []
