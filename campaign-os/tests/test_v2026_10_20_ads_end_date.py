"""Decision date on an ad set: preview, apply, undo. Meta is faked."""
import datetime as dt

import pytest
from itsdangerous import URLSafeTimedSerializer

from _lib import ads_actions as aa

ACCT = "act_111"
TODAY = dt.date(2026, 10, 20)


class FakeMeta:
    def __init__(self, end_time=None, account="111"):
        self.adset = {"id": "777", "name": "Putter Traffic", "effective_status": "ACTIVE", "end_time": end_time}
        self.ad = {"id": "555", "name": "Putter ad", "account_id": account}
        self.posts = []

    def __call__(self, method, path, token, params=None):
        if method == "GET":
            return dict(self.ad, adset=dict(self.adset), adset_id="777")
        self.posts.append((path, dict(params)))
        self.adset["end_time"] = None if params["end_time"] == "0" else params["end_time"]
        return {"success": True}


class Store:
    def __init__(self):
        self.data = {}

    def read(self, rel):
        return self.data.get(rel)

    def write(self, rel, obj):
        self.data[rel] = obj
        return True


@pytest.fixture
def signer():
    return URLSafeTimedSerializer("s3cret", salt=aa.TICKET_SALT)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "1")


def _preview(meta, signer, end="2026-11-03"):
    return aa.preview_end_date("stick", "555", end, graph=meta, token="t", account_id=ACCT,
                               signer=signer, today=TODAY)


def test_preview_changes_nothing_and_names_the_ad_set(signer):
    meta = FakeMeta()
    p = _preview(meta, signer)
    assert p["adset_name"] == "Putter Traffic" and p["will_set"] == "2026-11-03T23:59:00+02:00"
    assert meta.posts == []


@pytest.mark.parametrize("end", ["2026-10-20", "2026-10-01", "nonsense", "2027-03-01"])
def test_preview_refuses_bad_dates(signer, end):
    with pytest.raises(aa.ActionRefused):
        _preview(FakeMeta(), signer, end)


def test_preview_refuses_when_there_is_already_an_end_date_or_wrong_account(signer):
    with pytest.raises(aa.ActionRefused):
        _preview(FakeMeta(end_time="2026-12-01T00:00:00+0200"), signer)
    with pytest.raises(aa.ActionRefused):
        _preview(FakeMeta(account="999"), signer)


def test_apply_off_by_default(signer, monkeypatch):
    monkeypatch.delenv("ADS_WRITES_ENABLED", raising=False)
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    with pytest.raises(aa.ActionRefused) as e:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                 read=store.read, write=store.write)
    assert e.value.status == 403 and meta.posts == []


def test_apply_sets_the_ad_set_end_date_logs_and_undo_clears_it(signer, on):
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    entry = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                     read=store.read, write=store.write)
    assert meta.posts == [("777", {"end_time": "2026-11-03T23:59:00+02:00"})]
    assert entry["kind"] == "set_end_date" and entry["before"] is None
    done = aa.undo("stick", entry["id"], graph=meta, token="t", account_id=ACCT,
                   read=store.read, write=store.write)
    assert meta.adset["end_time"] is None and done["undone_at"]
    assert meta.posts[-1] == ("777", {"end_time": "0"})


def test_apply_refuses_if_an_end_date_appeared_since_preview(signer, on):
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    meta.adset["end_time"] = "2026-12-01T00:00:00+0200"
    with pytest.raises(aa.ActionRefused) as e:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                 read=store.read, write=store.write)
    assert e.value.status == 409 and meta.posts == []


def test_undo_refuses_if_the_date_was_changed_elsewhere(signer, on):
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    entry = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                     read=store.read, write=store.write)
    meta.adset["end_time"] = "2026-12-24T23:59:00+02:00"
    with pytest.raises(aa.ActionRefused) as e:
        aa.undo("stick", entry["id"], graph=meta, token="t", account_id=ACCT,
                read=store.read, write=store.write)
    assert e.value.status == 409
