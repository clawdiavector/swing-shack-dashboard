#!/usr/bin/env python3
"""Gate 2: Add Create Campaign button + modal form with all 13 fields to cockpit HTML.
No data writes. No pipeline. No campaign creation.
"""
import re

SRC = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/campaign-os/cockpit-operational.html'
BACKUP = SRC + '.gate2.bak'

with open(SRC, 'r') as f:
    html = f.read()

# Backup
with open(BACKUP, 'w') as f:
    f.write(html)
print(f'Backup saved: {BACKUP}')

# --- 1. ADD CREATE CAMPAIGN BUTTON to header ---
button_html = '<button class="create-btn" id="btn-create" onclick="openCreateModal()">+ Create Campaign</button>'
# Find the view-toggle div and insert button before it
if 'id="btn-create"' in html:
    print('Button already exists — skipping')
else:
    # Insert before view-toggle
    html = html.replace(
        '<div class="view-toggle">',
        button_html + '\n<div class="view-toggle">'
    )
    print('Button added to header')

# --- 2. FULL MODAL FORM with all 13 fields ---
modal_html = '''
<div class="modal-overlay" id="createModal">
<div class="modal">
<div class="modal-title">Create Campaign</div>
<form id="createForm" onsubmit="handleFormSubmit(event)">
<div class="form-group">
<label class="form-label">Campaign Name *</label>
<input type="text" class="form-input" id="f-name" placeholder="e.g. Winter Golf Promotions 2026" required>
</div>
<div class="form-row">
<div class="form-group">
<label class="form-label">Campaign Type *</label>
<select class="form-select" id="f-type" required>
<option value="">Select type...</option>
<option value="evergreen">Evergreen</option>
<option value="seasonal">Seasonal</option>
<option value="product-launch">Product Launch</option>
<option value="event">Event</option>
<option value="promo">Promo</option>
</select>
</div>
<div class="form-group">
<label class="form-label">Campaign Source Type *</label>
<select class="form-select" id="f-source-type" required>
<option value="">Select source...</option>
<option value="Manual">Manual</option>
<option value="Research Opportunity">Research Opportunity</option>
<option value="Trend">Trend</option>
<option value="Seasonal">Seasonal</option>
<option value="Product Launch">Product Launch</option>
<option value="Competitor Response">Competitor Response</option>
<option value="Customer Request">Customer Request</option>
</select>
</div>
</div>
<div class="form-group">
<label class="form-label">Campaign Source Reference</label>
<input type="text" class="form-input" id="f-source-ref" placeholder="e.g. Reddit thread, competitor site, trend report...">
</div>
<div class="form-row">
<div class="form-group">
<label class="form-label">Primary Goal *</label>
<select class="form-select" id="f-goal" required>
<option value="">Select goal...</option>
<option value="Bookings">Bookings</option>
<option value="Leads">Leads</option>
<option value="Sales">Sales</option>
<option value="Awareness">Awareness</option>
<option value="Event Registrations">Event Registrations</option>
<option value="Memberships">Memberships</option>
<option value="Reviews">Reviews</option>
<option value="Website Traffic">Website Traffic</option>
<option value="Custom">Custom</option>
</select>
</div>
<div class="form-group">
<label class="form-label">Campaign Priority</label>
<select class="form-select" id="f-priority">
<option value="high">High</option>
<option value="medium" selected>Medium</option>
<option value="low">Low</option>
</select>
</div>
</div>
<div class="form-row">
<div class="form-group">
<label class="form-label">Platforms</label>
<select class="form-select" id="f-platforms" multiple style="min-height:80px">
<option value="instagram" selected>Instagram</option>
<option value="tiktok">TikTok</option>
<option value="gmb">Google Business</option>
</select>
</div>
<div class="form-group">
<label class="form-label">Success Target</label>
<input type="text" class="form-input" id="f-target" placeholder="e.g. 10 bookings/week">
</div>
</div>
<div class="form-group">
<label class="form-label">Campaign Duration</label>
<input type="text" class="form-input" id="f-duration" placeholder="e.g. 8 weeks, 3 months, ongoing">
</div>
<div class="form-group">
<label class="form-label">Target Audience</label>
<input type="text" class="form-input" id="f-audience" placeholder="e.g. Beginner to intermediate golfers, 25-55, Johannesburg">
</div>
<div class="form-group">
<label class="form-label">Primary Offer / CTA</label>
<input type="text" class="form-input" id="f-offer" placeholder="e.g. TrackMan Assessment from R900. First session R250.">
</div>
<div class="form-group">
<label class="form-label">Goal Notes</label>
<textarea class="form-textarea" id="f-notes" placeholder="Refine or expand on the primary goal..."></textarea>
</div>
<div class="form-group">
<label class="form-label">Notes / Context</label>
<textarea class="form-textarea" id="f-notes-context" placeholder="Any additional context, references, or notes for the campaign..."></textarea>
</div>
<div class="form-actions">
<button type="button" class="btn-secondary" onclick="closeCreateModal()">Cancel</button>
<button type="submit" class="btn-primary" id="btn-submit">Create Campaign</button>
</div>
</form>
</div>
</div>
'''

