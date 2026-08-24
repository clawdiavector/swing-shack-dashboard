#!/usr/bin/env python3
"""
weekly_strategy_brief.py — Cron entry point.

Runs Monday 06:00 SAST (= 04:00 UTC). Generates the Monday brief,
prints it to stdout (the cron harness captures & delivers it).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent.parent / "campaign-os" / "_lib"))

from weekly_brief import compose_monday_brief, render_brief_markdown

def main():
    brand = os.environ.get("STRATEGY_BRAND", "swing-shack")
    brief = compose_monday_brief(brand, snapshot_first=True)
    print(render_brief_markdown(brief))

if __name__ == "__main__":
    main()