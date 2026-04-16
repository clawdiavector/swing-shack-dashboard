#!/usr/bin/env node
/**
 * run_geo_audit.js
 * Checks if pages are easy for AI/search summaries to understand
 * GEO = Generative Engine Optimisation
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DATA_FILE = path.join(__dirname, '..', 'data', 'geo-audit.json');
const SITE = 'https://swingshack.co.za';

async function fetchPage(url) {
  try {
    const cmd = `curl -s -L -A "Mozilla/5.0" --max-time 15 "${url}" 2>/dev/null | head -c 80000`;
    return execSync(cmd, { encoding: 'utf8', timeout: 20000 });
  } catch (e) { return ''; }
}

function geoAudit(html, url) {
  const findings = [];
  const positive = [];
  
  // Extract main content text
  const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  
  // Entity clarity: does it mention who, what, where clearly?
  const hasWho = html.match(/(Swing Shack|coaches|instructors| certified|TrackMan)/i);
  const hasWhat = html.match(/(golf|simulator|fitting|lessons|sessions|indoor)/i);
  const hasWhere = html.match(/(Johannesburg|Randburg|Parkview|South Africa|SA)/i);
  
  if (hasWho && hasWhat && hasWhere) {
    positive.push('Clear entity signals (who/what/where) present');
  } else {
    if (!hasWho) findings.push({ type: 'unclear_entity', severity: 'medium', message: 'Page does not clearly identify who provides the service' });
    if (!hasWhat) findings.push({ type: 'unclear_offering', severity: 'high', message: 'Page does not clearly state what the service is' });
    if (!hasWhere) findings.push({ type: 'missing_location', severity: 'high', message: 'Page does not clearly state the location' });
  }
  
  // Q&A blocks (good for AI summarisation)
  const qaBlocks = (html.match(/<dl>|<dt>|<dd>|<h[23][^>]*>(?:What|Why|How|Is|Can|Should)/gi) || []).length;
  const hasFaqSchema = html.includes('FAQPage') || html.includes('schema.org/FAQ');
  if (qaBlocks > 2) {
    positive.push(`${qaBlocks} Q&A blocks found - good for AI extraction`);
  } else {
    findings.push({ type: 'no_qa_blocks', severity: 'medium', message: 'No clear Q&A blocks found - AI summaries may miss key info' });
  }
  
  // Service clarity
  const servicePages = ['membership', 'coaching', 'fitting', 'lessons', 'practice'];
  const pageService = servicePages.find(s => url.includes(s));
  if (pageService) {
    const hasPrice = html.match(/R\s*\d+/);
    const hasDuration = html.match(/\d+\s*(min|hour|session)/i);
    const hasCta = html.match(/(book|contact|call|schedule|get started)/i);
    
    if (hasPrice && hasDuration && hasCta) {
      positive.push(`${pageService} page has clear pricing, duration, and CTA`);
    } else {
      if (!hasPrice) findings.push({ type: 'missing_price', severity: 'medium', message: `${pageService} page missing pricing` });
      if (!hasDuration) findings.push({ type: 'missing_duration', severity: 'low', message: `${pageService} page missing session duration` });
      if (!hasCta) findings.push({ type: 'missing_cta', severity: 'high', message: `${pageService} page missing clear call-to-action` });
    }
  }
  
  // Structured data check
  const hasJsonLd = html.includes('application/ld+json') || html.includes('schema.org');
  if (hasJsonLd) {
    positive.push('Structured data (JSON-LD/schema.org) detected');
  } else {
    findings.push({ type: 'no_structured_data', severity: 'medium', message: 'No structured data found - AI/search engines may struggle to extract entities' });
  }
  
  // Content depth
  if (text.length < 300) {
    findings.push({ type: 'thin_content', severity: 'high', message: `Page content very thin (${text.length} chars) - may not satisfy AI summaries` });
  } else if (text.length > 800) {
    positive.push(`Good content depth (${text.length} chars)`);
  }
  
  return { findings, positive };
}

async function run() {
  console.log('🌍 Running GEO audit...');
  
  const pages = [
    { url: SITE, name: 'Homepage' },
    { url: `${SITE}/membership`, name: 'Membership' },
    { url: `${SITE}/coaching`, name: 'Coaching' },
    { url: `${SITE}/club-fitting`, name: 'Club Fitting' },
  ];
  
  const allFindings = [];
  const allPositive = [];
  const pageReports = [];
  
  for (const page of pages) {
    const html = await fetchPage(page.url);
    if (!html) {
      pageReports.push({ name: page.name, status: 'FETCH_FAILED', findings: [], positive: [] });
      continue;
    }
    const { findings, positive } = geoAudit(html, page.url);
    pageReports.push({ name: page.name, status: 'OK', findings, positive });
    allFindings.push(...findings.map(f => ({ ...f, page: page.name })));
    allPositive.push(...positive.map(p => ({ text: p, page: page.name })));
  }
  
  const result = {
    updated: new Date().toISOString(),
    site: SITE,
    geo_score: allPositive.length > 0 && allFindings.filter(f => f.severity === 'high').length === 0 ? 'GOOD' : 'NEEDS_WORK',
    summary: {
      clear_pages: pageReports.filter(p => p.status === 'OK' && p.findings.filter(f => f.severity === 'high').length === 0).length,
      needs_work: pageReports.filter(p => p.findings.filter(f => f.severity === 'high').length > 0).length,
    },
    high_priority: allFindings.filter(f => f.severity === 'high'),
    medium_priority: allFindings.filter(f => f.severity === 'medium'),
    low_priority: allFindings.filter(f => f.severity === 'low'),
    positive_signals: allPositive,
    recommendations: allFindings.map(f => ({
      type: f.type,
      severity: f.severity,
      message: f.message,
      page: f.page,
      fix: f.type === 'no_qa_blocks' ? 'Add FAQ section with clear Q&A format' :
           f.type === 'missing_price' ? 'Add pricing information with R amount' :
           f.type === 'missing_location' ? 'Add Johannesburg/Randburg location prominently' :
           f.type === 'no_structured_data' ? 'Add LocalBusiness schema markup' :
           f.type === 'unclear_offering' ? 'State clearly what the service is in the first 100 chars' :
           f.type === 'missing_cta' ? 'Add "Book Now" or "Contact" button above the fold' :
           'Review and improve ' + f.type,
    })),
  };
  
  fs.writeFileSync(DATA_FILE, JSON.stringify(result, null, 2));
  console.log(`✅ GEO Audit: ${result.geo_score} - ${allFindings.length} findings, ${allPositive.length} positive signals`);
  return result;
}

module.exports = { run };
if (require.main === module) run().catch(console.error);