// End-to-end test of /colectii — the site-wide aggregate of what everyone marked.
//
//   php -S localhost:8777 -t public/ &
//   node tests/test_colectii.js
//
// Override the target with OTIOS_TEST_URL. It creates two anonymous users and writes
// annotations to app.db, so point it at a dev instance.
//
// Three of the five properties here fail *invisibly* if broken — a word that should be
// on a tab and is not looks exactly like a word nobody marked:
//
//   1. The fav-beats-meh precedence is per *person*, not per word. One visitor's ★+⛔️ on
//      the same word is one positive vote and no negative one; two different visitors
//      disagreeing put the word on both tabs, with each tab's chip naming the opposing
//      count. Collapsing that to "a word belongs to one tab" hides real disagreement.
//   2. The ranking counts *people*, not marks. The annotations PK is (user_id, word), so
//      one person who both ★'d and 🤣'd a word must count once — while still showing up
//      in both breakdown chips.
//   3. Marks still never subtract. Appearing on the „respinse" tab must not remove a word
//      from the explorer, which is the invariant the whole community layer rests on.
const BASE = require('./lib/target').testBase('tests/test_colectii.js');

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

const mark = (word, patch) => Object.assign(
  { word, bookmarked: false, note: '', tags: [], updated_at: new Date().toISOString(), deleted: false },
  patch
);
const annotate = (f, changes) => f(`${BASE}/api/sync.php`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ since: 0, changes }),
}).then((r) => r.json());

