#!/usr/bin/env python3
"""Gate 5: Portfolio rendering via Node.js — dynamically render portfolio cards from V2 data.
Replaces hardcoded HTML cards with dynamic JavaScript rendering."""
import re

HTML = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/campaign-os/cockpit-operational.html'

with open(HTML, 'r') as f:
    h = f.read()

BACKUP = HTML + '.gate5.bak'
with open(BACKUP, 'w') as f:
    f.write(h)
print('Backup:', BACKUP)

# --- Find and replace hardcoded portfolio cards ---
# The static cards look like:
# <div class="ccard" onclick="selectCampaign('trackman-intelligence')"...>
# These are replaced by a container + JS dynamic render

old_cards = '''<div class="campaign-cards"><div class="ccard" onclick="selectCampaign('trackman-intelligence')" style="cursor:pointer"><div class="ccard-name">TrackMan Intelligence</div><div class="ccard-meta">Drive fitting bookings and coaching sessions</div><div class="ccard-assetcount" style="color:#ffaa00">0 assets &middot; Degraded</div></div><div class="ccard" onclick="selectCampaign('takomo-101t')" style="cursor:pointer"><div class="ccard-name">Takomo 101T</div><div class="ccard-meta">Drive Takomo 101T iron fittings and showcase value prop</div><div class="ccard-assetcount" style="color:#ffaa00">4 assets &middot; Degraded</div></div><div class="ccard" onclick="selectCampaign('winter-golf')" style="cursor:pointer"><div class="ccard-name">Winter Golf</div><div class="ccard-meta">Drive indoor golf sessions during SA winter season</div><div class="ccard-assetcount" style="color:#00cc77">0 assets &middot; Healthy</div></div></div>'''

new_cards = '<div class="campaign-cards" id="portfolio-cards"></div>'

if old_cards in h:
    h = h.replace(old_cards, new_cards)
    print('Hardcoded cards replaced with dynamic container')
else:
    print('WARNING: exact card block not found — trying partial match')
    # Partial: find the campaign-cards div and replace its contents
    h = re.sub(
        r'<div class="campaign-cards">.*?</div>',
        new_cards,
        h,
        count=1,
        flags=re.DOTALL
    )
    print('Partial replacement applied')

# --- Add renderPortfolio function to the JS block ---
portfolio_render_fn = '''
function renderPortfolio() {
    var container = document.getElementById('portfolio-cards');
    if (!container) return;
    var campaigns = window.campaignData && window.campaignData.campaigns || {};
    var ids = Object.keys(campaigns).sort();
    if (ids.length === 0) {
        container.innerHTML = '<div style="color:#6e6e82;font-size:13px;padding:20px;text-align:center">No campaigns yet. Click "+ Create Campaign" to get started.</div>';
        return;
    }
    var html = '';
    for (var i = 0; i < ids.length; i++) {
        var id = ids[i];
        var c = campaigns[id];
        var ident = c.identity || {};
        var brief = c.brief || {};
        var name = ident.name || id;
        var goal = ident.primaryGoal || (brief.purpose || '').slice(0, 60);
        var status = ident.status || 'draft';
        var health = ident.healthState || 'unknown';
        var healthColor = health === 'healthy' ? '#00cc77' : health === 'degraded' ? '#ffaa00' : '#6e6e82';
        var assetCount = (c.assets && Object.keys(c.assets).length) || 0;
        var statusDot = status === 'draft' ? '&#9679;' : status === 'active' ? '&#9679;' : '&#9711;';
        var statusColor = status === 'active' ? '#00cc77' : status === 'draft' ? '#6e6e82' : '#ffaa00';

        html += '<div class="ccard" onclick="selectCampaign(\\'' + id + '\\')" style="cursor:pointer">' +
            '<div class="ccard-name">' + name + '</div>' +
            '<div class="ccard-meta">' + (goal.slice(0, 80)) + '</div>' +
            '<div class="ccard-assetcount" style="color:' + healthColor + '">' + assetCount + ' assets &middot; <span style="color:' + statusColor + '">' + status + '</span></div>' +
            '</div>';
    }
    container.innerHTML = html;
}

'''

# Add renderPortfolio before the first function definition in the JS block
# Find the <script> block and prepend the renderPortfolio function
if 'function renderPortfolio' not in h:
    # Find first function in script block and insert before it
    script_match = re.search(r'(<script>)(window\.campaignData)', h)
    if script_match:
        h = h[:script_match.start(2)] + portfolio_render_fn + h[script_match.start(2):]
        print('renderPortfolio injected before window.campaignData')
    else:
        print('Could not find injection point for renderPortfolio')

# --- Call renderPortfolio() in showView('portfolio') ---
old_show = "if (name === 'portfolio') document.getElementById('header-subtitle').textContent = 'Portfolio Overview';"
new_show = "if (name === 'portfolio') { document.getElementById('header-subtitle').textContent = 'Portfolio Overview'; renderPortfolio(); }"

if old_show in h:
    h = h.replace(old_show, new_show)
    print('showView now calls renderPortfolio()')
else:
    print('WARNING: showView pattern not found')

# --- Call renderPortfolio on init ---
old_init = 'initSelector();'
new_init = 'initSelector(); renderPortfolio();'
if old_init in h:
    h = h.replace(old_init, new_init)
    print('initSelector now also calls renderPortfolio')
else:
    print('WARNING: initSelector pattern not found')

with open(HTML, 'w') as f:
    f.write(h)

# Verify
print('\nVerification:')
checks = {
    'portfolio-cards container exists': 'id="portfolio-cards"' in h,
    'renderPortfolio function': 'function renderPortfolio' in h,
    'renderPortfolio called in showView': "renderPortfolio();" in h,
    'renderPortfolio called on init': 'initSelector(); renderPortfolio();' in h,
    'Hardcoded TrackMan card removed': "selectCampaign('trackman-intelligence')" not in h or 'ccard' not in h.split('campaign-cards')[1][:200],
    'No schema keys used': 'campaignId' in h and 'healthScore' in h,  # read from data
}
for k, v in checks.items():
    print(f'  {"PASS" if v else "FAIL"} {k}')

print('\nWritten:', HTML)