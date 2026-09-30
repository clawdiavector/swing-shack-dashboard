// scripts/inline-to-campaign-os.mjs
//
// Vite produces dist/index.html (454 bytes) that references external
// assets/dist/index-*.js + assets/index-*.css with the base='/app/' prefix.
//
// Flask's app.py serves a single self-contained HTML at
// campaign-os.html from cwd via send_from_directory('.', 'campaign-os.html').
// That file is the historical entry point and is what production loads.
//
// This script reads dist/index.html, inlines the JS + CSS into it (same
// origin so it works in the browser), writes the result to ../campaign-os/campaign-os.html
// and removes any <script type="module" src=...> reference so the inline bundle takes over.
//
// Run after `vite build`.

import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(process.cwd(), '..');
const DIST = path.join(process.cwd(), 'dist');
const OUT = path.join(ROOT, 'campaign-os', 'campaign-os.html');

function read(p) { return fs.readFileSync(p, 'utf8'); }
function write(p, content) { fs.writeFileSync(p, content); }

const indexHtml = read(path.join(DIST, 'index.html'));
const assetsDir = path.join(DIST, 'assets');

// Find all <script type="module" src="..."> and <link rel="stylesheet" href="...">
const scriptSrcs = [...indexHtml.matchAll(/<script[^>]*src="([^"]+\.js)"[^>]*><\/script>/g)].map(m => m[1]);
const styleHrefs = [...indexHtml.matchAll(/<link[^>]*rel="stylesheet"[^>]*href="([^"]+\.css)"[^>]*\/?>/g)].map(m => m[1]);

// Convert base='/app/' references → local file paths in dist/
function resolve(p) {
    return path.join(DIST, p.replace(/^\/app\//, ''));
}

let out = indexHtml;

// Inline CSS
for (const href of styleHrefs) {
    const css = read(resolve(href));
    out = out.replace(
        new RegExp(`<link[^>]*rel="stylesheet"[^>]*href="${href.replace(/[/]/g, '\\/')}"[^>]*\\/?>`),
        `<style>\n${css}\n</style>`,
    );
}

// Inline JS — replace the module script with a non-module <script> wrapping the bundle
for (const src of scriptSrcs) {
    const js = read(resolve(src));
    out = out.replace(
        new RegExp(`<script[^>]*src="${src.replace(/[/]/g, '\\/')}"[^>]*><\\/script>`),
        `<script>\n${js}\n</script>`,
    );
}

write(OUT, out);
console.log(`Wrote ${OUT}: ${fs.statSync(OUT).size.toLocaleString()} bytes (inlined ${scriptSrcs.length} JS + ${styleHrefs.length} CSS)`);