// The page is server-rendered prose, so the assertions read the markup rather than JSON:
// one .lista-item per word, with the headword in the ?word= link.
const words = (html) => [...html.matchAll(/class="lista-word" href="[^"]*\?word=([^"]+)"/g)]
  .map((m) => decodeURIComponent(m[1]));
const page = (f, qs = '') => f(`${BASE}/colectii.php${qs}`).then(async (r) => ({
  status: r.status, html: await r.text(),
}));
// The chip that follows a headword: `★a · 🤣b · ⛔️c`, inline between the word and its
// POS/register tags. Taken from the *first* .agg-marks after the link — every row has
// at most one, and the next row's link is what bounds it.
//
// It sat *before* the headword as a block until the 2026-08-13 compaction, and reading
// it from the wrong side is silent rather than empty: `lastIndexOf` before the anchor
// happily returned the previous row's chip, so the numbers were real and belonged to
// another word.
const chip = (html, word) => {
  const at = html.indexOf(`?word=${encodeURIComponent(word)}"`);
  if (at < 0) return null;
  const from = html.indexOf('<span class="agg-marks"', at);
  if (from < 0) return null;
  const next = html.indexOf('class="lista-item"', at);
  if (next >= 0 && from > next) return null;    // this row has no chip; don't read the next one's
  const end = html.indexOf('</span>', from);
  return html.slice(from, end).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
};

// The chip as numbers: { lead, fav, lol }. The test asserts *deltas* on these rather than
// absolute values — every run mints fresh anonymous users and leaves its annotations in
// app.db, so the counts on a dev instance only ever grow.
const nums = (c) => {
  if (!c) return { lead: 0, fav: 0, lol: 0 };
  const head = c.split('·')[0];
  return {
    lead: parseInt((head.match(/(\d+)/) || [0, 0])[1], 10),
    fav: parseInt((c.match(/★(\d+)/) || [0, 0])[1], 10),
    lol: parseInt((c.match(/🤣(\d+)/) || [0, 0])[1], 10),
  };
};

// Three real shortlist words, picked from api/search.php so the test never depends on a
// hardcoded word surviving the next rebuild.
async function pickWords(f, n) {
  const html = await f(`${BASE}/api/search.php?word_tier=forgotten&sort=alpha`).then((r) => r.text());
  const all = [...html.matchAll(/data-word="([^"]+)"/g)].map((m) => m[1]);
  return all.slice(0, n);
}

(async () => {
  const a = makeJar();
  const b = makeJar();

  const [wFav, wMeh, wBoth] = await pickWords(a, 3);
  if (!wBoth) {
    console.log('FAIL  could not read three words out of api/search.php');
    process.exit(1);
  }
  console.log(`\nfixtures: fav=${wFav}  meh=${wMeh}  both=${wBoth}`);

  // Baseline, so section 4 can assert deltas on a db that already holds earlier runs.
  const before = await page(a).then((p) => ({
    fav: nums(chip(p.html, wFav)), both: nums(chip(p.html, wBoth)),
  }));

  // User A: one ★, one ⛔️, and one word carrying ★ + 🤣 + ⛔️ at once.
  await annotate(a, [
    mark(wFav, { bookmarked: true }),
    mark(wMeh, { tags: ['meh'] }),
    mark(wBoth, { bookmarked: true, tags: ['lol', 'meh'] }),
  ]);
  // User B ★s the same word, so the lead count is two people rather than one.
  await annotate(b, [mark(wFav, { bookmarked: true })]);

  console.log('\n1. Both tabs render');
  const up = await page(a);
  const down = await page(a, '?t=respinse');
  check(up.status === 200, 'GET /colectii → 200');
  check(down.status === 200, 'GET /colectii?t=respinse → 200');
  check(up.html.includes('seg-link is-on') && down.html.includes('seg-link is-on'),
    'each tab marks itself live (.seg-link.is-on)');
  check(/t=respinse/.test(up.html) && /href="[^"]*\/colectii"/.test(down.html),
    'each tab links to the other');

  console.log('\n2. A marked word reaches its tab');
  const upW = words(up.html);
  const downW = words(down.html);
  check(upW.includes(wFav), `★ „${wFav}" is on „îndrăgite"`);
  check(downW.includes(wMeh), `⛔️ „${wMeh}" is on „respinse"`);

  console.log('\n3. A positive mark beats meh on the same row — per person, not per word');
  check(upW.includes(wBoth), `„${wBoth}" (one person's ★+🤣+⛔️) is on „îndrăgite"`);
  check(!downW.includes(wBoth), `„${wBoth}" is NOT also on „respinse" — same person, one vote`);

  console.log('\n4. The ranking counts people, not marks');
  const dBoth = nums(chip(up.html, wBoth));
  const dFav = nums(chip(up.html, wFav));
  check(dBoth.lead - before.both.lead === 1,
    `one person's ★+🤣 moves the lead number by 1, not 2 (chip: "${chip(up.html, wBoth)}")`);
  check(dBoth.fav - before.both.fav === 1 && dBoth.lol - before.both.lol === 1,
    'and still shows in both breakdown chips — the breakdown may sum higher than the lead');
  check(dFav.lead - before.fav.lead === 2,
    `two people's ★ moves the lead number by 2 (chip: "${chip(up.html, wFav)}")`);

  console.log('\n5. Two people disagreeing is not collapsed — the word is on both tabs');
  // Different from §3: user B *replaces* their ★ on wFav with a ⛔️, so one person likes
  // it and another rejects it. That belongs on both lists, with both counts visible.
  await annotate(b, [mark(wFav, { tags: ['meh'] })]);
  const up2 = await page(a);
  const down2 = await page(a, '?t=respinse');
  check(words(up2.html).includes(wFav), `„${wFav}" is still on „îndrăgite"`);
  check(words(down2.html).includes(wFav), `„${wFav}" is now also on „respinse"`);
  check(/★/.test(chip(down2.html, wFav) || ''),
    `and „respinse" names the ★ count too (chip: "${chip(down2.html, wFav)}")`);

  console.log('\n6. Marks still never subtract, and the playlist link is real');
  const search = await a(`${BASE}/api/search.php?word_tier=forgotten&sort=alpha`).then((r) => r.text());
  check(search.includes(`data-word="${wMeh}"`),
    `„${wMeh}" is still in the explorer after being meh'd by everyone who marked it`);
  const packed = up.html.match(/\/\?w=([^"]+)"/);
  check(packed !== null && packed[1].length > 2, 'the „deschide toate" ?w= link is non-empty');

  console.log(`\n${failures ? failures + ' FAILED' : 'all passed'}`);
  process.exit(failures ? 1 : 0);
})();
