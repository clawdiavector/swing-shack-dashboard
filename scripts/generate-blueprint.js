#!/usr/bin/env node
/**
 * Gate 6: M4 Blueprint Generator
 *
 * Generates campaign blueprint by populating:
 *   identity.dna        — tone, contentMix, requiredContentTypes, ctaPhilosophy
 *   identity.visualDirection — palette, mood, creativeDirection, layoutStyle
 *   strategy           — positioningStatement, primaryOffer, pillars
 *   memory.notes       — structured notes array
 *
 * Then sets pipeline to generatingBlueprint (step 1, Scout).
 *
 * Usage: node scripts/generate-blueprint.js <campaignId>
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '..');
const DATA_FILE = path.join(REPO_ROOT, 'campaign-os', 'campaign-data.json');

function main() {
  const campaignId = process.argv[2];
  if (!campaignId) {
    console.log('Usage: node generate-blueprint.js <campaignId>');
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  const campaign = data.campaigns && data.campaigns[campaignId];

  if (!campaign) {
    console.error('Campaign not found:', campaignId);
    process.exit(1);
  }

  const ident = campaign.identity || {};
  const brief = campaign.brief || {};

  // ── Build DNA from campaign metadata ───────────────────────────────────
  const campaignType = ident.campaignType || 'evergreen';
  const platforms = (ident.platforms || []).join(', ');

  const dna = {
    tone: 'Authentic, informative, and persuasive. Matches the voice appropriate for ' + platforms + ' audiences.',
    contentMix: campaignType === 'product-launch'
      ? '40% educational / 30% proof / 20% promotional / 10% social'
      : campaignType === 'seasonal'
      ? '30% urgency / 30% lifestyle / 20% practical / 20% proof'
      : '50% educational / 25% promotional / 25% social proof',
    requiredContentTypes: ['hook-stats', 'hero-visual'],
    preferredVisualStyles: ['data overlay on dark background', 'premium equipment photography'],
    ctaPhilosophy: 'Lead with value, anchor with price. Include R-amount in every CTA.',
    platformStrategy: {},
    exampleHighPerforming: [],
    exampleLowPerforming: [],
    forbiddenVisualStyles: ['bright neon backgrounds', 'cartoon imagery', 'heavily filtered photos']
  };

  // Platform-specific strategy
  for (const p of (ident.platforms || [])) {
    if (p === 'instagram') {
      dna.platformStrategy.instagram = 'Stat-first hook stops the scroll. Visual tells the story. Caption earns the click.';
    } else if (p === 'tiktok') {
      dna.platformStrategy.tiktok = 'Hook is the number/stat. 3-second hook, then explain. Fast, punchy.';
    } else if (p === 'gmb') {
      dna.platformStrategy.gmb = 'Trust + proof + convenience. Clean, professional, no gimmicks.';
    }
  }

  // ── Build visualDirection ──────────────────────────────────────────────
  const visualDirection = {
    palette: {
      primary: ident.primaryColor || '#0066CC',
      secondary: '#111118',
      accent: '#00CC77',
      background: '#0A0A14',
      text: '#E8E8F0'
    },
    mood: 'Premium, focused, performance-driven.',
    creativeDirection: ident.primaryGoal
      ? 'Content must communicate: ' + ident.primaryGoal
      : 'Content aligned with campaign brief.',
    imageReferences: [],
    colorUsage: 'Use primary brand colour as dominant. Accent for CTAs and positive metrics. Keep dark backgrounds.',
    typography: 'Roboto Condensed Bold for numbers. Inter for body.',
    layoutStyle: 'Split screen where relevant. Dark backgrounds throughout. Numbers dominate visual hierarchy.',
    contentExamples: []
  };

  // ── Build strategy ──────────────────────────────────────────────────────
  const strategy = campaign.strategy || {};

  strategy.positioningStatement = ident.primaryGoal
    ? 'For ' + (brief.audience || 'target golfers') + ' who want to ' + ident.primaryGoal + '.'
    : 'For ' + (brief.audience || 'target golfers') + '.';

  strategy.targetAudience = brief.audience || '';
  // primaryOffer is set by create-campaign.js from formData.primaryOffer (f-offer field).
  // Preserve it here — do not overwrite.

  if (!strategy.pillars || strategy.pillars.length === 0) {
    strategy.pillars = [
      { id: 'p1', name: 'Value', description: 'What makes this offer compelling' },
      { id: 'p2', name: 'Proof', description: 'Why Swing Shack is the right choice' },
      { id: 'p3', name: 'Urgency', description: 'Why act now' }
    ];
  }

  // ── Build memory.notes ──────────────────────────────────────────────────
  const memory = campaign.memory || { notes: [] };
  if (!memory.notes) memory.notes = [];

  memory.notes.push({
    type: 'blueprint-generated',
    timestamp: new Date().toISOString(),
    detail: 'Campaign blueprint generated from form inputs. DNA, visualDirection, strategy, and memory initialised.'
  });

  // ── Update campaign — V2 schema paths ────────────────────────────────
  campaign.dna = dna;
  campaign.visualDirection = visualDirection;
  campaign.strategy = strategy;
  campaign.memory = memory;

  // ── Update pipeline to generatingBlueprint (step 1, Scout) ────────────
  campaign.pipeline = {
    status: 'generatingBlueprint',
    currentStep: 1,
    totalSteps: 4,
    currentAgent: 'Scout'
  };

  campaign.identity.status = 'generatingBlueprint';
  data.updatedAt = new Date().toISOString();

  // ── Write back ─────────────────────────────────────────────────────────
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2) + '\n');
  console.log('Blueprint generated for:', campaignId);

  // ── Git commit and push ─────────────────────────────────────────────────
  try {
    execSync('git add campaign-os/campaign-data.json', { cwd: REPO_ROOT, stdio: 'pipe' });
    execSync(
      'git commit -m "feat: generate blueprint for ' + campaignId + ' [gate-6]"',
      { cwd: REPO_ROOT, stdio: 'pipe' }
    );
    execSync('git push origin main', { cwd: REPO_ROOT, stdio: 'pipe' });
    console.log('Committed and pushed — GitHub Actions will regenerate cockpit');
  } catch (err) {
    if (err.message.includes('nothing to commit')) {
      console.log('No changes to commit');
    } else {
      console.error('Git error:', err.message);
    }
  }
}

main();