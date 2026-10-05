// A shared `?word=` link lands on the word — the list behind the panel included.
//
//   php -S 127.0.0.1:8011 -t public tools/dev-router.php &
//   OTIOS_TEST_URL=http://127.0.0.1:8011 node tests/test_share_view.js
//
// The panel was never the problem: `api/word.php` is a bare `WHERE word = ?` and no
// filter has ever reached it, which is what §1 pins. Everything *around* the panel was.
// 15,803 of the 18,270 words are outside the default view — 11,193 on the seam alone —
// so a shared `curiosity` word opened over a list that did not contain it, and closing
// the panel stranded the reader on a page whose rail named filters they never set as the
// reason the word had gone. That is the worst answer this site can give about a word it
// has, and it is the same failure `test_search_scope.js` pins for a typed query.
//
// Two halves, and neither is enough on its own:
//
//   share_relax_params()  makes the word *eligible* — it names which of the sheet's
//                         defaults are hiding this particular word, and app.js ticks
//                         exactly those before htmx fires the first search
//   pin_order_sql()       makes it *visible* — with the seam relaxed a `curiosity` word
//                         still ranks 2,468–13,660 under the default sort, and a page is
//                         250 rows, so relaxing alone would move nothing anyone can see
//
// The sample words are read out of the API rather than hardcoded, so a rebuild that
// reflags a word cannot turn this into a test of the fixture.
const BASE = require('./lib/target').testBase('tests/test_share_view.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

const enc  = encodeURIComponent;
const text = (url) => fetch(url).then((r) => r.text());

// The relax map as the browser sees it, off the page's own boot script.
const relaxOf = async (word) => {
  const html = await text(`${BASE}/?word=${enc(word)}`);
  const m = html.match(/OTIOS_SHARE_RELAX = ([^;\n]*)/);
  return m ? JSON.parse(m[1]) : null;
};

const search = (qs) => text(`${BASE}/api/search.php?${qs}`);
const wordsIn = (html) => (html.match(/data-word="([^"]*)"/g) || [])
  .map((s) => s.slice(11, -1));
const totalIn = (html) => {
  const m = html.match(/id="result-count"[^>]*>([\d., ]*)</);
  return m ? parseInt(m[1].replace(/[^\d]/g, ''), 10) : NaN;
};
const firstWord = async (qs) => (await search(qs)).match(/data-word="([^"]*)"/)?.[1];

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

