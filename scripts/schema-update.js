#!/usr/bin/env node
const fs = require('fs');
const DASH = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard';
const data = JSON.parse(fs.readFileSync(DASH + '/campaign-os/campaign-data.json','utf8'));
const now = new Date().toISOString();

for (const cid of Object.keys(data.campaigns)) {
  const id = data.campaigns[cid].identity;

  id.primaryGoal = 'Bookings';
  id.campaignSource = {
    type: cid === 'takomo-101t' ? 'Product Launch' : 'Manual',
    reference: cid === 'takomo-101t' ? 'Takomo 101T product launch' : 'Manual creation',
    createdBy: 'christelle'
  };
  id.duration = cid === 'trackman-intelligence' ? '12 months (evergreen)'
    : cid === 'takomo-101t' ? '3 months'
    : '4 months (Jun–Sep 2026)';
  if (id.status === 'planned') id.status = 'draft';
  if (!data.campaigns[cid].memory.notes) {
    data.campaigns[cid].memory.notes = [];
  }
}

data.portfolioMetadata.lastUpdated = now;
fs.writeFileSync(DASH + '/campaign-os/campaign-data.json', JSON.stringify(data, null, 2));
console.log('Schema update complete');
for (const cid of Object.keys(data.campaigns)) {
  const id = data.campaigns[cid].identity;
  console.log(cid + ':');
  console.log('  primaryGoal:', id.primaryGoal);
  console.log('  campaignSource.type:', id.campaignSource.type);
  console.log('  duration:', id.duration);
  console.log('  status:', id.status);
}