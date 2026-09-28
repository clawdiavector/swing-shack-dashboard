# cwd: /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-compose-gate-gen-template/campaign-os

## Build / test / lint

pytest tests/jobs/test_compose_gate_and_recipe.py tests/jobs/test_draft_assets_serial_complete.py -q
pytest tests/jobs/test_archetype_selection.py -q
grep -n enqueue_compose_post_for_moment _lib/jobs/layer5/krea_poll_draft_images.py

## Web

cd ../web && npm test -- --run src/lib/api.inbox.test.ts
