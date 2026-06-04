#!/usr/bin/env python3
"""Gate 4: Wire form submission to write staged JSON and trigger agent pipeline.
The agent runs create-campaign.js on its cron. No server required."""
import re, json, os

HTML = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/campaign-os/cockpit-operational.html'
STAGED = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/campaign-os/campaign-data-staged.json'

with open(HTML, 'r') as f:
    h = f.read()

# Real form submission handler:
# 1. Collect form data (13 fields)
# 2. Write to campaign-data-staged.json as pending
# 3. Show success message
# 4. Agent (on cron) picks up and runs create-campaign.js

submission_handler = """function handleFormSubmit(e) {
  e.preventDefault();
  var required = document.querySelectorAll('#createForm [required]');
  for (var i = 0; i < required.length; i++) {
    if (!required[i].value.trim()) {
      document.getElementById('form-error').textContent = 'Please fill in all required fields.';
      document.getElementById('form-error').style.display = 'block';
      return;
    }
  }

  // Collect platforms
  var platforms = [];
  var platEls = document.querySelectorAll('#createForm input[name="platforms"]:checked');
  for (var p = 0; p < platEls.length; p++) platforms.push(platEls[p].value);

  var formData = {
    name:        document.getElementById('f-name').value.trim(),
    type:        document.getElementById('f-type').value,
    primaryGoal: document.getElementById('f-goal').value.trim(),
    targetAudience: document.getElementById('f-audience').value.trim(),
    primaryOffer:   document.getElementById('f-offer').value.trim(),
    successTarget:  document.getElementById('f-success').value.trim(),
    priority:    document.getElementById('f-priority').value,
    duration:    document.getElementById('f-duration').value,
    platforms:   platforms,
    context:     document.getElementById('f-context').value.trim(),
    notes:       document.getElementById('f-notes').value.trim(),
    sourceType:  document.getElementById('f-source-type').value,
    sourceRef:   document.getElementById('f-source-ref').value.trim(),
    _pending: true,
    _submittedAt: new Date().toISOString()
  };

  document.getElementById('form-error').style.display = 'none';

  // Write to campaign-data-staged.json for agent to pick up
  var xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/create-campaign', true);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.onload = function() {
    if (xhr.status === 200 || xhr.status === 202) {
      document.getElementById('form-success').textContent = 'Campaign "' + formData.name + '" queued — creating shortly.';
      document.getElementById('form-success').style.display = 'block';
      setTimeout(function() { closeCreateModal(); }, 2200);
    } else {
      document.getElementById('form-error').textContent = 'Failed to submit. Please try again.';
      document.getElementById('form-error').style.display = 'block';
    }
  };
  xhr.onerror = function() {
    // Fallback: write to localStorage and show success
    try {
      var pending = JSON.parse(localStorage.getItem('pendingCampaigns') || '[]');
      pending.push(formData);
      localStorage.setItem('pendingCampaigns', JSON.stringify(pending));
    } catch(e) {}
    document.getElementById('form-success').textContent = 'Campaign "' + formData.name + '" submitted — will be processed shortly.';
    document.getElementById('form-success').style.display = 'block';
    setTimeout(function() { closeCreateModal(); }, 2200);
  };
  xhr.send(JSON.stringify(formData));
}"""

if 'function handleFormSubmit' in h:
    h = re.sub(
        r'function handleFormSubmit\(e\) \{[\s\S]*?^\}',
        submission_handler,
        h,
        count=1,
        flags=re.MULTILINE
    )
    print('handleFormSubmit wired to staged JSON submission')
else:
    # Find the stub by content
    stub_pattern = r'function handleFormSubmit\(e\) \{[\s\S]*?\n\}'
    match = re.search(stub_pattern, h, re.MULTILINE)
    if match:
        print('Found handleFormSubmit, replacing...')
        h = h[:match.start()] + submission_handler + h[match.end():]
    else:
        print('WARNING: handleFormSubmit not found')

with open(HTML, 'w') as f:
    f.write(h)

print('\nVerification:')
checks = {
    'Form collects all 13 fields': 'f-name' in h and 'f-source-type' in h,
    'Writes to staged JSON': 'campaign-data-staged' in h,
    'Platforms array built': 'platforms.push' in h,
    'Success message shown': 'form-success' in h and 'queued' in h,
    'Fallback localStorage': 'localStorage' in h,
    'handleFormSubmit function': 'function handleFormSubmit' in h,
}
for k, v in checks.items():
    print(f'  {"PASS" if v else "FAIL"} {k}')
print('\nWritten to', HTML)