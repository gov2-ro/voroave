// End-to-end test of the quiz page (public/ghici.php), driven in a real DOM.
//
//   php -S 127.0.0.1:8011 -t public tools/dev-router.php &
//   node tests/test_ghici.js
//
// Override the target with OTIOS_TEST_URL. Read-only against ui.db; it creates one
// anonymous device and writes a couple of annotations, so point it at a dev instance.
//
// **This one needs jsdom** — the only test here that needs anything off-disk. The
// page's whole behaviour is DOM behaviour (spoilers hidden then revealed, marks moved
// out of the panel footer, a countdown that any interaction cancels), and none of it
// is reachable by asserting on HTML the way the API tests do. It skips rather than
// fails when jsdom is missing, so `node tests/*.js` still runs everywhere:
//
//   npm install jsdom     # anywhere; NODE_PATH is honoured too
//
// The four properties worth pinning, all of which fail *silently* — the page keeps
// working and just gives the game away, or quietly stops advancing:
//
//   1. In `sensuri` the definition AND the part of speech are withheld. The POS is the
//      one people forget: "s.f." under the headword eliminates every option phrased as
//      a verb, which on a four-option round is most of the work.
//   2. Everything withheld is revealed once the round is decided — including when the
//      detail pane's fetch lands *after* the answer, which is the race `roundDecided`
//      exists for.
//   3. A grilă option's marks are siblings of the option button, never children. A
//      <button> inside a <button> is invalid markup that parsers recover from by
//      dropping the inner one, so this fails as "the marks vanished", not as an error.
//   4. Auto-advance is correct-answers-only. On a wrong answer the two definitions
//      side by side are the entire value of the round.
const { JSDOM, VirtualConsole } = require('./lib/deps').loadJsdom('tests/test_ghici.js');

const BASE = process.env.OTIOS_TEST_URL || 'http://127.0.0.1:8011';

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function waitFor(fn, ms = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(50); }
  return false;
}

// jsdom ships no fetch, and every question goes through one — without this the page
// loads and simply never renders a card. Node's fetch plus a cookie jar, so the device
// identity survives across requests the way a browser's would (quiz.php calls
// current_user() to build the per-player pool).
const jar = {};
function beforeParse(window) {
  window.fetch = async (url, opts = {}) => {
    const abs = new URL(url, BASE).href;
    const cookie = Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; ');
    const res = await fetch(abs, {
      ...opts,
      redirect: 'follow',
      headers: { ...(opts.headers || {}), ...(cookie ? { cookie } : {}) },
    });
    (res.headers.getSetCookie ? res.headers.getSetCookie() : []).forEach(c => {
      const [kv] = c.split(';');
      const i = kv.indexOf('=');
      jar[kv.slice(0, i).trim()] = kv.slice(i + 1).trim();
    });
    return { ok: res.ok, status: res.status, text: () => res.text(), json: () => res.json() };
  };
}

const errors = [];
function newConsole() {
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push(e.message));
  vc.on('error', (...a) => errors.push(a.join(' ')));
  return vc;
}

function open(path) {
  return JSDOM.fromURL(BASE + path, {
    runScripts: 'dangerously',
    resources: 'usable',
    pretendToBeVisual: true,
    virtualConsole: newConsole(),
    beforeParse,
  });
}

