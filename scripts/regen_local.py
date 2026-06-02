#!/usr/bin/env python3
"""Regenerate cockpit from local campaign-data.json"""
import json, pathlib, sys

src = pathlib.Path('campaign-os/campaign-data.json').resolve()
dst = pathlib.Path('campaign-os/cockpit-operational.html').resolve()

sys.path.insert(0, str(src.parent.parent / 'scripts'))
import regenerate_cockpit as rc

with open(src) as f:
    D = json.load(f)

rc.main(D, dst)
print('OK Written:', dst)
print('Size:', dst.stat().st_size, 'bytes')