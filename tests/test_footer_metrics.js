// `--statusbar-h` is a *reservation*, and this checks it against reality.
//
//   php -S 127.0.0.1:8011 -t public tools/dev-router.php &
//   OTIOS_TEST_URL=http://127.0.0.1:8011 node tests/test_footer_metrics.js
//
// Needs playwright. Skips cleanly when it is not installed, like test_ghici.js does
// without jsdom — a missing dev dependency should not read as a failure.
//
// On mobile the footer is `position: fixed`, so the body's bottom padding, the detail
// sheet's `bottom` and the toast's all reserve space for it from that one token. Get it
// too small and the last row of the list sits under the bar; too large and there is a
// band of blank page above it. Both were live on 2026-08-12: 49px of dead space at
// ≤480px and 56px at 481–710px, against tiers written for a wrap that no longer happens.
//
// The bar's height is a function of viewport width AND text scale AND skin, and it moves
// by *reflow* — one line at 540px/100%, two at 540px/125% — so no set of CSS constants
// covers the matrix. prefs.js measures the rendered bar and writes the token back. This
// is the test that says the measurement is actually right, across the matrix that broke
// every constant anyone tried.
const deps = require('./lib/deps');
const { chromium } = deps.loadPlaywright('tests/test_footer_metrics.js');

const BASE = process.env.OTIOS_TEST_URL || 'http://localhost:8777';
const SKINS  = ['paper', 'brutal', 'govuk', 'registru', 'tezaur', 'velin'];
const WIDTHS = [320, 390, 479, 540, 768];
const SCALES = ['100', '125', '150'];

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

(async () => {
  const browser = await deps.launchChromium('tests/test_footer_metrics.js', chromium);

  // One context, one page, reused across the matrix. A fresh context per combination
  // is ~90 browser launches and pushed this past two minutes; skin and text scale are
  // just attributes on <html>, so they can be swapped in place. `data-skin` is what the
  // stylesheets key on and `style.fontSize` is what the A−/A+ stepper sets, which is
  // exactly what the pre-paint boot script does from localStorage on a real load.
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } });
  const page = await ctx.newPage();
  let loaded = null;

  const measure = async (skin, width, scale, path = '/') => {
    if (loaded !== path) { await page.goto(BASE + path, { waitUntil: 'networkidle' }); loaded = path; }
    await page.setViewportSize({ width, height: 800 });
    await page.evaluate(([s, z]) => {
      document.documentElement.setAttribute('data-skin', s);
      document.documentElement.style.fontSize = z + '%';
    }, [skin, scale]);
    // Two frames: one for the restyle, one for the ResizeObserver that follows it.
    await page.evaluate(() => new Promise((r) =>
      requestAnimationFrame(() => requestAnimationFrame(r))));
    return page.evaluate(() => {
      const sb = document.getElementById('status-bar');
      if (!sb) return null;
      return {
        bar: Math.round(sb.getBoundingClientRect().height),
        reserved: Math.round(parseFloat(getComputedStyle(document.body).paddingBottom)),
        hOverflow: sb.scrollWidth > sb.clientWidth + 1,
        fixed: getComputedStyle(sb).position === 'fixed',
      };
    });
  };

  console.log('\n1. The reservation always covers the bar — 6 skins × 5 widths × 3 scales');
  let under = 0, waste = 0, worst = null, n = 0;
  for (const skin of SKINS) for (const w of WIDTHS) for (const s of SCALES) {
    const m = await measure(skin, w, s);
    n++;
    if (m.bar > m.reserved) {
      under++;
      console.log(`     under-reserved: ${skin} ${w}px @${s}% — bar ${m.bar} > reserved ${m.reserved}`);
    }
    const dead = m.reserved - m.bar;
    if (dead > waste) { waste = dead; worst = `${skin} ${w}px @${s}%`; }
  }
  check(under === 0, `${n} combinations, none put the list under the bar`);
  // 8px of slack is fine; the tiers this replaced were 49 and 56.
  check(waste <= 8, `worst over-reservation is ${waste}px (${worst})`);

  console.log('\n2. Nothing in the bar is clipped or overflowing');
  let clipped = 0;
  for (const skin of SKINS) for (const w of [320, 390, 768]) {
    const m = await measure(skin, w, '125');
    if (m.hOverflow) { clipped++; console.log(`     ${skin} ${w}px scrolls horizontally`); }
  }
  check(clipped === 0, 'no horizontal overflow in the fixed bar');

  console.log('\n3. The measurement settles — no observer feedback loop');
  // The bar must not take its own height from the token prefs.js writes, or the two
  // chase each other. Watch the token across 30 frames after a reflowing resize.
  await measure('paper', 390, '100');
  await page.setViewportSize({ width: 540, height: 800 });
  // Let the ResizeObserver apply the reflow once. Sampling from the resize itself catches
  // the stale value in frame 1 and reports "unsettled" on a slow run. A real feedback loop
  // still keeps changing the token for all 30 frames after this wait, so it still fails.
  await page.waitForTimeout(300);
  const seen = await page.evaluate(async () => {
    const vals = [];
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => requestAnimationFrame(r));
      vals.push(getComputedStyle(document.documentElement)
        .getPropertyValue('--statusbar-h').trim());
    }
    return [...new Set(vals)];
  });
  check(seen.length === 1, `token settled on ${JSON.stringify(seen)} across 30 frames`);

  console.log('\n4. ghici reserves nothing — it hides the bar on a phone');
  const g = await measure('paper', 390, '100', '/ghici');
  check(g === null || g.reserved === 0,
    `ghici reserves ${g === null ? 'n/a (no bar)' : g.reserved + 'px'}`);

  console.log('\n5. On desktop the bar is in flow and reserves nothing');
  const d = await measure('paper', 1440, '100');
  check(!d.fixed, 'bar is not fixed at 1440px');
  check(d.reserved === 0, 'body reserves 0 — the bar takes its own space');

  await browser.close();
  console.log(failures ? `\n${failures} FAILED\n` : '\nAll checks passed\n');
  process.exit(failures ? 1 : 0);
})();
