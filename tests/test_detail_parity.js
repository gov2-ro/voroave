// F05: direct arrival (`/?word=`, server-rendered) and the click path (api/word.php)
// must show the same definition: senses, citations, tags, etymon and synonyms.
// Runs through tools/run_tests.py (isolated server). Needs the sqlite3 CLI for the
// older-schema fixture, which swaps the staged ui.db (never the repository copy).
'use strict';
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const BASE = require('./lib/target').testBase('tests/test_detail_parity.js');
let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };
const enc = encodeURIComponent;
const get = async (url) => { const r = await fetch(url); return { status: r.status, body: await r.text() }; };
const squash = (h) => h.replace(/\s+/g, ' ').trim();

const dataDir = process.env.OTIOS_TEST_DATA_DIR || path.join(__dirname, '..', 'public', 'data');
const dbPath = path.join(dataDir, 'ui.db');
const sql = (q) => execFileSync('sqlite3', [dbPath, q], { encoding: 'utf8' }).trim();

/** The panel markup of a direct-arrival page: everything after the panel's opening tag. */
function ssrPanel(html) {
  const m = html.match(/<div id="detail-panel"[^>]*>/);
  return m ? squash(html.slice(m.index + m[0].length)) : null;
}
/** Same panel with the SSR-only <h1> turned into the fragment's <div>. */
const asFragment = (p) => p.replace(/<h1 class="fp-title">(.*?)<\/h1>/, '<div class="fp-title">$1</div>');

async function parity(word) {
  const direct = await get(`${BASE}/?word=${enc(word)}`);
  const api = await get(`${BASE}/api/word.php?word=${enc(word)}`);
  check(direct.status === 200 && api.status === 200, `${word}: both paths answer 200`);
  const panel = ssrPanel(direct.body);
  const frag = squash(api.body);
  check(panel !== null, `${word}: direct page has a #detail-panel`);
  check(/<h1 class="fp-title">/.test(panel || ''), `${word}: direct arrival has a real <h1>`);
  check(!/<h1/.test(api.body) && /<div class="fp-title">/.test(api.body),
    `${word}: fragment has no <h1> (no duplicate page heading)`);
  check(asFragment(panel || '').startsWith(frag),
    `${word}: panel markup equals the fragment (apart from the heading tag)`);
  check((direct.body.match(/<h1\b/g) || []).length === 1, `${word}: exactly one <h1> on the page`);
  return { direct: direct.body, api: api.body };
}

