#!/usr/bin/env node
/**
 * run_seo_audit.js
 * Audits swingshack.co.za for SEO issues and produces actionable recommendations
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DATA_FILE = path.join(__dirname, '..', 'data', 'seo-audit.json');
const SITE = 'https://swingshack.co.za';

const SEO_KEYWORDS = [
  'indoor golf johannesburg',
  'golf simulator johannesburg',
  'club fitting johannesburg',
  'golf lessons randburg',
  'golf practice johannesburg',
  'trackman johannesburg',
  'custom clubs johannesburg',
];

async function fetchPage(url) {
  try {
    const cmd = `curl -s -L -A "Mozilla/5.0" --max-time 15 "${url}" 2>/dev/null | head -c 80000`;
    return execSync(cmd, { encoding: 'utf8', timeout: 20000 });
  } catch (e) { return ''; }
}

function auditPage(html, url) {
  const findings = [];
  
  // Title check
  const titleMatch = html.match(/<title[^>]*>([^<]+)<\/title>/i);
  const title = titleMatch ? titleMatch[1].trim() : '';
  if (!title) {
    findings.push({ type: 'missing_title', severity: 'high', message: 'Page missing <title> tag' });
  } else if (title.length < 30) {
    findings.push({ type: 'title_too_short', severity: 'medium', message: `Title too short (${title.length} chars): "${title}"` });
  } else if (title.length > 60) {
    findings.push({ type: 'title_too_long', severity: 'medium', message: `Title too long (${title.length} chars): "${title.substring(0, 60)}..."` });
  }
  
  // Meta description
  const descMatch = html.match(/<meta[^>]*name="description"[^>]*content="([^"]+)"/i);
  if (!descMatch) {
    findings.push({ type: 'missing_meta_description', severity: 'high', message: 'Missing meta description' });
  } else if (descMatch[1].length < 120) {
    findings.push({ type: 'meta_description_short', severity: 'medium', message: 'Meta description too short' });
  }
  
  // H1 check
  const h1Matches = html.match(/<h1[^>]*>([^<]+)<\/h1>/gi) || [];
  if (h1Matches.length === 0) {
    findings.push({ type: 'missing_h1', severity: 'high', message: 'No H1 found' });
  } else if (h1Matches.length > 1) {
    findings.push({ type: 'multiple_h1', severity: 'medium', message: `Multiple H1s (${h1Matches.length})` });
  }
  
  // Image alts
  const imgWithoutAlt = (html.match(/<img(?![^>]*alt=)[^>]*>/gi) || []).length;
  if (imgWithoutAlt > 0) {
    findings.push({ type: 'images_missing_alt', severity: 'medium', message: `${imgWithoutAlt} images missing alt text` });
  }
  
  // FAQ check
  const hasFaq = html.includes('faq') || html.includes('FAQ') || html.includes('frequently');
  if (!hasFaq) {
    findings.push({ type: 'missing_faq', severity: 'low', message: 'No FAQ section found - adding FAQ could improve SEO' });
  }
  
  // Local intent
  const localSignals = ['johannesburg', 'randburg', 'south africa', 'sa', 'parkview'];
  const hasLocal = localSignals.some(s => html.toLowerCase().includes(s));
  if (!hasLocal) {
    findings.push({ type: 'missing_local_signals', severity: 'medium', message: 'Page missing local intent terms (Johannesburg/Randburg/SA)' });
  }
  
  // Internal links
  const internalLinks = (html.match(/href="(https?:\/\/swingshack[^"]+)"/gi) || []).length;
  const externalLinks = (html.match(/href="(https?:\/\/(?!swingshack)[^"]+)"/gi) || []).length;
  if (internalLinks < 3) {
    findings.push({ type: 'weak_internal_linking', severity: 'low', message: `Only ${internalLinks} internal links found` });
  }
  
  return findings;
}

async function run() {
  console.log('🔍 Running SEO audit on swingshack.co.za...');
  
  const pagesToAudit = [
    { url: SITE, name: 'Homepage' },
    { url: `${SITE}/membership`, name: 'Membership' },
    { url: `${SITE}/coaching`, name: 'Coaching' },
    { url: `${SITE}/club-fitting`, name: 'Club Fitting' },
  ];
  
  const allFindings = [];
  const pageReports = [];
  
  for (const page of pagesToAudit) {
    console.log(`  Auditing: ${page.name}`);
    const html = await fetchPage(page.url);
    if (!html) {
      pageReports.push({ name: page.name, url: page.url, status: 'FETCH_FAILED', findings: [] });
      continue;
    }
    const findings = auditPage(html, page.url);
    pageReports.push({ name: page.name, url: page.url, status: 'OK', findings });
    allFindings.push(...findings.map(f => ({ ...f, page: page.name })));
  }
  
  // Categorise recommendations
  const high = allFindings.filter(f => f.severity === 'high');
  const medium = allFindings.filter(f => f.severity === 'medium');
  const low = allFindings.filter(f => f.severity === 'low');
  
  const recommendations = [
    ...high.map(f => ({ ...f, action: 'FIX ASAP', priority: 1 })),
    ...medium.map(f => ({ ...f, action: 'Fix this week', priority: 2 })),
    ...low.map(f => ({ ...f, action: 'Consider fixing', priority: 3 })),
  ];
  
  const result = {
    updated: new Date().toISOString(),
    site: SITE,
    total_findings: allFindings.length,
    high_severity: high.length,
    medium_severity: medium.length,
    low_severity: low.length,
    recommendations,
    pages: pageReports,
  };
  
  fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
  console.log(`✅ SEO Audit: ${allFindings.length} findings (${high.length} high, ${medium.length} medium)`);
  return result;
}

module.exports = { run };
if (require.main === module) run().catch(console.error);