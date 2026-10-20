"""_ga4_run_report must build a request, including the page filter (it failed on a bad import)."""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_run_report_builds_request_with_page_filter():
    os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cos-ga4-"))
    import app as m

    fake_resp = mock.Mock(rows=[])
    fake_client = mock.Mock()
    fake_client.run_report.return_value = fake_resp
    cred = Path(tempfile.mkdtemp()) / "c.json"
    cred.write_text("{}")
    creds = {"property_id": "123", "credentials_path": str(cred)}
    with mock.patch("google.analytics.data_v1beta.BetaAnalyticsDataClient.from_service_account_file",
                    return_value=fake_client):
        status, body = m._ga4_run_report(creds, ["sessionSource"], ["sessions"],
                                         [{"start_date": "7daysAgo", "end_date": "today"}],
                                         page_filter="/fitting")
    assert body["ok"] is True, body
    req = fake_client.run_report.call_args[0][0]
    assert req.dimension_filter.filter.field_name == "pagePath"
    assert req.dimension_filter.filter.string_filter.value == "/fitting"
