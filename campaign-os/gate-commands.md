# cwd: /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-brand-p1a-registry/campaign-os

## Build / test / lint
pytest tests/ -k "brand_lanes or jobs_status or connected_accounts" -v
python3 -c "from _lib.jobs.registry import JOBS; from _lib.jobs.brand_lanes import validate_brands_registry, clear_brands_cache; clear_brands_cache(); validate_brands_registry(); assert len(JOBS)==25"
python3 -c "import os; os.environ['BUNDLED_DATA_DIR']='../data'; os.environ['DATA_DIR']='/tmp/cos-gate'; import app; assert len(app._JOBS_REGISTRY)==28"
