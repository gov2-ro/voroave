// After a search, Tab from the search box lands on the results (backlog: "ux: wordlist
// should be the next tabindex after search box"). In DOM order the shortcuts link, the
// filter button and the sheet's controls come first, so without the handler in app.js a
// keyboard reader walked through the whole filter sheet to reach a word.
//
// Run through the isolated runner: python3 tools/run_tests.py --only "search tab"
'use strict';
const deps = require('./lib/deps');
const { chromium } = deps.loadPlaywright('tests/test_search_tab.js');
const BASE = require('./lib/target').testBase('tests/test_search_tab.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };
const focused = (page) => page.evaluate(() => {
  const e = document.activeElement;
  return { id: e.id, row: e.classList.contains('word-row'), word: e.dataset ? e.dataset.word || '' : '' };
});

(async () => {
  const browser = await deps.launchChromium('tests/test_search_tab.js', chromium);
  for (const width of [1366, 390]) {
    console.log(`\nviewport ${width}px`);
    const page = await (await browser.newContext({ viewport: { width, height: 800 } })).newPage();
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });

    // 1. Empty box: Tab keeps its normal order (does not jump into the list).
    const toggle = await page.$('#search-toggle-btn');
    if (toggle && await toggle.isVisible()) await toggle.click();
    await page.focus('#search');
    await page.keyboard.press('Tab');
    const f0 = await focused(page);
    check(!f0.row, `empty box: Tab follows DOM order (focus on ${f0.id || 'a non-row element'})`);

    // 2. With a query and results: Tab lands on the first result. Leaving the empty
    //    box collapsed it (closeSearchIfEmpty), so reopen it first.
    if (toggle && await toggle.isVisible()) await toggle.click();
    await page.focus('#search');
    await page.fill('#search', 'cal');
    await page.waitForFunction(() => document.querySelectorAll('.word-row').length > 0
      && document.getElementById('search').value === 'cal', null, { timeout: 8000 });
    await page.waitForTimeout(600);                    // let the debounced search swap in
    await page.focus('#search');
    await page.keyboard.press('Tab');
    const f1 = await focused(page);
    const first = await page.$eval('.word-row', (r) => r.dataset.word || '');
    check(f1.row && f1.word === first, `query: Tab lands on the first result („${f1.word}")`);
    check(await page.$eval('.word-row[tabindex="0"]', (r) => r === document.activeElement),
          'the focused row holds the roving tabindex');

    // 3. The arrow keys work from there, and Shift+Tab returns to the box.
    await page.keyboard.press('ArrowDown');
    const f2 = await focused(page);
    check(f2.row && f2.word !== f1.word, `ArrowDown moves to the next word („${f2.word}")`);
    await page.keyboard.press('Shift+Tab');
    const f3 = await focused(page);
    check(f3.id === 'search', 'Shift+Tab from a result returns to the search box');
    check(await page.$eval('#search', (i) => i.value) === 'cal', 'the query is kept');
    await page.close();
  }
  await browser.close();
  console.log(failures ? `\n${failures} FAILED` : '\nall passed');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