(async () => {
  const dom = await open('/ghici?game=sensuri');
  const { window } = dom;
  const $ = s => window.document.querySelector(s);
  const $$ = s => [...window.document.querySelectorAll(s)];

  console.log('\n1. sensuri — the card loads and withholds every hint');
  check(await waitFor(() => $$('.joc-choice').length === 4), 'four choices rendered');
  check(!!$('.joc-word') && $('.joc-word').textContent.trim() !== '', 'the word is shown');
  const pos = $('.joc-pos');
  check(!pos || pos.classList.contains('joc-spoiler'), 'the card POS line is withheld');

  await waitFor(() => $('#panel-pane .fp-title'));
  check(!!$('#panel-pane .fp-title'), 'detail pane populated');
  const paneDef = $('#panel-pane .definition-text, #panel-pane .fp-nodef');
  check(!!paneDef && paneDef.classList.contains('joc-spoiler'), 'the pane definition is withheld');
  const panePos = $('#panel-pane .fp-pos-line');
  check(!panePos || panePos.classList.contains('joc-spoiler'), 'the pane POS line is withheld');

  console.log('\n2. The marks are lifted out of the panel footer');
  const btns = $('#panel-pane .fp-btns');
  check(!!btns && btns.classList.contains('fp-btns--lifted'), 'the marks row is the lifted one');
  const body = $('#panel-pane .fp-body');
  check(!!btns && !!body && (btns.compareDocumentPosition(body) & 4) !== 0,
    'the marks precede the body, i.e. they are above the definition');

  console.log('\n3. Answering reveals everything that was withheld');
  $$('.joc-choice')[0].click();
  check(await waitFor(() => $('#quiz-actions #quiz-next')), 'the next button appears');
  check($$('.joc-spoiler').length === 0, 'nothing is left withheld after the verdict');
  const fb = $('#quiz-feedback');
  check(/corect|greșit/.test(fb.textContent), 'a verdict is stated');

  console.log('\n4. Auto-advance is correct-answers-only');
  // Which choice is right is the server's secret (that is what the sealed `qid` is
  // for), so the correct branch cannot be reached on demand — play rounds until one
  // is won. Both branches get asserted as they come up; 20 rounds makes never seeing
  // a win about a 0.3% event, and it is reported rather than silently passed.
  let sawCorrect = false, sawWrong = fb.className.includes('no');
  if (fb.className.includes('ok')) {
    sawCorrect = true;
    check($('#quiz-next').classList.contains('joc-btn--counting'), 'the countdown runs on a correct answer');
  } else {
    check(!$('#quiz-next').classList.contains('joc-btn--counting'), 'no countdown on a wrong answer');
    await sleep(1400);
    check(!!$('#quiz-next'), 'a wrong answer is still waiting for you well past 1s');
  }

  for (let round = 0; round < 20 && !sawCorrect; round++) {
    $('#quiz-next').click();
    if (!await waitFor(() => $$('.joc-choice').length === 4 && !$('#quiz-next'))) break;
    $$('.joc-choice')[round % 4].click();
    if (!await waitFor(() => $('#quiz-next'))) break;
    const f = $('#quiz-feedback');
    if (!f.className.includes('ok')) { sawWrong = true; continue; }
    sawCorrect = true;

    check($('#quiz-next').classList.contains('joc-btn--counting'), 'the countdown runs on a correct answer');
    // It must actually fire: a countdown that only animates is decoration.
    check(await waitFor(() => !$('#quiz-next') || $('#quiz-feedback').textContent === '', 2500),
      'the next question loads on its own within ~1s');
  }
  check(sawCorrect, sawCorrect ? 'a correct round was reached and asserted'
                               : 'INCONCLUSIVE — 20 rounds without a correct answer (p≈0.3%)');

  console.log('\n4b. Any interaction cancels the countdown');
  // The cancel is what makes 1s safe rather than rushed — the pane stays readable the
  // moment you reach for it. Play until another correct round, then interrupt it.
  let cancelled = false;
  for (let round = 0; round < 20 && !cancelled; round++) {
    if ($('#quiz-next')) $('#quiz-next').click();
    if (!await waitFor(() => $$('.joc-choice').length === 4 && !$('#quiz-next'))) break;
    $$('.joc-choice')[round % 4].click();
    if (!await waitFor(() => $('#quiz-next'))) break;
    if (!$('#quiz-feedback').className.includes('ok')) { sawWrong = true; continue; }

    window.document.dispatchEvent(new window.Event('pointerdown', { bubbles: true }));
    check(!$('#quiz-next').classList.contains('joc-btn--counting'), 'the countdown stops on a pointer event');
    await sleep(1500);
    check(!!$('#quiz-next') && $('#quiz-feedback').textContent !== '',
      'the verdict is still on screen 1.5s later — it did not advance anyway');
    cancelled = true;
  }
  if (!cancelled) console.log('  ....  INCONCLUSIVE — no correct round to interrupt');
  // Asserted here rather than after §4: that loop stops at the first win, so a run
  // whose very first answer was correct would never have seen a wrong one. Across
  // both loops it always does.
  check(sawWrong, 'a wrong round was reached and asserted too');

  console.log('\n5. grilă — a mark group beside every option, and the URL follows');
  window.setMode('quiz');
  check(window.location.search.includes('game=grila'),
    `the URL says game=grila (${window.location.search})`);
  check(await waitFor(() => $$('.joc-choice-row').length === 4), 'four option rows');
  check($$('.joc-choice-row .joc-marks').length === 4, 'every option carries a mark group');
  check($$('.joc-choice-row .joc-mark').length === 12, 'three marks each');
  check($$('.joc-choice .joc-mark').length === 0,
    'the marks are siblings of the option button, never children of it');

  console.log('\n6. Marking an option does not answer the question');
  const mark = $('.joc-choice-row .joc-mark[data-joc-tag="fav"]');
  const word = mark.dataset.jocWord;
  mark.click();
  await sleep(150);
  check(mark.classList.contains('active'), 'the mark shows as applied');
  check(mark.getAttribute('aria-pressed') === 'true', 'aria-pressed follows the class');
  check($('#quiz-feedback').textContent.trim() === '', 'no verdict was triggered');
  const stored = JSON.parse(window.localStorage.getItem('otios.research') || '{}');
  check(!!(stored.words && stored.words[word] && stored.words[word].bookmarked),
    `the mark reached the shared store for „${word}"`);
  mark.click();
  await sleep(150);
  check(!mark.classList.contains('active'), 'pressing it again removes it');

  console.log('\n7. The legacy ?mode= spelling still selects the game');
  const dom2 = await open('/ghici?mode=quiz');
  await waitFor(() => dom2.window.document.querySelector('.joc-choice-row'));
  check(!!dom2.window.document.querySelector('.joc-choice-row'), '?mode=quiz still lands in grilă');
  dom2.window.close();

  console.log('\n8. No script errors along the way');
  // Stylesheet fetches are jsdom's own limitation, not the page's.
  const real = errors.filter(e => !/Could not load|css|stylesheet/i.test(e));
  check(real.length === 0, real.length ? `errors: ${real.slice(0, 3).join(' | ')}` : 'clean console');

  window.close();
  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error('harness error:', e); process.exit(2); });
