from _lib.compose_visual_copy import visual_copy_for_archetype
from _lib.poster_copy import (
    poster_copy_mode_for_archetype,
    poster_hook_cap,
    resolve_poster_hook,
)


def test_poster_copy_mode_defaults_to_llm_hook():
    assert poster_copy_mode_for_archetype({}) == "from_llm_hook"
    assert poster_copy_mode_for_archetype({"poster_copy_mode": "nonsense"}) == "from_llm_hook"


def test_poster_hook_cap_from_zone():
    ss_promo = {
        "zones": {"headline": {"max_lines": 4, "max_chars_per_line": 16}},
    }
    stick_stmt = {
        "zones": {"headline": {"max_lines": 5, "max_chars_per_line": 16}},
    }
    assert poster_hook_cap(ss_promo) == 64
    assert poster_hook_cap(stick_stmt) == 80
    assert poster_hook_cap({}) == 72


def test_lodge_title_becomes_poster_hook_ss_service_promo():
    arch = {
        "id": "ss-service-promo",
        "poster_copy_mode": "from_lodge_title",
        "applies_to": {"needs_photo": False},
        "zones": {"headline": {"max_lines": 4, "max_chars_per_line": 16}},
    }
    sidecar = {
        "lodge_title": "Off-the-rack is for groceries",
        "copy_package": {
            "caption_body": "Unrelated feed body.",
            "poster_hook": "SOMETHING ELSE",
            "cta_line": "Book online",
        },
    }
    fields = visual_copy_for_archetype(
        brand_id="swing-shack",
        moment_id="calendar_candidate:swing-shack:cal-1",
        caption="Totally different caption for the feed.",
        archetype=arch,
        sidecar=sidecar,
    )
    assert fields["caption_hook"] == "Off-the-rack is for groceries"
    assert fields["_poster_copy_source"] == "lodge_title"


def test_fixed_mode_stick_brand_statement():
    arch = {
        "id": "stick-brand-statement",
        "poster_copy_mode": "fixed",
        "poster_copy": {"fixed_headline": "FITTINGS\nCOACHING\nEQUIPMENT\nAPPAREL"},
        "applies_to": {"needs_photo": False},
        "zones": {"headline": {"max_lines": 5, "max_chars_per_line": 16}},
    }
    fields = visual_copy_for_archetype(
        brand_id="stick",
        moment_id="proposal:stick:x",
        caption="Random caption that should not win.",
        archetype=arch,
        sidecar={
            "copy_package": {"poster_hook": "IGNORE ME", "caption_body": "x", "cta_line": ""},
        },
    )
    assert fields["caption_hook"] == "FITTINGS\nCOACHING\nEQUIPMENT\nAPPAREL"
    assert fields["_poster_copy_source"] == "fixed"


def test_sidecar_compose_headline_overrides_mode():
    arch = {"poster_copy_mode": "from_lodge_title", "zones": {"headline": {"max_lines": 4, "max_chars_per_line": 16}}}
    headline, src = resolve_poster_hook(
        brand_id="stick",
        moment_id="proposal:stick:x",
        caption="caption",
        archetype=arch,
        sidecar={"compose_headline": "Operator override", "lodge_title": "Lodge title"},
    )
    assert headline == "Operator override"
    assert src == "sidecar"


def test_llm_hook_mode_uses_copy_package():
    arch = {
        "poster_copy_mode": "from_llm_hook",
        "zones": {"headline": {"max_lines": 4, "max_chars_per_line": 16}},
    }
    headline, src = resolve_poster_hook(
        brand_id="stick",
        moment_id="proposal:stick:x",
        caption="caption",
        archetype=arch,
        sidecar={"copy_package": {"poster_hook": "Personalised fitting"}},
    )
    assert headline == "Personalised fitting"
    assert src == "llm_hook"
