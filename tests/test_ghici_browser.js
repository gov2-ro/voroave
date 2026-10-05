// F03 in a real browser: the sense quiz withholds the whole answer body before grading.
//
//   OTIOS_TEST_URL=http://127.0.0.1:8011 node tests/test_ghici_browser.js
//   OTIOS_SHOT_DIR=/some/dir ...      # optional: save screenshots there
//
// jsdom (test_ghici.js) checks attributes. This checks what a browser really does with
// them: computed display, innerText (which skips hidden content), and the Tab order,
// at a desktop and a phone width. Detail requests are forced to a structured word so
// the pane carries senses, expressions, citations and synonyms.
const deps = require('./lib/deps');
const { chromium } = deps.loadPlaywright('tests/test_ghici_browser.js');

const BASE = require('./lib/target').testBase('tests/test_ghici_browser.js');
const SHOTS = process.env.OTIOS_SHOT_DIR || '';
const WORD = 'abraș';

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

(async () => {
  const browser = await deps.launchChromium('tests/test_ghici_browser.js', chromium);
  for (const [name, width, height] of [['desktop', 1280, 900], ['mobile', 390, 844]]) {
    console.log(`\n${name} (${width}px)`);
    const ctx = await browser.newContext({ viewport: { width, height } });
    const page = await ctx.newPage();
    await page.route('**/api/word.php?word=*', route => {
      const u = new URL(route.request().url());
      u.searchParams.set('word', WORD);
      route.continue({ url: u.href });
    });
    await page.goto(BASE + '/ghici?game=sensuri', { waitUntil: 'networkidle' });
    await page.waitForSelector('#panel-pane .fp-title');

    const state = () => page.evaluate(() => {
      const pane = document.getElementById('panel-pane');
      const body = pane.querySelector('.fp-body');
      const sense = pane.querySelector('.sense-text');
      return {
        bodyDisplay: getComputedStyle(body).display,
        bodyBox: body.getBoundingClientRect().height,
        senseText: sense ? sense.textContent.trim().slice(0, 25) : '',
        inner: pane.innerText,
        titleVisible: pane.querySelector('.fp-title').getBoundingClientRect().height > 0,
        marksVisible: pane.querySelector('.fp-btns').getBoundingClientRect().height > 0,
      };
    });

    const before = await state();
    check(before.bodyDisplay === 'none' && before.bodyBox === 0, 'the answer body is not rendered');
    check(before.senseText.length > 5 && !before.inner.includes(before.senseText),
      'the sense text is not in the rendered text');
    check(!/sinonime|citate|expresie/.test(before.inner), 'no synonym, citation or expression label is rendered');
    check(before.titleVisible && before.marksVisible, 'the headword and the marks stay visible');

    // Tab through the page: focus must never land inside the withheld body.
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    let leaked = 0;
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press('Tab');
      leaked += await page.evaluate(() => {
        const a = document.activeElement;
        return a && a.closest && a.closest('#panel-pane .fp-body') ? 1 : 0;
      });
    }
    check(leaked === 0, 'Tab never reaches the withheld body (40 presses)');
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}-before.png` });

    await page.locator('.joc-choice').first().click();
    await page.waitForSelector('#quiz-next');
    const after = await state();
    check(after.bodyDisplay !== 'none' && after.bodyBox > 0, 'the body is rendered after grading');
    check(after.inner.includes(after.senseText), 'the sense text is in the rendered text after grading');
    check(/sinonime/.test(after.inner), 'the synonyms are shown after grading');
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}-after.png` });
    await ctx.close();
  }
  await browser.close();
  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error('harness error:', e); process.exit(2); });
