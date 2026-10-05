// The full sense tree (docs/senses-plan.md) against a running server.
//
//   php -S 127.0.0.1:8011 -t public tools/dev-router.php &
//   OTIOS_TEST_URL=http://127.0.0.1:8011 node tests/test_senses.js
//
// `bidinea` is hardcoded on purpose — it's the plan's own fixture (§2, §8) and a real
// DEX entry, not user-editable state, so it can't drift the way a filtered sample word
// could. The "no senses" word is the opposite: picked live off the API, because a
// rebuild can reflag which words have a Tree/Meaning structure and hardcoding one would
// make this a test of a stale fixture rather than of the fallback.
const { execSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const BASE = require('./lib/target').testBase('tests/test_senses.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

const enc  = encodeURIComponent;
const text = (url) => fetch(url).then((r) => r.text());
const wordsIn = (html) => (html.match(/data-word="([^"]*)"/g) || [])
  .map((s) => s.slice(11, -1));

(async () => {
  console.log('\n1. `?word=bidinea` renders 2 numbered senses, `vulgar` on the second');
  const html = await text(`${BASE}/api/word.php?word=bidinea`);
  const senseBlocks = [...html.matchAll(/<li class="fp-sense"[^>]*>([\s\S]*?)<\/li>/g)]
    .map((m) => m[1]);
  check(senseBlocks.length === 2, `2 <li class="fp-sense"> found (got ${senseBlocks.length})`);
  check(/>1\.</.test(senseBlocks[0] || ''), 'first sense numbered 1.');
  check(/Pensulă mare/.test(senseBlocks[0] || ''), 'first sense is the brush definition');
  check(/>2\.</.test(senseBlocks[1] || ''), 'second sense numbered 2.');
  check(/class="detail-tag sense-tag">vulgar</.test(senseBlocks[1] || ''),
    'second sense carries the `vulgar` meaning-level tag');
  check(/Organ genital feminin\./.test(senseBlocks[1] || ''), 'second sense is the vulgar one');

  console.log('\n2. A word with no sense tree falls back to the flat definition');
  // Sampled off the default listing rather than hardcoded — see header comment. 41% of
  // the shortlist has no Tree/Meaning structure at all, so a handful of candidates is
  // enough to find one.
  const candidates = wordsIn(await text(`${BASE}/api/search.php?seam=relevant,curiosity`))
    .slice(0, 40);
  let flatWord = null, flatHtml = null;
  for (const w of candidates) {
    const h = await text(`${BASE}/api/word.php?word=${enc(w)}`);
    if (!h.includes('fp-senses')) { flatWord = w; flatHtml = h; break; }
  }
  if (flatWord) {
    check(true, `„${flatWord}" has no sense tree`);
    check(!/<ol class="fp-senses">/.test(flatHtml), 'no empty <ol class="fp-senses"> is emitted');
    const hasDef = /<div class="definition-text">/.test(flatHtml);
    const hasNodef = /<span class="fp-nodef">/.test(flatHtml);
    check(hasDef || hasNodef, 'renders the flat definition, or the "no definition" note');
  } else {
    console.log('  SKIP  no sense-less word found in the first 40 default-view results');
  }

  console.log('\n3. api/word.php still answers 200 with a ui.db that has no senses table');
  // Swaps the real ui.db for a stripped copy for one request, then restores it via an
  // atomic rename either way. Safe against a crash mid-test: the `finally` always runs,
  // and the original file is never deleted, only renamed aside and back.
  // OTIOS_TEST_DATA_DIR points at the runner's private copy of public/data, so this swap
  // never touches the repository's ui.db. Without it (a manual run) the repo copy is used.
  const dataDir      = process.env.OTIOS_TEST_DATA_DIR || path.join(__dirname, '..', 'public', 'data');
  const dbPath       = path.join(dataDir, 'ui.db');
  const backupPath   = dbPath + '.senses-test-backup';
  const strippedPath = dbPath + '.senses-test-stripped';
  let swapped = false;
  try {
    execSync('which sqlite3', { stdio: 'ignore' });
    if (!fs.existsSync(dbPath)) throw new Error('ui.db not found');
    fs.copyFileSync(dbPath, strippedPath);
    execSync(`sqlite3 "${strippedPath}" "DROP TABLE IF EXISTS senses; DROP TABLE IF EXISTS sense_citations;"`);
    fs.renameSync(dbPath, backupPath);
    fs.renameSync(strippedPath, dbPath);
    swapped = true;

    const r = await fetch(`${BASE}/api/word.php?word=bidinea`);
    check(r.status === 200, `still 200 without the senses tables (got ${r.status})`);
    const body = await r.text();
    check(!body.includes('fp-senses'), 'falls back to the flat definition without the tables');
  } catch (e) {
    console.log(`  SKIP  missing-table check (${e.message})`);
  } finally {
    if (swapped) {
      fs.renameSync(dbPath, strippedPath);
      fs.renameSync(backupPath, dbPath);
      // PDO's sqlite driver opens WAL mode, which leaves -wal/-shm siblings behind the
      // db file it queried — clean those up too, or they linger next to the real one.
      for (const suffix of ['', '-wal', '-shm']) {
        try { fs.unlinkSync(strippedPath + suffix); } catch (_) { /* not created */ }
      }
    }
  }

  console.log('\n4. The panel does not overflow horizontally at 320px');
  {
    const deps = require('./lib/deps');
    const { chromium } = deps.loadPlaywright('tests/test_senses.js');
    const browser = await deps.launchChromium('tests/test_senses.js', chromium);
    const ctx = await browser.newContext({ viewport: { width: 320, height: 700 } });
    const page = await ctx.newPage();
    for (const skin of ['paper', 'brutal', 'govuk', 'registru', 'tezaur', 'velin']) {
      await page.goto(`${BASE}/?word=bidinea`, { waitUntil: 'networkidle' });
      await page.evaluate((s) => document.documentElement.setAttribute('data-skin', s), skin);
      const hOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
      check(!hOverflow, `${skin}: no horizontal overflow at 320px`);
    }
    await browser.close();
  }

  console.log(failures === 0 ? '\nAll passed.\n' : `\n${failures} FAILED\n`);
  process.exit(failures === 0 ? 0 : 1);
})();
