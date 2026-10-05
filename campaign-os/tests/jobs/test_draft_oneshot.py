"""draft_oneshot cook path — provider always mocked."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import _purge_modules, _seed_brands, _seed_queue_row  # noqa: E402

PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture()
def oneshot_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(CAMPAIGN_OS.parent / "data"))
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "10.00")
    monkeypatch.setenv("CAMPAIGN_OS_MAX_IMAGES_PER_DAY", "2")
    _purge_modules()
    _seed_brands(tmp_path, brand="stick", campaign_id="camp-stick")
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "calendar_id": "cal-os",
        "event_key": "cal-os",
        "status": "approved",
        "title": "Hello world",
        "headline": "Hit more greens",
        "cta": "Book a fitting",
        "post_type": "fitting_headline",
        "event_start": "2026-10-01",
        "type": "content",
        "render_mode": "oneshot",
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    item_id = "calendar_candidate:stick:cal-os"
    return tmp_path, item_id


def test_cook_writes_draft_mocked(oneshot_env):
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_oneshot", item_id=item_id, brand="stick")
    png_path = tmp_path / "out.png"
    meta_path = tmp_path / "out.meta.json"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(PNG_1x1)
    meta_path.write_text(json.dumps({"prompt_used": "wire", "model": "m", "cost_usd": 0.05}), encoding="utf-8")

    mock_gen = MagicMock()
    mock_gen.model = "ideogram/ideogram-3"
    mock_gen.provider = "krea"
    mock_gen.bytes = PNG_1x1
    mock_gen.saved_path = str(png_path)
    mock_gen.saved_sidecar_path = str(meta_path)
    mock_gen.prompt_used = 'Render "Hello world"'
    mock_gen.provider_job_id = None
    mock_gen.cost_usd = 0.05
    mock_gen.cost_source = "estimate"

    pick_calls = []

    def spy_pick(req, **kw):
        pick_calls.append(req)
        return {"model": "ideogram/ideogram-3", "provider": "krea", "reason": "test"}

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen) as gen_mock, patch(
        "_lib.creative_director.pick_model", side_effect=spy_pick
    ), patch("_lib.brand_overlay.overlay_logo_only", side_effect=lambda b, *a, **k: b):
        draft_assets.run()

    gen_mock.assert_called_once()
    assert gen_mock.call_args.kwargs["size"] == "1024x1280"
    assert gen_mock.call_args.kwargs.get("background_plate") is True
    assert pick_calls and pick_calls[0].get("typography") is True
    sidecars = list((tmp_path / "draft-assets").glob("draft-*.json"))
    assert sidecars
    sidecar = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert sidecar.get("action") == "draft_oneshot"
    assert sidecar.get("literal_text") == "Hit more greens\nBook a fitting"
    assert sidecar.get("image_size") == "1024x1280"


def test_krea_submit_sets_waiting(oneshot_env):
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5 import draft_assets

    _seed_queue_row(tmp_path, action="draft_oneshot", item_id=item_id, brand="stick")
    mock_gen = MagicMock()
    mock_gen.model = "ideogram/ideogram-3"
    mock_gen.provider = "krea"
    mock_gen.bytes = b""
    mock_gen.provider_job_id = "krea-job-99"
    mock_gen.saved_path = None
    mock_gen.saved_sidecar_path = None

    with patch("_lib.image_gen_router.generate_image_with_persistence", return_value=mock_gen), patch(
        "_lib.creative_director.pick_model",
        return_value={"model": "ideogram/ideogram-3", "provider": "krea", "reason": "test"},
    ):
        draft_assets.run(brand="stick")

    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    assert queue["rows"][0]["status"] == "waiting"
    jobs = json.loads((tmp_path / "draft-assets" / "_image-jobs.json").read_text(encoding="utf-8"))
    assert jobs["jobs"][item_id]["job_id"] == "krea-job-99"


def test_krea_poll_finalizes_oneshot(oneshot_env):
    tmp_path, item_id = oneshot_env
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    (cal_dir / "stick.jsonl").write_text(
        json.dumps(
            {
                "calendar_id": "cal-os",
                "event_key": "cal-os",
                "status": "approved",
                "title": "Hello world",
                "headline": "Hit more greens",
                "cta": "Book a fitting",
                "post_type": "fitting_headline",
                "event_start": "2026-10-01",
                "type": "content",
                "render_mode": "oneshot",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    from _lib.jobs.layer1._io import utc_now_iso

    jobs_doc = {
        "schema": "campaign-os/image-jobs/v1",
        "generated_at": utc_now_iso(),
        "jobs": {
            item_id: {
                "job_id": "j-os",
                "brand": "stick",
                "size": "1024x1280",
                "est_usd": 0.04,
                "submitted_at": utc_now_iso(),
                "last_status": "running",
                "polls": 0,
                "retry_count": 0,
            }
        },
    }
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "draft-assets" / "_image-jobs.json").write_text(json.dumps(jobs_doc), encoding="utf-8")
    queue = {
        "schema": "campaign-os/agent-queue/v1",
        "generated_at": "2026-09-25T00:00:00Z",
        "rows": [
            {
                "id": "wait-os",
                "layer": "L5",
                "agent": "cos-image",
                "brand": "stick",
                "action": "draft_oneshot",
                "payload_ref": f"inbox/{item_id}",
                "status": "waiting",
            }
        ],
    }
    (tmp_path / "agent-queue.json").write_text(json.dumps(queue), encoding="utf-8")
    png = tmp_path / "draft-assets" / "images" / "stick" / "images" / "krea-stick-j-os.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(PNG_1x1)

    from _lib.jobs.layer5 import krea_poll_draft_images

    with patch("_lib.brand_overlay.overlay_logo_only", side_effect=lambda b, *a, **k: b):
        krea_poll_draft_images.run(brand="stick")

    sidecars = list((tmp_path / "draft-assets").glob("draft-*.json"))
    assert sidecars
    sidecar = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert sidecar.get("action") == "draft_oneshot"
    assert sidecar.get("literal_text") == "Hit more greens\nBook a fitting"
    rows = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["status"] == "done"


def _write_calendar(tmp_path, record: dict) -> None:
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    (cal_dir / "stick.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")


_BASE_RECORD = {
    "calendar_id": "cal-os",
    "event_key": "cal-os",
    "status": "approved",
    "title": "Coaching promo — one-shot",
    "post_type": "coaching_promo",
    "event_start": "2026-10-01",
    "type": "content",
    "render_mode": "oneshot",
}


def test_card_with_only_a_title_refuses_instead_of_painting_the_label(oneshot_env):
    """The 2 Oct review card rendered its own planning label. Never again."""
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5 import draft_assets

    _write_calendar(tmp_path, dict(_BASE_RECORD))
    _seed_queue_row(tmp_path, action="draft_oneshot", item_id=item_id, brand="stick")

    with patch("_lib.image_gen_router.generate_image_with_persistence") as gen_mock:
        draft_assets.run(brand="stick")

    gen_mock.assert_not_called()
    row = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))["rows"][0]
    assert row["status"] == "error"
    assert row["note"].startswith("copy:")
    assert "headline" in row["note"]


def test_headline_equal_to_the_card_title_is_refused(oneshot_env):
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5.draft_oneshot import OneshotCopyMissing, oneshot_copy_for_card

    record = dict(_BASE_RECORD, headline="Coaching promo — one-shot")
    with pytest.raises(OneshotCopyMissing) as exc:
        oneshot_copy_for_card("stick", item_id, record)
    assert "card label" in str(exc.value)


def test_falls_back_to_the_approved_poster_copy_from_the_caption_draft(oneshot_env):
    """compose_headline/compose_cta are what the template path overlays."""
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5.draft_oneshot import oneshot_copy_for_card

    drafts = tmp_path / "draft-assets"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "draft-caption1.json").write_text(
        json.dumps(
            {
                "asset_id": "draft-caption1",
                "action": "draft_caption",
                "source_inbox_item_id": item_id,
                "created_at": "2026-10-04T00:00:00Z",
                "compose_headline": "Hit more greens",
                "compose_cta": "Book a fitting",
            }
        ),
        encoding="utf-8",
    )

    copy = oneshot_copy_for_card("stick", item_id, dict(_BASE_RECORD))
    assert copy.headline == "Hit more greens"
    assert copy.kicker == "Book a fitting"
    assert copy.source == "caption_draft:compose_headline"


def test_default_model_is_ideogram_4_with_a_named_fallback(oneshot_env):
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5 import draft_oneshot

    _write_calendar(tmp_path, dict(_BASE_RECORD, headline="Hit more greens"))
    bundle, err = draft_oneshot._prepare_oneshot_bundle("stick", item_id)
    assert err is None and bundle is not None
    assert bundle.routing["model"] == draft_oneshot.ONESHOT_DEFAULT_MODEL == "ideogram/ideogram-4"
    assert bundle.routing["provider"] == "krea"
    assert draft_oneshot._ONESHOT_FALLBACK_MODEL in bundle.routing["reason"]
    assert bundle.art.treatment == "photo"
    assert bundle.art.scene_source == "recipe:coaching_promo"


def test_operator_override_still_wins_and_recraft_v4_is_selectable(oneshot_env):
    tmp_path, item_id = oneshot_env
    from _lib.jobs.layer5 import draft_oneshot

    _write_calendar(
        tmp_path,
        dict(
            _BASE_RECORD,
            headline="Range balls.",
            cta="The lie you keep telling yourself",
            post_type="humour_card",
            oneshot_model="recraft/recraft-v4",
        ),
    )
    bundle, err = draft_oneshot._prepare_oneshot_bundle("stick", item_id)
    assert err is None and bundle is not None
    assert bundle.routing["model"] == "recraft/recraft-v4"
    assert bundle.art.treatment == "collage"


def test_krea_rejecting_the_model_id_falls_back_once(oneshot_env):
    tmp_path, item_id = oneshot_env
    from _lib.image_gen_router import ImageGenUpstreamError
    from _lib.jobs.layer5 import draft_assets, draft_oneshot

    _write_calendar(tmp_path, dict(_BASE_RECORD, headline="Hit more greens"))
    _seed_queue_row(tmp_path, action="draft_oneshot", item_id=item_id, brand="stick")

    png_path = tmp_path / "out.png"
    png_path.write_bytes(PNG_1x1)
    ok = MagicMock()
    ok.model = draft_oneshot._ONESHOT_FALLBACK_MODEL
    ok.provider = "krea"
    ok.bytes = PNG_1x1
    ok.saved_path = str(png_path)
    ok.saved_sidecar_path = None
    ok.prompt_used = "wire"
    ok.provider_job_id = None
    ok.cost_usd = 0.05
    ok.cost_source = "estimate"

    calls: list[str] = []

    def flaky(**kwargs):
        calls.append(str(kwargs.get("model")))
        if len(calls) == 1:
            raise ImageGenUpstreamError("Krea error (400): Unsupported image model")
        return ok

    with patch("_lib.image_gen_router.generate_image_with_persistence", side_effect=flaky), patch(
        "_lib.brand_overlay.overlay_logo_only", side_effect=lambda b, *a, **k: b
    ):
        draft_assets.run(brand="stick")

    assert calls == ["ideogram/ideogram-4", draft_oneshot._ONESHOT_FALLBACK_MODEL]
    sidecars = list((tmp_path / "draft-assets").glob("draft-*.json"))
    assert sidecars
    sidecar = json.loads(sidecars[0].read_text(encoding="utf-8"))
    routing = sidecar["model_routing"]["pick_model"]
    assert routing["fallback_from"] == "ideogram/ideogram-4"
