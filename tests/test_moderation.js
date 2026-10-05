// End-to-end test of the list moderation path (api/lists.php {action:'report'} +
// admin.php).
//
//   php -S localhost:8777 -t public/ &
//   OTIOS_ADMIN_TOKEN=<the token in api/config.local.php> node tests/test_moderation.js
//
// Override the target with OTIOS_TEST_URL. Writes to the real app.db, so point it at
// a dev instance, not production. Creates two fresh anonymous users (owner, reporter).
//
// The admin-page checks are skipped unless OTIOS_ADMIN_TOKEN is set, so the suite
// still runs on an install that has not configured moderation.
const BASE = process.env.OTIOS_TEST_URL || 'http://localhost:8777';
const ADMIN_TOKEN = process.env.OTIOS_ADMIN_TOKEN || '';

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

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

const post = (f, path, body) => f(`${BASE}${path}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}).then(async (r) => ({ status: r.status, body: await r.json() }));

const lists = (f, body) => post(f, '/api/lists.php', body);
const annotate = (f, changes) => post(f, '/api/sync.php', { since: 0, changes });
const mark = (word, patch) => Object.assign(
  { word, bookmarked: false, note: '', tags: [], updated_at: new Date().toISOString(), deleted: false },
  patch
);

(async () => {
  const owner = makeJar();
  const reporter = makeJar();

  // Real words, taken from whatever this ui.db holds — the API filters against it.
  const search = await owner(`${BASE}/api/search.php?page=1`).then((r) => r.text());
  const words = [...search.matchAll(/data-word="([^"]+)"/g)].map((m) => m[1]).slice(0, 2);

  console.log('\n0. Fixture: a published public list');
  check(words.length === 2, `two words pulled from ui.db (${words.join(', ')})`);
  if (words.length < 2) { console.log('\nCannot continue without words.'); process.exit(1); }

  await post(owner, '/api/profile.php', { nickname: 'owner-mod-test' });
  await annotate(owner, words.map((w) => mark(w, { bookmarked: true })));
  const published = await lists(owner, { action: 'publish_bucket', bucket: 'fav' });
  const slug = published.body.list.slug;
  check(published.status === 200 && published.body.items === 2, `published a 2-word list (${slug})`);

  console.log('\n1. Reporting');
  const own = await lists(owner, { action: 'report', slug });
  check(own.status === 400 && own.body.error === 'own_list', 'the owner cannot report their own list');

  const ghost = await lists(reporter, { action: 'report', slug: 'nu-exista-xyz' });
  check(ghost.status === 404, 'reporting a nonexistent list is a 404');

  const ok = await lists(reporter, { action: 'report', slug, reason: 'spam de test' });
  check(ok.status === 200 && ok.body.reported === true, 'a stranger can report a public list');

  const again = await lists(reporter, { action: 'report', slug, reason: 'iar' });
  check(again.status === 200 && again.body.reported === true,
        're-reporting returns the same success (and is a no-op, not an error)');

  console.log('\n2. A private list is not reportable, and does not leak');
  const priv = await lists(owner, { action: 'create', title: 'privata-mod-test' });
  const privSlug = priv.body.list.slug;
  const privReport = await lists(reporter, { action: 'report', slug: privSlug });
  check(privReport.status === 404,
        'a private list reports 404 — same as a missing one, so the endpoint is no slug oracle');

  if (!ADMIN_TOKEN) {
    console.log('\n3. admin.php — SKIPPED (set OTIOS_ADMIN_TOKEN to run)');
    if (process.env.OTIOS_STRICT === '1') {
      console.log('  FAIL  OTIOS_ADMIN_TOKEN is required in strict mode');
      failures++;
    }
  } else {
    console.log('\n3. admin.php');
    const admin = makeJar();

    const noAuth = await admin(`${BASE}/admin.php`);
    check(noAuth.status === 404, 'no token → 404 (not 403: the page does not admit to existing)');

    const badAuth = await admin(`${BASE}/admin.php?token=wrong-token-entirely`);
    check(badAuth.status === 404, 'wrong token → 404');

    const login = await admin(`${BASE}/admin.php?token=${encodeURIComponent(ADMIN_TOKEN)}`);
    check(login.status === 302, 'right token → redirect, so it leaves the address bar');

    const queue = await admin(`${BASE}/admin.php`).then((r) => r.text());
    check(queue.includes(slug), 'the reported list appears in the queue');
    check(queue.includes('spam de test'), 'the reporter’s reason is shown');

    // The list is public right up until it is acted on.
    const before = await fetch(`${BASE}/api/lists.php?public=1`).then((r) => r.json());
    check(before.lists.some((l) => l.slug === slug), 'still in the public directory before review');

    const listId = published.body.list.id;
    const act = await admin(`${BASE}/admin.php`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: BASE },
      body: `do=unpublish&list_id=${listId}`,
    });
    check(act.status === 302, 'unpublish redirects (POST/redirect/GET)');

    const after = await fetch(`${BASE}/api/lists.php?public=1`).then((r) => r.json());
    check(!after.lists.some((l) => l.slug === slug), 'gone from the public directory after unpublish');

    const page = await fetch(`${BASE}/lista.php?l=${encodeURIComponent(slug)}`).then((r) => r.text());
    check(page.includes('Listă negăsită'), 'the shared link now 404s for strangers');

    const cleared = await admin(`${BASE}/admin.php`).then((r) => r.text());
    check(!cleared.includes(slug), 'the report left the open queue once resolved');

    // The owner keeps their data — unpublish hides, it does not destroy.
    const stillMine = await lists(owner, { action: 'refresh', id: listId });
    check(stillMine.status === 200 && stillMine.body.items === 2,
          'the owner still has the list and its words');
  }

  console.log(`\n${failures ? `${failures} failure(s)` : 'All checks passed'}\n`);
  process.exit(failures ? 1 : 0);
})();
