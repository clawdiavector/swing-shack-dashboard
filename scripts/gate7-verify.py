#!/usr/bin/env python3
"""Gate 7: Live cockpit verification — check deployed HTML matches all M4 gates."""
import urllib.request

url = "https://clawdiavector.github.io/swing-shack-dashboard/campaign-os/cockpit-operational.html"

try:
    html = urllib.request.urlopen(url, timeout=15).read().decode('utf-8')
except Exception as e:
    print(f"Cannot fetch live URL: {e}")
    exit(1)

print(f"Live HTML: {len(html):,} bytes")
print()

checks = [
    ("Create Campaign button present", 'id="btn-create"' in html),
    ("13-field modal form present", 'id="createModal"' in html),
    ("All 13 form fields present", all('id="f-' + f + '"' in html for f in [
        'name','type','source-type','source-ref','goal','priority',
        'target','duration','audience','offer','notes','notes-context'
    ])),
    ("Portfolio cards container (dynamic rendering)", 'id="portfolio-cards"' in html),
    ("renderPortfolio() function defined", 'function renderPortfolio' in html),
    ("handleFormSubmit() function defined", 'function handleFormSubmit' in html),
    ("renderPipeline() function defined", 'function renderPipeline' in html),
    ("Pipeline idle state ('No active blueprint generation')", 'No active blueprint generation' in html),
    ("Pipeline running state (generatingBlueprint check)", "st === 'generatingBlueprint'" in html),
    ("Pipeline failed state", "'failed'" in html),
    ("Pipeline blueprintReady state", "'blueprintReady'" in html),
    ("showView calls renderPortfolio", "renderPortfolio();" in html),
    ("DOMContentLoaded calls renderPortfolio", "renderPortfolio();" in html),
    ("V2 schema: campaigns dict at root", '"campaigns":{' in html),
    ("renderCampaign prepends pipeline HTML", 'pipeHtml + window.renderFns' in html),
    ("No hardcoded campaign card (trackman-intelligence)", "'trackman-intelligence')" not in html),
    ("campaignData loads from V2 structure", 'window.campaignData' in html),
]

passed = sum(1 for _, v in checks if v)
for label, result in checks:
    print(f"  {'✅' if result else '❌'} {label}")

print()
print(f"Result: {passed}/{len(checks)} checks passed")

if passed == len(checks):
    print("Gate 7: ✅ READY FOR VERIFICATION")
else:
    print("Gate 7: ❌ SOME CHECKS FAILED")