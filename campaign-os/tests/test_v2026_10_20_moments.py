"""Moments desk: feeds parsed, sensitive stories hidden, calendar looks ahead. Nothing touches the network."""
import datetime as dt

from _lib import moments as m

NOW = dt.datetime(2026, 10, 20, 10, 0, tzinfo=dt.timezone.utc)

TRENDS = b"""<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>kwagga smith leaves japanese rugby club</title><ht:approx_traffic>500+</ht:approx_traffic>
<pubDate>Tue, 20 Oct 2026 08:50:00 +0000</pubDate>
<ht:news_item><ht:news_item_title>Springboks star back home</ht:news_item_title></ht:news_item></item>
<item><title>election poster</title><ht:approx_traffic>200+</ht:approx_traffic>
<pubDate>Tue, 20 Oct 2026 08:50:00 +0000</pubDate></item>
</channel></rss>"""

NEWS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Air Force flyover thrills the crowd at Loftus</title><link>https://x/1</link>
<pubDate>Tue, 20 Oct 2026 09:30:00 +0000</pubDate></item>
<item><title>Rugby community rallies around Lions after injury</title>
<pubDate>Tue, 20 Oct 2026 09:30:00 +0000</pubDate></item>
<item><title>What a shot: Clark joins the Nedbank Golf Challenge field</title>
<pubDate>Tue, 20 Oct 2026 07:00:00 +0000</pubDate></item>
<item><title>Old golf story from last week</title><pubDate>Tue, 13 Oct 2026 07:00:00 +0000</pubDate></item>
<item><title>Interest rates held</title><pubDate>Tue, 20 Oct 2026 07:00:00 +0000</pubDate></item>
</channel></rss>"""


def _items():
    return m.parse_feed(TRENDS, "Google Trends SA", "trends") + m.parse_feed(NEWS, "IOL", "news")


def test_parse_reads_traffic_context_and_time():
    rows = m.parse_feed(TRENDS, "Google Trends SA", "trends")
    assert rows[0]["traffic"] == "500+" and rows[0]["context"] == ["Springboks star back home"]
    assert rows[0]["published"].hour == 8
    assert m.parse_feed(b"not xml", "x", "news") == []


def test_live_keeps_angles_and_ranks_the_flyover_first():
    out = m.live(_items(), now=NOW)
    titles = [r["title"] for r in out["items"]]
    assert titles[0].startswith("Air Force flyover")
    assert any("Nedbank Golf Challenge" in t for t in titles)  # "what a shot" is golf, not violence
    assert not any("Interest rates" in t for t in titles)       # no angle
    assert not any("Old golf story" in t for t in titles)       # older than 72 hours
    assert out["items"][0]["act_today"] is True


def test_sensitive_stories_are_hidden_and_counted():
    out = m.live(_items(), now=NOW)
    titles = " ".join(r["title"] for r in out["items"])
    assert "election" not in titles and "rallies around" not in titles
    assert out["hidden_sensitive"] >= 1
    assert m.is_sensitive("Man shot dead outside stadium")
    assert not m.is_sensitive("Dead heat at the Masters, what a shot")


def test_upcoming_has_prepare_by_and_status():
    events = [
        {"date": "2026-10-31", "title": "Halloween", "lead_days": 7, "angle": "a"},
        {"date": "2026-10-23", "title": "Soon", "lead_days": 7, "angle": "b"},
        {"date": "2027-04-08", "end": "2027-04-11", "title": "Masters", "lead_days": 7},
        {"date": "2026-09-01", "title": "Past", "lead_days": 7},
    ]
    up = m.upcoming(events, today=dt.date(2026, 10, 20))
    assert [e["title"] for e in up] == ["Soon", "Halloween"]  # Masters beyond 60 days, Past dropped
    assert up[0]["status"] == "prepare now" and up[1]["prep_by"] == "2026-10-24" and up[1]["status"] == "coming"


def test_seed_calendar_loads_and_has_valid_dates():
    events = m.load_calendar()
    assert len(events) >= 15
    for e in events:
        dt.date.fromisoformat(e["date"])
        assert e["title"] and e.get("angle")


def test_build_survives_a_dead_feed():
    def get(url):
        if "trends" in url:
            raise OSError("down")
        return NEWS

    out = m.build(now=NOW, get=get, calendar=[])
    assert any("Google Trends" in e for e in out["errors"])
    assert out["live"] and out["feeds_read"] > 0
