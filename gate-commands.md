# cwd: /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-brand-p2b-cron

## Build / test / lint
python3 scripts/check_lib_modules.py
pytest campaign-os/tests/test_brand_lanes_p2b.py -q
pytest self-tests/test_cos_job_summary_self.py -q
pytest campaign-os/tests/test_brand_lanes_p2a.py campaign-os/tests/test_p1b_brand_ui.py -q
