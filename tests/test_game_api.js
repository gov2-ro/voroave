// End-to-end test of the graded quiz API (api/quiz.php + api/game.php).
//
//   php -S localhost:8777 -t public/ &
//   node tests/test_game_api.js
//
// Override the target with OTIOS_TEST_URL. Writes to the real app.db, so point it at
// a dev instance, not production.
const BASE = require('./lib/target').testBase('tests/test_game_api.js');

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

const ask = (f, mode) => f(`${BASE}/api/quiz.php?mode=${mode}`, { credentials: 'same-origin' }).then((r) => r.json());
const answer = (f, body) => f(`${BASE}/api/game.php`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}).then(async (r) => ({ status: r.status, body: await r.json() }));


(async () => {
  const f = makeJar();

  console.log('\n1. Question payloads never reveal the answer');
  const sense = await ask(f, 'sense');
  const quiz = await ask(f, 'quiz');
  check(sense.word && !sense.definition, 'sense mode shows the word, withholds the definition');
  check(quiz.definition && quiz.word === null, 'quiz mode shows the definition, withholds the word');
  check(quiz.options.length === 4 && quiz.options.every((o) => 'id' in o && 'text' in o),
        'options are opaque {id, text} pairs');
  check(!JSON.stringify(quiz.options).includes('"word"'), 'options never carry the word key');
  const raw = Buffer.from(quiz.qid.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
  let readable = false;
  try { JSON.parse(raw.subarray(28).toString('utf8')); readable = true; } catch (_) {}
  check(!readable, 'qid is encrypted, not merely signed');

  console.log('\n2. Grading is server-side and single-use');
  const q = await ask(f, 'quiz');
  const a1 = await answer(f, { qid: q.qid, choice_id: 0, ms: 1000 });
  check(typeof a1.body.correct === 'boolean' && typeof a1.body.correct_id === 'number',
        'server returns a verdict and the correct id');
  const a2 = await answer(f, { qid: q.qid, choice_id: a1.body.correct_id, ms: 1000 });
  check(a2.status === 409, 'replaying the same qid is rejected');

  console.log('\n3. A tampered qid is rejected');
  const q3 = await ask(f, 'quiz');
  const bad = await answer(f, { qid: q3.qid.slice(0, -3) + 'AAA', choice_id: 0, ms: 1000 });
  check(bad.status === 400, 'forged token refused');

  // The client cannot know the answer in advance — that is the security property
  // under test elsewhere — so instead of trying to force a winning run, play a fixed
  // sequence of guesses and assert the server's counters against locally tracked
  // expectations after every single answer. This pins down the increment/reset/best
  // logic deterministically, with no reliance on luck.
  console.log('\n4. Streak counters follow the rules on every answer');
  const f4 = makeJar();   // a fresh device, so the counters start from zero
  let expStreak = 0, expBest = 0, corrects = 0, sawIncrement = false, drift = null;
  for (let i = 0; i < 40; i++) {
    const qq = await ask(f4, 'quiz');
    const r = await answer(f4, { qid: qq.qid, choice_id: i % 4, ms: 700 });
    if (r.status !== 200) { drift = drift || `unexpected status ${r.status}`; break; }

    if (r.body.correct) { expStreak += 1; corrects++; if (expStreak > 1) sawIncrement = true; }
    else expStreak = 0;
    expBest = Math.max(expBest, expStreak);

    if (r.body.streak !== expStreak) { drift = `after answer ${i + 1}: streak ${r.body.streak}, expected ${expStreak}`; break; }
    if (r.body.best !== expBest) { drift = `after answer ${i + 1}: best ${r.body.best}, expected ${expBest}`; break; }
    if (r.body.total !== i + 1) { drift = `after answer ${i + 1}: total ${r.body.total}, expected ${i + 1}`; break; }
  }
  check(drift === null, drift || 'streak/best/total matched expectations on all 40 answers');
  check(corrects > 0, `at least one correct answer occurred (${corrects}/40)`);
  check(expBest > 0, `best_streak rose above zero (${expBest}) — it was pinned at 0 before the affinity fix`);
  if (!sawIncrement) console.log('  note: no consecutive correct guesses this run; increment beyond 1 not exercised');

  console.log('\n5. A question is never built out of a cross-reference');
  // „Diminutiv al lui sfânt" is not a definition, it is a pointer — and reveals_word()
  // does not catch it: it needs a 4-character shared prefix and Romanian vowel
  // alternation breaks that at character 2 (`sfințișor` / `sfânt` share „sf"). Same
  // family as the „vezi X" segments pick_sense() already refused.
  const POINTER = /^\s*(?:vezi\s|diminutiv|augmentativ)/i;
  let pointers = 0;
  const targets = [];
  for (let i = 0; i < 40; i++) {
    const q = await ask(f, i % 2 ? 'quiz' : 'sense');
    for (const o of q.options) if (POINTER.test(o.text)) pointers++;
    if (q.word) targets.push(q.word);
  }
  check(pointers === 0, `no option over 40 questions is a bare cross-reference (${pointers})`);
  check(targets.length > 0, `sense mode produced ${targets.length} targets`);

  console.log('\n6. CSRF and method guards');
  const xo = await f(`${BASE}/api/game.php`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'https://evil.example' },
    body: JSON.stringify({ qid: 'x', choice_id: 0 }),
  });
  check(xo.status === 403, 'cross-origin POST refused');
  const wrongMethod = await f(`${BASE}/api/game.php`, { method: 'GET' });
  check(wrongMethod.status === 405, 'GET on game.php refused');

  console.log(failures ? `\n${failures} FAILED\n` : '\nAll checks passed\n');
  process.exit(failures ? 1 : 0);
})();
