// The class controls in the filter sheet, over the real endpoint.
//
//   php -S 127.0.0.1:8011 -t public tools/dev-router.php &
//   OTIOS_TEST_URL=http://127.0.0.1:8011 node tests/test_class_filters.js
//
// The thing most worth pinning here is that **`variants` is one control over three
// columns** (variant_like / archaic_spelling / dex_variant) and that every superseded
// spelling of the params that used to be their own rows still resolves onto it. A link
// someone shared before the bundle must not silently stop filtering.
const BASE = require('./lib/target').testBase('tests/test_class_filters.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

const total = (html) => {
  const m = html.match(/id="result-count"[^>]*>([\d., ]*)</);
  return m ? parseInt(m[1].replace(/[^\d]/g, ''), 10) : NaN;
};
const count = (qs) => fetch(`${BASE}/api/search.php?${qs}`).then((r) => r.text()).then(total);

(async () => {
  console.log('\n1. The bundle is one control over three columns');
  const dflt = await count('');
  const show = await count('variants=show');
  const only = await count('variants=only');
  check(dflt > 0 && show > dflt, `defaults ${dflt}, „cu variante" ${show}`);
  check(only > 0, `„doar variante" is ${only} words, not empty`);
  check(dflt + only === show,
    `the three states partition cleanly: ${dflt} + ${only} = ${show}`);

  console.log('\n2. Every superseded spelling lands on the bundle');
  // `spellings` and `dexvar` were their own rows; `show_*=1` are checkbox-era links.
  // All of them predate the bundle and all were shareable.
  for (const [qs, expect, label] of [
    ['spellings=show',   show, 'spellings=show'],
    ['dexvar=show',      show, 'dexvar=show'],
    ['spellings=only',   only, 'spellings=only'],
    ['dexvar=only',      only, 'dexvar=only'],
    ['show_variants=1',  show, 'show_variants=1  (checkbox era)'],
    ['show_spellings=1', show, 'show_spellings=1 (checkbox era)'],
  ]) {
    const n = await count(qs);
    check(n === expect, `${label.padEnd(32)} → ${n} (= ${expect})`);
  }

  console.log('\n3. An explicit value beats an alias');
  check(await count('variants=hide&spellings=show') === dflt,
    'variants=hide wins over spellings=show');

  console.log('\n4. Each remaining class still subtracts on its own');
  for (const name of ['regional', 'deverbal', 'diminutives']) {
    const withIt = await count(`${name}=show`);
    const onlyIt = await count(`${name}=only`);
    check(withIt > dflt, `${name}=show adds ${withIt - dflt} words`);
    check(onlyIt > 0 && dflt + onlyIt === withIt,
      `${name}: ${dflt} + ${onlyIt} = ${withIt}`);
  }

  console.log('\n5. `only` across classes is a union, not an intersection');
  const both = await count('variants=only&deverbal=only');
  const vOnly = only;
  const dOnly = await count('deverbal=only');
  check(both >= Math.max(vOnly, dOnly),
    `„doar" on two classes is their union (${both} >= max(${vOnly}, ${dOnly}))`);

  console.log('\n6. `editorial` demotes rather than subtracts');
  check(await count('editorial=show') === dflt,
    'editorial=show returns the same count — it only reorders');

  console.log(failures ? `\n${failures} FAILED\n` : '\nAll checks passed\n');
  process.exit(failures ? 1 : 0);
})();
