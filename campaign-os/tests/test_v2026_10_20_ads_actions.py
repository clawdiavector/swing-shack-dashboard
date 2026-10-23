"""One-click pause: preview, apply, undo. Meta is faked; nothing reaches the network."""
import pytest
from itsdangerous import URLSafeTimedSerializer

from _lib import ads_actions as aa

ACCT = "act_111"


class FakeMeta:
    def __init__(self, status="ACTIVE", account="111", ad_id="555"):
        self.ad = {"id": ad_id, "name": "Putter ad", "status": status,
                   "effective_status": status, "account_id": account}
        self.posts = []

    def __call__(self, method, path, token, params=None):
        if method == "GET":
            return dict(self.ad)
        self.posts.append((path, dict(params)))
        self.ad["status"] = params["status"]
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


def _preview(meta, signer, ad_id="555"):
    return aa.preview("stick", ad_id, graph=meta, token="t", account_id=ACCT, signer=signer)


def test_preview_changes_nothing(signer):
    meta = FakeMeta()
    p = _preview(meta, signer)
    assert p["will_set"] == "PAUSED" and p["status_now"] == "ACTIVE"
    assert meta.posts == []


def test_preview_refuses_other_account_and_bad_id_and_paused(signer):
    with pytest.raises(aa.ActionRefused):
        _preview(FakeMeta(account="999"), signer)
    with pytest.raises(aa.ActionRefused):
        _preview(FakeMeta(), signer, ad_id="55; DROP")
    with pytest.raises(aa.ActionRefused):
        _preview(FakeMeta(status="PAUSED"), signer)


def test_apply_is_off_by_default(signer, monkeypatch):
    monkeypatch.delenv("ADS_WRITES_ENABLED", raising=False)
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    with pytest.raises(aa.ActionRefused) as e:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                 read=store.read, write=store.write)
    assert e.value.status == 403 and meta.posts == []


def test_apply_pauses_logs_and_undo_restores(signer, on):
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    entry = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                     read=store.read, write=store.write)
    assert meta.ad["status"] == "PAUSED" and meta.posts == [("555", {"status": "PAUSED"})]
    assert entry["before"] == "ACTIVE" and len(aa.load_log("stick", store.read)) == 1
    done = aa.undo("stick", entry["id"], graph=meta, token="t", account_id=ACCT,
                   read=store.read, write=store.write)
    assert meta.ad["status"] == "ACTIVE" and done["undone_at"]
    with pytest.raises(aa.ActionRefused):  # cannot undo twice
        aa.undo("stick", entry["id"], graph=meta, token="t", account_id=ACCT,
                read=store.read, write=store.write)


def test_apply_refuses_when_the_ad_moved_since_preview(signer, on):
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    meta.ad["status"] = "PAUSED"  # someone paused it in Ads Manager meanwhile
    with pytest.raises(aa.ActionRefused) as e:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                 read=store.read, write=store.write)
    assert e.value.status == 409 and meta.posts == []


def test_ticket_is_bound_to_brand_and_cannot_be_forged(signer, on):
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    with pytest.raises(aa.ActionRefused):
        aa.apply("swing-shack", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                 read=store.read, write=store.write)
    with pytest.raises(aa.ActionRefused):
        aa.apply("stick", t + "x", graph=meta, token="t", account_id=ACCT, signer=signer,
                 read=store.read, write=store.write)
    other = URLSafeTimedSerializer("s3cret")  # a session-style token, different salt
    with pytest.raises(aa.ActionRefused):
        aa.apply("stick", other.dumps({"b": "stick", "ad": "555", "before": "ACTIVE"}), graph=meta,
                 token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert meta.posts == []


def test_undo_refuses_if_changed_elsewhere(signer, on):
    meta, store = FakeMeta(), Store()
    t = _preview(meta, signer)["ticket"]
    entry = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer,
                     read=store.read, write=store.write)
    meta.ad["status"] = "ACTIVE"  # someone resumed it in Ads Manager
    with pytest.raises(aa.ActionRefused) as e:
        aa.undo("stick", entry["id"], graph=meta, token="t", account_id=ACCT,
                read=store.read, write=store.write)
    assert e.value.status == 409
