"""Weekly report wording: negatives read as -R891, chats and leads only on the ads they belong to."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import weekly_report_v3 as wr  # noqa: E402


def test_negative_money_reads_as_minus_rand():
    assert wr._money0(-891.4) == "-R891"
    assert wr._money0(2391.2) == "R2,391"
    assert wr._money0(-0.2) == "R-0" or wr._money0(-0.2) == "R0"
    assert wr._money0(None) == "—"


def _row(dest, **perf):
    base = {"leads": 0, "messages": 0, "cost_per_lead": None, "cost_per_message": None, "cost_per_session": None,
            "engaged_pct": None, "key_events": None}
    base.update(perf)
    return {"destination": dest, "spend": 100.0, "ga_sessions": 0, "perf": base}


def test_a_website_ads_stray_chat_is_not_called_its_result():
    row = _row("WEBSITE", messages=1, cost_per_message=100.0, cost_per_session=2.0, engaged_pct=30.0, key_events=0)
    row["ga_sessions"] = 50
    bits = " · ".join(wr._ad_result_bits(row))
    assert "chat" not in bits and "50 visits at R2" in bits


def test_lead_and_message_ads_name_their_results_with_the_right_plural():
    assert "1 lead at R100" in " · ".join(wr._ad_result_bits(_row("LEAD_FORM", leads=1, cost_per_lead=100.0)))
    assert "8 leads at R12" in " · ".join(wr._ad_result_bits(_row("LEAD_FORM", leads=8, cost_per_lead=12.0)))
    assert "1 chat at R100" in " · ".join(wr._ad_result_bits(_row("MESSAGING", messages=1, cost_per_message=100.0)))


def test_an_ad_with_no_visits_says_so_instead_of_going_quiet():
    assert "no website visits recorded" in " · ".join(wr._ad_result_bits(_row("UNKNOWN")))
    assert "no website visits recorded" not in " · ".join(wr._ad_result_bits(_row("LEAD_FORM", leads=3, cost_per_lead=1.0)))