(async () => {
  // Four words, each hidden from the default view by a different control — or by none.
  // `only` on one class still subtracts the classes left on `hide`, so each of these is
  // guaranteed to carry exactly the one flag it was selected for.
  const inView    = await firstWord('');
  const curiosity = await firstWord('seam=curiosity');
  const variant   = await firstWord('seam=curiosity&variants=only');
  const regional  = await firstWord('seam=relevant&regional=only');

  console.log('\n1. The panel ignores every filter — it always did, and must keep doing');
  for (const [w, label] of [[inView, 'in the default view'],
                            [curiosity, 'curiosity seam'],
                            [variant, 'a variant spelling'],
                            [regional, 'a regionalism']]) {
    const r = await fetch(`${BASE}/api/word.php?word=${enc(w)}`);
    check(r.status === 200, `${label.padEnd(22)} → 200 for „${w}"`);
  }

  console.log('\n2. The relax map names exactly the defaults hiding that word');
  check(same(await relaxOf(inView), {}),
    `„${inView}" is already visible → nothing to relax`);
  check(same(await relaxOf(curiosity), { seam: 'relevant,curiosity' }),
    `„${curiosity}" → seam only`);
  check(same(await relaxOf(variant), { seam: 'relevant,curiosity', variants: 'show' }),
    `„${variant}" → seam + variants`);
  check(same(await relaxOf(regional), { regional: 'show' }),
    `„${regional}" → regional only, its seam untouched`);

  console.log('\n3. The seam is added, never swapped');
  // Arriving at one curiosity word is not a reason to take the default list away. The
  // map says `relevant,curiosity`, so the reader keeps the 2,467 and gains the rest.
  const relaxed = await relaxOf(curiosity);
  check(relaxed.seam.split(',').includes('relevant'),
    `„${relaxed.seam}" keeps the default seam alongside the word's`);
  const dfltTotal   = totalIn(await search(''));
  const widerTotal  = totalIn(await search(`seam=${enc(relaxed.seam)}`));
  check(widerTotal > dfltTotal, `${dfltTotal} → ${widerTotal} words, a superset`);

  console.log('\n4. Nothing is relaxed for a word that is not a word');
  // Same property as share_meta()'s fallback, and for the same reason: the param is
  // attacker-supplied. A junk `?word=` must not reshape the list either.
  for (const junk of ['nonexistentword', '', '<script>alert(1)</script>', 'a'.repeat(200)]) {
    check(same(await relaxOf(junk), {}), `„${junk.slice(0, 24)}" → {}`);
  }

  console.log('\n5. Relax + pin puts the shared word first');
  for (const [w, qs] of [[curiosity, `seam=relevant,curiosity`],
                         [variant,   `seam=relevant,curiosity&variants=show`],
                         [regional,  `regional=show`],
                         [inView,    ``]]) {
    const first = await firstWord(`pin=${enc(w)}&${qs}`);
    check(first === w, `„${w}" is row 1 of ${totalIn(await search(qs))}`);
  }

  console.log('\n6. The pin is an ORDER BY, not a WHERE');
  // It moves a row the filters already admit; it never admits one. Otherwise the list
  // would quietly contain a word its own controls say it should not — the mirror image
  // of the bug this file is about, and just as unexplainable from the page.
  const pinnedNarrow = await search(`pin=${enc(curiosity)}`);
  check(!wordsIn(pinnedNarrow).includes(curiosity),
    `„${curiosity}" pinned but not relaxed → still absent`);
  check(totalIn(pinnedNarrow) === dfltTotal,
    `count unchanged by the pin: ${totalIn(pinnedNarrow)} = ${dfltTotal}`);

  console.log('\n7. Pinned once, on page 1 — not at the top of every page');
  // The pin is part of one global order that every page request repeats (the hidden
  // #share-word input rides inside the form, so `next_url` carries it). Were it applied
  // per page, the word would head page 2 and page 3 as well.
  const qs = `pin=${enc(curiosity)}&seam=relevant,curiosity`;
  for (const page of [1, 2, 3]) {
    const n = wordsIn(await search(`${qs}&page=${page}`)).filter((x) => x === curiosity).length;
    check(n === (page === 1 ? 1 : 0), `page ${page}: appears ${n}×`);
  }
  check((await search(qs)).includes(`pin=${enc(curiosity)}`),
    'the load-more URL carries the pin into the next page');

  console.log('\n8. The pin outranks the curator demotion');
  // `editorial=back` sinks a demoted word to the end of the order — about eleven pages
  // down. A word someone shared has to arrive on top of that too, so pin_order_sql()
  // is prefixed ahead of demote_order_sql().
  const demoted = await firstWord('editorial=only');
  if (demoted) {
    check(await firstWord(`pin=${enc(demoted)}`) === demoted,
      `„${demoted}" is demoted and still lands first when shared`);
  } else {
    console.log('  SKIP  no curator-demoted word in this build');
  }

  console.log('\n9. The pin input is named `pin`, and clicking a word still opens it');
  // The regression this section exists for: the pin rode in a hidden input named `word`,
  // inside #filter-form. `hx-include` is inherited in htmx, so `#word-list`'s
  // `hx-include="#filter-form, #search"` applies to every `.word-row` in it — and a row's
  // own request is `api/word.php?word=<its word>`. The form appended a second, empty
  // `word=`; PHP keeps the last occurrence, so the panel endpoint saw `''` and answered
  // 400. Every word on the site stopped opening, with nothing in the diff naming
  // `word.php`. Both halves are checked: the input's name, and the request it corrupted.
  const home = await text(`${BASE}/`);
  const pinInput = home.match(/<input[^>]*id="share-word"[^>]*>/)?.[0] || '';
  check(/name="pin"/.test(pinInput), 'the hidden pin input posts as `pin`');
  check(!/name="word"/.test(pinInput), 'and never as `word`, which the rows already use');

  // The row's own URL, taken from the markup the list actually renders, with every
  // hidden input of #filter-form appended empty behind it — which is what hx-include
  // does to it in the browser. Any of them named `word` overwrites the row's own.
  const rowUrl  = (await search('')).match(/hx-get="([^"]*word\.php[^"]*)"/)[1].replace(/&amp;/g, '&');
  const hiddens = [...home.matchAll(/<input type="hidden"[^>]*name="([^"]*)"/g)].map((m) => m[1]);
  check(!hiddens.includes('word'),
    `no hidden input shadows the row's own param (${hiddens.join(', ')})`);
  const asRowSends = await fetch(
    `${BASE}${rowUrl}&${hiddens.map((n) => n + '=').join('&')}`);
  check(asRowSends.status === 200,
    `a row's request survives the form riding along with it (${asRowSends.status})`);

  console.log(failures === 0 ? '\nAll passed.\n' : `\n${failures} FAILED\n`);
  process.exit(failures === 0 ? 0 : 1);
})();