(async () => {
  console.log('\n1. A structured word (zapciu): same senses, citations, synonyms on both paths');
  const z = await parity('zapciu');
  const nSense = (h) => (h.match(/<li class="fp-sense"/g) || []).length;
  check(nSense(z.direct) === 3 && nSense(z.api) === 3, 'zapciu: 3 senses on both paths');
  check(/<ol class="fp-senses">/.test(z.direct), 'zapciu: no-JS HTML carries <ol class="fp-senses">');
  check(!/Degrabă el trămitea[^<]* \| /.test(z.direct), 'zapciu: quotations are not pipe-joined');
  check(/class="sense-cite"/.test(z.direct), 'zapciu: citations render as sense-cite blocks');
  check(/class="syn-chip"/.test(z.direct), 'zapciu: sense synonyms render in direct HTML');

  console.log('\n2. A synonym-only sense (zăticni)');
  const t = await parity('zăticni');
  check(/sense-syn/.test(t.direct) && /sense-syn/.test(t.api), 'zăticni: synonym-only sense shown on both');
  check(/>deranja</.test(t.direct), 'zăticni: synonym text in direct HTML');

  console.log('\n3. A flat-only word renders its definition without JavaScript');
  let flat = null;
  try {
    flat = sql("SELECT word FROM words w WHERE definition <> '' AND NOT EXISTS " +
      "(SELECT 1 FROM senses s WHERE s.word = w.word) AND archaic_spelling = 0 LIMIT 1");
  } catch (e) { console.log(`  SKIP  sqlite3 unavailable (${e.message})`); }
  if (flat) {
    const f = await parity(flat);
    check(!/fp-senses/.test(f.direct) && /<div class="definition-text">/.test(f.direct),
      `${flat}: flat definition, no empty sense list`);
  }

  console.log('\n4. Answer-body contract: wrapper and class kept on both paths');
  for (const h of [z.direct, z.api]) {
    check((h.match(/<div class="fp-body">/g) || []).length === 1, 'one .fp-body wrapper');
    check(/<span class="fp-pos-line">/.test(h) &&
      h.indexOf('fp-pos-line') < h.indexOf('class="fp-body"'), '.fp-pos-line sits before .fp-body (in .fp-head)');
  }

  console.log('\n5. Missing and invalid words keep their status and metadata');
  const bad = await get(`${BASE}/?word=${enc('nu-exista-xyzq')}`);
  check(bad.status === 200 && !/id="detail-panel"[^>]*panel-open/.test(bad.body)
    && !/class="fp-title"/.test(bad.body), 'unknown word: page renders, no panel content');
  check(/<title>Voroave neglijate<\/title>/.test(bad.body)
    && /rel="canonical" href="[^"]*\/">/.test(bad.body), 'unknown word: site title and site canonical');
  check(!/nu-exista-xyzq/.test(bad.body.replace(/<script[\s\S]*?<\/script>/g, '')
    .replace(/value="[^"]*"/g, '')), 'unknown word is not reflected into the head');
  check((await get(`${BASE}/api/word.php?word=${enc('nu-exista-xyzq')}`)).status === 404, 'api: unknown word is 404');
  check((await get(`${BASE}/api/word.php?word=`)).status === 400, 'api: empty word is 400');
  const ok = await get(`${BASE}/?word=zapciu`);
  check(/rel="canonical" href="[^"]*\/\?word=zapciu"/.test(ok.body), 'known word: canonical names the word');
  check(/<title>[^<]*zapciu/.test(ok.body), 'known word: title names the word');

  console.log('\n6. Older ui.db without the sense tables: flat fallback; other errors are not hidden');
  const backup = dbPath + '.f05-backup', work = dbPath + '.f05-work';
  let swapped = false;
  const swapIn = (stmts) => {
    fs.copyFileSync(backup, work);
    execFileSync('sqlite3', [work, stmts]);
    fs.renameSync(work, dbPath);
  };
  try {
    execFileSync('which', ['sqlite3'], { stdio: 'ignore' });
    fs.renameSync(dbPath, backup); // original kept aside, restored in `finally`
    swapped = true;
    swapIn('DROP TABLE senses; DROP TABLE sense_citations;');
    const d = await get(`${BASE}/?word=zapciu`);
    const a = await get(`${BASE}/api/word.php?word=zapciu`);
    check(d.status === 200 && a.status === 200, 'old schema: both paths answer 200');
    check(!/fp-senses/.test(d.body + a.body), 'old schema: no sense list on either path');
    check(/<div class="definition-text">Cârmuitor/.test(d.body)
      && /<div class="definition-text">Cârmuitor/.test(a.body), 'old schema: flat definition shown on both');
    check(/<h1 class="fp-title">/.test(d.body), 'old schema: direct arrival keeps its <h1>');

    fs.unlinkSync(dbPath);
    swapIn('DROP TABLE senses; CREATE TABLE senses(word TEXT, junk TEXT);');
    const e1 = await get(`${BASE}/api/word.php?word=zapciu`);
    // A dev PHP server prints the fatal error with status 200; production gives 500.
    // Either way the panel must not render as if nothing happened.
    check(e1.status >= 500 || !/fp-body/.test(e1.body),
      `a different DB error (no such column) is not masked (status ${e1.status})`);
  } catch (e) {
    console.log(`  SKIP  older-schema check (${e.message})`);
  } finally {
    if (swapped) {
      try { fs.unlinkSync(dbPath); } catch (_) { /* already moved */ }
      fs.renameSync(backup, dbPath);
      for (const sfx of ['-wal', '-shm']) { try { fs.unlinkSync(work + sfx); } catch (_) {} }
    }
  }

  console.log(failures === 0 ? '\nAll passed.\n' : `\n${failures} FAILED\n`);
  process.exit(failures === 0 ? 0 : 1);
})();
