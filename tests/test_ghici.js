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

// F03: the pane's answer body (`.fp-body`) is withheld as ONE unit — `hidden` + `inert`
// + `aria-hidden` — and revealed in full after grading, right or wrong. Late and stale
// detail responses are controlled with `window.__detailHook` (see beforeParse below).
const BASE = require('./lib/target').testBase('tests/test_ghici.js');

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
    // Test hook: decide which word a detail request gets, and hold its response back.
    // The server still renders the real fragment (real detail.php markup) for it.
    if (window.__detailHook && String(url).includes('/api/word.php?word=')) {
      const u = new URL(url, BASE);
      const r = await window.__detailHook(u.searchParams.get('word'));
      if (r && r.word) { u.searchParams.set('word', r.word); url = u.pathname + u.search; }
      if (r && r.wait) await r.wait;
    }
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

// Text a reader can see: skips subtrees that are hidden, inert or aria-hidden.
function visibleText(node) {
  if (node.nodeType === 3) return node.textContent;
  if (node.nodeType !== 1) return '';
  if (node.hidden || node.hasAttribute('inert') || node.getAttribute('aria-hidden') === 'true'
      || node.classList.contains('joc-spoiler')) return '';
  return [...node.childNodes].map(visibleText).join(' ');
}
// Focusable elements that a keyboard user can actually reach (no hidden/inert ancestor).
function reachable(pane) {
  return [...pane.querySelectorAll('a[href], button, summary, input, select, textarea, [tabindex]')]
    .filter(el => !el.closest('[hidden], [inert], .joc-spoiler'));
}
function gate() {
  let release; const wait = new Promise(r => { release = r; });
  return { wait, release };
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
  const paneBody = $('#panel-pane .fp-body');
  check(!!paneBody && paneBody.hidden && paneBody.hasAttribute('inert')
        && paneBody.getAttribute('aria-hidden') === 'true',
    'the pane answer body is withheld (hidden + inert + aria-hidden)');
  const panePos = $('#panel-pane .fp-pos-line');
  check(!panePos || panePos.hidden, 'the pane POS line is withheld');
  check(reachable($('#panel-pane')).every(el => !el.closest('.fp-body')),
    'nothing inside the answer body is keyboard reachable');

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
  check(!$('#panel-pane .fp-body').hidden && !$('#panel-pane .fp-body').hasAttribute('inert')
        && !$('#panel-pane .fp-body').hasAttribute('aria-hidden'),
    'the full answer body is visible after the verdict');
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
  // Play on until a wrong round turns up (each pick is wrong with p≈3/4), so this
  // assertion does not depend on luck. A wrong round must reveal the full body too.
  for (let round = 0; round < 20 && !sawWrong; round++) {
    if ($('#quiz-next')) $('#quiz-next').click();
    if (!await waitFor(() => $$('.joc-choice').length === 4 && !$('#quiz-next'))) break;
    $$('.joc-choice')[round % 4].click();
    if (!await waitFor(() => $('#quiz-next'))) break;
    if ($('#quiz-feedback').className.includes('no')) {
      sawWrong = true;
      await waitFor(() => $('#panel-pane .fp-body'));
      check(!$('#panel-pane .fp-body').hidden && !$('#panel-pane .fp-body').hasAttribute('inert'),
        'a wrong answer reveals the full body too');
    }
  }
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

  console.log('\n7b. F03 — the answer body is withheld as one unit, per content shape');
  // Real detail.php markup for words with each shape; only the word choice is forced.
  // Preconditions are asserted too, so a rebuilt ui.db that loses a shape fails loudly.
  const SHAPES = [
    ['abraș',  'structured senses + expressions + citations + synonyms',
      ['.fp-senses', '.fp-extras', '.sense-cite, .sense-cites', '.syn-chip']],
    ['însul',  'flat definition fallback', ['.definition-text']],
    ['zăticni', 'synonym-only sense', ['.fp-senses', '.sense-syn']],
  ];
  async function playOne(word) {
    const d = await open('/ghici?game=sensuri');
    const w = d.window, q = s => w.document.querySelector(s), qa = s => [...w.document.querySelectorAll(s)];
    w.__detailHook = async () => ({ word });
    await waitFor(() => qa('.joc-choice').length === 4);
    await waitFor(() => q('#panel-pane .fp-title'));
    return { d, w, q, qa };
  }
  for (const [word, label, sels] of SHAPES) {
    const { d, w, q, qa } = await playOne(word);
    const pane = q('#panel-pane');
    check(q('#panel-pane .fp-title') && q('#panel-pane .fp-title').textContent.trim() === word,
      `${label}: pane shows „${word}"`);
    sels.forEach(sel => check(!!pane.querySelector(sel), `${label}: fixture has ${sel}`));
    // Everything answer-bearing sits inside the one wrapper, and the wrapper is out.
    const bearing = ['.fp-senses', '.fp-extras', '.sense-cite', '.sense-cites', '.syn-chip',
                     '.definition-text', '.fp-chips', '.fp-spelling', '.fp-dicts', '.fp-nodef']
      .flatMap(sel => [...pane.querySelectorAll(sel)]);
    check(bearing.length > 0 && bearing.every(el => el.closest('.fp-body[hidden][inert]')),
      `${label}: every answer element is inside the withheld wrapper`);
    const firstText = (pane.querySelector('.sense-text, .definition-text') || {}).textContent || '';
    check(firstText.length > 5 && !visibleText(pane).includes(firstText.trim().slice(0, 25)),
      `${label}: the definition text is not visible before answering`);
    check(reachable(pane).every(el => !el.closest('.fp-body')),
      `${label}: no answer-body control is keyboard reachable`);
    const posLine = pane.querySelector('.fp-pos-line');
    check(!posLine || posLine.hidden, `${label}: the POS line is withheld`);
    check(!!pane.querySelector('.fp-title') && !pane.querySelector('.fp-title').closest('[hidden]'),
      `${label}: the headword stays visible`);
    const marks = pane.querySelector('.fp-btns');
    check(!!marks && !marks.closest('[hidden], [inert]') && reachable(pane).some(el => el.closest('.fp-btns')),
      `${label}: the marks stay usable`);
    // Marking does not answer.
    pane.querySelector('#bookmark-btn').click();
    await sleep(120);
    check(q('#quiz-next') === null && q('#quiz-feedback').textContent.trim() === '',
      `${label}: pressing a mark is not an answer`);
    pane.querySelector('#bookmark-btn').click();
    // Answer; reveal in full.
    qa('.joc-choice')[0].click();
    check(await waitFor(() => q('#quiz-next')), `${label}: verdict arrives`);
    const body = q('#panel-pane .fp-body');
    check(!body.hidden && !body.hasAttribute('inert') && !body.hasAttribute('aria-hidden')
          && visibleText(q('#panel-pane')).includes(firstText.trim().slice(0, 25)),
      `${label}: the full body is visible after grading (${q('#quiz-feedback').className.includes('ok') ? 'right' : 'wrong'} answer)`);
    check(!pane.querySelector('.fp-pos-line') || !pane.querySelector('.fp-pos-line').hidden,
      `${label}: the POS line is back after grading`);
    d.window.close();
  }

  console.log('\n7c. F03 — grade before the detail response arrives');
  {
    const g = gate();
    const d = await open('/ghici?game=sensuri');
    const w = d.window, q = s => w.document.querySelector(s), qa = s => [...w.document.querySelectorAll(s)];
    w.__detailHook = async () => ({ word: 'abraș', wait: g.wait });
    // The hook is installed after the first request may already have started, so use a
    // fresh question: the next load() goes through the gated hook.
    await waitFor(() => qa('.joc-choice').length === 4);
    await waitFor(() => q('#panel-pane .fp-title'));
    qa('.joc-choice')[0].click();
    await waitFor(() => q('#quiz-next'));
    q('#quiz-next').click();
    await waitFor(() => qa('.joc-choice').length === 4 && !q('#quiz-next'));
    check(!!q('#panel-pane .panel-placeholder'), 'the pane is still loading');
    qa('.joc-choice')[1].click();
    check(await waitFor(() => q('#quiz-next')), 'the verdict arrives while the detail is still pending');
    g.release();
    check(await waitFor(() => q('#panel-pane .fp-body')), 'the late detail then lands');
    const body = q('#panel-pane .fp-body');
    check(!body.hidden && !body.hasAttribute('inert') && !body.hasAttribute('aria-hidden')
          && !q('#panel-pane .fp-pos-line, #panel-pane .fp-body').classList.contains('joc-spoiler'),
      'the late detail is shown in full, not re-hidden');
    d.window.close();
  }

  console.log('\n7d. F03 — a stale response never replaces the current question');
  {
    const slow = gate();
    const d = await open('/ghici?game=sensuri');
    const w = d.window, q = s => w.document.querySelector(s), qa = s => [...w.document.querySelectorAll(s)];
    await waitFor(() => qa('.joc-choice').length === 4);
    await waitFor(() => q('#panel-pane .fp-title'));
    let n = 0;
    // Question 2's detail is held back; question 3's answers at once.
    w.__detailHook = async () => { n++; return n === 1 ? { word: 'abraș', wait: slow.wait } : { word: 'însul' }; };
    qa('.joc-choice')[0].click();
    await waitFor(() => q('#quiz-next'));
    q('#quiz-next').click();                 // question 2: detail request 1, held
    await waitFor(() => qa('.joc-choice').length === 4 && !q('#quiz-next') && n === 1);
    qa('.joc-choice')[0].click();
    await waitFor(() => q('#quiz-next'));
    q('#quiz-next').click();                 // question 3: detail request 2, immediate
    check(await waitFor(() => n === 2 && q('#panel-pane .fp-title')
        && q('#panel-pane .fp-title').textContent.trim() === 'însul'), 'the current question\'s detail is shown');
    slow.release();
    await sleep(400);
    check(q('#panel-pane .fp-title').textContent.trim() === 'însul',
      'the stale response for the earlier question did not replace the pane');
    check(q('#panel-pane .fp-body') && q('#panel-pane .fp-body').hidden,
      'and the current question\'s body is still withheld');
    d.window.close();
  }

  console.log('\n7e. F03 — grilă: a wrong answer compares a structured entry readably');
  {
    const d = await open('/ghici?game=grila');
    const w = d.window, q = s => w.document.querySelector(s), qa = s => [...w.document.querySelectorAll(s)];
    w.__detailHook = async () => ({ word: 'abraș' });
    let wrong = false;
    for (let round = 0; round < 20 && !wrong; round++) {
      if (q('#quiz-next')) q('#quiz-next').click();
      if (!await waitFor(() => qa('.joc-choice').length === 4 && !q('#quiz-next'))) break;
      qa('.joc-choice')[round % 4].click();
      if (!await waitFor(() => q('#quiz-next'))) break;
      if (q('#quiz-feedback').className.includes('no')) {
        wrong = true;
        check(await waitFor(() => q('#panel-pane .panel-compare-def')), 'the comparison card appears');
        check(!/fără definiție locală/.test(q('#panel-pane .panel-compare-def').textContent),
          'the comparison card reads the senses of a structured entry');
        check(!q('#panel-pane .fp-body').hidden, 'grilă reveals the correct word\'s full body');
      }
    }
    check(wrong, 'a wrong grilă round was reached');
    d.window.close();
  }

  console.log('\n8. No script errors along the way');
  // Stylesheet fetches are jsdom's own limitation, not the page's.
  const real = errors.filter(e => !/Could not load|css|stylesheet/i.test(e));
  check(real.length === 0, real.length ? `errors: ${real.slice(0, 3).join(' | ')}` : 'clean console');

  window.close();
  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error('harness error:', e); process.exit(2); });
