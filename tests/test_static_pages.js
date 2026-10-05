// F06 — static document pages: inline scripts parse, and /despre applies preferences.
//
// Part A reads public/*.html and needs no server. Part B drives /despre.html in Chromium
// through the runner's isolated server (despre.html is static; no page here mints a device).
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const deps = require('./lib/deps');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

// ---- A. every inline executable <script> in public/*.html parses -----------------------
const pubDir = path.join(__dirname, '..', 'public');
const JS_TYPES = ['', 'text/javascript', 'application/javascript', 'module'];
let scriptCount = 0;
for (const f of fs.readdirSync(pubDir).filter(n => n.endsWith('.html')).sort()) {
  const html = fs.readFileSync(path.join(pubDir, f), 'utf8');
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m, n = 0;
  while ((m = re.exec(html))) {
    const attrs = m[1];
    if (/\bsrc\s*=/.test(attrs)) continue;
    const t = (/\btype\s*=\s*["']?([^"'\s>]*)/i.exec(attrs) || [, ''])[1].toLowerCase();
    if (!JS_TYPES.includes(t)) continue;       // JSON-LD and other data blocks
    n++; scriptCount++;
    let err = null;
    try { new vm.Script(m[2], { filename: `${f}#script${n}` }); } catch (e) { err = e.message; }
    check(!err, `${f} inline script #${n} parses${err ? ' — ' + err : ''}`);
  }
}
check(scriptCount > 0, `found ${scriptCount} inline scripts to check`);

// ---- B. /despre.html in Chromium -------------------------------------------------------
const { chromium } = deps.loadPlaywright('tests/test_static_pages.js');
const BASE = require('./lib/target').testBase('tests/test_static_pages.js');

(async () => {
  const browser = await deps.launchChromium('tests/test_static_pages.js', chromium);

  // Load /despre.html with an init script; return what the page looked like at the
  // earliest point (DOMContentLoaded) and after load, plus uncaught errors.
  async function visit(init, arg) {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(init, arg);
    await page.addInitScript(() => {
      const snap = () => ({
        theme: document.documentElement.getAttribute('data-theme'),
        skin: document.documentElement.getAttribute('data-skin'),
        size: document.documentElement.style.fontSize,
      });
      // First paint cannot precede the boot script in <head>; DOMContentLoaded is later still.
      document.addEventListener('DOMContentLoaded', () => { window.__early = snap(); });
    });
    await page.goto(BASE + '/despre.html', { waitUntil: 'load' });
    const early = await page.evaluate(() => window.__early);
    const text = await page.evaluate(() => document.body.innerText.length);
    await ctx.close();
    return { early, errors, text };
  }
  const seed = (kv) => visit((kv) => {
    try { for (const k in kv) localStorage.setItem(k, kv[k]); } catch (e) {}
  }, kv);

  let r = await visit(() => {});
  check(r.errors.length === 0, `default: no page error ${JSON.stringify(r.errors)}`);
  check(r.early.theme === 'light' && r.early.skin === 'govuk' && r.early.size === '100%',
        `default: light, govuk, 100% (${JSON.stringify(r.early)})`);

  r = await seed({ 'otios.theme': 'dark', 'otios.skin': 'brutal', 'otios.textscale': '125' });
  check(r.errors.length === 0, `saved: no page error ${JSON.stringify(r.errors)}`);
  check(r.early.theme === 'dark' && r.early.skin === 'brutal' && r.early.size === '125%',
        `saved: dark, brutal, 125% before DOMContentLoaded (${JSON.stringify(r.early)})`);

  for (const skin of ['paper', 'govuk', 'registru', 'tezaur', 'velin']) {
    r = await seed({ 'otios.skin': skin });
    check(r.early.skin === skin, `every shipped skin is accepted: ${skin}`);
  }

  r = await seed({ 'otios.theme': 'banana', 'otios.skin': 'nope', 'otios.textscale': 'huge' });
  check(r.errors.length === 0 && r.early.theme === 'light' && r.early.skin === 'govuk' &&
        r.early.size === '100%', `invalid values: safe defaults (${JSON.stringify(r.early)})`);

  r = await visit(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new Error('denied'); } });
  });
  check(r.errors.length === 0, `storage unavailable: no uncaught error ${JSON.stringify(r.errors)}`);
  check(r.early.skin === 'govuk' && r.text > 500, `storage unavailable: readable page (${r.text} chars)`);

  await browser.close();
  console.log(failures ? `\n${failures} FAILED` : '\nall passed');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
