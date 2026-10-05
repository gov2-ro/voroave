// A typed query searches the whole table — no filters, no playlist.
//
//   php -S localhost:8777 -t public/ &
//   node tests/test_search_scope.js
//
// Override the target with OTIOS_TEST_URL. Read-only against ui.db; it creates one
// anonymous user (§3 needs a user with no marks) but writes nothing.
//
// Why this is pinned rather than left to the reading: the failure it guards against is
// invisible. The defaults leave 2,682 of 18,270 words standing — `relevant` seam only,
// no regionalisms, no variants, no old spellings, no diminutives — so before this change
// a search for `-țiune` words returned 29 of the 406 that exist, and a search for
// `celșag` returned nothing at all. „Niciun rezultat" reads as "this project has never
// heard of that word", which is the opposite of what the project is for, and no control
// on the page was set by the reader or pointed at as the cause.
//
// Three properties, each of which a later change will otherwise break quietly:
//
//   1. Every filter in the sheet is dropped while `q` is non-empty — including `marks`,
//      which lives in the same sheet and would otherwise be the one row still biting.
//   2. `q` beats a playlist. A shared list plus a query is a search of everything, not a
//      search inside the list; the sheet says which is in force (setSearchMode, app.js).
//   3. It stays scoped to `q`. With the box empty, the filters are back — this must not
//      turn into "the filter sheet does nothing".
const BASE = require('./lib/target').testBase('tests/test_search_scope.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

function makeJar() {
  const jar = {};
  return async (url, opts = {}) => {
    const headers = Object.assign({}, opts.headers);
    const cookie = Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; ');
    if (cookie) headers.Cookie = cookie;
    const res = await fetch(url, Object.assign({ redirect: 'manual' }, opts, { headers }));
    for (const sc of (res.headers.getSetCookie ? res.headers.getSetCookie() : [])) {
      const [pair] = sc.split(';');
      const i = pair.indexOf('=');
      jar[pair.slice(0, i)] = pair.slice(i + 1);
    }
    return res;
  };
}

// The page is capped at PAGE_SIZE rows, so membership questions have to be asked of the
// total the partial swaps out of band, not of the rows on screen.
const rows  = (html) => [...html.matchAll(/data-word="([^"]+)"/g)].map((m) => m[1]);
const total = (html) => {
  const m = html.match(/id="result-count"[^>]*>([\d., ]*)</);
  return m ? parseInt(m[1].replace(/[^\d]/g, ''), 10) : NaN;
};
const get = (f, qs) => f(`${BASE}/api/search.php?${qs}`).then((r) => r.text());

// Query fragments picked because their matches are spread across the classes the
// defaults hide: `-țiune` is the archaic-spelling rule's own shape, and „iță" catches
// diminutives and regionalisms.
const Q = 'iune';

(async () => {
  const u = makeJar();

  console.log('\n1. A query ignores every filter in the sheet');
  const plain = await get(u, `q=${Q}`);
  const found = total(plain);
  check(found > 0, `„${Q}" matches ${found} words`);

  const variants = {
    'seam (both ticked)':   `q=${Q}&seam%5B%5D=relevant&seam%5B%5D=curiosity`,
    'seam (curiosity)':     `q=${Q}&seam%5B%5D=curiosity`,
    'variants=only':        `q=${Q}&variants=only`,
    'deverbal=only':        `q=${Q}&deverbal=only`,
    'regional=only':        `q=${Q}&regional=only`,
    'diminutives=hide':     `q=${Q}&diminutives=hide`,
    'verdict=extinct':      `q=${Q}&verdict%5B%5D=extinct`,
    'tier=high':            `q=${Q}&tier%5B%5D=high`,
    'hist_min=500':         `q=${Q}&hist_min=500`,
    'attested_before=1900': `q=${Q}&attested_before=1900`,
    'word_tier=rare_in_use': `q=${Q}&word_tier=rare_in_use`,
  };
  for (const [label, qs] of Object.entries(variants)) {
    const n = total(await get(u, qs));
    check(n === found, `${label}: ${n} — same ${found} matches`);
  }

  console.log('\n2. …including the marks filter, and including a playlist');
  // This user has no annotations at all, so a live `marks` clause would return 0.
  const marked = total(await get(u, `q=${Q}&marks=bookmarked`));
  check(marked === found, `marks=bookmarked on a user with no marks: ${marked}`);

  // A playlist of one word, plus a query that word does not match. The query wins, so the
  // answer is the query's matches — not the one word, and not their (empty) intersection.
  const first  = rows(await get(u, 'sort=alpha'))[0];
  const packed = await u(`${BASE}/api/pack.php?words=${encodeURIComponent(first)}`)
    .then((r) => r.json()).catch(() => null);
  const listQs = packed && packed.packed
    ? `w=${encodeURIComponent(packed.packed)}`
    : `words=${encodeURIComponent(first)}`;
  check(total(await get(u, listQs)) === 1, `the playlist alone is 1 word („${first}")`);
  const both = total(await get(u, `${listQs}&q=${Q}`));
  check(both === found, `playlist + q=${Q}: ${both} — the query, not the list`);

  console.log('\n3. It is scoped to `q` — the filters still work with the box empty');
  const dflt  = total(await get(u, ''));
  // Every class switched to `show`, so `wide` means the whole table. A class missing
  // from this list quietly turns it into "the whole table minus that class", and the
  // `found <= wide` check below then compares a query against a filtered base.
  const wide  = total(await get(u, 'seam%5B%5D=relevant&seam%5B%5D=curiosity&regional=show&variants=show&deverbal=show&diminutives=show'));
  check(dflt > 0 && wide > dflt,
    `defaults show ${dflt} of ${wide} — the sheet still subtracts when nothing is typed`);
  check(found <= wide, `„${Q}" (${found}) is searched against the whole table (${wide})`);

  console.log('\n4. The query itself still filters');
  check(total(await get(u, 'q=zzzzzz')) === 0, 'a query nothing matches returns 0, not everything');
  const bare = total(await get(u, 'q=otios'));
  const dia  = total(await get(u, `q=${encodeURIComponent('oțios')}`));
  check(bare > 0 && bare === dia, `diacritics stay optional: „otios" ${bare} = „oțios" ${dia}`);

  console.log(failures ? `\n${failures} FAILED` : '\nAll passed');
  process.exit(failures ? 1 : 0);
})();
