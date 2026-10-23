"""Moments: sharper filter and the drafted take. The model is faked; nothing reaches the network."""
import datetime as dt
import json

from _lib import moments as m

NOW = dt.datetime(2026, 10, 20, 10, 0, tzinfo=dt.timezone.utc)
HOURS_AGO = lambda h: NOW - dt.timedelta(hours=h)  # noqa: E731


def item(title, *, kind="news", ctx=(), traffic=None, age=2, source="IOL Sport"):
    return {"source": source, "kind": kind, "title": title, "link": None, "published": HOURS_AGO(age),
            "traffic": traffic, "context": list(ctx)}


def titles(out):
    return [r["title"] for r in out["items"]]


def test_generic_searches_and_club_business_are_dropped():
    out = m.live([
        item("rugby union", kind="trends", traffic="1000+"),
        item("Sundowns officially announce Maku signing"),
        item("Springboks star's contract terminated at Japanese club"),
        item("US Open champion Clark joins Nedbank Golf Challenge field for 2026"),
    ], now=NOW)
    assert titles(out) == ["US Open champion Clark joins Nedbank Golf Challenge field for 2026"]


def test_a_national_team_match_is_kept_even_with_a_transfer_word_in_it():
    out = m.live([item("Springboks name squad to face Ireland, coach explains selection")], now=NOW)
    assert len(out["items"]) == 1


def test_trends_searches_show_the_headline_not_the_bare_name():
    out = m.live([item("marco jansen", kind="trends", traffic="10000+",
                       ctx=["DAY 2: Bavuma fights but Boland tears through Proteas in Test"])], now=NOW)
    assert titles(out) == ["DAY 2: Bavuma fights but Boland tears through Proteas in Test"]


def test_act_today_is_strict():
    hot = m.live([item("Proteas v Australia Test: day 2 live", kind="trends", traffic="10000+", age=2,
                       ctx=["Proteas v Australia Test: day 2 live"])], now=NOW)
    assert hot["items"][0]["act_today"] is True
    quiet_sport = m.live([item("Proteas v Australia Test: day 2 live", kind="trends", traffic="200+", age=2)], now=NOW)
    assert quiet_sport["items"][0]["act_today"] is False  # too few searches
    stale = m.live([item("Proteas v Australia Test: day 2 live", kind="trends", traffic="10000+", age=30)], now=NOW)
    assert stale["items"][0]["act_today"] is False
    weather = m.live([item("Cold front brings heavy rain to Gauteng", age=1)], now=NOW)
    assert weather["items"][0]["act_today"] is False  # weather is never an alert
    flyover = m.live([item("Air Force flyover thrills the crowd at Loftus", age=1)], now=NOW)
    assert flyover["items"][0]["act_today"] is True


GOOD = json.dumps({"angle": "Everyone looked up.", "swing-shack": "That flyover was lower than our handicap. Almost.",
                   "stick": "Low and steady. Same as a good swing."})


def test_parse_draft_checks_the_model():
    ok = m.parse_draft("Sure! " + GOOD)
    assert ok["lines"]["swing-shack"].startswith("That flyover") and ok["angle"]
    assert m.parse_draft("not json") is None
    assert m.parse_draft('{"skip": true}') == {"skip": True}
    long_line = json.dumps({"swing-shack": "x" * 200, "stick": "fine line"})
    assert list(m.parse_draft(long_line)["lines"]) == ["stick"]  # the long one is dropped
    bad = json.dumps({"swing-shack": "Nice one #golf", "stick": "Man shot dead, ha"})
    assert m.parse_draft(bad) is None  # hashtag and sensitive both rejected


def _live_items():
    return m.live([item("Air Force flyover thrills the crowd at Loftus", age=1)], now=NOW)["items"]


def test_draft_lines_adds_the_take_and_falls_back_on_failure():
    items = _live_items()
    m.draft_lines(items, chat=lambda msgs: (GOOD, None))
    assert items[0]["lines"]["stick"] and items[0]["angle"]
    again = _live_items()
    m.draft_lines(again, chat=lambda msgs: (None, "boom"))
    assert "lines" not in again[0] and again[0]["starter_line"]  # template stays


def test_draft_lines_reuses_a_saved_draft_and_honours_skip():
    first = _live_items()
    m.draft_lines(first, chat=lambda msgs: (GOOD, None))
    calls = []
    second = _live_items()
    m.draft_lines(second, chat=lambda msgs: calls.append(1) or (GOOD, None), previous=first)
    assert calls == [] and second[0]["lines"] == first[0]["lines"]
    third = _live_items()
    m.draft_lines(third, chat=lambda msgs: ('{"skip": true}', None))
    assert third[0]["skip_joke"] is True and "lines" not in third[0]


def test_the_prompt_sets_the_voice_and_the_guardrails():
    s = m.VOICE_SYSTEM
    assert "Nando" in s and "side of the ordinary person" in s
    for guard in ("skip", "No made-up facts", "No hashtags", "never at a person"):
        assert guard.lower() in s.lower()
