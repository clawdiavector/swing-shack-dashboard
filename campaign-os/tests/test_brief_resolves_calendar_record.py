"""An approved calendar date (a campaign or moment put on the calendar) must
resolve for the Brief by the same key the Plan alert banner shows. Without this,
"Make a plan" died with "opportunity '...' not found" for Halloween 2026."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import campaign_brief as cb  # noqa: E402

HALLOWEEN_KEY = "swing-shack:cal-swing-shack-cam-1792132350-40e9cb87:2026-10-31"
HALLOWEEN = {
    "event_key": HALLOWEEN_KEY,
    "calendar_id": "cal-swing-shack-cam-1792132350-40e9cb87",
    "brand_id": "swing-shack",
    "title": "Halloween",
    "type": "campaign",
    "status": "approved",
    "event_start": "2026-10-31",
    "event_end": "2026-10-31",
    "source_origin": "operator",
}


def fake_mc(records):
    """The canonical list is empty here, as it was on live for this date."""
    return SimpleNamespace(
        canonical_records=lambda brand_id, status_filter=None: [],
        list_records=lambda brand_id, status_filter=None: list(records),
        latest_revisions=lambda rs: list(rs),
    )


class CalendarRecordResolve(unittest.TestCase):
    def resolve(self, key, records=(HALLOWEEN,)):
        with patch.object(cb, "_marketing_calendar_import", return_value=fake_mc(records)), \
                patch.object(cb, "_resolve_spine_opportunity", return_value={}):
            return cb._resolve_opportunity("swing-shack", key)

    def test_banner_key_resolves(self):
        opp = self.resolve(HALLOWEEN_KEY)
        self.assertEqual(opp["event_key"], HALLOWEEN_KEY)
        self.assertEqual(opp["date"], "2026-10-31")
        self.assertEqual(opp["source"], "calendar")

    def test_calendar_id_resolves(self):
        opp = self.resolve(HALLOWEEN["calendar_id"])
        self.assertEqual(opp["event_key"], HALLOWEEN_KEY)

    def test_watchlist_record_does_not_resolve(self):
        watch = dict(HALLOWEEN, status="watchlist")
        self.assertEqual(self.resolve(HALLOWEEN_KEY, records=[watch]), {})

    def test_unknown_key_still_not_found(self):
        self.assertEqual(self.resolve("swing-shack:nope:2026-10-31"), {})


if __name__ == "__main__":
    unittest.main()
