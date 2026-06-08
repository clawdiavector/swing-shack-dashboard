#!/usr/bin/env python3
"""Patch cockpit HTML: replace window.campaignData blob with fresh data from campaign-data.json"""
import json, re

HTML  = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/campaign-os/cockpit-operational.html'
DATA  = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/campaign-os/campaign-data.json'

with open(DATA) as f:
    d = json.load(f)

with open(HTML) as f:
    h = f.read()

# Find and replace the window.campaignData = {...} block
# It starts at "window.campaignData = {" and ends at the matching "};"
start = h.index('window.campaignData = ')
# Find the end: count braces from the first {
depth = 0
end = start
for i, ch in enumerate(h[start:], start):
    if ch == '{': depth += 1
    elif ch == '}':
        depth -= 1
        if depth == 0:
            end = i + 1
            break

new_data = 'window.campaignData = ' + json.dumps(d, separators=(',', ':'))

new_h = h[:start] + new_data + h[end:]
print(f'Original: {len(h):,} bytes → New: {len(new_h):,} bytes')

with open(HTML, 'w') as f:
    f.write(new_h)

# Verify
checks = {
    'Takomo Winter campaign': 'takomo-winter-iron-upgrade-mq0udo38' in new_h,
    'DNA tone': 'Authentic, informative, and persuasive' in new_h,
    'visualDirection mood': 'Premium, focused, performance-driven' in new_h,
    'pipeline currentAgent Scout': "currentAgent: 'Scout'" in new_h,
    'pipeline step 1': 'currentStep: 1' in new_h,
    'brief.audience': 'Golfers considering new irons' in new_h,
    'strategy.primaryOffer': 'Free Assessment' in new_h,
    'All 3 pillars': new_h.count('"id": "p') == 3,
    'campaignSource Manual': "type: 'Manual'" in new_h,
}
all_pass = all(checks.values())
for k, v in checks.items():
    print(f'  {"PASS" if v else "FAIL"} {k}')
print('\nPatched HTML written to:', HTML)
print('Result:', 'ALL PASS' if all_pass else 'SOME FAILURES')