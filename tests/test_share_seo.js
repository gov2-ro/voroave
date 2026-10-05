// A `?word=` hit ships real, indexable body content — not just a filled <head>.
//
//   php -S 127.0.0.1:8011 -t public tools/dev-router.php &
//   OTIOS_TEST_URL=http://127.0.0.1:8011 node tests/test_share_seo.js
//
// test_share_meta.js already pins the <head> (title/description/canonical/og:*):
// share_meta() filled that in well before this, but #detail-panel shipped as an
// empty div — the definition was injected only client-side, an async second wave a
// crawler is not guaranteed to wait for. This pins the other half: a real <h1> with
// the word, #detail-panel already carrying `panel-open` with non-empty content, and
// a matching JSON-LD DefinedTerm block — all server-rendered, on the very first
// response.
//
// Also pins the row markup landing this same change depended on (§SEO plan, part 1):
// a `.word-row` is now a real `<a href="…?word=…">`, not a bare div a crawler could
// never follow.
const BASE = require('./lib/target').testBase('tests/test_share_seo.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

const text = (url) => fetch(url).then((r) => r.text());
const firstWord = async (qs) => (await text(`${BASE}/api/search.php?${qs}`))
  .match(/data-word="([^"]*)"/)?.[1];

(async () => {
  const w = await firstWord('');

  console.log('\n1. A `?word=` hit renders a real <h1>, not the empty div app.js used to fill');
  const html = await text(`${BASE}/?word=${encodeURIComponent(w)}`);
  const h1 = html.match(/<h1 class="fp-title">([^<]*)<\/h1>/);
  check(!!h1, `<h1 class="fp-title"> is present`);
  check(h1 && h1[1] === w, `<h1> names the word: „${h1 && h1[1]}" = „${w}"`);

  console.log('\n2. #detail-panel carries panel-open with non-empty content, on arrival');
  check(/id="detail-panel" class="word-detail-panel panel-open"/.test(html), '#detail-panel has .panel-open server-side');
  check(html.includes('fp-close'), 'panel body is non-empty (carries the close button)');

  console.log('\n3. A matching JSON-LD DefinedTerm block is in <head>');
  const ld = html.match(/<script type="application\/ld\+json">([^<]*)<\/script>/);
  check(!!ld, 'application/ld+json script is present');
  if (ld) {
    const data = JSON.parse(ld[1]);
    check(data['@type'] === 'DefinedTerm', '@type is DefinedTerm');
    check(data.name === w, `name matches the word: „${data.name}"`);
    check(data.inLanguage === 'ro', 'inLanguage is ro');
    check(data.inDefinedTermSet && data.inDefinedTermSet['@type'] === 'DefinedTermSet',
      'inDefinedTermSet is a DefinedTermSet');
  }

  console.log('\n4. The bare explorer (no ?word=) ships neither');
  const bare = await text(`${BASE}/`);
  check(!/<h1 class="fp-title">/.test(bare), 'no <h1 class="fp-title"> without a word');
  check(!/application\/ld\+json/.test(bare), 'no JSON-LD without a word');
  check(/id="detail-panel" class="word-detail-panel">/.test(bare),
    '#detail-panel has no panel-open class, and is empty');

  console.log('\n5. api/word.php is untouched — its output stays byte-identical');
  const frag = await text(`${BASE}/api/word.php?word=${encodeURIComponent(w)}`);
  check(/<div class="fp-title">/.test(frag), 'the ajax fragment still uses <div class="fp-title">, not <h1>');
  check(!/<h1 class="fp-title">/.test(frag), 'never an <h1> from this endpoint');

  console.log('\n6. Word rows are real links a crawler can follow, not bare divs');
  const rowsHtml = await text(`${BASE}/api/search.php`);
  const rowMatch = rowsHtml.match(/<a class="word-row[^"]*"\s+href="([^"]*)"/);
  check(!!rowMatch, 'a row renders as <a class="word-row …" href="…">');
  check(!!rowMatch && rowMatch[1].includes('/?word='), `row href points at a word page: „${rowMatch && rowMatch[1]}"`);
  check(/hx-get="[^"]*api\/word\.php\?word=/.test(rowsHtml),
    'the row still carries its hx-get, for the ajax path');

  console.log(failures === 0 ? '\nAll passed.\n' : `\n${failures} FAILED\n`);
  process.exit(failures === 0 ? 0 : 1);
})();
