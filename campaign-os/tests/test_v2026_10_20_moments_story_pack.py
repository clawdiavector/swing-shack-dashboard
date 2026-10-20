"""Moments story pack: the model also drafts a short headline per brand, checked before it is shown."""
import json

from _lib import moments as m


def _reply(**over):
    base = {"angle": "Everyone looked up.", "swing-shack": "Lower than our handicap. Almost.",
            "stick": "Low and steady, like a good swing.",
            "headlines": {"swing-shack": "Lower than our handicap", "stick": "Low and steady"}}
    base.update(over)
    return json.dumps(base)


def test_parse_draft_keeps_valid_headlines():
    out = m.parse_draft(_reply())
    assert out["headlines"] == {"swing-shack": "Lower than our handicap", "stick": "Low and steady"}


def test_parse_draft_drops_headlines_that_are_too_long_or_unsafe():
    out = m.parse_draft(_reply(headlines={"swing-shack": "x" * 41, "stick": "Man shot dead #golf"}))
    assert out["headlines"] == {}  # lines survive, bad headlines do not


def test_parse_draft_works_when_the_model_gives_no_headlines():
    out = m.parse_draft(json.dumps({"swing-shack": "A fine line.", "angle": "a"}))
    assert out["lines"] and out["headlines"] == {}


def test_a_headline_is_only_kept_for_a_brand_whose_line_survived():
    out = m.parse_draft(_reply(**{"swing-shack": "#hashtag line"}))
    assert "swing-shack" not in out["lines"] and "swing-shack" not in out["headlines"]


def test_draft_lines_stores_headlines_and_reuses_them():
    def item():
        return [{"title": "Flyover", "source": "IOL", "category": "flyover", "starter_line": "x"}]

    first = item()
    m.draft_lines(first, chat=lambda msgs: (_reply(), None))
    assert first[0]["headlines"]["stick"] == "Low and steady"
    calls = []
    again = item()
    m.draft_lines(again, chat=lambda msgs: calls.append(1) or (_reply(), None), previous=first)
    assert calls == [] and again[0]["headlines"] == first[0]["headlines"]


def test_an_older_saved_draft_without_headlines_is_redone_once():
    old = [{"title": "Flyover", "source": "IOL", "category": "flyover", "starter_line": "x",
            "lines": {"stick": "Old line."}, "angle": "old"}]  # saved before headlines existed
    items = [{"title": "Flyover", "source": "IOL", "category": "flyover", "starter_line": "x"}]
    calls = []
    m.draft_lines(items, chat=lambda msgs: calls.append(1) or (_reply(), None), previous=old)
    assert calls == [1] and items[0]["headlines"]


def test_the_prompt_asks_for_a_short_story_headline():
    assert "40 characters or fewer" in m.VOICE_SYSTEM and "headlines" in m.VOICE_SYSTEM


def test_a_quote_that_belongs_to_the_line_is_kept():
    out = m.parse_draft(json.dumps({"swing-shack": '"No pressure," they say. Same fib on the first tee.',
                                    "stick": '"Wrapped whole line"'}))
    assert out["lines"]["swing-shack"].startswith('"No pressure,"')  # a quote inside the line stays
    assert out["lines"]["stick"] == "Wrapped whole line"  # quotes around the whole line go
