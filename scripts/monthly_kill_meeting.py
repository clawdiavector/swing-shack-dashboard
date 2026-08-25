#!/usr/bin/env python3
"""
monthly_kill_meeting.py — Monthly strategy clutter + kill-meeting generator.

Runs first Monday of each month at 06:00 SAST (04:00 UTC).
Surfaces:
  - STRATEGY CLUTTER REPORT (counts + recommendations)
  - WHAT SHOULD WE STOP DOING? (weakest items for KILL/UPDATE/PAUSE/RETIRE)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent.parent / "campaign-os" / "_lib"))

from audit import run_audit, kill_meeting, render_audit_markdown, AUDIT_STATUSES


def main():
    brand = os.environ.get("STRATEGY_BRAND", "swing-shack")
    audit = run_audit(brand)
    meeting = kill_meeting(brand)

    md = []
    md.append("## Monthly strategy check-up + clean-up")
    md.append("")
    md.append(render_audit_markdown(audit, "all"))
    md.append("")
    md.append(f"### {meeting['title']}")
    md.append(f"_{meeting['subtitle']}_")
    md.append("")

    if not meeting["candidates"]:
        md.append("_Nothing to surface. Strategy is healthy._")
    else:
        for i, c in enumerate(meeting["candidates"], 1):
            md.append(f"{i}. **{c['title']}** ({c['item_type']})")
            md.append(f"   - Verdict: {c['audit_status'].upper()} · Score: {c['audit_score']}/100")
            md.append(f"   - Why flagged: {c['why_surface']}")
            md.append(f"   - Reason for existence: {c['reason_for_existence'][:160]}")
            md.append(f"   - Next action: {c['next_action']}")
            if c.get("flags"):
                for f in c["flags"][:2]:
                    md.append(f"   - Flag: {f.get('code', '')} — {f.get('detail', '')[:120]}")
            md.append("")

    print("\n".join(md))


if __name__ == "__main__":
    main()