// Head metadata for a `?word=` link — the half of a share that a crawler or a chat
// preview actually reads.
//
//   php -S 127.0.0.1:8011 -t public tools/dev-router.php &
//   OTIOS_TEST_URL=http://127.0.0.1:8011 node tests/test_share_meta.js
//
// Before 2026-08-12 `?word=` was read only by app.js, after load, so every word link
// ever posted previewed as the generic site card. The thing to keep pinned is that a
// real word fills the head, and that anything else falls back rather than reflecting
// the URL — the params here are attacker-supplied and land in <title>, og:url and
// rel=canonical.
const BASE = require('./lib/target').testBase('tests/test_share_meta.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };

const head = async (qs) => {
  const html = await fetch(`${BASE}/${qs}`).then((r) => r.text());
  const grab = (re) => { const m = html.match(re); return m ? m[1] : null; };
  return {
    title:  grab(/<title>([^<]*)<\/title>/),
    desc:   grab(/<meta name="description" content="([^"]*)"/),
    canon:  grab(/<link rel="canonical" href="([^"]*)"/),
    ogType: grab(/<meta property="og:type" content="([^"]*)"/),
    ogUrl:  grab(/<meta property="og:url" content="([^"]*)"/),
    raw:    html.slice(0, html.indexOf('</head>')),
  };
};

const DEFAULT_TITLE = 'Voroave neglijate';

(async () => {
  console.log('\n1. A real word fills the head');
  const w = await head('?word=sofragerie');
  check(w.title.startsWith('sofragerie'), `title names the word: „${w.title}"`);
  check(w.title !== DEFAULT_TITLE, 'title is not the site default');
  check(w.desc && w.desc.length > 20 && w.desc.length <= 160,
    `description is ${w.desc.length} chars (<= 160)`);
  check(w.ogType === 'article', 'og:type is article for a single word');
  check(/^https?:\/\/[^/]+\/\?word=/.test(w.canon), `canonical is absolute: ${w.canon}`);
  check(w.ogUrl === w.canon, 'og:url matches canonical');

  console.log('\n2. The description is a definition, not a citation dump');
  const t = await head('?word=tibi%C8%99ir');
  check(!/\p{Lu}{3,}/u.test(t.desc), `no author marker in „${t.desc}"`);
  check(!t.desc.includes('|'), 'no raw pipe separators');

  console.log('\n3. Diacritics survive a round trip');
  const p = await head('?word=potc%C4%83');
  check(p.title.startsWith('potcă'), `„${p.title}"`);
  check(p.canon.includes('potc%C4%83'), `canonical percent-encodes: ${p.canon}`);

  console.log('\n4. Anything that is not a word falls back — it never echoes the URL');
  for (const [qs, label] of [
    ['?word=nonexistentword', 'unknown word'],
    ['?word=', 'empty word'],
    ['?word=%3Cscript%3Ealert(1)%3C%2Fscript%3E', 'script tag'],
    ['?word=%22%3E%3Cimg%20src%3Dx%20onerror%3D1%3E', 'attribute break-out'],
    [`?word=${'a'.repeat(200)}`, 'over-long word'],
    ['?w=1.1f2', 'a playlist, not a word'],
    ['', 'the bare explorer'],
  ]) {
    const h = await head(qs);
    const clean = h.title === DEFAULT_TITLE && h.ogType === 'website';
    check(clean, `${label.padEnd(22)} → site default`);
  }

  console.log('\n5. The share tags carry no raw markup');
  // §4 covers the injection path — those inputs are not words, so nothing is echoed at
  // all. This checks the values that *are* echoed: everything in the share tags comes
  // from ui.db through e(), and a definition containing < or > (or a future change that
  // forgets the escape) would show up here rather than in a reader's timeline.
  for (const qs of ['?word=sofragerie', '?word=potc%C4%83',
                    '?word=%3Cscript%3E', '']) {
    const h = await head(qs);
    const vals = [h.title, h.desc, h.canon, h.ogUrl].filter(Boolean);
    const dirty = vals.filter((v) => /[<>]/.test(v));
    check(dirty.length === 0,
      `${(qs || '(bare)').padEnd(24)} → ${vals.length} share values, none with < or >`);
  }

  console.log(failures ? `\n${failures} FAILED\n` : '\nAll checks passed\n');
  process.exit(failures ? 1 : 0);
})();
