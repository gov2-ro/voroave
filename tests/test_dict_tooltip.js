// The dict-name tooltip (.dict-tooltip, opened by .fp-dicts-toggle in detail.php) is
// `position: fixed`, meant to escape #detail-panel's own `overflow: hidden` and
// .fp-body's scroll clipping. On desktop (>=769px) #detail-panel also carries
// `transform: translateX(-50%)` to centre itself over the list — and any transformed
// ancestor becomes the *containing block* for a `position: fixed` descendant, so the
// tooltip's top/left (computed in real viewport coordinates by store.js) were being
// resolved against the panel's own box instead, landing it wherever the panel happened
// to sit rather than under the toggle. Reported 2026-08-18 via screenshot: the tooltip
// rendered far off in the bottom-right corner of the screen, overlapping unrelated
// list rows. Fixed by reparenting the tooltip to <body> (untransformed) before
// positioning it — see the comment at the `.fp-dicts-toggle` handler in store.js.
//
//   php -S 127.0.0.1:8011 -t public tools/dev-router.php &
//   OTIOS_TEST_URL=http://127.0.0.1:8011 node tests/test_dict_tooltip.js
//
// `bidinea` is the same fixture docs/senses-plan.md uses elsewhere — a real DEX entry
// short enough that its dict-toggle always sits within a default-height panel, so this
// test isn't confounded by the separate (and separately known) issue where a long
// multi-sense entry can push the toggle below .fp-body's scrollable fold.
const deps = require('./lib/deps');
const { chromium } = deps.loadPlaywright('tests/test_dict_tooltip.js');

const BASE = require('./lib/target').testBase('tests/test_dict_tooltip.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

(async () => {
  const browser = await deps.launchChromium('tests/test_dict_tooltip.js', chromium);

  console.log('1. The tooltip renders at its computed position, not offset by #detail-panel\'s transform');
  for (const width of [900, 1100, 1280, 1600]) {
    const ctx = await browser.newContext({ viewport: { width, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/?word=bidinea`, { waitUntil: 'networkidle' });
    const btn = await page.$('.fp-dicts-toggle');
    const box = await btn.boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(200);
    const pos = await page.evaluate(() => {
      const t = document.querySelector('.dict-tooltip');
      const r = t.getBoundingClientRect();
      return {
        hidden: t.hasAttribute('hidden'),
        matches: Math.round(r.x) === parseInt(t.style.left, 10)
          && Math.round(r.y) === parseInt(t.style.top, 10),
      };
    });
    check(!pos.hidden, `${width}px: tooltip opened`);
    check(pos.matches, `${width}px: rendered position matches its computed top/left`);
    await ctx.close();
  }

  console.log('\n2. Reparenting doesn\'t leak: switching words leaves exactly one .dict-tooltip');
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/?word=bidinea`, { waitUntil: 'networkidle' });
    const btn = await page.$('.fp-dicts-toggle');
    const box = await btn.boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(200);
    check(await page.evaluate(() => document.querySelector('.dict-tooltip').parentElement === document.body),
      'first open reparents the tooltip to <body>');

    // Leave it open and switch to a different word without closing it first — the
    // stale, now-orphaned <body>-level tooltip from the word above must be cleaned up,
    // not accumulate across every word ever opened in the session.
    await page.evaluate(() => openWordPanel('puținel'));
    await page.waitForTimeout(400);
    const count = await page.evaluate(() => document.querySelectorAll('.dict-tooltip').length);
    check(count === 1, `exactly one .dict-tooltip survives a word switch (got ${count})`);
    await ctx.close();
  }

  console.log('\n3. Closing the panel hides an open tooltip even after it was reparented to <body>');
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/?word=bidinea`, { waitUntil: 'networkidle' });
    const btn = await page.$('.fp-dicts-toggle');
    const box = await btn.boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(200);
    await page.evaluate(() => closePanel());
    const hidden = await page.evaluate(() => document.querySelector('.dict-tooltip').hasAttribute('hidden'));
    check(hidden, 'tooltip is hidden after closePanel(), regardless of its DOM location');
    await ctx.close();
  }

  await browser.close();
  console.log(failures === 0 ? '\nAll passed.\n' : `\n${failures} FAILED\n`);
  process.exit(failures === 0 ? 0 : 1);
})();