# Replace existing modal if present, or insert before </body>
if 'id="createModal"' in html:
    # Replace existing modal
    start = html.find('<div class="modal-overlay" id="createModal">')
    end = html.find('</div></div></div>', start) + len('</div></div></div>')
    html = html[:start] + modal_html + html[end:]
    print('Modal replaced')
else:
    # Insert before </body>
    html = html.replace('</body>', modal_html + '\n</body>')
    print('Modal inserted before </body>')

# --- 3. ADD JAVASCRIPT for open/close/validation ---
# Remove any existing openCreateModal / closeCreateModal / handleFormSubmit functions first
for fn in ['openCreateModal', 'closeCreateModal', 'handleFormSubmit']:
    pattern = re.compile(r'function\s+' + fn + r'\s*\([^)]*\)\s*\{[^}]*\}')
    html = pattern.sub('', html)

js_functions = '''
function openCreateModal() {
    document.getElementById('createModal').classList.add('active');
    document.getElementById('f-name').focus();
}
function closeCreateModal() {
    document.getElementById('createModal').classList.remove('active');
    document.getElementById('createForm').reset();
    document.getElementById('form-error').style.display = 'none';
}
function handleFormSubmit(e) {
    e.preventDefault();
    var name = document.getElementById('f-name').value.trim();
    var ctype = document.getElementById('f-type').value;
    var goal = document.getElementById('f-goal').value;
    var stype = document.getElementById('f-source-type').value;
    if (!name || !ctype || !goal || !stype) {
        var err = document.getElementById('form-error');
        if (err) { err.style.display = 'block'; err.textContent = 'Please fill in all required fields (*)'; }
        return;
    }
    // Gate 2: no data writes, no pipeline calls
    // Show success and close
    var btn = document.getElementById('btn-submit');
    btn.textContent = 'Saved (Gate 2 — no write)';
    btn.style.background = '#4488ff';
    setTimeout(function() {
        closeCreateModal();
        btn.textContent = 'Create Campaign';
        btn.style.background = '';
    }, 1500);
}
'''

# Insert JS before </script>
if '</script>' in html:
    html = html.replace('</script>', js_functions + '\n</script>')
    print('JS functions added')
else:
    # No script tag found — append before </body>
    html = html.replace('</body>', '<script>' + js_functions + '</script>\n</body>')
    print('JS functions added (no existing script)')

# Add form error element inside modal
if 'id="form-error"' not in html:
    modal_error = '<div id="form-error" style="display:none;color:#ff4455;font-size:12px;margin-bottom:12px;padding:8px;background:rgba(255,68,85,0.1);border-radius:6px"></div>'
    html = html.replace(
        '<div class="modal-title">Create Campaign</div>',
        '<div class="modal-title">Create Campaign</div>' + modal_error
    )
    print('Form error element added')

# Write result
with open(SRC, 'w') as f:
    f.write(html)

size = len(html)
print(f'Written: {SRC}')
print(f'Size: {size} bytes')
print(f'Button present: {"btn-create" in html}')
print(f'Modal present: {"createModal" in html}')
print(f'All 13 fields present:')
for fid in ['f-name','f-type','f-source-type','f-source-ref','f-goal','f-priority',
            'f-platforms','f-target','f-duration','f-audience','f-offer','f-notes','f-notes-context']:
    print(f'  {fid}: {fid in html}')
print(f'JS openCreateModal: {"function openCreateModal" in html}')
print(f'JS closeCreateModal: {"function closeCreateModal" in html}')
print(f'JS handleFormSubmit: {"function handleFormSubmit" in html}')
no_pipe = not any(x in html.lower() for x in ['scout','copywriter','imagegen','publisher'])
no_write = 'write-campaign' not in html
print(f'No pipeline calls: {no_pipe}')
print(f'No write-campaign: {no_write}')
print(f'No write-campaign: {"write-campaign" not in html}')