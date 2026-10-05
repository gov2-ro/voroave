// End-to-end test of the offline-first annotation sync.
//
// Runs the real public/assets/store.js inside a stubbed browser (localStorage,
// document events, cookie jar) against a live PHP server, so the client queue, the
// last-write-wins merge and the API all get exercised together.
//
//   php -S localhost:8777 -t public/ &
//   node tests/test_store_sync.js
//
// Override the target with OTIOS_TEST_URL. Writes to the real app.db, so point it at
// a dev instance, not production.
const vm   = require('vm');
const fs   = require('fs');
const path = require('path');

const BASE = require('./lib/target').testBase('tests/test_store_sync.js');
const SRC  = fs.readFileSync(path.join(__dirname, '..', 'public', 'assets', 'store.js'), 'utf8');

// Minimal cookie jar so a "device" keeps its identity across requests.
function makeJar() {
  const jar = {};
  return {
    jar,
    fetch: async (url, opts = {}) => {
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
    },
  };
}

// A "browser": its own localStorage, sharing a cookie jar (= same device/user).
function boot(initialStorage, jar) {
  const ls = Object.assign({}, initialStorage);
  const listeners = {};
  const ctx = {
    localStorage: {
      getItem: (k) => (k in ls ? ls[k] : null),
      setItem: (k, v) => { ls[k] = String(v); },
      removeItem: (k) => { delete ls[k]; },
    },
    document: {
      visibilityState: 'visible',
      addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
      dispatchEvent: (e) => { (listeners[e.type] || []).forEach((f) => f(e)); return true; },
    },
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
    fetch: jar.fetch,
    setTimeout, clearTimeout, console,
    OTIOS_BASE: BASE,
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  return { ctx, ls };
}

const say = (ok, msg) => console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`);
let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; say(ok, msg); };

(async () => {
  // The sync API only accepts words that exist in ui.db, and a rebuild can drop any
  // hardcoded word (`abecedar` and `zăbavă` both went that way). Two sources, both durable:
  //   - OTIOS_SYNC_WORDS="a,b": the runner's synthetic ui.db fixture holds exactly these.
  //   - otherwise: two words discovered from the server's own ui.db, one with diacritics
  //     when possible, so the UTF-8 path is still exercised (as in test_lists_api.js).
  let picked = (process.env.OTIOS_SYNC_WORDS || '').split(',').map((w) => w.trim()).filter(Boolean);
  if (picked.length < 2) {
    const search = await fetch(`${BASE}/api/search.php?page=1`).then((r) => r.text());
    const found = [...new Set([...search.matchAll(/data-word="([^"]+)"/g)].map((m) => m[1]))];
    const accented = found.filter((w) => /[^\x00-\x7f]/.test(w));
    const plain = found.filter((w) => !/[^\x00-\x7f]/.test(w));
    picked = [accented[0], plain[0] || accented[1]].filter(Boolean);
  }
  if (picked.length < 2) {
    console.log(`  FAIL  need 2 fixture words (set OTIOS_SYNC_WORDS or serve a built ui.db)`);
    process.exit(1);
  }
  const [W1, W2] = picked;
  console.log(`  fixture words: ${W1}, ${W2}`);

  console.log('\n1. Returning beta user: existing localStorage, never synced before');
  const jar = makeJar();
  const legacy = {
    'otios.research': JSON.stringify({
      version: 1,
      words: {
        [W1]: { bookmarked: true, note: 'nota mea', tags: ['funny'], updated_at: '2026-07-01T00:00:00.000Z' },
        [W2]: { bookmarked: true, note: '', tags: [], updated_at: '2026-07-01T00:00:01.000Z' },
      },
    }),
  };
  const a = boot(legacy, jar);
  check(JSON.parse(a.ls['otios.sync']).migrated === true, 'migration flag set on load');
  check(Object.keys(JSON.parse(a.ls['otios.pending'])).length === 2, 'both existing words queued for push');

  await a.ctx.syncNow();
  check(Object.keys(JSON.parse(a.ls['otios.pending'])).length === 0, 'queue drained after successful push');
  check(!!JSON.parse(a.ls['otios.sync']).since, 'sync watermark stored');

  console.log('\n2. Same device, wiped localStorage (the "cleared my browser" case)');
  const b = boot({}, jar);
  await b.ctx.syncNow();
  const restored = JSON.parse(b.ls['otios.research']).words;
  check(!!restored[W1] && restored[W1].bookmarked, `${W1} restored from server`);
  check(restored[W1].note === 'nota mea', 'note restored');
  check(JSON.stringify(restored[W1].tags) === '["funny"]', 'tags restored');
  check(!!restored[W2], `${W2} restored from server`);

  console.log('\n3. Edit on device B propagates to device A');
  b.ctx.updateWord(W1, { note: 'editat pe B' });
  await b.ctx.syncNow();
  await a.ctx.syncNow();
  check(JSON.parse(a.ls['otios.research']).words[W1].note === 'editat pe B', 'device A picked up the edit');

  console.log('\n4. Local edit is not clobbered by a stale server copy');
  a.ctx.updateWord(W1, { note: 'cea mai nouă' });
  await a.ctx.syncNow();
  check(JSON.parse(a.ls['otios.research']).words[W1].note === 'cea mai nouă', 'newer local edit survives the pull');
  // Assert the SERVER took it too: asserting only local state hides a rejected push.
  const fresh = boot({}, jar);
  await fresh.ctx.syncNow();
  check(JSON.parse(fresh.ls['otios.research']).words[W1].note === 'cea mai nouă',
        'server accepted the edit (verified via a third clean device)');

  console.log('\n4b. Two edits inside the same second both stick');
  b.ctx.updateWord(W1, { note: 'rapid unu' });
  await b.ctx.syncNow();
  b.ctx.updateWord(W1, { note: 'rapid doi' });   // milliseconds later
  await b.ctx.syncNow();
  const fresh2 = boot({}, jar);
  await fresh2.ctx.syncNow();
  check(JSON.parse(fresh2.ls['otios.research']).words[W1].note === 'rapid doi',
        'sub-second consecutive edits are not dropped');

  console.log('\n5. Delete propagates as a tombstone');
  b.ctx.updateWord(W2, { bookmarked: false });   // prunes locally -> tombstone
  await b.ctx.syncNow();
  await a.ctx.syncNow();
  check(!JSON.parse(a.ls['otios.research']).words[W2], `${W2} removed on device A too`);

  console.log('\n6. Server down: writes still work and stay queued');
  const offline = boot({}, { fetch: async () => { throw new Error('network down'); } });
  offline.ctx.updateWord(W1, { bookmarked: true });
  const res = await offline.ctx.syncNow();
  check(res === false, 'sync reports failure rather than throwing');
  check(!!JSON.parse(offline.ls['otios.research']).words[W1], 'local write landed despite outage');
  check(Object.keys(JSON.parse(offline.ls['otios.pending'])).length === 1, 'change stayed queued for retry');

  console.log('\n7. Per-change outcomes from the real server (docs/sync-protocol.md)');
  const post = async (changes, since = 0) => {
    const r = await jar.fetch(`${BASE}/api/sync.php`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ since, changes }),
    });
    return r.json();
  };
  const T0 = Date.now() + 1000;                       // later than anything above, within the 60 s clamp
  const iso = (n) => new Date(T0 + n).toISOString();
  const mk = (word, rev, ts, extra = {}) =>
    Object.assign({ word, rev, bookmarked: true, note: 'o', tags: [], updated_at: iso(ts), deleted: false }, extra);
  let out = await post([mk(W1, 11, 10), mk('cuvant-inexistent-xyz', 12, 10)]);
  const byRev = (o, rev) => (o.outcomes || []).find((x) => x.rev === rev);
  check(byRev(out, 11) && byRev(out, 11).status === 'stored' && byRev(out, 11).word === W1, 'new revision is "stored"');
  check(byRev(out, 12) && byRev(out, 12).status === 'invalid', 'unknown word is "invalid"');
  check(out.applied === 1 && out.rejected === 1, 'applied / rejected counters match the outcomes');
  out = await post([mk(W1, 13, 10)]);                  // same updated_at: the server already has it
  check(byRev(out, 13).status === 'current' && out.applied === 0 && out.unchanged === 1,
        'a database no-op is "current", not applied');
  out = await post([mk(W1, 14, 5)]);                   // older
  check(byRev(out, 14).status === 'current', 'an older change is "current"');
  out = await post([mk(W1, 15, 20, { note: 'unu' }), mk(W1, 16, 21, { note: 'doi' })]);
  check(byRev(out, 15).status === 'stored' && byRev(out, 16).status === 'stored', 'two changes to one word in one request both report');

  console.log('\n8. A request over the 5,000 slice reports the overflow as deferred');
  const many = [];
  for (let i = 0; i < 5001; i++) many.push(mk(W2, 100 + i, 30 + i));
  out = await post(many);
  check(out.outcomes.length === 5001, 'one outcome per submitted change');
  check(out.outcomes[5000].status === 'deferred' && out.outcomes[4999].status === 'stored',
        'the 5,001st change is "deferred", the 5,000th is processed');

  console.log('\n9. Client keeps a rejected word and stops retrying it');
  const rj = boot({}, jar);
  rj.ctx.updateWord('cuvant-inexistent-xyz', { note: 'nu exista' });
  await rj.ctx.syncNow();
  const rq = JSON.parse(rj.ls['otios.pending']);
  check(rq['cuvant-inexistent-xyz'] && rq['cuvant-inexistent-xyz'].rejected === 'invalid',
        'the entry is marked rejected, not cleared');
  check(!!JSON.parse(rj.ls['otios.research']).words['cuvant-inexistent-xyz'], 'its local data is kept');

  console.log(failures ? `\n${failures} FAILED\n` : '\nAll checks passed\n');
  process.exit(failures ? 1 : 0);
})();
