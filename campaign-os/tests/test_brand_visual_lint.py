"""Brand-visual colour lint — bible prose must match palette/brand.json."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT = REPO_ROOT / "scripts" / "lint_brand_visual.py"


def test_brand_visual_lint_all_brands_pass():
    proc = subprocess.run(
        [sys.executable, str(LINT), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
