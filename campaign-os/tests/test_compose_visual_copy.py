from _lib.compose_visual_copy import _hook_from_caption, _service_cta, visual_copy_for_archetype


def test_hook_from_caption_question():
    cap = (
        "Swing hard and hope for the best? may be a popular mantra, but it is not coaching. "
        "TrackMan helps you find tempo."
    )
    assert _hook_from_caption(cap) == "Swing hard and hope for the best?"


def test_service_cta_coaching():
    cta = _service_cta(brand_id="stick", moment_id="calendar_candidate:stick:noop", caption="TrackMan session")
    assert "swing assessment" in cta.lower()


def test_visual_copy_service_frame_uses_hook_not_full_caption():
    arch = {
        "id": "stick-service-frame",
        "applies_to": {"needs_photo": False},
    }
    cap = "Swing hard and hope for the best?\n\nLong body about TrackMan and tempo."
    fields = visual_copy_for_archetype(
        brand_id="stick",
        moment_id="proposal:stick:x",
        caption=cap,
        archetype=arch,
        asset_title="TrackMan coaching session",
    )
    assert fields["caption_hook"] == "Swing hard and hope for the best?"
    assert "swing assessment" in fields["cta"].lower()
