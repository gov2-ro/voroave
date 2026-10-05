// End-to-end test of the editorial layer: curator picks/demotes (ui.db columns, the
// `respinse` control) and community votes (the `populare` sort).
//
//   php -S localhost:8777 -t public/ &
//   node tests/test_editorial.js
//
// Override the target with OTIOS_TEST_URL. Read-only against ui.db, but it creates one
// anonymous user and writes annotations to app.db, so point it at a dev instance.
//
// The two properties worth pinning here are the ones a later change will otherwise
// break quietly, because both fail *invisibly* — a missing word looks like a word that
// was never a candidate:
//
//   1. Community votes never remove a word from any result set. Identity is an
//      anonymous device token, so if votes could subtract, hiding a word would be
//      cheaper than publishing a list. They may only reorder.
//   2. editor_demote subtracts only while `editorial=hide`, and never inside a
//      playlist — a shared list of twenty words must not arrive as eleven.
const BASE = require('./lib/target').testBase('tests/test_editorial.js');

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

const rows = (html) => [...html.matchAll(/data-word="([^"]+)"/g)].map((m) => m[1]);
const search = (f, qs) => f(`${BASE}/api/search.php?${qs}`).then((r) => r.text()).then(rows);

const mark = (word, patch) => Object.assign(
  { word, bookmarked: false, note: '', tags: [], updated_at: new Date().toISOString(), deleted: false },
  patch
);
const annotate = (f, changes) => f(`${BASE}/api/sync.php`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ since: 0, changes }),
}).then((r) => r.json());

(async () => {
  const u = makeJar();

  console.log('\n1. The `respinse` control is three-state and consistent');
  const hide = await search(u, 'word_tier=forgotten&editorial=hide');
  const show = await search(u, 'word_tier=forgotten&editorial=show');
  const only = await search(u, 'word_tier=forgotten&editorial=only');

  check(show.length > 0, `„cu" returns words (${show.length} on page 1)`);
  if (only.length === 0) {
    console.log('  SKIP  no editor_demote rows in this ui.db — run tools/export_editorial.py');
  } else {
    check(only.every((w) => !hide.includes(w)),
      '„doar" and „fără" are disjoint — nothing appears in both');
    check(only.every((w) => show.includes(w)) || show.length >= 250,
      '„doar" is a subset of „cu" (or „cu" is page-capped)');
  }

  console.log('\n2. Links from before the rare tab was removed still resolve');
  // `word_tier` is forced to 'forgotten' now, so an old `?word_tier=rare_in_use` link
  // lands on the list rather than returning nothing. The failure it replaces was worse:
  // the class controls were hidden on that tab, so carrying „doar" across returned 0
  // words with nothing on the page to explain why.
  const legacy = await search(u, 'word_tier=rare_in_use&editorial=only');
  const here   = await search(u, 'editorial=only');
  check(legacy.length === here.length,
    `?word_tier=rare_in_use is ignored, not empty (${legacy.length} words)`);

  console.log('\n2b. The modern-usage filter partitions the list');
  const [m0, m1, m2] = await Promise.all(
    ['modern=0', 'modern=1', 'modern=2'].map((q) => search(u, q)));
  check(m0.length > 0 && m2.length > 0, `bands are populated (${m0.length} / … / ${m2.length})`);
  check(!m0.some((w) => m2.includes(w)), 'a word cannot be both „fără urme" and „în circulație"');

  console.log('\n2c. „în spate" demotes — it must not remove anything');
  // The whole point of the 2026-08-11 change: editor_demote sinks a word to the end of
  // the order instead of dropping it from the result set. If someone turns this back into
  // a WHERE clause, these two counts diverge and this fails.
  const back = await search(u, 'editorial=back');
  const norm = await search(u, 'editorial=show');
  check(back.length === norm.length,
    `„în spate" and „normal" return the same words (${back.length} vs ${norm.length})`);
  if (only.length) {
    check(!back.slice(0, 20).some((w) => only.includes(w)),
      'no demoted word appears in the first 20 rows under „în spate"');
  }

  console.log('\n3. A playlist is immune to the demote');
  // Take demoted words straight from „doar" and ask for them back as a playlist.
  if (only.length >= 3) {
    const picked = only.slice(0, 3);
    const packed = await u(`${BASE}/api/pack.php?words=${picked.map(encodeURIComponent).join(',')}`)
      .then((r) => r.json()).catch(() => null);
    const qs = packed && packed.packed
      ? `w=${encodeURIComponent(packed.packed)}&editorial=hide`
      : `words=${picked.map(encodeURIComponent).join(',')}&editorial=hide`;
    const back = await search(u, qs);
    check(back.length === picked.length,
      `${picked.length} demoted words shared as a playlist arrive as ${back.length}`);
  } else {
    console.log('  SKIP  need 3 demoted words');
  }

  console.log('\n4. Votes reorder but never remove');
  const beforeIds = await search(u, 'word_tier=forgotten&sort=populare');
  check(beforeIds.length > 0, `populare returns words (${beforeIds.length})`);

  // Bury a word under this user's meh, then confirm it is still in the result set.
  const victim = beforeIds[Math.min(5, beforeIds.length - 1)];
  await annotate(u, [mark(victim, { tags: ['meh'] })]);
  const afterMeh = await search(u, 'word_tier=forgotten&sort=populare');
  check(afterMeh.includes(victim),
    `„${victim}" is still present after a meh vote (rank ${afterMeh.indexOf(victim) + 1}, was ${beforeIds.indexOf(victim) + 1})`);
  check(afterMeh.indexOf(victim) >= beforeIds.indexOf(victim),
    `„${victim}" did not move up after a meh vote`);

  // And a fav lifts it without removing anything.
  const total = (qs) => u(`${BASE}/api/search.php?${qs}`).then((r) => r.text()).then(rows).then((r) => r.length);
  await annotate(u, [mark(victim, { bookmarked: true, tags: [] })]);
  const afterFav = await search(u, 'word_tier=forgotten&sort=populare');
  check(afterFav.includes(victim), `„${victim}" is still present after a fav vote`);
  check(afterFav.length === beforeIds.length,
    `the result set is the same size after voting (${afterFav.length} vs ${beforeIds.length})`);

  console.log('\n5. Sorting never changes membership, only order');
  const byQuality = await search(u, 'word_tier=forgotten&sort=quality');
  const byPopular = await search(u, 'word_tier=forgotten&sort=populare');
  const sameSet = byQuality.length === byPopular.length
    && [...byQuality].sort().join('|') === [...byPopular].sort().join('|');
  // Page 1 of two different orders need not hold the same words once the list is longer
  // than a page — so this only has to hold when the whole list fits on one page.
  if (byQuality.length < 250) {
    check(sameSet, 'quality and populare return the same words in a different order');
  } else {
    check(byPopular.length === byQuality.length, 'both sorts fill the same page size');
  }

  // Clean up so a re-run starts from the same place.
  await annotate(u, [mark(victim, { deleted: true })]);

  console.log(failures ? `\n${failures} failure(s)` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})();
