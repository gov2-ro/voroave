// End-to-end test of the lists API (api/lists.php + api/pack.php + api/sync.php).
//
//   php -S localhost:8777 -t public/ &
//   node tests/test_lists_api.js
//
// Override the target with OTIOS_TEST_URL. Writes to the real app.db, so point it at
// a dev instance, not production. Each run creates two fresh anonymous users (one per
// cookie jar) and leaves their lists behind.
const BASE = require('./lib/target').testBase('tests/test_lists_api.js');

function makeJar() {
  const jar = {};
  return async (url, opts = {}) => {
    const headers = Object.assign({}, opts.headers);
    const cookie = Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; ');
    if (cookie) headers.Cookie = cookie;
    const res = await fetch(url, Object.assign({}, opts, { headers }));
    for (const sc of (res.headers.getSetCookie ? res.headers.getSetCookie() : [])) {
      const [pair] = sc.split(';');
      const i = pair.indexOf('=');
      jar[pair.slice(0, i)] = pair.slice(i + 1);
    }
    return res;
  };
}

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

const post = (f, path, body) => f(`${BASE}${path}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}).then(async (r) => ({ status: r.status, body: await r.json() }));

const get = (f, path) => f(`${BASE}${path}`).then(async (r) => ({ status: r.status, body: await r.json() }));

const lists = (f, body) => post(f, '/api/lists.php', body);

// Mark words via the same path the browser uses, so the bucket is built from real
// annotations rather than a fixture.
const annotate = (f, changes) => post(f, '/api/sync.php', { since: 0, changes });
const mark = (word, patch) => Object.assign(
  { word, bookmarked: false, note: '', tags: [], updated_at: new Date().toISOString(), deleted: false },
  patch
);

(async () => {
  const f = makeJar();

  // Real words, taken from whatever this ui.db actually holds — the API filters
  // against it, so invented words would silently produce empty lists.
  const search = await f(`${BASE}/api/search.php?page=1`).then((r) => r.text());
  const words = [...search.matchAll(/data-word="([^"]+)"/g)].map((m) => m[1]).slice(0, 3);

  console.log('\n0. Fixture');
  check(words.length === 3, `three words pulled from ui.db (${words.join(', ')})`);
  if (words.length < 3) { console.log('\nCannot continue without words.'); process.exit(1); }

  console.log('\n1. pack.php round-trips');
  const packed = await post(f, '/api/pack.php', { words });
  check(packed.body.count === 3, `packs 3 words → ${packed.body.w}`);
  const unpacked = await get(f, `/api/pack.php?w=${encodeURIComponent(packed.body.w)}`);
  check(JSON.stringify(unpacked.body.words) === JSON.stringify(words), 'unpacks to the same words, in order');
  check(packed.body.w.length < words.join(',').length, 'packed form is shorter than the plaintext one');

  const badVersion = await get(f, '/api/pack.php?w=9.1.2');
  check(badVersion.body.count === 0, 'unknown version decodes to nothing');

  console.log('\n2. search.php honours ?w=');
  const html = await f(`${BASE}/api/search.php?w=${encodeURIComponent(packed.body.w)}`).then((r) => r.text());
  const shown = [...html.matchAll(/data-word="([^"]+)"/g)].map((m) => m[1]);
  check(shown.length === 3 && words.every((w) => shown.includes(w)), 'returns exactly the packed words');

  const empty = await f(`${BASE}/api/search.php?w=9.1.2`).then((r) => r.text());
  check(!/data-word="/.test(empty), 'an undecodable ?w= yields no rows, not all 25k');

  // A curated list is not filtered again. The default view is seam=relevant, so a
  // `curiosity` word is one the filters would drop — the recipient of a shared list
  // must still see it, or the list silently shrinks between sender and reader.
  const curio = await f(`${BASE}/api/search.php?seam=curiosity`).then((r) => r.text());
  const hidden = (curio.match(/data-word="([^"]+)"/) || [])[1];
  if (hidden) {
    const mixed = await post(f, '/api/pack.php', { words: [words[0], hidden] });
    const withDefaults = await f(
      `${BASE}/api/search.php?w=${encodeURIComponent(mixed.body.w)}` +
      '&seam=relevant&diminutives=hide&word_tier=forgotten').then((r) => r.text());
    const got = [...withDefaults.matchAll(/data-word="([^"]+)"/g)].map((m) => m[1]);
    check(got.includes(hidden) && got.includes(words[0]),
          `filters are ignored inside a playlist (${hidden} survives seam=relevant)`);
  } else {
    check(false, 'could not find a curiosity-seam word to test playlist filtering');
  }

  console.log('\n3. publish_bucket reads the bucket server-side');
  const noBucket = await lists(f, { action: 'publish_bucket', bucket: 'nope' });
  check(noBucket.status === 400, 'unknown bucket rejected');

  const needsName = await lists(f, { action: 'publish_bucket', bucket: 'fav' });
  check(needsName.status === 409 && needsName.body.error === 'nickname_required',
        'publishing without a nickname is refused');

  await post(f, '/api/profile.php', { nickname: 'tester' });

  const emptyBucket = await lists(f, { action: 'publish_bucket', bucket: 'fav' });
  check(emptyBucket.status === 200 && emptyBucket.body.items === 0,
        'an empty bucket publishes as an empty list rather than erroring');

  await annotate(f, [mark(words[0], { bookmarked: true }), mark(words[1], { bookmarked: true })]);
  const filled = await lists(f, { action: 'publish_bucket', bucket: 'fav' });
  check(filled.body.list.item_count === 2, 'two bookmarks → item_count 2');
  check(filled.body.list.id === emptyBucket.body.list.id, 're-publishing reuses the same list');
  check(filled.body.list.source_tag === 'fav', 'source_tag records the bucket');

  console.log('\n4. refresh re-reads the bucket');
  await annotate(f, [mark(words[1], { bookmarked: false, deleted: true })]);
  const refreshed = await lists(f, { action: 'refresh', id: filled.body.list.id });
  check(refreshed.body.list.item_count === 1, 'unbookmarking one word → item_count 1');

  const manual = await lists(f, { action: 'create', title: 'manuală' });
  const badRefresh = await lists(f, { action: 'refresh', id: manual.body.list.id });
  check(badRefresh.status === 400, 'a hand-built list cannot be refreshed');

  console.log('\n5. tag buckets');
  await annotate(f, [mark(words[2], { tags: ['lol'] })]);
  const lol = await lists(f, { action: 'publish_bucket', bucket: 'lol' });
  check(lol.body.list.item_count === 1, 'lol bucket publishes its one word');
  check(lol.body.list.id !== filled.body.list.id, 'each bucket gets its own list');

  console.log('\n6. visibility');
  const slug = filled.body.list.slug;
  const stranger = makeJar();

  const publicRead = await get(stranger, `/api/lists.php?slug=${encodeURIComponent(slug)}`);
  check(publicRead.status === 200, "a stranger can read someone else's public list");

  await lists(f, { action: 'update', id: filled.body.list.id, is_public: false });
  const privateRead = await get(stranger, `/api/lists.php?slug=${encodeURIComponent(slug)}`);
  check(privateRead.status === 404, 'made private, the same slug 404s for the stranger');

  const dir = await get(stranger, '/api/lists.php?public=1');
  check(Array.isArray(dir.body.lists), 'the public directory returns a list');
  check(!dir.body.lists.some((l) => l.slug === slug), 'the private list is not in the directory');
  check(dir.body.lists.every((l) => l.item_count > 0), 'empty lists are kept out of the directory');
  check(dir.body.lists.every((l) => typeof l.owner_name === 'string'), 'directory rows carry an owner name');

  console.log(`\n${failures ? `${failures} failure(s)` : 'All checks passed'}\n`);
  process.exit(failures ? 1 : 0);
})();
